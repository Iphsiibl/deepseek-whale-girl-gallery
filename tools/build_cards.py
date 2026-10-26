#!/usr/bin/env python3
"""从出处文件生成页面上的「社区二创」卡片。

社区作品有 140+ 件，手写 HTML 不现实也容易出错。这里用生成器保证
「页面 == 出处文件 == 缩略图清单」三者永远一致。

数据来源
--------
* ``docs/community/_meta.json``  —— ``import_upstream.py`` 写出的逐图出处
  （标题 / 作者 / 来源 / 投稿 issue / 创作类型 / 尺寸 / 许可）
* ``docs/thumbs/_manifest.json`` —— ``make_thumbs.py`` 写出的档位清单

用法
----
    python tools/build_cards.py            # 生成/更新 docs/index.html
    python tools/build_cards.py --check    # 只检查是否已是最新（CI 用）
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
META_PATH = DOCS_DIR / "community" / "_meta.json"
MANIFEST_PATH = DOCS_DIR / "thumbs" / "_manifest.json"

BEGIN_MARK = "<!-- BEGIN:community-cards -->"
END_MARK = "<!-- END:community-cards -->"

#: 排除项：上游的这张是本站「萌娘百科」原立绘的**低分辨率副本**（750×1344
#: vs 本站 1152×2048），展示低清版会拉低画质，保留本站高清版即可。
EXCLUDE_IDS: dict[str, str] = {
    "community-2026-09-29": "本站 moegirl/02-nvpu-whale-girl.png 为同一作品的高清版，不重复收录",
}

#: 与页面其它卡片一致的 sizes 声明（列宽随断点变化，见 TUTORIAL §5.2）
SIZES_ATTR = (
    "(max-width:560px) calc(100vw - 36px), (max-width:693px) calc(50vw - 25px), "
    "(max-width:1101px) calc(33.33vw - 22px), (max-width:1320px) calc(25vw - 25.5px), 305px"
)

UNKNOWN_AUTHOR = "作者未知（上游未标注）"


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def load_sources() -> tuple[dict, dict]:
    if not META_PATH.exists():
        sys.exit(f"缺少 {META_PATH}，请先运行 python tools/import_upstream.py")
    if not MANIFEST_PATH.exists():
        sys.exit(f"缺少 {MANIFEST_PATH}，请先运行 python tools/make_thumbs.py")
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))["works"]
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return meta, manifest


def sort_key(work: dict) -> tuple:
    issue = work.get("issue")
    return (0 if isinstance(issue, int) else 1, issue if isinstance(issue, int) else 0, work["id"])


def build_cards(meta: dict, manifest: dict) -> tuple[str, list[dict]]:
    by_src = {item["src"]: item for item in manifest["items"]}
    works = [w for w in meta.values() if w["id"] not in EXCLUDE_IDS]
    works.sort(key=sort_key)

    cards: list[str] = []
    stats: list[dict] = []
    for work in works:
        item = by_src.get(work["file"])
        if item is None:
            continue
        files = item["files"]
        if not files:
            continue
        # 兜底 src 取"不超过 960w 的最大档"（与 sync_srcset.py 的规则一致）
        fallback = files[0]
        for f in files:
            if f["w"] <= 960:
                fallback = f
        largest = files[-1]
        srcset = ", ".join(f'{f["path"]} {f["w"]}w' for f in files)
        width, height = work.get("width") or 0, work.get("height") or 0

        author = work.get("author") or UNKNOWN_AUTHOR
        title = work.get("title") or work["id"]
        desc = work.get("creationType") or "社区作品"
        source = work.get("source") or ""
        issue_url = work.get("issueUrl") or ""
        license_ = work.get("license") or ""

        alt = f"{title}（作者：{author}）" if author != UNKNOWN_AUTHOR else title

        card = f"""      <figure class="card">
        <a class="shot" href="{esc(work['file'])}" target="_blank" rel="noreferrer"
           data-full="{esc(largest['path'])}" data-orig="{esc(work['file'])}"
           data-title="{esc(title)}" data-desc="{esc(desc)}" data-author="{esc(author)}"
           data-size="{esc(f'{width}×{height}')}" data-source="{esc(source)}"
           data-issue="{esc(issue_url)}" data-license="{esc(license_)}"
           data-handmade="{'true' if work.get('handmade') else 'false'}">
          <img src="{esc(fallback['path'])}"
               srcset="{esc(srcset)}"
               sizes="{esc(SIZES_ATTR)}"
               width="{width}" height="{height}" alt="{esc(alt)}" loading="lazy" decoding="async" />
        </a>
        <figcaption class="cap">
          <b>{esc(title)}</b><span>{esc(desc)}</span><em>{esc(author)}</em>
          <div class="links"><a class="il" href="{esc(work['file'])}" target="_blank" rel="noreferrer">原图</a>
            {f'<a class="il" href="{esc(issue_url)}" target="_blank" rel="noreferrer">投稿 #{esc(work["issue"])} ↗</a>' if issue_url else ''}</div>
        </figcaption>
      </figure>"""
        cards.append(card)
        stats.append({"id": work["id"], "author": author, "title": title})
    return "\n".join(cards), stats


def render_section(cards_html: str, stats: list[dict]) -> str:
    authors: dict[str, int] = {}
    for item in stats:
        authors[item["author"]] = authors.get(item["author"], 0) + 1
    options = "\n".join(
        f'            <option value="{esc(a)}">{esc(a)}（{c}）</option>'
        for a, c in sorted(authors.items(), key=lambda kv: (-kv[1], kv[0]))
    )
    return f"""  <section class="part" id="p-gallery">
    <h2>四、社区二创全集<span class="count">{len(stats)} 张</span></h2>
    <p class="note">来自<a href="https://github.com/TreapGoGo/deepseek-whale-girl" target="_blank" rel="noreferrer">鲸鱼娘开源资产库</a>的社区画廊，
      逐图署名与出处见每张卡片；筛选作者可快速定位某位画师的作品。</p>
    <div class="filters" hidden>
      <label for="f-author">作者</label>
      <select id="f-author">
        <option value="">全部（{len(stats)} 张）</option>
{options}
      </select>
      <label class="chk"><input type="checkbox" id="f-handmade" /> 仅看纯手工作品</label>
      <span class="filters-count" id="f-count">显示 {len(stats)} / {len(stats)} 张</span>
    </div>
    <div class="grid">
{BEGIN_MARK}
{cards_html}
{END_MARK}
    </div>
  </section>"""


SECTION_START = '  <section class="part" id="p-gallery">'
SECTION_END = "</section>"


def main() -> int:
    parser = argparse.ArgumentParser(description="生成社区二创卡片")
    parser.add_argument("--check", action="store_true", help="只检查，不修改（不一致时退出码 1）")
    args = parser.parse_args()

    if not PAGE.exists():
        sys.exit(f"缺少页面: {PAGE}")
    meta, manifest = load_sources()
    cards_html, stats = build_cards(meta, manifest)
    section = render_section(cards_html, stats)

    document = PAGE.read_text(encoding="utf-8")
    if BEGIN_MARK not in document or END_MARK not in document:
        sys.exit(f"页面里找不到 {BEGIN_MARK} / {END_MARK} 标记")
    if SECTION_START not in document:
        sys.exit(f"页面里找不到分区起始标记 {SECTION_START!r}")
    start = document.index(SECTION_START)
    end = document.index(SECTION_END, start) + len(SECTION_END)
    new_document = document[:start] + section + document[end:]

    if new_document == document:
        print(f"社区卡片已是最新（{len(stats)} 张）✓")
        return 0
    if args.check:
        print(f"::error::页面里的社区卡片与出处文件不一致（应为 {len(stats)} 张），请运行 python tools/build_cards.py")
        return 1
    PAGE.write_text(new_document, encoding="utf-8")
    print(f"已更新 {PAGE.relative_to(REPO_ROOT)}：社区二创 {len(stats)} 张")
    return 0


if __name__ == "__main__":
    sys.exit(main())
