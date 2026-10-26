#!/usr/bin/env python3
"""从出处文件生成页面上的「社区二创」分区。

社区作品有 140+ 件，手写 HTML 在这个量级必然失控。这里用生成器保证
「页面 == 出处文件 == 缩略图清单」三者永远一致。

数据来源
--------
* ``docs/community/_meta.json``  —— ``import_upstream.py`` 写出的逐图出处
  （标题 / 作者 / 来源 / 投稿 issue / 创作类型 / 尺寸 / 许可）
* ``docs/thumbs/_manifest.json`` —— ``make_thumbs.py`` 写出的档位清单

设计契约见 ``docs/design/community-redesign.md``：主轴按**内容类型**分流
（解决"角色内容太多"），副轴按**作者**分栏。

用法
----
    python tools/build_cards.py            # 生成/更新 docs/index.html
    python tools/build_cards.py --check    # 只检查是否已是最新（CI 用）
"""

from __future__ import annotations

import argparse
import hashlib
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

BEGIN_MARK = "<!-- BEGIN:community-section -->"
END_MARK = "<!-- END:community-section -->"

SECTION_START = '  <section class="part" id="p-gallery">' 

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

#: 内容类型（主轴）。判定顺序即优先级。
TYPE_META: dict[str, tuple[str, str]] = {
    # type: (显示名, 说明)
    "character": ("角色立绘", "单角色插画 / 立绘"),
    "meme": ("表情包", "梗图与表情包"),
    "sheet": ("设定图", "三视图与设定集"),
    "scene": ("场景壁纸", "背景与场景"),
}
TYPE_ORDER = ("character", "meme", "sheet", "scene")


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


# ---------------------------------------------------------------- 分类与配色


def classify_work(work: dict) -> str:
    """按 id 形态 → 标题关键词 → 宽高比判定内容类型。

    判定不了的一律归 ``character``（并在灯箱里标「未分类」），不做猜测。
    """
    work_id = work.get("id", "")
    title = work.get("title", "") or ""
    width = work.get("width") or 0
    height = work.get("height") or 0
    if work_id.startswith("meme") or re.search(r"表情包|梗图", title):
        return "meme"
    if re.search(r"三视图|设定图|character.?sheet", title, re.I):
        return "sheet"
    if re.search(r"壁纸|背景|场景", title):
        return "scene"
    if width and height and width / height > 1.5 and width >= 1200:
        return "scene"
    return "character"


