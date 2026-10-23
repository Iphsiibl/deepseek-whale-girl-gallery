#!/usr/bin/env python3
"""比较仓库里已提交的缩略图清单与重新生成的结果。

为什么不能直接比字节
--------------------
清单里的 ``bytes`` 字段是**编码产物的字节数**，而 WebP 的字节输出依赖
libwebp 版本。不同机器（本地 Pillow 11.x / CI 装到 12.x）编出来的同一个图，
字节数可能差几十字节 —— 逐字节比对清单就会误报"你忘了重新生成"，
把排查方向带偏。

所以这里只比**结构**：有哪些图、每张图有哪些档位、每档的宽度是多少、
原图的宽高是多少。这些只取决于原图和代码，与编码器版本无关。

用法::

    python tools/check_manifest.py                 # 与 git HEAD 比
    python tools/check_manifest.py --against FILE  # 与指定文件比
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_REL = "docs/thumbs/_manifest.json"


def shape(manifest: dict | list) -> dict:
    """抽取与编码器版本无关的结构信息。

    兼容旧版清单格式：最早的清单顶层就是一个数组（没有 items 包装）。
    """
    if isinstance(manifest, list):
        items = manifest
        head: dict = {"legacyFormat": True}
    else:
        items = manifest.get("items", [])
        head = {
            "sizes": manifest.get("sizes"),
            "quality": manifest.get("quality"),
            "method": manifest.get("method"),
            "count": manifest.get("count"),
        }
    return {
        **head,
        "items": [
            {
                **{k: v for k, v in item.items() if k not in ("origBytes", "thumbBytes")},
                "files": [
                    {k: v for k, v in f.items() if k != "bytes"} for f in item.get("files", [])
                ],
            }
            for item in items
        ],
    }


def load_head() -> dict:
    result = subprocess.run(
        ["git", "show", f"HEAD:{MANIFEST_REL}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"::error::无法读取已提交的 {MANIFEST_REL}：{result.stderr.strip()}\n"
            f"（首次提交或还没跑过 make_thumbs.py 时会这样，属正常）"
        )
        sys.exit(1)
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description="比对缩略图清单结构")
    parser.add_argument("--against", help="与指定的 manifest 文件比对（默认与 git HEAD 比）")
    args = parser.parse_args()

    current_path = REPO_ROOT / MANIFEST_REL
    if not current_path.exists():
        print(f"::error::缺少 {MANIFEST_REL}，请先运行 python tools/make_thumbs.py")
        return 1
    current = json.loads(current_path.read_text(encoding="utf-8"))

    if args.against:
        other_path = Path(args.against)
        other = json.loads(other_path.read_text(encoding="utf-8"))
        label = str(other_path)
    else:
        other = load_head()
        label = "git HEAD"

    if shape(current) == shape(other):
        print(f"缩略图清单结构与 {label} 一致 ✓")
        return 0

    print(f"::error::缩略图清单结构与 {label} 不一致。请在本地运行 "
          f"python tools/make_thumbs.py 和 python tools/sync_srcset.py 后提交。")
    cur_items = {i["src"]: i for i in current.get("items", [])}
    oth_items = {i["src"]: i for i in other.get("items", [])}
    for src in sorted(set(cur_items) | set(oth_items)):
        a = cur_items.get(src)
        b = oth_items.get(src)
        if a is None:
            print(f"  · {src}: 重新生成后不再出现")
        elif b is None:
            print(f"  · {src}: 重新生成后新增")
        else:
            aw = [f["w"] for f in a["files"]]
            bw = [f["w"] for f in b["files"]]
            if aw != bw:
                print(f"  · {src}: 档位 {bw} → {aw}")
            elif (a["origW"], a["origH"]) != (b["origW"], b["origH"]):
                print(f"  · {src}: 原图尺寸 {b['origW']}×{b['origH']} → {a['origW']}×{a['origH']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
