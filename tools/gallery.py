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


def run(script: str, *args: str) -> None:
    """跑一个 tools/ 下的脚本，出错直接抛出。"""
    cmd = [sys.executable, str(TOOLS_DIR / script), *args]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"::error::{script} 执行失败（退出码 {proc.returncode}）")


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


# ---------------------------------------------------------------- add


def cmd_add(args: argparse.Namespace) -> int:
    src = Path(args.image).expanduser()
    if not src.is_file():
        return int(bool(print(f"::error::找不到文件 {src}"))) or 1
    if src.suffix.lower() not in SOURCE_EXTS:
        print(f"::error::不支持的格式 {src.suffix}（支持 {'/'.join(sorted(SOURCE_EXTS))}）")
        return 1

    section = args.section
    group = "community" if section == COMMUNITY else STATIC_SECTIONS[section][0]
    target_dir = DOCS_DIR / group
    target_dir.mkdir(parents=True, exist_ok=True)

    image_id = args.id or src.stem
    if not ID_RE.match(image_id):
        print(f"::error::ID 非法：{image_id}（只允许字母、数字、点、横线、下划线与中文）")
        return 1

    target = target_dir / f"{image_id}{src.suffix.lower()}"
    if target.exists() and target.resolve() != src.resolve():
        print(f"::error::{target.relative_to(REPO_ROOT)} 已存在，换个 --id 或先 remove")
        return 1

    width, height = image_size(src)
    size_bytes = src.stat().st_size
    print(f"目标分区：{section}")
    print(f"  文件：{target.relative_to(REPO_ROOT)}")
    print(f"  尺寸：{width}×{height}  ·  {human(size_bytes)}")
    print(f"  ID  ：{image_id}")

    if args.dry_run:
        print("（--dry-run，未落盘）")
        return 0

    if target.resolve() != src.resolve():
        shutil.copy2(src, target)

    if section == COMMUNITY:
        meta = load_json(META, {"works": {}})
        works = meta.setdefault("works", {})
        work = {
            "id": image_id,
            "file": f"community/{image_id}{src.suffix.lower()}",
            "title": args.title,
            "author": args.author,
            "source": args.source or "",
            "issue": args.issue,
            "issueUrl": args.issue_url or "",
            "attachment": args.attachment or "",
            "license": args.license or "",
            "handmade": True,
            "creationType": args.creation_type or "手工创作",
            "width": width,
            "height": height,
            "upstreamId": None,
            "sha256": "",
        }
        if args.type:
            work["type"] = args.type
        works[image_id] = work
        save_json(META, meta)
        print(f"  已写入 {META.relative_to(REPO_ROOT)}")
    else:
        data = load_json(DATA, {"version": 1, "sections": {}})
        sec = data["sections"].setdefault(
            section,
            {"anchor": f"p-{section}", "heading": section, "note": "", "items": []},
        )
        links = [{"href": f"{group}/{image_id}{src.suffix.lower()}", "label": f"原图 · {human(size_bytes)}"}]
        if args.source:
            links.append({"href": args.source, "label": "出处 ↗"})
        item = {
            "id": image_id,
            "orig": f"{group}/{image_id}{src.suffix.lower()}",
            "width": width,
            "height": height,
            "title": args.title,
            "desc": args.desc or "",
            "author": args.author,
            "alt": args.alt or args.title,
            "links": links,
        }
        sec["items"] = [i for i in sec["items"] if i.get("id") != image_id]
        sec["items"].append(item)
        save_json(DATA, data)
        print(f"  已写入 {DATA.relative_to(REPO_ROOT)}")

    print()
    sync(check_manifest=False)
    print(f"\n✓ 已加入「{section}」：{args.title}")
    return 0


# ---------------------------------------------------------------- remove


def cmd_remove(args: argparse.Namespace) -> int:
    data = load_json(DATA, {"sections": {}})
    meta = load_json(META, {"works": {}})
    manifest = manifest_index()

    # 定位：指定分区就只在该分区找，否则全找
    targets: list[tuple[str, str, str]] = []  # (section, id, 原图相对路径)
    if args.section:
        scopes = [args.section]
    else:
        scopes = list(ALL_SECTIONS)
    for key in scopes:
        if key == COMMUNITY:
            for wid, w in meta.get("works", {}).items():
                targets.append((COMMUNITY, wid, w.get("file", "")))
        else:
            for item in data.get("sections", {}).get(key, {}).get("items", []):
                targets.append((key, item.get("id", ""), item.get("orig", "")))

    hit = [t for t in targets if t[1] == args.id]
    if not hit:
        print(f"::error::找不到 ID「{args.id}」，用 python tools/gallery.py list 看看有哪些")
        return 1
    if len(hit) > 1:
        print(f"::error::ID「{args.id}」在多个分区里都有，请加 --section 指定")
        return 1

    section, image_id, orig = hit[0]
    print(f"将删除：{section} / {image_id}")
    print(f"  原图：{orig}")
    entry = manifest.get(orig)
    if entry:
        for f in entry.get("files", []):
            print(f"  缩略图：{f['path']}")
    if args.dry_run:
        print("（--dry-run，未落盘）")
        return 0

    # 删文件
    for f in (entry or {}).get("files", []):
        p = DOCS_DIR / f["path"]
        if p.exists():
            p.unlink()
    orig_path = DOCS_DIR / orig
    if orig_path.exists():
        orig_path.unlink()

    # 删数据源条目
    if section == COMMUNITY:
        meta = load_json(META, {"works": {}})
        meta.get("works", {}).pop(image_id, None)
        save_json(META, meta)
        print(f"  已从 {META.relative_to(REPO_ROOT)} 移除")
    else:
        data = load_json(DATA, {"sections": {}})
        items = data["sections"][section]["items"]
        data["sections"][section]["items"] = [i for i in items if i.get("id") != image_id]
        save_json(DATA, data)
        print(f"  已从 {DATA.relative_to(REPO_ROOT)} 移除")

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
