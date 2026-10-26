#!/usr/bin/env python3
"""从出处文件生成 ATTRIBUTION.md 里的「社区二创全集」署名表。

CC BY 要求**逐图署名**，且署名要能随作品一起看到（页面卡片上已有作者行，
这里负责仓库内的完整台账）。手抄 140+ 行既慢又易错，用生成器保证与
`docs/community/_meta.json` 永远一致。

用法
----
    python tools/build_attribution.py           # 更新 ATTRIBUTION.md
    python tools/build_attribution.py --check   # 只检查（CI 用）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
DOCS_DIR = REPO_ROOT / "docs"
META_PATH = DOCS_DIR / "community" / "_meta.json"
TARGET = REPO_ROOT / "ATTRIBUTION.md"

BEGIN_MARK = "<!-- BEGIN:community-table -->"
END_MARK = "<!-- END:community-table -->"

UNKNOWN_AUTHOR = "作者未知（上游未标注）"


def esc(value: object) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 ATTRIBUTION.md 的社区署名表")
    parser.add_argument("--check", action="store_true", help="只检查，不修改")
    args = parser.parse_args()

    if not META_PATH.exists():
        sys.exit(f"缺少 {META_PATH}，请先运行 python tools/import_upstream.py")
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    works = meta["works"]

    def key(w: dict) -> tuple:
        issue = w.get("issue")
        return (0 if isinstance(issue, int) else 1, issue if isinstance(issue, int) else 0, w["id"])

    rows = []
    for work in sorted(works.values(), key=key):
        author = work.get("author") or UNKNOWN_AUTHOR
        title = esc(work.get("title") or work["id"])
        issue = work.get("issue")
        issue_link = (
            f"[#{issue}]({work['issueUrl']})" if work.get("issueUrl") else (f"#{issue}" if issue else "—")
        )
        source = esc(work.get("source") or "—")
        creation = esc(work.get("creationType") or "—")
        license_ = esc(work.get("license") or "")
        handmade = "手作" if work.get("handmade") else "AI/未标注"
        file_name = esc(work.get("file") or work["id"])
        rows.append(
            f"| `{file_name}` | {title} | {esc(author)} | {issue_link} | {creation} · {handmade} | "
            f"{source}{(' · ' + license_) if license_ else ''} |"
        )

    table = "\n".join(
        [
            BEGIN_MARK,
            "",
            f"共 {len(rows)} 件，来自 [鲸鱼娘开源资产库 · 社区画廊]"
            "(https://github.com/TreapGoGo/deepseek-whale-girl)（作品各自授权，"
            "上游明确声明「收录不把图片变成 MIT 素材」）。",
            "上游未标注作者的作品如实记为「作者未知（上游未标注）」，不做推测。",
            "",
            "| 文件 | 作品 | 作者 | 投稿 | 创作类型 | 来源 / 许可 |",
            "| --- | --- | --- | --- | --- | --- |",
            *rows,
            "",
            END_MARK,
        ]
    )

    if not TARGET.exists():
        sys.exit(f"缺少 {TARGET}")
    document = TARGET.read_text(encoding="utf-8")
    if BEGIN_MARK not in document or END_MARK not in document:
        sys.exit(f"{TARGET.name} 里找不到 {BEGIN_MARK} / {END_MARK} 标记")
    start = document.index(BEGIN_MARK)
    end = document.index(END_MARK) + len(END_MARK)
    new_document = document[:start] + table + document[end:]

    if new_document == document:
        print(f"ATTRIBUTION.md 已是最新（{len(rows)} 条）✓")
        return 0
    if args.check:
        print(f"::error::ATTRIBUTION.md 与出处文件不一致（应为 {len(rows)} 条），请运行 python tools/build_attribution.py")
        return 1
    TARGET.write_text(new_document, encoding="utf-8")
    print(f"已更新 {TARGET.name}：{len(rows)} 条社区署名")
    return 0


if __name__ == "__main__":
    sys.exit(main())
