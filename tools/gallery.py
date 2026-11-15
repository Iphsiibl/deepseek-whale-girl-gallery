#!/usr/bin/env python3
"""画廊图片管理 CLI —— 增 / 删 / 查 / 重建，一条命令搞定。

为什么需要它
------------
最早「社区二创」是数据驱动的（``docs/community/_meta.json`` → ``build_cards.py``），
另外 4 个分区（角色设定图 / 萌娘百科 / 换装三视图 / 壁纸）的图块却是直接手写
在 ``docs/index.html`` 里的 —— 加一张图要手抄 ``<figure>``、``srcset``、
``data-full``、宽高、``alt``，漏一个属性就是一处不一致。

现在全部 5 个分区都是数据源驱动的：

* 静态分区 → ``docs/_gallery.json`` → ``tools/render.py`` → 页面
* 社区分区 → ``docs/community/_meta.json`` → ``tools/build_cards.py`` → 页面

本脚本把「拷文件 + 改数据源 + 生成缩略图 + 重渲染 + 更新署名 + 跑校验」
这一整条链包成一条命令。

用法
----

::

    # 看看现在有什么
    python tools/gallery.py list

    # 加一张图（社区二创）
    python tools/gallery.py add ~/Pictures/新图.png --section community \\
        --title "标题" --author "作者" --source "出处链接"

    # 加一张图（换装三视图这类静态分区）
    python tools/gallery.py add ~/Pictures/新图.png --section refs \\
        --title "08 新造型" --author "AI 萌图"

    # 删一张图
    python tools/gallery.py remove issue-31-01
    python tools/gallery.py remove 01-black-gown --section refs

    # 只重建不改动内容（改了元数据之后用）
    python tools/gallery.py sync

常用选项
--------

``--id``        自定义 ID（默认取文件名），也决定缩略图文件名
``--desc``      副标题 / 描述
``--source``    出处（社区分区是投稿链接，静态分区是资产库链接）
``--license``   许可标注
``--dry-run``   只打印计划，不落盘
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("缺少 Pillow，请先运行 pip install -r tools/requirements.txt")

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
DOCS_DIR = REPO_ROOT / "docs"
DATA = DOCS_DIR / "_gallery.json"
META = DOCS_DIR / "community" / "_meta.json"
MANIFEST = DOCS_DIR / "thumbs" / "_manifest.json"

# 同目录模块：既要能 `python tools/gallery.py` 直接跑，也要能被 admin.py 当模块导入
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
from imageopt import store_image  # noqa: E402

#: 静态分区：key → (原图目录, README 显示名)
STATIC_SECTIONS = {
    "sheets": ("sheets", "角色设定图"),
    "moegirl": ("moegirl", "萌娘百科收录图"),
    "refs": ("refs", "换装三视图"),
    "wallpaper": ("wallpaper", "场景壁纸"),
}
COMMUNITY = "community"
ALL_SECTIONS = (*STATIC_SECTIONS, COMMUNITY)

SOURCE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ID_RE = re.compile(r"^[A-Za-z0-9._\-一-鿿]+$")


# ---------------------------------------------------------------- 工具函数


def human(size: int) -> str:
    mb = size / 1024 / 1024
    if mb >= 1:
        return f"{mb:.1f} MB"
    return f"{size / 1024:.0f} KB"


def run(script: str, *args: str) -> str:
    """跑一个 tools/ 下的脚本，出错直接抛出。返回脚本的输出。

    输出先收再打，是为了让管理台（admin.py）能把整条重建链的日志收进面板里。
    """
    cmd = [sys.executable, str(TOOLS_DIR / script), *args]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    if out.strip():
        print(out.rstrip())
    if proc.returncode != 0:
        raise SystemExit(f"::error::{script} 执行失败（退出码 {proc.returncode}）")
    return out


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data) -> None:
    # 与 import_upstream.py / build_cards.py 的写法保持一致：不加末尾换行，
    # 否则每次 sync 都会凭空多出一个 "\ No newline at end of file" 的 diff。
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as img:
        return img.size


def manifest_index() -> dict[str, dict]:
    if not MANIFEST.exists():
        return {}
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {item["src"]: item for item in data["items"]}


# ---------------------------------------------------------------- 同步链


def sync(clean: bool = False, check_manifest: bool = True) -> None:
    """重建全站：缩略图 → 社区分区 → 静态分区 → srcset → 署名表。

    ``check_manifest`` 是「已提交的清单 vs 重新生成的清单」的一致性校验，
    属于提交前 / CI 阶段。本地刚 add/remove 时改动还没进 git，比对必然不一致，
    所以那种场景下跳过它。
    """
    print("重建中：")
    run("make_thumbs.py", *(["--clean"] if clean else []))
    run("build_cards.py")
    run("render.py")
    run("sync_srcset.py")
    run("build_attribution.py")
    print("\n校验：")
    run("check_gallery.py")
    if check_manifest:
        run("check_manifest.py")
    else:
        print("  缩略图清单一致性留给 CI 校验（本次改动尚未提交）")


# ---------------------------------------------------------------- list


def cmd_list(args: argparse.Namespace) -> int:
    data = load_json(DATA, {"sections": {}})
    meta = load_json(META, {"works": {}})
    manifest = manifest_index()

    sections = [args.section] if args.section else list(ALL_SECTIONS)
    total = 0
    for key in sections:
        if key == COMMUNITY:
            items = [
                {
                    "id": wid,
                    "title": w.get("title", ""),
                    "author": w.get("author", ""),
                    "width": w.get("width", 0),
                    "height": w.get("height", 0),
                }
                for wid, w in meta.get("works", {}).items()
            ]
            label = "社区二创"
        else:
            items = data.get("sections", {}).get(key, {}).get("items", [])
            label = STATIC_SECTIONS[key][1]
        total += len(items)
        print(f"\n{label}（{key}）· {len(items)} 张")
        for item in items:
            size = f"{item.get('width', 0)}×{item.get('height', 0)}"
            print(f"  {item['id']:32s} {size:>11s}  {item.get('title', '')}")
    print(f"\n合计 {total} 张")
    return 0


# ---------------------------------------------------------------- 增删（数据层）
#
# 这一层只做两件事：把文件存进 docs/、把条目写进数据源。**不重建页面。**
# CLI（gallery.py add/remove）和图形化管理台（admin.py）都调它，
# 保证两条路写出来的数据完全一致 —— 不能各写各的。


def add_item(
    section: str,
    image_id: str,
    src: Path,
    *,
    title: str,
    author: str,
    desc: str = "",
    alt: str = "",
    source: str = "",
    license: str = "",
    content_type: str = "",
    issue=None,
    issue_url: str = "",
    attachment: str = "",
    creation_type: str = "",
    handmade: bool = True,
    compress: bool = True,
) -> dict:
    """把一张图登记进数据源。

    默认入库即压缩（``imageopt.store_image``：长边 2560 / WebP q82）。
    返回 ``{"id", "section", "file", "compress": {...}}``。
    """
    if section not in ALL_SECTIONS:
        raise ValueError(f"未知分区：{section}")
    if not ID_RE.match(image_id):
        raise ValueError(f"ID 非法：{image_id}（只允许字母、数字、点、横线、下划线与中文）")
    src = Path(src)
    if not src.is_file():
        raise ValueError(f"找不到文件 {src}")
    ext = src.suffix.lower()
    if ext not in SOURCE_EXTS:
        raise ValueError(f"不支持的格式 {ext}（支持 {'/'.join(sorted(SOURCE_EXTS))}）")

    group = "community" if section == COMMUNITY else STATIC_SECTIONS[section][0]
    target_dir = DOCS_DIR / group
    target_dir.mkdir(parents=True, exist_ok=True)

    # 落盘（顺带压缩）——压缩完扩展名可能变成 .webp，所以文件名要用落盘结果
    target, cinfo = store_image(src, target_dir, image_id, compress=compress)
    rel = f"{group}/{target.name}"
    width, height = cinfo["width"], cinfo["height"]

    if section == COMMUNITY:
        meta = load_json(META, {"works": {}})
        works = meta.setdefault("works", {})
        work = {
            "id": image_id,
            "file": rel,
            "title": title,
            "author": author,
            "source": source or "",
            "issue": issue,
            "issueUrl": issue_url or "",
            "attachment": attachment or "",
            "license": license or "",
            "handmade": bool(handmade),
            "creationType": creation_type or ("手工创作" if handmade else "AI 创作"),
            "width": width,
            "height": height,
            "upstreamId": None,
            "sha256": "",
        }
        if content_type:
            work["type"] = content_type
        works[image_id] = work
        save_json(META, meta)
    else:
        data = load_json(DATA, {"version": 1, "sections": {}})
        sec = data["sections"].setdefault(
            section,
            {"anchor": f"p-{section}", "heading": section, "note": "", "items": []},
        )
        links = [{"href": rel, "label": f"原图 · {human(cinfo['after'])}"}]
        if source:
            links.append({"href": source, "label": "出处 ↗"})
        item = {
            "id": image_id,
            "orig": rel,
            "width": width,
            "height": height,
            "title": title,
            "desc": desc or "",
            "author": author,
            "alt": alt or title,
            "links": links,
        }
        sec["items"] = [i for i in sec["items"] if i.get("id") != image_id]
        sec["items"].append(item)
        save_json(DATA, data)

    return {"id": image_id, "section": section, "file": rel, "compress": cinfo}


def find_item(section: str | None, image_id: str) -> tuple[str, str, str]:
    """找出图片所在的分区、ID 和原图相对路径。找不到就抛 ValueError。"""
    data = load_json(DATA, {"sections": {}})
    meta = load_json(META, {"works": {}})

    targets: list[tuple[str, str, str]] = []
    scopes = [section] if section else list(ALL_SECTIONS)
    for key in scopes:
        if key == COMMUNITY:
            for wid, w in meta.get("works", {}).items():
                targets.append((COMMUNITY, wid, w.get("file", "")))
        else:
            for item in data.get("sections", {}).get(key, {}).get("items", []):
                targets.append((key, item.get("id", ""), item.get("orig", "")))

    hit = [t for t in targets if t[1] == image_id]
    if not hit:
        raise ValueError(f"找不到 ID「{image_id}」，用 python tools/gallery.py list 看看有哪些")
    if len(hit) > 1:
        raise ValueError(f"ID「{image_id}」在多个分区里都有，请指定分区")
    return hit[0]


def remove_item(section: str | None, image_id: str) -> dict:
    """删掉一张图（缩略图 + 原图 + 数据源条目）。"""
    sec, wid, orig = find_item(section, image_id)
    manifest = manifest_index()
    entry = manifest.get(orig)

    removed: list[str] = []
    for f in (entry or {}).get("files", []):
        p = DOCS_DIR / f["path"]
        if p.exists():
            p.unlink()
            removed.append(f["path"])
    orig_path = DOCS_DIR / orig
    if orig_path.exists():
        orig_path.unlink()
        removed.append(orig)

    if sec == COMMUNITY:
        meta = load_json(META, {"works": {}})
        meta.get("works", {}).pop(wid, None)
        save_json(META, meta)
    else:
        data = load_json(DATA, {"sections": {}})
        items = data["sections"][sec]["items"]
        data["sections"][sec]["items"] = [i for i in items if i.get("id") != wid]
        save_json(DATA, data)

    return {"id": wid, "section": sec, "removed": removed}


# ---------------------------------------------------------------- add


def cmd_add(args: argparse.Namespace) -> int:
    src = Path(args.image).expanduser()
    if not src.is_file():
        print(f"::error::找不到文件 {src}")
        return 1
    if src.suffix.lower() not in SOURCE_EXTS:
        print(f"::error::不支持的格式 {src.suffix}（支持 {'/'.join(sorted(SOURCE_EXTS))}）")
        return 1

    section = args.section
    group = "community" if section == COMMUNITY else STATIC_SECTIONS[section][0]
    image_id = args.id or src.stem
    if not ID_RE.match(image_id):
        print(f"::error::ID 非法：{image_id}（只允许字母、数字、点、横线、下划线与中文）")
        return 1

    width, height = image_size(src)
    size_bytes = src.stat().st_size
    print(f"目标分区：{section}")
    print(f"  文件：{group}/{image_id}.webp" if not args.raw else f"  文件：{group}/{image_id}{src.suffix.lower()}")
    print(f"  尺寸：{width}×{height}  ·  {human(size_bytes)}")
    print(f"  ID  ：{image_id}")
    print("  压缩：关闭（原样入库）" if args.raw else "  压缩：开启（长边 2560 · WebP q82）")

    if args.dry_run:
        print("（--dry-run，未落盘）")
        return 0

    try:
        result = add_item(
            section,
            image_id,
            src,
            title=args.title,
            author=args.author,
            desc=args.desc,
            alt=args.alt,
            source=args.source,
            license=args.license,
            content_type=args.type,
            issue=args.issue,
            issue_url=args.issue_url,
            attachment=args.attachment,
            creation_type=args.creation_type,
            handmade=not args.ai,
            compress=not args.raw,
        )
    except ValueError as exc:
        print(f"::error::{exc}")
        return 1

    cinfo = result["compress"]
    if not args.raw:
        print(f"  压缩后：{result['file']} · {human(cinfo['after'])}（省 {human(cinfo['saved'])}）")
    print(f"  已写入 {META.relative_to(REPO_ROOT) if section == COMMUNITY else DATA.relative_to(REPO_ROOT)}")

    print()
    sync(check_manifest=False)
    print(f"\n✓ 已加入「{section}」：{args.title}")
    return 0


# ---------------------------------------------------------------- remove


def cmd_remove(args: argparse.Namespace) -> int:
    try:
        section, image_id, orig = find_item(args.section, args.id)
    except ValueError as exc:
        print(f"::error::{exc}")
        return 1

    print(f"将删除：{section} / {image_id}")
    print(f"  原图：{orig}")
    manifest = manifest_index()
    entry = manifest.get(orig)
    for f in (entry or {}).get("files", []):
        print(f"  缩略图：{f['path']}")
    if args.dry_run:
        print("（--dry-run，未落盘）")
        return 0

    remove_item(args.section, args.id)
    print("  已从数据源移除")

    print()
    sync(check_manifest=False)
    print(f"\n✓ 已删除：{image_id}")
    return 0


# ---------------------------------------------------------------- 入口


def main() -> int:
    parser = argparse.ArgumentParser(
        description="画廊图片管理：add / remove / list / sync",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="列出所有图")
    p_list.add_argument("--section", choices=ALL_SECTIONS, help="只看某个分区")
    p_list.set_defaults(func=cmd_list)

    p_add = sub.add_parser("add", help="加入一张图")
    p_add.add_argument("image", help="图片文件路径")
    p_add.add_argument("--section", required=True, choices=ALL_SECTIONS, help="加入哪个分区")
    p_add.add_argument("--title", required=True, help="标题")
    p_add.add_argument("--author", required=True, help="作者 / 署名")
    p_add.add_argument("--desc", default="", help="副标题 / 描述")
    p_add.add_argument("--alt", default="", help="图片 alt 文本（默认同标题）")
    p_add.add_argument("--id", default="", help="自定义 ID（默认取文件名），也决定缩略图文件名")
    p_add.add_argument("--source", default="", help="出处链接 / 说明")
    p_add.add_argument("--license", default="", help="许可标注")
    p_add.add_argument("--type", default="", help="内容类型（社区分区：character/meme/sheet/scene）")
    p_add.add_argument("--issue", type=int, default=None, help="上游 issue 号（社区分区）")
    p_add.add_argument("--issue-url", default="", help="上游 issue 链接（社区分区）")
    p_add.add_argument("--attachment", default="", help="附件直链（社区分区）")
    p_add.add_argument("--creation-type", default="", help="创作方式说明（社区分区）")
    p_add.add_argument("--raw", action="store_true", help="跳过压缩，原样入库（默认入库即压缩）")
    p_add.add_argument("--ai", action="store_true", help="标记为 AI 生成（默认按手工创作记录）")
    p_add.add_argument("--dry-run", action="store_true", help="只打印计划")
    p_add.set_defaults(func=cmd_add)

    p_rm = sub.add_parser("remove", help="删掉一张图")
    p_rm.add_argument("id", help="图片 ID")
    p_rm.add_argument("--section", choices=ALL_SECTIONS, help="在哪个分区找（默认全找）")
    p_rm.add_argument("--dry-run", action="store_true", help="只打印计划")
    p_rm.set_defaults(func=cmd_remove)

    p_sync = sub.add_parser("sync", help="只重建，不改内容")
    p_sync.add_argument("--clean", action="store_true", help="连缩略图一起清空重建（慢）")
    p_sync.set_defaults(func=lambda a: (sync(a.clean), 0)[1])

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
