#!/usr/bin/env python3
"""一次性迁移工具：把 index.html 里手写的 4 个静态分区反向提取成数据源。

背景
----
画廊最早只有「社区二创」一个分区是数据驱动的（``docs/community/_meta.json``
→ ``build_cards.py`` → 写进页面）。另外 4 个分区（角色设定图 / 萌娘百科 /
换装三视图 / 壁纸）的图块是直接手写在 HTML 里的 —— 加一张图要手抄
``<figure>``、``srcset``、``data-full``、宽高、``alt``，漏一个属性就是一处
不一致。

本脚本把历史手写内容抽成 ``docs/_gallery.json``，之后由 ``tools/render.py``
统一渲染、由 ``tools/gallery.py`` 提供增删命令。

**只在首次迁移时用一次**，日常增删图片不需要它。

用法::

    python tools/extract_static.py            # 预览，不写文件
    python tools/extract_static.py --write    # 写入 docs/_gallery.json
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
OUT = DOCS_DIR / "_gallery.json"

STATIC_KEYS = ("sheets", "moegirl", "refs", "wallpaper")

SECTION_RE = re.compile(
    r'  <section class="part" id="p-(?P<key>' + "|".join(STATIC_KEYS) + r')">\n'
    r'    <h2>(?P<heading>.*?)<span class="count">(?P<count>.*?)</span></h2>\n'
    r'    <p class="note">(?P<note>.*?)</p>\n'
    r'    <div class="grid">\n(?P<body>.*?)    </div>\n'
    r'  </section>',
    re.S,
)
FIGURE_RE = re.compile(r'<figure class="card">(?P<body>.*?)</figure>', re.S)
SHOT_RE = re.compile(r'<a class="shot"(?P<attrs>[^>]*)>(?P<inner>.*?)</a>', re.S)
IMG_RE = re.compile(r"<img\b(?P<attrs>[^>]*?)/>", re.S)
CAPTION_RE = re.compile(
    r"<b>(?P<title>.*?)</b><span>(?P<desc>.*?)</span><em>(?P<author>.*?)</em>", re.S
)
LINK_RE = re.compile(r'<a class="il" href="(?P<href>[^"]*)"[^>]*>(?P<label>.*?)</a>', re.S)
ATTR_RE = re.compile(r'(?P<name>[\w-]+)="(?P<value>[^"]*)"')


def attrs_of(fragment: str) -> dict[str, str]:
    return {m.group("name"): m.group("value") for m in ATTR_RE.finditer(fragment)}


def extract_items(body: str) -> list[dict]:
    items: list[dict] = []
    for fig in FIGURE_RE.finditer(body):
        fbody = fig.group("body")

        shot = SHOT_RE.search(fbody)
        if not shot:
            continue
        a_attrs = attrs_of(shot.group("attrs"))
        img = IMG_RE.search(shot.group("inner"))
        if not img:
            continue
        i_attrs = attrs_of(img.group("attrs"))

        cap = CAPTION_RE.search(fbody)
        if not cap:
            continue

        orig = a_attrs.get("data-orig") or shot.group("attrs")
        links = [
            {"href": html.unescape(m.group("href")), "label": html.unescape(m.group("label").strip())}
            for m in LINK_RE.finditer(fbody)
        ]

        item = {
            "id": Path(orig).stem,
            "orig": orig,
            "width": int(i_attrs.get("width", "0")),
            "height": int(i_attrs.get("height", "0")),
            # 卡片上显示的文本（<b>/<span>/<em>）
            "title": html.unescape(cap.group("title").strip()),
            "desc": html.unescape(cap.group("desc").strip()),
            "author": html.unescape(cap.group("author").strip()),
            "alt": html.unescape(i_attrs.get("alt", "")),
            "links": links,
        }
        # 灯箱/筛选用的机器可读元数据（data-*）。多数与显示文本一致，
        # 但历史上手写时有过简写版（例如作者「AI 萌图 · 三视图设定集」vs
        # 「AI 萌图 · 大肥鱼娘三视图设定集」），不一致时单独记一份。
        for key, attr in (
            ("dataTitle", "data-title"),
            ("dataDesc", "data-desc"),
            ("dataAuthor", "data-author"),
        ):
            raw = a_attrs.get(attr)
            if raw is None:
                continue
            value = html.unescape(raw.strip())
            if value != item[{"dataTitle": "title", "dataDesc": "desc", "dataAuthor": "author"}[key]]:
                item[key] = value
        items.append(item)
    return items


def main() -> int:
    ap = argparse.ArgumentParser(description="从 index.html 提取静态分区成数据源")
    ap.add_argument("--write", action="store_true", help="写入 docs/_gallery.json")
    args = ap.parse_args()

    document = PAGE.read_text(encoding="utf-8")
    sections: dict[str, dict] = {}

    for m in SECTION_RE.finditer(document):
        key = m.group("key")
        items = extract_items(m.group("body"))
        sections[key] = {
            "anchor": f"p-{key}",
            "heading": html.unescape(m.group("heading").strip()),
            "note": html.unescape(m.group("note").strip()),
            "items": items,
        }
        print(f"  {key:10s} {len(items):>3d} 张  {m.group('heading').strip()}")

    missing = [k for k in STATIC_KEYS if k not in sections]
    if missing:
        print(f"::error::页面里没找到分区：{missing}", file=sys.stderr)
        return 1

    total = sum(len(s["items"]) for s in sections.values())
    print(f"合计 {total} 张静态分区图")

    data = {"version": 1, "sections": sections}
    if args.write:
        OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"已写入 {OUT.relative_to(REPO_ROOT)}")
    else:
        print("（预览模式，加 --write 才写文件）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
