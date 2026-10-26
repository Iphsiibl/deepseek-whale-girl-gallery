#!/usr/bin/env python3
"""为画廊生成多档展示版缩略图（WebP）。

设计要点
--------
1. 路径相对脚本自身解析，任何机器、任何克隆位置都能直接跑。
2. **多档尺寸**（默认 480/960/1440/1920 宽），配合页面 ``<img srcset>``，
   浏览器按设备像素比只下载一档，避免"为手机发 1920px 图"这类浪费。
3. 档位语义是**输出图片的宽度**（与 ``srcset`` 的 ``w`` 描述符一致），
   竖构图按宽度等比缩放，绝不拉伸。
4. 保留 alpha 通道：RGBA 原图转 RGBA WebP，不铺黑底。
5. 增量生成：目标文件已存在且不比源文件旧就跳过，可重复运行。
6. 清理上一版遗留的旧命名缩略图（无 ``-<n>w`` 后缀的单文件）。
7. 输出 ``docs/thumbs/_manifest.json``，供 CI 校验页面与图片是否一致。

用法
----
    python tools/make_thumbs.py            # 生成缩略图
    python tools/make_thumbs.py --clean    # 先清空 thumbs/ 再生成
    python tools/make_thumbs.py --report   # 只打印体积报告，不写入
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("缺少依赖 Pillow，请先执行: pip install -r tools/requirements.txt")

# ---------------------------------------------------------------- 路径与配置

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
DOCS_DIR = REPO_ROOT / "docs"
THUMB_DIR = DOCS_DIR / "thumbs"

#: 原图分组目录 -> 页面分区 id（顺序即页面展示顺序）
GROUPS: tuple[str, ...] = ("sheets", "moegirl", "refs", "community", "wallpaper")

#: 缩略图宽度档位（像素）。页面按 ``sizes`` + DPR 选档。
SIZES: tuple[int, ...] = (480, 960, 1440, 1920)

#: WebP 编码参数
QUALITY = 80
METHOD = 6

#: 允许的原图扩展名
SOURCE_EXTS = (".png", ".jpg", ".jpeg", ".webp")

#: 旧版单尺寸缩略图的尺寸后缀，形如 ``-480w``
_SIZE_SUFFIX = re.compile(r"^\d+w$")


# ---------------------------------------------------------------- 工具函数


def human(size: int) -> str:
    """字节数转人类可读。"""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def is_legacy_thumb(path: Path) -> bool:
    """是否为旧版单尺寸缩略图（无 ``-<数字>w`` 后缀）。

    ``preview-1.webp``          -> 旧版，需清理
    ``preview-1-480w.webp``     -> 新版，保留
    ``01-chibi-character-sheet.webp`` -> 旧版，需清理
    """
    if not path.name.endswith(".webp"):
        return False
    stem = path.name[: -len(".webp")]
    tail = stem.rsplit("-", 1)[-1]
    return not bool(_SIZE_SUFFIX.match(tail))


def collect_sources() -> list[tuple[str, Path]]:
    """扫描原图目录，返回 ``(分组名, 路径)`` 列表（按分组与文件名排序）。"""
    found: list[tuple[str, Path]] = []
    for group in GROUPS:
        directory = DOCS_DIR / group
        if not directory.is_dir():
            continue
        for entry in sorted(directory.iterdir()):
            if not entry.is_file():
                continue
            if entry.suffix.lower() not in SOURCE_EXTS:
                continue
            found.append((group, entry))
    return found


def target_sizes(width: int) -> list[int]:
    """按**输出宽度**裁出需要生成的档位。

    规则：
    1. 只生成严格小于原图宽度的标准档位——放大既失真又徒增体积。
    2. 若原图本身比最大标准档还窄，补一档"原图宽度"，
       避免出现"900px 宽的图只有 480w 档"这种高 DPR 屏发虚的情况。
       阈值取 1.15 倍（不是 1.2）并用 ``>=``：1152 = 960 × 1.2 正好卡在
       严格大于的边界上，会被漏掉，而 1152 正是"原图 1152 宽"这类竖图的常见尺寸。
    """
    usable = [size for size in SIZES if size < width]
    if not usable:
        return [width]
    # 与现有最大档差距过大时，补一档原图宽度
    if width >= usable[-1] * 1.15 and width < SIZES[-1]:
        usable.append(width)
    return usable


def make_one(src: Path, group: str, force: bool) -> dict:
    """为一张原图生成全部档位，返回 manifest 条目。"""
    base = src.stem
    src_mtime = src.stat().st_mtime

    with Image.open(src) as image:
        width, height = image.size
        # 只有"真的存在半透明/全透明像素"才算 alpha 图。
        # 不少 PNG 带了一个全 255 的无用 alpha 通道，对它编 WebP alpha 是纯浪费。
        has_alpha = False
        if image.mode in ("RGBA", "LA") or "transparency" in image.info:
            alpha = image.convert("RGBA").split()[-1]
            has_alpha = alpha.getextrema()[0] < 255
        sizes = target_sizes(width)

        entries = []
        for size in sizes:
            out = THUMB_DIR / f"{base}-{size}w.webp"
            # 增量：已存在且不比源文件旧，就跳过重编码
            if out.exists() and not force and out.stat().st_mtime >= src_mtime:
                entries.append({"file": out, "size": size, "bytes": out.stat().st_size})
                continue

            scale = size / width
            if scale < 1.0:
                new_size = (size, max(1, round(height * scale)))
                work = image.resize(new_size, Image.LANCZOS)
            else:
                work = image

            # 关键：RGBA 原图必须保留真实存在的透明通道，不能 convert("RGB") 铺黑底
            if work.mode in ("P", "LA"):
                work = work.convert("RGBA")

            if work.mode in ("RGBA", "LA") and has_alpha:
                work.save(out, "WEBP", quality=QUALITY, method=METHOD)
            else:
                # 透明通道全是不透明像素时，显式转 RGB —— 少编一个用不上的 alpha 通道
                work.convert("RGB").save(out, "WEBP", quality=QUALITY, method=METHOD)

            entries.append({"file": out, "size": size, "bytes": out.stat().st_size})

    # 同一张原图的档位按宽度升序，srcset 顺序与之一致
    entries.sort(key=lambda item: item["size"])
    smallest, largest = entries[0], entries[-1]

    return {
        "group": group,
        "src": f"{group}/{src.name}",
        "origBytes": src.stat().st_size,
        "origW": width,
        "origH": height,
        "alpha": has_alpha,
        "sizes": [item["size"] for item in entries],
        "files": [
            {"path": f"thumbs/{item['file'].name}", "w": item["size"], "bytes": item["bytes"]}
            for item in entries
        ],
        "srcset": ", ".join(f"thumbs/{item['file'].name} {item['size']}w" for item in entries),
        "thumb": f"thumbs/{largest['file'].name}",
        "thumbSmall": f"thumbs/{smallest['file'].name}",
        "thumbBytes": largest["bytes"],
    }


def clean_legacy() -> list[str]:
    """删除上一版遗留的单尺寸缩略图。"""
    removed: list[str] = []
    if not THUMB_DIR.is_dir():
        return removed
    for path in sorted(THUMB_DIR.iterdir()):
        if path.is_file() and is_legacy_thumb(path):
            path.unlink()
            removed.append(path.name)
    return removed


def build(force: bool, clean: bool) -> dict:
    if clean and THUMB_DIR.is_dir():
        # 逐个删除而不是 shutil.rmtree 一把梭：
        # 在 NFS / 某些网络文件系统 / overlay 上，rmtree 删大批文件会抛
        # "Directory not empty"，且报错完全指不到真因。
        for entry in THUMB_DIR.iterdir():
            if entry.is_file() or entry.is_symlink():
                entry.unlink(missing_ok=True)
            else:
                shutil.rmtree(entry, ignore_errors=True)
    THUMB_DIR.mkdir(parents=True, exist_ok=True)

    sources = collect_sources()
    items: list[dict] = []
    # Pillow 的编码在 C 层执行、编码时会释放 GIL，线程能真正并行。
    # 图一多（本作 150+ 张 × 4 档 ≈ 600 个文件），串行编码要十几分钟，
    # 并行后能压到几分钟；结果按原顺序收集，manifest 依旧可复现。
    workers = min(8, max(1, os.cpu_count() or 2))
    if len(sources) > 1 and workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(make_one, src, group, force) for group, src in sources]
            for index, future in enumerate(futures, 1):
                items.append(future.result())
                if index % 25 == 0 or index == len(futures):
                    print(f"  已处理 {index}/{len(futures)} 张原图", flush=True)
    else:
        items = [make_one(src, group, force) for group, src in sources]
    manifest = {
        "sizes": list(SIZES),
        "quality": QUALITY,
        "method": METHOD,
        "count": len(items),
        "origBytes": sum(item["origBytes"] for item in items),
        "thumbBytes": sum(item["thumbBytes"] for item in items),
        "items": items,
    }

    (THUMB_DIR / "_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return manifest


def report(manifest: dict) -> None:
    items = manifest["items"]
    print(f"图片 {len(items)} 张")
    print(f"原图合计 {human(manifest['origBytes'])}")
    print("-" * 66)
    for size in manifest["sizes"]:
        bucket = [
            entry["bytes"]
            for item in items
            for entry in item["files"]
            if entry["w"] == size
        ]
        if not bucket:
            continue
        print(f"  {size:>5}w 档：{len(bucket):>2} 张 · {human(sum(bucket))}")
    print("-" * 66)

    # 首屏实际下载量估算：桌面 1x 走 480 档，移动 2x 走 960 档
    for probe in (480, 960):
        bucket = [
            entry["bytes"]
            for item in items
            for entry in item["files"]
            if entry["w"] == probe
        ]
        if bucket:
            print(f"  单档全量（{probe}w）: {human(sum(bucket))}")
    print("-" * 66)
    for item in sorted(items, key=lambda item: -item["origBytes"])[:10]:
        print(
            f"  {item['src']:<44} {item['origW']}x{item['origH']:<5} "
            f"{human(item['origBytes']):>9} -> {human(item['thumbBytes']):>8}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="生成画廊多档 WebP 缩略图")
    parser.add_argument("--force", action="store_true", help="忽略缓存，强制重新编码")
    parser.add_argument("--clean", action="store_true", help="先清空 thumbs/ 再生成")
    parser.add_argument("--report", action="store_true", help="只输出体积报告，不写入文件")
    args = parser.parse_args()

    if not DOCS_DIR.is_dir():
        sys.exit(f"找不到 docs 目录: {DOCS_DIR}")

    if args.report:
        manifest_path = THUMB_DIR / "_manifest.json"
        if not manifest_path.exists():
            sys.exit("还没有 manifest，请先不带 --report 运行一次")
        report(json.loads(manifest_path.read_text(encoding="utf-8")))
        return

    removed = clean_legacy()
    if removed:
        print(f"清理旧版缩略图 {len(removed)} 个\n")

    manifest = build(force=args.force, clean=args.clean)
    report(manifest)
    print(f"\nmanifest -> {THUMB_DIR / '_manifest.json'}")


if __name__ == "__main__":
    main()
