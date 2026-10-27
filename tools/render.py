#!/usr/bin/env python3
"""从数据源渲染 index.html 里的 4 个静态分区。

背景
----
「社区二创」分区本来就是数据驱动的（``docs/community/_meta.json`` →
``build_cards.py``）。另外 4 个分区（角色设定图 / 萌娘百科 / 换装三视图 /
壁纸）原先是手写在 HTML 里的 —— 增删一张图要手抄 ``<figure>``、``srcset``、
``data-full``、宽高、``alt``，漏一个属性就是一处不一致。

本脚本把这 4 个分区也变成数据源驱动：

    docs/_gallery.json  +  docs/thumbs/_manifest.json  →  docs/index.html

``_gallery.json`` 只存元数据（标题、描述、作者、链接），缩略图档位一律
从 ``_manifest.json`` 算，与 ``sync_srcset.py`` 用的是同一套规则：

* ``src``       —— 不超过 960w 的最大档（没有则取最大档）
* ``srcset``    —— 全部档位
* ``data-full`` —— 最高档（灯箱大图）

渲染出来的仍是纯静态 HTML：零外部请求、关掉 JS 也能完整浏览。

用法::

    python tools/render.py           # 就地更新 docs/index.html
    python tools/render.py --check   # 只检查不修改（有差异时退出码 1）
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
DOCS_DIR = REPO_ROOT / "docs"
PAGE = DOCS_DIR / "index.html"
DATA = DOCS_DIR / "_gallery.json"
MANIFEST = DOCS_DIR / "thumbs" / "_manifest.json"

#: 兜底 src 选用的目标宽度（与 sync_srcset.py 保持一致）
FALLBACK_WIDTH = 960

#: 所有图块共用的 sizes 表达式
SIZES = (
    "(max-width:560px) calc(100vw - 36px), (max-width:693px) calc(50vw - 25px), "
    "(max-width:1101px) calc(33.33vw - 22px), (max-width:1320px) calc(25vw - 25.5px), 305px"
)

SECTION_TEMPLATE = """  <section class="part" id="{anchor}">
    <h2>{heading}<span class="count">{count}</span></h2>
    <p class="note">{note}</p>
    <div class="grid">
{items}    </div>
  </section>"""

CARD_TEMPLATE = """      <figure class="card">
        <a class="shot" href="{orig}" target="_blank" rel="noreferrer"
           data-full="{data_full}"
           data-orig="{orig}"
           data-title="{data_title}"
           data-desc="{data_desc}"
           data-author="{data_author}"
           data-size="{width}×{height}">
          <img src="{src}"
               srcset="{srcset}"
               sizes="{sizes}"
               width="{width}" height="{height}" alt="{alt}" loading="lazy" decoding="async" />
        </a>
        <figcaption class="cap">
          <b>{title}</b><span>{desc}</span><em>{author}</em>
          <div class="links">{links}</div>
        </figcaption>
      </figure>"""


def esc(value: str) -> str:
    return html.escape(value or "", quote=True)


def load_data() -> dict:
    if not DATA.exists():
        sys.exit(f"找不到 {DATA}，请先运行 python tools/extract_static.py --write")
    return json.loads(DATA.read_text(encoding="utf-8"))


def load_manifest() -> dict[str, dict]:
    if not MANIFEST.exists():
        sys.exit(f"找不到 {MANIFEST}，请先运行 python tools/make_thumbs.py")
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {item["src"]: item for item in data["items"]}


def render_links(links: list[dict], orig: str) -> str:
    """渲染 figcaption 里的链接区；没有链接时给一个「原图」兜底。"""
    if not links:
        links = [{"href": orig, "label": "原图"}]
    out: list[str] = []
    for i, link in enumerate(links):
        prefix = "" if i == 0 else "\n            "
        out.append(
            f'{prefix}<a class="il" href="{esc(link["href"])}" target="_blank" '
            f'rel="noreferrer">{esc(link["label"])}</a>'
        )
    return "".join(out)


def render_card(item: dict, manifest: dict[str, dict]) -> str:
    orig = item["orig"]
    entry = manifest.get(orig)
    if entry is None:
        raise KeyError(
            f"缩略图清单里没有 {orig}，请先运行 python tools/make_thumbs.py 生成缩略图"
        )

    files = entry["files"]
    widths = [f["w"] for f in files]
    fallback = next((w for w in reversed(widths) if w <= FALLBACK_WIDTH), widths[-1])
    src = next(f["path"] for f in files if f["w"] == fallback)
    data_full = files[-1]["path"]
    srcset = ", ".join(f"{f['path']} {f['w']}w" for f in files)

    width = item.get("width") or entry.get("origW") or 0
    height = item.get("height") or entry.get("origH") or 0

    title = item.get("title", "")
    desc = item.get("desc", "")
    author = item.get("author", "")

    return CARD_TEMPLATE.format(
        orig=esc(orig),
        data_full=esc(data_full),
        src=esc(src),
        srcset=esc(srcset),
        sizes=SIZES,
        width=width,
        height=height,
        title=esc(title),
        desc=esc(desc),
        author=esc(author),
        data_title=esc(item.get("dataTitle", title)),
        data_desc=esc(item.get("dataDesc", desc)),
        data_author=esc(item.get("dataAuthor", author)),
        alt=esc(item.get("alt") or title),
        links=render_links(item.get("links", []), orig),
    )


def render_section(section: dict, manifest: dict[str, dict]) -> str:
    items = section.get("items", [])
    cards = "\n".join(render_card(item, manifest) for item in items)
    count = section.get("count") or f"{len(items)} 张"
    heading = section.get("heading", "").replace("{n}", str(len(items)))
    return SECTION_TEMPLATE.format(
        anchor=section["anchor"],
        heading=esc(heading),
        count=esc(count),
        note=esc(section.get("note", "")),
        items=(cards + "\n") if cards else "",
    )


def apply_sections(document: str, data: dict, manifest: dict[str, dict]) -> tuple[str, list[str]]:
    """按分区 id 替换整段 <section class="part">。"""
    changes: list[str] = []
    for key, section in data["sections"].items():
        anchor = section["anchor"]
        pattern = re.compile(
            r'  <section class="part" id="' + re.escape(anchor) + r'">.*?\n  </section>',
            re.S,
        )
        if not pattern.search(document):
            raise KeyError(f"页面里找不到分区 {anchor}")
        new_html = pattern.sub(lambda _: render_section(section, manifest), document, count=1)
        if new_html != document:
            changes.append(f"{key}: 已重渲染 {len(section.get('items', []))} 张")
            document = new_html
    return document, changes


#: README 统计表里各行对应的分区 key
README_ROWS = {
    "角色设定图": "sheets",
    "萌娘百科收录图": "moegirl",
    "换装三视图": "refs",
    "社区二创全集": "community",
    "场景壁纸": "wallpaper",
}


def counts(data: dict, community_count: int) -> dict[str, int]:
    """各分区的图数。"""
    result = {key: len(s.get("items", [])) for key, s in data["sections"].items()}
    result["community"] = community_count
    return result


def update_stats(document: str, data: dict, manifest: dict[str, dict], community_count: int) -> tuple[str, list[str]]:
    """同步页面顶部的总图数，以及 README 统计表里的数字。"""
    changes: list[str] = []
    tally = counts(data, community_count)
    total = sum(tally.values())

    # 页面顶部：<b id="stat-count">165</b>
    def replace_count(match: re.Match[str]) -> str:
        old = match.group(1)
        if old != str(total):
            changes.append(f"页面总图数 {old} → {total}")
        return f'<b id="stat-count">{total}</b>'

    document = re.sub(r'<b id="stat-count">(\d+)</b>', replace_count, document)

    # README 统计表
    readme_path = REPO_ROOT / "README.md"
    if readme_path.exists():
        readme = readme_path.read_text(encoding="utf-8")
        orig_bytes = sum(item.get("origBytes", 0) for item in manifest.values())

        for label, key in README_ROWS.items():
            if key not in tally:
                continue
            pattern = re.compile(r"(\| " + re.escape(label) + r" \| )(\d+)( \|)")

            def sub_row(m: re.Match[str]) -> str:
                new = str(tally[key])
                if m.group(2) != new:
                    changes.append(f"README {label} {m.group(2)} → {new}")
                return f"{m.group(1)}{new}{m.group(3)}"

            readme = pattern.sub(sub_row, readme, count=1)

        def sub_total(m: re.Match[str]) -> str:
            new = str(total)
            if m.group(1) != new:
                changes.append(f"README 合计 {m.group(1)} → {new}")
            return f"| **合计** | **{new}** |"

        readme = re.sub(r"\| \*\*合计\*\* \| \*\*(\d+)\*\* \|", sub_total, readme, count=1)
        readme = re.sub(
            r"原图 ([\d.]+) MB",
            f"原图 {orig_bytes / 1024 / 1024:.1f} MB",
            readme,
        )
        if readme != readme_path.read_text(encoding="utf-8"):
            readme_path.write_text(readme, encoding="utf-8")

    return document, changes


def community_count() -> int:
    """社区分区的图数（数据源是 docs/community/_meta.json）。"""
    meta = DOCS_DIR / "community" / "_meta.json"
    if not meta.exists():
        return 0
    return len(json.loads(meta.read_text(encoding="utf-8")).get("works", {}))


def main() -> int:
    parser = argparse.ArgumentParser(description="从数据源渲染静态分区")
    parser.add_argument("--check", action="store_true", help="只检查不修改，有差异时退出码 1")
    args = parser.parse_args()

    document = PAGE.read_text(encoding="utf-8")
    data = load_data()
    manifest = load_manifest()

    try:
        new_document, changes = apply_sections(document, data, manifest)
        new_document, stat_changes = update_stats(
            new_document, data, manifest, community_count()
        )
        changes += stat_changes
    except KeyError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    if not changes:
        print("静态分区已是最新 ✓")
        return 0
    if args.check:
        for c in changes:
            print(f"::error::{c}，请运行 python tools/render.py")
        return 1

    PAGE.write_text(new_document, encoding="utf-8")
    for c in changes:
        print(f"已更新 {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