def author_hue(author: str) -> int:
    """作者强调色的色相：作者名 md5 → 0..359，跨机器稳定。"""
    digest = hashlib.md5(author.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 360


def author_color(author: str) -> str:
    return f"hsl({author_hue(author)} 62% 66%)"


def sort_key(work: dict) -> tuple:
    issue = work.get("issue")
    return (0 if isinstance(issue, int) else 1, issue if isinstance(issue, int) else 0, work["id"])


# ---------------------------------------------------------------- 卡片生成


def build_card(work: dict, item: dict, author: str, work_type: str, solo: int = 0) -> str:
    files = item["files"]
    if not files:
        return ""
    # 兜底 src 取"不超过 960w 的最大档"（与 sync_srcset.py 的规则一致）
    fallback = files[0]
    for f in files:
        if f["w"] <= 960:
            fallback = f
    largest = files[-1]
    srcset = ", ".join(f'{f["path"]} {f["w"]}w' for f in files)
    width, height = work.get("width") or 0, work.get("height") or 0

    title = work.get("title") or work["id"]
    desc = work.get("creationType") or "社区作品"
    source = work.get("source") or ""
    issue_url = work.get("issueUrl") or ""
    license_ = work.get("license") or ""
    color = author_color(author)

    alt = f"{title}（作者：{author}）" if author != UNKNOWN_AUTHOR else title

    return f"""        <figure class="card" data-type="{esc(work_type)}" data-author="{esc(author)}" data-solo="{solo}" style="--ac:{color}">
        <a class="shot" href="{esc(work['file'])}" target="_blank" rel="noreferrer"
           data-full="{esc(largest['path'])}" data-orig="{esc(work['file'])}"
           data-title="{esc(title)}" data-desc="{esc(desc)}" data-author="{esc(author)}"
           data-size="{esc(f'{width}×{height}')}" data-source="{esc(source)}"
           data-issue="{esc(issue_url)}" data-license="{esc(license_)}"
           data-type-label="{esc(TYPE_META.get(work_type, (work_type, ''))[0])}"
           data-handmade="{'true' if work.get('handmade') else 'false'}">
          <img src="{esc(fallback['path'])}"
               srcset="{esc(srcset)}"
               sizes="{esc(SIZES_ATTR)}"
               width="{width}" height="{height}" alt="{esc(alt)}" loading="lazy" decoding="async" />
          <i class="tdot" data-t="{esc(work_type)}" title="{esc(TYPE_META.get(work_type, (work_type, ''))[0])}"></i>
        </a>
        <figcaption class="cap">
          <b>{esc(title)}</b><em class="by">{esc(author)}</em>
        </figcaption>
      </figure>"""


def build_cards(meta: dict, manifest: dict) -> tuple[dict[tuple[str, str], list[str]], list[dict]]:
    """返回 (按 (类型,作者) 分组的卡片 HTML, 作品列表)。"""
    by_src = {item["src"]: item for item in manifest["items"]}
    works = [w for w in meta.values() if w["id"] not in EXCLUDE_IDS]
    works.sort(key=sort_key)

    # 先做类型 × 作者聚合，才能知道哪些作者只贡献了 1 件（要进"署名卡墙"）
    prelim = []
    for work in works:
        if work["file"] not in by_src:
            continue
        prelim.append(
            {
                "work": work,
                "author": work.get("author") or UNKNOWN_AUTHOR,
                "type": work.get("type") or classify_work(work),
            }
        )
    per_author: dict[tuple[str, str], int] = {}
    for item in prelim:
        key = (item["type"], item["author"])
        per_author[key] = per_author.get(key, 0) + 1

    cards: dict[tuple[str, str], list[str]] = {}
    stats: list[dict] = []
    for item in prelim:
        work = item["work"]
        manifest_item = by_src.get(work["file"])
        if manifest_item is None:
            continue
        author = item["author"]
        work_type = item["type"]
        solo = 1 if per_author[(work_type, author)] == 1 else 0
        card = build_card(work, manifest_item, author, work_type, solo)
        if not card:
            continue
        cards.setdefault((work_type, author), []).append(card)
        stats.append(
            {
                "id": work["id"],
                "author": author,
                "title": work.get("title") or work["id"],
                "type": work_type,
                "issueUrl": work.get("issueUrl", ""),
            }
        )
    return cards, stats


# ---------------------------------------------------------------- 分区渲染


def group_works(stats: list[dict]) -> dict:
    """按类型 → 作者聚合。"""
    by_type: dict[str, list[dict]] = {t: [] for t in TYPE_ORDER}
    for item in stats:
        by_type.setdefault(item["type"], []).append(item)
    result = {}
    for work_type, items in by_type.items():
        by_author: dict[str, list[dict]] = {}
        for item in items:
            by_author.setdefault(item["author"], []).append(item)
        # 系列栏（≥2 件）按件数降序；署名卡（1 件）另行收集
        series = sorted(
            [a for a, items2 in by_author.items() if len(items2) >= 2],
            key=lambda a: (-len(by_author[a]), a),
        )
        solo = sorted([a for a, items2 in by_author.items() if len(items2) == 1], key=lambda a: a)
        result[work_type] = {
            "total": len(items),
            "authors": len(by_author),
            "series": [(a, by_author[a]) for a in series],
            "solo": [(a, by_author[a][0]) for a in solo],
        }
    return result


def render_author_view(groups: dict, cards: dict) -> str:
    """作者分栏视图：类型 → 作者系列栏 + 单件作者署名卡墙。

    卡片**静态地**写在各自的栏目里 —— 禁 JS 时这一屏就是完整可读的，
    不依赖脚本把卡片搬过来。
    """
    out: list[str] = []
    for work_type in TYPE_ORDER:
        group = groups.get(work_type)
        if not group:
            continue
        label = TYPE_META.get(work_type, (work_type, ""))[0]
        blocks: list[str] = []
        for author, items in group["series"]:
            color = author_color(author)
            issue = items[0].get("issueUrl", "")
            src = f' <a class="src" href="{esc(issue)}" target="_blank" rel="noreferrer">投稿 ↗</a>' if issue else ""
            blocks.append(
                f"""      <div class="author-row" data-author="{esc(author)}" data-type="{esc(work_type)}">
        <header class="author-h" style="--ac:{color}">
          <b>{esc(author)}</b><span class="n">{len(items)} 件</span>{src}
        </header>
        <div class="grid grid-author">
{chr(10).join(cards.get((work_type, author), []))}
        </div>
      </div>"""
            )
        if group["solo"]:
            blocks.append(
                f"""      <div class="solo-wall" data-type="{esc(work_type)}">
        <div class="solo-h">其他创作者（各 1 件）· {len(group['solo'])} 位</div>
        <div class="grid grid-solo">
{chr(10).join(x for a, _ in group['solo'] for x in cards.get((work_type, a), []))}
        </div>
      </div>"""
            )
        out.append(
            f"""    <section class="atype" data-type="{esc(work_type)}">
      <h3 class="atype-h"><i class="tdot" data-t="{esc(work_type)}"></i>{esc(label)}<span class="n">{group['total']} 件 · {group['authors']} 位创作者</span></h3>
{chr(10).join(blocks)}
    </section>"""
        )
    return "\n".join(out)


def render_section(cards: dict, stats: list[dict]) -> str:
    groups = group_works(stats)
    type_buttons = []
    for work_type in TYPE_ORDER:
        group = groups.get(work_type)
        if not group:
            continue
        label = TYPE_META.get(work_type, (work_type, ""))[0]
        type_buttons.append(
            f'        <button type="button" class="chip" data-type="{esc(work_type)}" aria-pressed="false">'
            f'<i class="tdot" data-t="{esc(work_type)}"></i>{esc(label)} {group["total"]}</button>'
        )
    total = len(stats)
    author_counts: dict[str, int] = {}
    for item in stats:
        author_counts[item["author"]] = author_counts.get(item["author"], 0) + 1
    author_options = "\n".join(
        f'          <option value="{esc(a)}">{esc(a)}（{c}）</option>'
        for a, c in sorted(author_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    )
    authors = len(author_counts)
    return f"""{BEGIN_MARK}
    <h2>四、社区二创<span class="count">{total} 张</span></h2>
    <p class="note">来自<a href="https://github.com/TreapGoGo/deepseek-whale-girl" target="_blank" rel="noreferrer">鲸鱼娘开源资产库</a>的社区画廊，
      共 {total} 件、{authors} 位创作者，逐图署名与出处见每张卡片。按内容类型分流，按作者分栏。</p>
    <div class="controls" hidden>
      <div class="seg" role="group" aria-label="浏览方式">
        <button type="button" class="seg-b on" data-view="author" aria-pressed="true">按作者分栏</button>
        <button type="button" class="seg-b" data-view="flat" aria-pressed="false">全部平铺</button>
      </div>
      <div class="chips" role="group" aria-label="内容类型">
        <button type="button" class="chip on" data-type="" aria-pressed="true">全部 {total}</button>
{chr(10).join(type_buttons)}
      </div>
      <label class="chk"><input type="checkbox" id="f-handmade" /> 仅看纯手工作品</label>
      <label class="srch">作者
        <select id="f-author">
          <option value="">全部（{total} 张）</option>
{author_options}
        </select>
      </label>
      <span class="filters-count" id="f-count">显示 {total} / {total} 张</span>
    </div>
    <div class="gallery-views">
      <div class="view view-author" id="view-author">
{render_author_view(groups, cards)}
      </div>
      <div class="view view-flat" id="view-flat" hidden>
        <div class="grid grid-flat"></div>
      </div>
    </div>
{END_MARK}"""


def main() -> int:
    parser = argparse.ArgumentParser(description="生成社区二创分区")
    parser.add_argument("--check", action="store_true", help="只检查，不修改（不一致时退出码 1）")
    args = parser.parse_args()

    if not PAGE.exists():
        sys.exit(f"缺少页面: {PAGE}")
    if not META_PATH.exists():
        sys.exit(f"缺少 {META_PATH}，请先运行 python tools/import_upstream.py")
    if not MANIFEST_PATH.exists():
        sys.exit(f"缺少 {MANIFEST_PATH}，请先运行 python tools/make_thumbs.py")

    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    works = meta["works"]
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    # 分类结果写回出处文件（已存在则保留人工修正过的值）
    changed = False
    for work in works.values():
        computed = classify_work(work)
        if work.get("type") != computed:
            if "type" in work:
                continue  # 人工改过，尊重它
            work["type"] = computed
            changed = True
    if changed:
        META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    cards, stats = build_cards(works, manifest)
    section = render_section(cards, stats)

    document = PAGE.read_text(encoding="utf-8")
    if BEGIN_MARK not in document or END_MARK not in document:
        sys.exit(f"页面里找不到 {BEGIN_MARK} / {END_MARK} 标记")
    start = document.index(BEGIN_MARK)
    end = document.index(END_MARK) + len(END_MARK)
    new_document = document[:start] + section + document[end:]

    if new_document == document:
        print(f"社区分区已是最新（{len(stats)} 件）✓")
        return 0
    if args.check:
        print(f"::error::页面里的社区分区与出处文件不一致（应为 {len(stats)} 件），请运行 python tools/build_cards.py")
        return 1
    PAGE.write_text(new_document, encoding="utf-8")
    print(f"已更新 {PAGE.relative_to(REPO_ROOT)}：社区二创 {len(stats)} 件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
