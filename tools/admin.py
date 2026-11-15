#!/usr/bin/env python3
"""本地画廊管理台 —— 浏览器里点点就能加图 / 改标题 / 删图。

    python tools/admin.py                 # 起服务： http://127.0.0.1:8765
    python tools/admin.py --port 9000     # 换端口
    python tools/admin.py --open          # 起完自动打开浏览器

为什么要有它
------------

命令行 ``gallery.py add`` 一次只能加一张，还得自己起 ID、自己想标题。
二创素材往往是一整个文件夹、几十张图，逐条敲命令太慢。
管理台把「挑文件 → 填标题作者 → 压缩 → 入库 → 重建」串成一条流水线。

几条硬规矩
----------

* **入库即压缩**：所有新图先过 ``imageopt``（长边 2560 / WebP q82），
  再生成 480/960/1440/1920 四档展示图。页面永远只加载缩略图。
* **只听本机**：绑定 127.0.0.1，不对外网开放。
* **和命令行同源**：管理台调的是 ``gallery.add_item`` / ``gallery.remove_item``，
  和 ``python tools/gallery.py add`` 写出来的数据一模一样。
* **改完自动重建**：缩略图 → 社区卡片 → 静态分区 → srcset → 署名表 → 校验，
  日志实时显示在管理台右下角。
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import mimetypes
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
DOCS_DIR = REPO_ROOT / "docs"
UI_FILE = TOOLS_DIR / "admin_ui.html"

if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import gallery  # noqa: E402
from gallery import COMMUNITY, DOCS_DIR as GALLERY_DOCS  # noqa: E402

MAX_UPLOAD = 64 * 1024 * 1024  # 单次请求上限 64 MB
SECTION_LABELS = {
    "community": "社区二创",
    "sheets": "角色设定图",
    "moegirl": "萌娘百科收录图",
    "refs": "换装三视图",
    "wallpaper": "场景壁纸",
}
TYPE_LABELS = {
    "character": "角色立绘",
    "meme": "表情包",
    "sheet": "设定图",
    "scene": "场景壁纸",
}

# ---------------------------------------------------------------- 运行时状态

BUILD_LOCK = threading.Lock()
BUILD_STATE: dict = {"running": False, "ok": None, "started": None, "finished": None, "error": ""}
LOG: list[str] = []
LOG_LOCK = threading.Lock()


def log_line(text: str) -> None:
    with LOG_LOCK:
        LOG.append(text)
        if len(LOG) > 4000:
            del LOG[:1000]


def log_all(text: str) -> None:
    for line in text.splitlines():
        log_line(line.rstrip())


# ---------------------------------------------------------------- 工具

def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def human(size: float) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.0f} KB"
    return f"{int(size)} B"


def sanitize_id(text: str) -> str:
    """文件名 → 合法 ID（只留字母数字点横线下划线与中文）。"""
    text = (text or "").strip()
    text = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", text)  # 去扩展名
    text = re.sub(r"[^\w\-一-鿿]+", "-", text, flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("-_")
    return text[:60] or "image"


def unique_id(base: str, taken: set[str]) -> str:
    if base not in taken:
        return base
    for i in range(2, 500):
        candidate = f"{base}-{i}"
        if candidate not in taken:
            return candidate
    return f"{base}-{int(time.time())}"


def apply_template(template: str, *, name: str, index: int, ext: str) -> str:
    if not template:
        return name
    return (
        template.replace("{name}", name)
        .replace("{n}", str(index))
        .replace("{ext}", ext)
    )


def build_index() -> dict:
    """把两个数据源 + 缩略图清单拼成管理台要的列表。"""
    data = load_json(gallery.DATA, {"sections": {}})
    meta = load_json(gallery.META, {"works": {}})
    manifest = load_json(gallery.MANIFEST, {"items": []})
    thumbs = {item["src"]: item for item in manifest.get("items", [])}

    items: list[dict] = []
    for key in gallery.STATIC_SECTIONS:
        sec = data.get("sections", {}).get(key, {})
        for item in sec.get("items", []):
            src = item.get("orig", "")
            thumb = thumbs.get(src, {})
            items.append(
                {
                    "id": item.get("id", ""),
                    "section": key,
                    "file": src,
                    "title": item.get("title", ""),
                    "author": item.get("author", ""),
                    "desc": item.get("desc", ""),
                    "type": "",
                    "width": item.get("width", 0),
                    "height": item.get("height", 0),
                    "bytes": thumb.get("origBytes", 0),
                    "thumb": thumb.get("thumbSmall", ""),
                    "thumbBig": thumb.get("thumb", ""),
                    "links": item.get("links", []),
                }
            )
    for wid, work in meta.get("works", {}).items():
        src = work.get("file", "")
        thumb = thumbs.get(src, {})
        items.append(
            {
                "id": wid,
                "section": COMMUNITY,
                "file": src,
                "title": work.get("title", ""),
                "author": work.get("author", ""),
                "desc": "",
                "type": work.get("type", ""),
                "width": work.get("width", 0),
                "height": work.get("height", 0),
                "bytes": thumb.get("origBytes", 0),
                "thumb": thumb.get("thumbSmall", ""),
                "thumbBig": thumb.get("thumb", ""),
                "source": work.get("source", ""),
                "issueUrl": work.get("issueUrl", ""),
                "license": work.get("license", ""),
                "handmade": work.get("handmade", True),
                "creationType": work.get("creationType", ""),
            }
        )
    return {
        "sections": [
            {"key": key, "label": SECTION_LABELS.get(key, key), "count": sum(1 for i in items if i["section"] == key)}
            for key in (COMMUNITY, *gallery.STATIC_SECTIONS)
        ],
        "items": items,
        "stats": {
            "count": len(items),
            "bytes": sum(i["bytes"] for i in items),
        },
    }


# ---------------------------------------------------------------- 重建流水线

def run_pipeline(note: str = "") -> None:
    """在后台跑一遍全站重建，日志进 LOG。"""
    with BUILD_LOCK:
        if BUILD_STATE["running"]:
            log_line("· 已经有一次重建在跑，等它结束")
            return
        BUILD_STATE.update(running=True, ok=None, started=time.time(), error="")
    log_line(f"=== 重建开始 {note}===".strip())
    buf = io.StringIO()
    ok = True
    error = ""
    try:
        with contextlib.redirect_stdout(buf):
            gallery.sync(check_manifest=False)
    except SystemExit as exc:
        ok = False
        error = str(exc)
    except Exception as exc:  # noqa: BLE001
        ok = False
        error = f"{type(exc).__name__}: {exc}"
        buf.write("\n" + traceback.format_exc())
    log_all(buf.getvalue())
    if error:
        log_line(f"::error:: 重建失败：{error}")
    else:
        log_line("=== 重建完成 ✓ ===")
    with BUILD_LOCK:
        BUILD_STATE.update(running=False, ok=ok, finished=time.time(), error=error)


def pipeline_thread(note: str = "") -> None:
    threading.Thread(target=run_pipeline, args=(note,), daemon=True).start()


# ---------------------------------------------------------------- 数据写入

def collect_existing_ids(section: str) -> set[str]:
    data = load_json(gallery.DATA, {"sections": {}})
    meta = load_json(gallery.META, {"works": {}})
    if section == COMMUNITY:
        return set(meta.get("works", {}).keys())
    return {i.get("id", "") for i in data.get("sections", {}).get(section, {}).get("items", [])}


def write_community_fields(section: str, image_id: str, fields: dict) -> None:
    meta = load_json(gallery.META, {"works": {}})
    work = meta.get("works", {}).get(image_id)
    if work is None:
        raise ValueError(f"找不到作品 {image_id}")
    for key in ("title", "author", "type", "source", "issueUrl", "license", "desc"):
        if key in fields and fields[key] is not None:
            work[key] = fields[key]
    if "handmade" in fields:
        work["handmade"] = bool(fields["handmade"])
    if "creationType" in fields and fields["creationType"]:
        work["creationType"] = fields["creationType"]
    meta["works"][image_id] = work
    gallery.save_json(gallery.META, meta)


def write_static_fields(section: str, image_id: str, fields: dict) -> None:
    data = load_json(gallery.DATA, {"sections": {}})
    sec = data.get("sections", {}).get(section)
    if sec is None:
        raise ValueError(f"找不到分区 {section}")
    for item in sec.get("items", []):
        if item.get("id") != image_id:
            continue
        for key in ("title", "author", "desc", "alt"):
            if key in fields and fields[key] is not None:
                item[key] = fields[key]
        if fields.get("alt") is None and fields.get("title"):
            item["alt"] = fields["title"]
        sec["items"] = sec["items"]
        break
    else:
        raise ValueError(f"找不到图片 {image_id}")
    gallery.save_json(gallery.DATA, data)


def do_update(payload: dict) -> dict:
    section = payload.get("section") or COMMUNITY
    image_id = payload.get("id", "")
    fields = payload.get("fields", {})
    if section == COMMUNITY:
        write_community_fields(section, image_id, fields)
    else:
        write_static_fields(section, image_id, fields)
    log_line(f"· 改好了：{image_id}")
    pipeline_thread(f"（改标题 {image_id}）")
    return {"ok": True, "id": image_id}


def do_delete(payload: dict) -> dict:
    section = payload.get("section") or None
    image_id = payload.get("id", "")
    result = gallery.remove_item(section, image_id)
    log_line(f"· 删掉了：{image_id}（连带 {len(result['removed'])} 个文件）")
    pipeline_thread(f"（删除 {image_id}）")
    return {"ok": True, **result}


def do_upload(fields: dict, files: list[tuple[str, bytes]]) -> dict:
    section = fields.get("section") or COMMUNITY
    if section not in gallery.ALL_SECTIONS:
        raise ValueError(f"未知分区 {section}")
    title_tpl = fields.get("title", "")
    author = fields.get("author", "")
    desc = fields.get("desc", "")
    source = fields.get("source", "")
    license_ = fields.get("license", "")
    content_type = fields.get("type", "")
    id_prefix = fields.get("idPrefix", "")
    compress = str(fields.get("compress", "1")).lower() not in ("0", "false", "off", "no")
    handmade = str(fields.get("handmade", "1")).lower() not in ("0", "false", "off", "no")

    taken = collect_existing_ids(section)
    tmpdir = Path(tempfile.mkdtemp(prefix="dsg-admin-"))
    added: list[dict] = []
    failed: list[dict] = []
    try:
        for index, (filename, payload) in enumerate(files, start=1):
            stem = Path(filename).stem
            ext = Path(filename).suffix.lower().lstrip(".")
            base = sanitize_id(stem)
            if id_prefix:
                base = f"{sanitize_id(id_prefix)}-{base}"
            image_id = unique_id(base, taken)
            taken.add(image_id)

            title = apply_template(title_tpl, name=stem, index=index, ext=ext) or stem
            final_author = apply_template(author, name=stem, index=index, ext=ext)

            tmp = tmpdir / f"{image_id}{Path(filename).suffix.lower()}"
            tmp.write_bytes(payload)
            try:
                result = gallery.add_item(
                    section,
                    image_id,
                    tmp,
                    title=title,
                    author=final_author,
                    desc=desc,
                    alt=title,
                    source=source,
                    license=license_,
                    content_type=content_type,
                    handmade=handmade,
                    creation_type="手工创作" if handmade else "AI 创作",
                    compress=compress,
                )
            except Exception as exc:  # noqa: BLE001
                failed.append({"name": filename, "error": str(exc)})
                log_line(f"::error:: {filename}：{exc}")
                continue
            cinfo = result["compress"]
            added.append(
                {
                    "id": image_id,
                    "title": title,
                    "file": result["file"],
                    "before": cinfo["before"],
                    "after": cinfo["after"],
                    "saved": cinfo["saved"],
                    "width": cinfo["width"],
                    "height": cinfo["height"],
                }
            )
            log_line(
                f"· + {image_id}｜{title}｜{cinfo['width']}×{cinfo['height']}｜"
                f"{human(cinfo['before'])} → {human(cinfo['after'])}"
            )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    if added:
        pipeline_thread(f"（新增 {len(added)} 张）")
    return {
        "ok": True,
        "added": added,
        "failed": failed,
        "saved": sum(a["saved"] for a in added),
        "before": sum(a["before"] for a in added),
        "after": sum(a["after"] for a in added),
    }


# ---------------------------------------------------------------- HTTP

def parse_multipart(body: bytes, content_type: str) -> tuple[list[dict], dict[str, str]]:
    from email.parser import BytesParser
    from email.policy import HTTP

    match = re.search(r"boundary=([^;]+)", content_type)
    if not match:
        raise ValueError("上传格式不对（缺 boundary）")
    boundary = match.group(1).strip().strip('"').encode("utf-8")
    message = BytesParser(policy=HTTP).parsebytes(
        b"Content-Type: multipart/form-data; boundary=" + boundary
        + b"\r\nMIME-Version: 1.0\r\n\r\n"
        + body
    )
    parts: list[dict] = []
    fields: dict[str, str] = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        filename = part.get_filename()
        data = part.get_payload(decode=True) or b""
        if filename is not None:
            parts.append({"name": name, "filename": filename, "data": data})
        else:
            fields[name] = data.decode("utf-8", "replace")
    return parts, fields


class Handler(BaseHTTPRequestHandler):
    server_version = "DSG-Admin/1.0"

    # ---- 基础响应
    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8", extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError):
            pass

    def _json(self, data, code: int = 200):
        self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD:
            raise ValueError(f"上传太大了（{human(length)}），单次上限 {human(MAX_UPLOAD)}")
        return self.rfile.read(length) if length else b""

    def log_message(self, fmt, *args):  # 静音默认访问日志
        pass

    # ---- 路由
    def do_GET(self):  # noqa: N802
        path = unquote(urlparse(self.path).path)
        try:
            if path in ("/", "/index.html"):
                body = UI_FILE.read_bytes()
                return self._send(200, body, "text/html; charset=utf-8")
            if path == "/api/list":
                return self._json(build_index())
            if path == "/api/status":
                with LOG_LOCK:
                    lines = LOG[-400:]
                return self._json({"build": BUILD_STATE, "log": lines})
            if path.startswith("/preview"):
                # 预览整站：/preview/ 是页面，/preview/thumbs/xxx.webp 等相对资源原样映射到 docs/
                rel = path[len("/preview"):].lstrip("/")
                if not rel or rel == "index.html":
                    rel = "index.html"
                return self._serve_file(rel)
            if path.startswith("/files/"):
                rel = path[len("/files/"):]
                return self._serve_file(rel)
            self._json({"error": "没有这个页面"}, 404)
        except BrokenPipeError:
            pass
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._json({"error": str(exc)}, 500)

    def do_POST(self):  # noqa: N802
        path = unquote(urlparse(self.path).path)
        try:
            if path == "/api/upload":
                ctype = self.headers.get("Content-Type", "")
                body = self._read_body()
                parts, fields = parse_multipart(body, ctype)
                files = [(p["filename"], p["data"]) for p in parts if p.get("filename")]
                result = do_upload(fields, files)
                return self._json(result)
            body = self._read_body()
            payload = json.loads(body.decode("utf-8") or "{}")
            if path == "/api/update":
                return self._json(do_update(payload))
            if path == "/api/delete":
                return self._json(do_delete(payload))
            if path == "/api/sync":
                pipeline_thread("（手动重建）")
                return self._json({"ok": True, "started": True})
            self._json({"error": "没有这个接口"}, 404)
        except ValueError as exc:
            self._json({"error": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._json({"error": str(exc)}, 500)

    def _serve_file(self, rel: str):
        target = (DOCS_DIR / rel).resolve()
        try:
            target.relative_to(DOCS_DIR.resolve())
        except ValueError:
            return self._json({"error": "路径不合法"}, 403)
        if not target.is_file():
            return self._json({"error": "文件不在"}, 404)
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._send(200, target.read_bytes(), ctype, {"Cache-Control": "public, max-age=60"})


def main() -> int:
    parser = argparse.ArgumentParser(description="本地画廊管理台")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认只听本机）")
    parser.add_argument("--port", type=int, default=8765, help="端口（默认 8765）")
    parser.add_argument("--open", action="store_true", help="起完自动打开浏览器")
    args = parser.parse_args()

    if not UI_FILE.exists():
        print(f"::error::找不到管理台页面 {UI_FILE}")
        return 1

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print("大肥鱼画廊 · 管理台已启动")
    print(f"  {url}")
    print("  Ctrl+C 退出")
    if args.open:
        threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
