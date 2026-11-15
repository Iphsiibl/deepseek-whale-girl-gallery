# 大肥鱼画廊 · 协作约定（AGENTS.md）

这个仓库的页面是**数据源驱动**的：不要手改 `docs/index.html`，改数据源后跑管线重生成。

## 目录速查

| 路径 | 作用 |
| --- | --- |
| `docs/index.html` | 唯一页面（CSS/JS 全内联），由 `tools/render.py` + `tools/build_cards.py` 生成 |
| `docs/_gallery.json` | 角色设定图 / 萌娘百科 / 换装三视图 / 壁纸 四个静态分区的数据源 |
| `docs/community/_meta.json` | 社区二创的元数据（键 `works`） |
| `docs/thumbs/_manifest.json` | 缩略图清单（由 `tools/make_thumbs.py` 生成） |
| `tools/` | 管线与工具：`gallery.py`（CLI）、`admin.py`（管理台）、`imageopt.py`（压缩）、`import_upstream.py`、`render.py`、`build_cards.py`、`make_thumbs.py`、`check_gallery.py`、`verify_browser.py` |
| `docs/` | GitHub Pages 根目录 |

## 常用命令

```bash
python tools/admin.py                 # 本地管理台 http://127.0.0.1:8765
python tools/gallery.py sync          # 全量重建：缩略图 → 卡片 → 页面 → 署名表 → 校验
python tools/gallery.py add <文件> --section community --title "标题" --author "作者"
python tools/gallery.py remove <id> --section community
python tools/verify_browser.py        # 浏览器端验证（需 playwright）
```

改完内容后必须跑通：`check_gallery.py`、`render.py --check`、`build_cards.py --check`、
`build_attribution.py --check`、`sync_srcset.py --check`、`verify_browser.py`。

## 约定

- **改完自动推**：每次改完代码/内容，先跑上面那套校验，再 `git add -A && git commit && git push origin main`，
  不需要用户再确认；推完把 GitHub Actions 的结果一起报给用户。
- 新图**入库即压缩**（`tools/imageopt.py`：长边 2560 · WebP q82），再生成 480/960/1440/1920 四档展示图。
- 图片版权归各自作者，许可以源站标注为准；`ATTRIBUTION.md` 由 `tools/build_attribution.py` 自动生成，不要手改。
- 不要把临时脚本、截图、暂存目录提交进仓库（`.gitignore` 已覆盖 `.tmp_*`、`.shots/`、`.staging/`、`.deliverables/`）。
