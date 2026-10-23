#!/usr/bin/env python3
"""把 ``docs/thumbs/_manifest.json`` 里的档位信息同步进页面的 ``srcset`` / ``data-full``。

背景
----
``make_thumbs.py`` 会按每张原图的宽度算出一组可用档位（例如
``480w, 960w, 1440w``）。页面里的 ``srcset`` 如果漏写了某一档，
那个文件就永远不会被下载 —— 既是浪费仓库空间，也让高像素密度屏幕
拿不到本该有的清晰度。

这个脚本做幂等同步：

* ``srcset``      —— 写成 manifest 里的完整档位列表
* ``src``         —— 兜底图，取不超过 960w 的最大档（没有则取最大档）
* ``data-full``   —— 灯箱大图，取该图的最高档

用法::

    python tools/sync_srcset.py           # 就地更新 docs/index.html
    python tools/sync_srcset.py --check   # 只检查，不修改（有差异则退出码 1）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
DOCS_DIR = REPO_ROOT / "docs"
PAGE = DOCS_DIR / "index.html"
MANIFEST = DOCS_DIR / "thumbs" / "_manifest.json"

#: 兜底 src 选用的目标宽度（老浏览器只认 src 时用它）
FALLBACK_WIDTH = 960


def load_manifest() -> dict[str, dict]:
    if not MANIFEST.exists():
        sys.exit(f"找不到 {MANIFEST}，请先运行 python tools/make_thumbs.py")
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {item["src"]: item for item in data["items"]}


def build_targets(manifest: dict[str, dict]) -> dict[str, dict]:
    """按原图路径算出期望的 src / srcset / data-full。"""
    targets: dict[str, dict] = {}
    for src, item in manifest.items():
        files = item["files"]
        widths = [entry["w"] for entry in files]

        fallback = next((w for w in reversed(widths) if w <= FALLBACK_WIDTH), widths[-1])
        src_path = next(entry["path"] for entry in files if entry["w"] == fallback)
        full_path = files[-1]["path"]
        srcset = ", ".join(f"{entry['path']} {entry['w']}w" for entry in files)
        targets[src] = {"src": src_path, "srcset": srcset, "data-full": full_path}
    return targets


def apply_to_html(html: str, targets: dict[str, dict]) -> tuple[str, list[str]]:
    """把期望值写回 HTML，返回 (新 HTML, 变更说明列表)。

    以整个 ``<a class="shot">…</a>`` 块为单位处理：
    ``data-orig`` / ``data-full`` 在 ``<a>`` 上，而 ``src`` / ``srcset`` 在块内的
    ``<img>`` 上，两者必须一起改。
    """
    changes: list[str] = []
    by_name = {Path(src).name: values for src, values in targets.items()}

    def fix_block(block_match: re.Match[str]) -> str:
        block = block_match.group(0)
        data_orig = re.search(r'data-orig\s*=\s*"([^"]+)"', block)
        if not data_orig:
            return block
        key = Path(data_orig.group(1)).name
        values = by_name.get(key)
        if not values:
            return block

        new_block = block

        # <a> 上的 data-full（灯箱大图）
        current = re.search(r'data-full\s*=\s*"([^"]*)"', new_block)
        if current and current.group(1) != values["data-full"]:
            changes.append(
                f"{key}: data-full {current.group(1)} → {values['data-full']}"
            )
            new_block = new_block.replace(current.group(0), f'data-full="{values["data-full"]}"')

        # 块内 <img> 上的 src / srcset
        img_match = re.search(r"<img\b[^>]*>", new_block, flags=re.DOTALL)
        if not img_match:
            return new_block
        img_tag = img_match.group(0)
        new_img = img_tag
        for attr, want in (("src", values["src"]), ("srcset", values["srcset"])):
            current = re.search(rf'{attr}\s*=\s*"([^"]*)"', new_img)
            if current and current.group(1) != want:
                changes.append(f"{key}: {attr} {current.group(1)} → {want}")
                new_img = new_img.replace(current.group(0), f'{attr}="{want}"')
        return new_block.replace(img_tag, new_img)

    html = re.sub(
        r"<a\b[^>]*class=\"shot\"[^>]*>.*?</a>", fix_block, html, flags=re.DOTALL
    )
    return html, changes


def main() -> int:
    parser = argparse.ArgumentParser(description="同步页面 srcset / data-full 与缩略图清单")
    parser.add_argument("--check", action="store_true", help="只检查不修改，有差异时退出码 1")
    args = parser.parse_args()

    html = PAGE.read_text(encoding="utf-8")
    targets = build_targets(load_manifest())
    new_html, changes = apply_to_html(html, targets)

    if not changes:
        print("srcset / data-full 与清单完全一致 ✓")
        return 0

    print(f"发现 {len(changes)} 处需要同步：")
    for change in changes:
        print(f"  · {change}")

    if args.check:
        print("\n--check 模式，未修改文件")
        return 1

    PAGE.write_text(new_html, encoding="utf-8")
    print(f"\n已更新 {PAGE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
