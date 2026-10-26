#!/usr/bin/env python3
"""校验画廊的一致性。

检查项
------
1. 页面里每个 ``<img>`` 的 ``src`` / ``srcset`` 指向的文件都真实存在。
2. ``srcset`` 里声明的宽度与实际文件宽度一致（否则浏览器会按错的尺寸选图）。
3. 每个 ``<img>`` 都带 ``width`` / ``height``（避免布局抖动 CLS）。
4. 页面里引用的原图都存在，且已登记进 ``thumbs/_manifest.json``。
5. 反向检查：``docs/`` 里的每一张原图都在页面中被引用（漏加卡片会提示）。
6. 站内链接（``href`` 指向相对路径）都存在。

退出码 0 表示全部通过，1 表示有问题。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
DOCS_DIR = REPO_ROOT / "docs"
PAGE = DOCS_DIR / "index.html"

IMG_TAG = re.compile(r"<img\b[^>]*>", re.IGNORECASE | re.DOTALL)
ATTR = re.compile(r'(\w[\w-]*)\s*=\s*"([^"]*)"')
HREF = re.compile(r'href\s*=\s*"([^"]+)"')

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
#: 原图分组目录
SOURCE_GROUPS = ("sheets", "moegirl", "refs", "community", "wallpaper")


def attrs(tag: str) -> dict[str, str]:
    return {key.lower(): value for key, value in ATTR.findall(tag)}


def main() -> int:
    if not PAGE.exists():
        print(f"找不到页面: {PAGE}")
        return 1

    html = PAGE.read_text(encoding="utf-8")
    problems: list[str] = []
    notes: list[str] = []

    # ---------------------------------------------------------------- 图片
    referenced_sources: set[str] = set()
    img_count = 0
    for tag in IMG_TAG.findall(html):
        img_count += 1
        a = attrs(tag)
        # 灯箱大图的 src 由 JS 动态赋值，不参与静态校验
        if a.get("id") == "lb-img":
            continue
        src = a.get("src", "")
        if not src:
            problems.append(f"<img> 缺少 src: {tag[:70]}…")
            continue
        if not (DOCS_DIR / src).exists():
            problems.append(f"src 指向的文件不存在: {src}")

        if "width" not in a or "height" not in a:
            problems.append(f"<img> 缺少 width/height（会造成布局抖动）: {src}")
        if not a.get("alt"):
            problems.append(f"<img> 缺少 alt: {src}")
        if "srcset" not in a:
            problems.append(f"<img> 缺少 srcset（不会按设备像素比选档）: {src}")

        # srcset 里声明的宽度必须等于文件实际宽度
        for entry in a.get("srcset", "").split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split()
            if len(parts) != 2 or not parts[1].endswith("w"):
                problems.append(f"srcset 条目格式不对: {entry}（来自 {src}）")
                continue
            path, declared = parts[0], int(parts[1][:-1])
            full = DOCS_DIR / path
            if not full.exists():
                problems.append(f"srcset 指向的文件不存在: {path}（来自 {src}）")
                continue
            try:
                from PIL import Image

                with Image.open(full) as im:
                    actual = im.size[0]
                if actual != declared:
                    problems.append(
                        f"srcset 宽度与实际不符: {path} 声明 {declared}w 实际 {actual}px"
                    )
            except Exception as exc:  # pragma: no cover
                problems.append(f"无法读取 {path}: {exc}")

    # ---------------------------------------------------------------- 原图
    for match in re.finditer(r'data-orig\s*=\s*"([^"]+)"', html):
        referenced_sources.add(match.group(1))
        if not (DOCS_DIR / match.group(1)).exists():
            problems.append(f"data-orig 指向的原图不存在: {match.group(1)}")

    # 页面里所有指向站内资源的 href（不限图片后缀）
    for href in HREF.findall(html):
        if href.startswith(("http://", "https://", "#", "mailto:", "//", "data:")):
            continue
        target = href.split("#")[0].strip()
        if not target:
            continue
        if not (DOCS_DIR / target).exists():
            problems.append(f"站内相对链接失效: {href}")
        if target.lower().endswith(IMAGE_EXTS):
            referenced_sources.add(target)

    # 反向：磁盘上的原图是否都被引用
    on_disk: set[str] = set()
    for group in SOURCE_GROUPS:
        directory = DOCS_DIR / group
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
                on_disk.add(f"{group}/{path.name}")

    orphans = on_disk - referenced_sources
    for orphan in sorted(orphans):
        problems.append(f"原图未出现在页面里（漏加卡片）: {orphan}")

    # ---------------------------------------------------------------- manifest
    manifest_path = DOCS_DIR / "thumbs" / "_manifest.json"
    referenced_thumbs: set[str] = set()
    if not manifest_path.exists():
        problems.append("缺少 thumbs/_manifest.json，请运行 python tools/make_thumbs.py")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_by_src = {item["src"]: item for item in manifest["items"]}
        for item in manifest["items"]:
            for entry in item["files"]:
                if not (DOCS_DIR / entry["path"]).exists():
                    problems.append(f"manifest 里的缩略图缺失: {entry['path']}")
        # manifest 覆盖的原图集合应与磁盘一致
        manifest_sources = {item["src"] for item in manifest["items"]}
        for extra in sorted(manifest_sources - on_disk):
            problems.append(f"manifest 记录了已不存在的原图: {extra}")
        for missing in sorted(on_disk - manifest_sources):
            problems.append(f"原图没有对应的缩略图记录，请重新运行 make_thumbs.py: {missing}")

        # 页面里引用的所有缩略图
        for tag in IMG_TAG.findall(html):
            a = attrs(tag)
            if a.get("id") == "lb-img":
                continue
            for path in [a.get("src", "")] + [
                entry.strip().split()[0]
                for entry in a.get("srcset", "").split(",")
                if entry.strip()
            ]:
                if path.startswith("thumbs/"):
                    referenced_thumbs.add(path)
        for match in re.finditer(r'data-full\s*=\s*"([^"]+)"', html):
            if match.group(1).startswith("thumbs/"):
                referenced_thumbs.add(match.group(1))

        # 1) srcset 必须列出该图的全部档位，否则高 DPR 屏拿不到清晰图
        for block in re.finditer(
            r'<a\b[^>]*class="shot"[^>]*>(.*?)</a>', html, flags=re.DOTALL
        ):
            block_html = block.group(0)
            data_orig = re.search(r'data-orig\s*=\s*"([^"]+)"', block_html)
            img_match = re.search(r"<img\b[^>]*>", block_html, flags=re.DOTALL)
            if not data_orig or not img_match:
                continue
            item = manifest_by_src.get(data_orig.group(1))
            if not item:
                continue
            a = attrs(img_match.group(0))
            declared = {
                entry.strip().split()[0]
                for entry in a.get("srcset", "").split(",")
                if entry.strip()
            }
            expected = {entry["path"] for entry in item["files"]}
            for missing in sorted(expected - declared):
                problems.append(
                    f"srcset 漏了档位 {missing}（{data_orig.group(1)}）"
                    f"—— 运行 python tools/sync_srcset.py 修复"
                )
            for extra in sorted(declared - expected):
                problems.append(
                    f"srcset 引用了清单外的档位 {extra}（{data_orig.group(1)}）"
                )

            # 3) width/height 必须与原图真实像素一致
            #    这两个属性是布局的命门：浏览器靠它算固有宽高比，
            #    瀑布流也靠它算行高。写成别的值图片会被拉扁，而所有检查都放行。
            img_attrs = attrs(img_match.group(0))
            try:
                from PIL import Image

                with Image.open(DOCS_DIR / data_orig.group(1)) as im:
                    real_w, real_h = im.size
                declared_w = int(img_attrs.get("width", 0) or 0)
                declared_h = int(img_attrs.get("height", 0) or 0)
                if (declared_w, declared_h) != (real_w, real_h):
                    problems.append(
                        f"width/height 与原图不符: {data_orig.group(1)} "
                        f"声明 {declared_w}×{declared_h}，原图 {real_w}×{real_h}"
                    )
            except Exception as exc:  # pragma: no cover
                problems.append(f"无法读取原图 {data_orig.group(1)}: {exc}")

            # 4) 灯箱大图应指向该图最高档
            full_match = re.search(r'data-full\s*=\s*"([^"]+)"', block_html)
            if full_match and item["files"]:
                highest = item["files"][-1]["path"]
                if full_match.group(1) != highest:
                    problems.append(
                        f"data-full 应指向最高档：{data_orig.group(1)} "
                        f"当前 {full_match.group(1)}，应为 {highest}"
                    )

        # 5) 孤儿缩略图：生成了但页面从不引用
        all_manifest_thumbs = {
            entry["path"] for item in manifest["items"] for entry in item["files"]
        }
        for orphan in sorted(all_manifest_thumbs - referenced_thumbs):
            problems.append(f"缩略图从未被页面引用（孤儿文件）: {orphan}")

        # 6) 页面引用了但清单里没有的缩略图
        for unknown in sorted(referenced_thumbs - all_manifest_thumbs):
            problems.append(f"页面引用了清单外的缩略图: {unknown}")

        # 7) thumbs/ 目录里有、清单里没收录的散落文件
        on_disk_thumbs = {p.name for p in (DOCS_DIR / "thumbs").glob("*.webp")}
        manifest_thumbs = {
            Path(entry["path"]).name
            for item in manifest["items"]
            for entry in item["files"]
        }
        for stray in sorted(on_disk_thumbs - manifest_thumbs):
            problems.append(f"thumbs/ 里有清单未收录的文件: {stray}")

    # ---------------------------------------------------------------- 社区出处
    # 社区作品是批量导入的，出处必须与文件一一对应：
    # 磁盘上的每个文件都要登记在 _meta.json，且都要出现在页面上。
    meta_path = DOCS_DIR / "community" / "_meta.json"
    if (DOCS_DIR / "community").is_dir():
        if not meta_path.exists():
            problems.append("缺少 docs/community/_meta.json，请运行 python tools/import_upstream.py")
        else:
            meta = json.loads(meta_path.read_text(encoding="utf-8")).get("works", {})
            meta_files = {w.get("file", "") for w in meta.values()}
            disk_files = {
                f"community/{p.name}"
                for p in (DOCS_DIR / "community").iterdir()
                if p.is_file() and p.suffix.lower() in IMAGE_EXTS
            }
            for missing in sorted(disk_files - meta_files):
                problems.append(f"社区原图未登记出处: {missing}")
            for extra in sorted(meta_files - disk_files):
                problems.append(f"出处文件记录了不存在的社区原图: {extra}")
            for wid, work in meta.items():
                author = (work.get("author") or "").strip()
                known_author = bool(author) and author != "作者未知"
                if not known_author:
                    # 上游没标作者就如实记着，不猜、不算错
                    continue
                # 作者已知却查不到出处，是我们自己记录上的缺口，必须报
                if not work.get("issueUrl") and not work.get("source"):
                    problems.append(f"社区作品有作者但缺少来源信息: {wid}")

            # ---- 设计契约 A1/A2/A4：类型与作者分栏必须与出处文件一致 ----
            # 页面上的卡片按 data-type / data-author 聚合，与 _meta.json 逐一对账。
            card_pairs: dict[tuple[str, str], int] = {}
            for block in re.finditer(
                r'<figure\b[^>]*class="card"[^>]*>(.*?)</figure>', html, flags=re.DOTALL
            ):
                head = block.group(0)[: block.group(0).find(">") + 1]
                attrs_map = attrs(head)
                work_type = attrs_map.get("data-type", "")
                author = attrs_map.get("data-author", "")
                if not work_type:
                    continue
                key = (work_type, author)
                card_pairs[key] = card_pairs.get(key, 0) + 1
            meta_pairs: dict[tuple[str, str], int] = {}
            for work in meta.values():
                if work.get("file", "") not in meta_files:
                    continue
                key = (work.get("type", ""), work.get("author") or "作者未知（上游未标注）")
                meta_pairs[key] = meta_pairs.get(key, 0) + 1
            for key in sorted(set(meta_pairs) - set(card_pairs)):
                problems.append(
                    f"页面缺少 (类型,作者) 组合的卡片: {key[0]} / {key[1]}（共 {meta_pairs[key]} 件）"
                )
            for key in sorted(set(card_pairs) - set(meta_pairs)):
                problems.append(f"页面多出了出处文件里没有的 (类型,作者) 组合: {key[0]} / {key[1]}")
            for key in sorted(set(card_pairs) & set(meta_pairs)):
                if card_pairs[key] != meta_pairs[key]:
                    problems.append(
                        f"(类型,作者) 件数不一致: {key[0]} / {key[1]} "
                        f"页面 {card_pairs[key]} vs 出处 {meta_pairs[key]}"
                    )
            # 类型总数必须等于社区卡片总数
            type_total = sum(meta_pairs.values())
            if type_total != len(meta_files):
                problems.append(
                    f"社区作品类型合计 {type_total} != 原图数 {len(meta_files)}"
                )

    # ---------------------------------------------------------------- 结果
    print(f"页面图片 {img_count} 张 · 引用原图 {len(referenced_sources)} 张 · 磁盘原图 {len(on_disk)} 张")
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        notes.append(f"原图合计 {manifest['origBytes'] / 1024 / 1024:.1f} MB")
        for size in manifest["sizes"]:
            bucket = [
                entry["bytes"]
                for item in manifest["items"]
                for entry in item["files"]
                if entry["w"] == size
            ]
            if bucket:
                notes.append(f"{size}w 档 {sum(bucket) / 1024:.0f} KB")

    for note in notes:
        print(f"  · {note}")

    if problems:
        print(f"\n发现 {len(problems)} 个问题：")
        for problem in problems:
            print(f"  ✗ {problem}")
        return 1

    print("\n全部检查通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
