#!/usr/bin/env python3
"""从「鲸鱼娘开源资产库」批量导入社区作品，并记录逐图出处。

背景
----
社区作品的一手来源是 `TreapGoGo/deepseek-whale-girl`（MIT 许可的**网站代码**）。
该仓库维护了一份机器可读的清单 `site/assets/gallery/manifest.json`，
记录每件作品的标题、作者、来源、投稿 issue、创作类型、尺寸与文件路径。
本工具按这份清单把作品原图拉进本站，并生成一份出处文件，
供页面逐图署名与 `ATTRIBUTION.md` 自动生成。

重要：本工具**不改变**作品许可。上游明确声明「收录不把图片变成 MIT 素材」，
每件作品仍按其作者/投稿声明授权；上游未标注作者的作品，本工具如实记录为
「作者未知（上游未标注）」，不做猜测。

用法
----
    python tools/import_upstream.py --dry-run     # 只打印计划，不下载
    python tools/import_upstream.py               # 下载缺失的作品（可重复运行）
    python tools/import_upstream.py --limit 20    # 只处理前 20 件
    python tools/import_upstream.py --refresh     # 重新拉取上游清单
    python tools/import_upstream.py --force       # 已存在的也重新下载
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("缺少依赖 Pillow，请先执行: pip install -r tools/requirements.txt")

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
DOCS_DIR = REPO_ROOT / "docs"
TARGET_DIR = DOCS_DIR / "community"
META_PATH = TARGET_DIR / "_meta.json"

UPSTREAM_REPO = "TreapGoGo/deepseek-whale-girl"
UPSTREAM_RAW = f"https://raw.githubusercontent.com/{UPSTREAM_REPO}/main/site/"
UPSTREAM_API = f"https://api.github.com/repos/{UPSTREAM_REPO}"
VENDORED_MANIFEST = TOOLS_DIR / "upstream" / "manifest.json"

#: 上游清单里 `gallery: false` 的条目（多格总览，避免与单张作品重复占位）
SKIP_GALLERY_FALSE = True

#: 已知需要人工确认的重复（本地已存在的精选图 vs 上游同名作品）


def log(message: str) -> None:
    print(message, flush=True)


def fetch(url: str, *, token: str | None = None, timeout: int = 90, retries: int = 4) -> bytes:
    """带重试的 GET。优先用 GitHub API（带 token），失败再回落 raw。"""
    headers = {"User-Agent": "deepseek-whale-girl-gallery-import"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    last: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:  # noqa: BLE001 - 网络错误统一重试
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"下载失败 {url}: {last}")


def api_json(path: str, token: str | None) -> dict:
    raw = fetch(f"{UPSTREAM_API}{path}", token=token, timeout=60)
    return json.loads(raw)


def refresh_manifest(token: str | None) -> dict:
    """拉取上游最新清单并覆盖本地 vendor 副本。"""
    log(f"拉取上游清单 {UPSTREAM_REPO}/site/assets/gallery/manifest.json …")
    raw = fetch(UPSTREAM_RAW + "assets/gallery/manifest.json", token=token, timeout=60)
    manifest = json.loads(raw)
    VENDORED_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    VENDORED_MANIFEST.write_text(raw, encoding="utf-8")
    log(f"  已更新 {VENDORED_MANIFEST.relative_to(REPO_ROOT)}（{len(raw)} B，{len(manifest['works'])} 件作品）")
    return manifest


def load_manifest() -> dict:
    if not VENDORED_MANIFEST.exists():
        sys.exit(f"缺少 {VENDORED_MANIFEST}，请先运行 --refresh")
    return json.loads(VENDORED_MANIFEST.read_text(encoding="utf-8"))


def ahash(path: Path) -> str:
    """8x8 平均哈希（用于识别「同一张图但被重新编码」的情况）。"""
    with Image.open(path) as image:
        small = image.convert("L").resize((8, 8), Image.LANCZOS)
        pixels = list(small.getdata())
    average = sum(pixels) / len(pixels)
    return "".join("1" if p > average else "0" for p in pixels)


def hamming(a: str, b: str) -> int:
    return sum(1 for x, y in zip(a, b) if x != y)


def download_one(work: dict, tree_index: dict, token: str | None) -> tuple[dict, bytes]:
    """下载单件作品的原图。优先走 GitHub blobs API（稳定），回落 gh-pages。"""
    rel = work["original"].lstrip("./")
    entry = tree_index.get(rel)
    if entry:
        blob = api_json(f"/git/blobs/{entry['sha']}", token)
        data = base64.b64decode(blob["content"])
    else:
        data = fetch(f"https://treapgogo.github.io/{UPSTREAM_REPO.split('/')[1]}/{rel}", token=token)
    return work, data


def collect_existing_hashes() -> dict[str, str]:
    """已有本地图片的感知哈希，用于去重。"""
    result: dict[str, str] = {}
    for group in ("sheets", "moegirl", "refs", "gallery", "wallpaper"):
        directory = DOCS_DIR / group
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                try:
                    result[f"{group}/{path.name}"] = ahash(path)
                except Exception:  # noqa: BLE001 - 坏文件跳过
                    pass
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="从鲸鱼娘开源资产库导入社区作品")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不下载")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少件（0 = 全部）")
    parser.add_argument("--force", action="store_true", help="已存在的文件也重新下载")
    parser.add_argument("--refresh", action="store_true", help="先刷新上游清单")
    parser.add_argument("--token", default="", help="GitHub token（可选，用于 API 通道）")
    args = parser.parse_args()

    token = args.token or os.environ.get("GITHUB_TOKEN") or None
    if args.refresh:
        manifest = refresh_manifest(token)
    else:
        manifest = load_manifest()

    works = [w for w in manifest["works"] if not (SKIP_GALLERY_FALSE and w.get("gallery") is False)]
    if args.limit:
        works = works[: args.limit]

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = META_PATH
    meta: dict[str, dict] = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8")).get("works", {})

    todo = []
    for work in works:
        suffix = Path(work["original"]).suffix or ".webp"
        target = TARGET_DIR / f"{work['id']}{suffix}"
        if target.exists() and not args.force:
            continue
        todo.append((work, target, suffix))

    log(f"清单 {len(manifest['works'])} 件 → 可展示 {len(works)} 件；待下载 {len(todo)} 件")
    if not todo:
        log("没有需要下载的文件（已是最新）。")
    if args.dry_run:
        for work, target, _ in todo[:20]:
            log(f"  [计划] {target.relative_to(REPO_ROOT)}  ← {work['title']} / {work['author']}")
        if len(todo) > 20:
            log(f"  … 其余 {len(todo) - 20} 件")
        return 0

    # 文件树索引（blob sha → 直接走 API，比 raw 快且稳）
    tree_index: dict[str, dict] = {}
    try:
        tree = api_json("/git/trees/main?recursive=1", token)
        for node in tree.get("tree", []):
            if node.get("type") == "blob":
                tree_index[node["path"].replace("site/", "", 1)] = node
        log(f"上游文件树 {len(tree_index)} 个条目")
    except Exception as exc:  # noqa: BLE001 - 回落 gh-pages
        log(f"  文件树获取失败（{exc}），改用 gh-pages 通道")
        tree_index = {}

    log(f"开始下载 {len(todo)} 件 …")
    done = 0
    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(download_one, work, tree_index, token): (work, target) for work, target, _ in todo}
        for future in as_completed(futures):
            work, target = futures[future]
            try:
                _, data = future.result()
                target.write_bytes(data)
                done += 1
                if done % 20 == 0 or done == len(todo):
                    log(f"  已下载 {done}/{len(todo)}")
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{work['id']}: {exc}")
                log(f"  ✗ {work['id']} — {exc}")

    # 写出处文件
    for work in works:
        suffix = Path(work["original"]).suffix or ".webp"
        target = TARGET_DIR / f"{work['id']}{suffix}"
        if not target.exists():
            continue
        entry = meta.get(work["id"], {})
        entry.update(
            {
                "id": work["id"],
                "file": f"community/{target.name}",
                "title": work.get("title", ""),
                "author": work.get("author", ""),
                "source": work.get("source", ""),
                "issue": work.get("issue"),
                "issueUrl": work.get("issueUrl", ""),
                "attachment": work.get("attachment", ""),
                "license": work.get("license", ""),
                "handmade": work.get("handmade"),
                "creationType": work.get("creationType", ""),
                "width": work.get("width"),
                "height": work.get("height"),
                "upstreamId": work["id"],
            }
        )
        entry.setdefault("sha256", hashlib.sha256(target.read_bytes()).hexdigest())
        meta[work["id"]] = entry

    payload = {
        "source": f"https://github.com/{UPSTREAM_REPO}",
        "sourceLicense": "MIT（网站代码；作品许可逐件记录于 license 字段）",
        "manifestUpdated": manifest.get("updated", ""),
        "works": meta,
    }
    meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"出处文件 → {meta_path.relative_to(REPO_ROOT)}（{len(meta)} 件）")

    if failed:
        log(f"\n失败 {len(failed)} 件：")
        for item in failed[:10]:
            log(f"  ✗ {item}")
        return 1
    log("全部下载完成 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
