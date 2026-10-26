# 静态图集项目 · 独立审计报告

审计人：Verifier（独立审计，未参与实现）
审计日期：2026-10-23（初审） / 2026-10-24（复审，见 §1.5）
审计对象：`/workspace/gallery` 工作区未提交改动（`git diff HEAD` + 未跟踪文件）
方法：自建检查脚本 + 真实 Chromium（Playwright）实跑 + 变异测试 + 产物重生成比对

> **本报告有三次结论**：§1 起的正文是 **2026-10-23 初审**（基线见 §0），
> **§1.5 是 2026-10-24 对提交 `bf87e52` 的复审**，**§1.6 是复审后追加的 CI 缺陷（我的初审漏项）**，
> **§1.7 是 2026-10-26 画廊扩容（31 → 165 张）与画质升级后的复审**。
> 最终结论 = **PASS**（详见 §1.5 修复验收表、§1.6 追加发现、§1.7 扩容复审）。

---

## 0. 审计基线（revision）

本报告所有结论针对下面这组文件哈希。**审计期间仓库仍在被生产者修改**（`docs/index.html` 最后一次改动在
23:46:46，`tools/verify_browser.py` 在 23:47:17），审计开始时（23:31）`tools/sync_srcset.py` 甚至还不存在、
`make_thumbs.py` 的 alpha 逻辑还是死代码。以下问题清单是针对下面这版状态复现的；若后续再改动需重新核对。

```
c1802b78b680  docs/index.html
f73b008c4cba  tools/make_thumbs.py
370264627906  tools/check_gallery.py
29f6b68435b8  tools/sync_srcset.py
b237ce622935  tools/verify_browser.py
53ff195210fc  README.md
60a2e6b997e8  TUTORIAL.md
3cd0115cd143  .github/workflows/verify.yml
6217a4a9c588  docs/thumbs/_manifest.json
```

审计期间**未修改**仓库中除本文件（`AUDIT_REPORT.md`）以外的任何文件。所有实验都在
`/tmp/mut`、`/tmp/gcopy`、`/tmp/oldgallery` 的副本里做，截图在 `/workspace/audit-shots/`。

---

## 1. 总体结论

> **初审（2026-10-23，基线 = §0 的 sha256）：VERDICT: FAIL** —— 6 个「重要」级缺陷，无崩溃级/阻断级缺陷。
>
> **复审（2026-10-24，commit `bf87e52`）：VERDICT: PASS** —— 6 个「重要」项**全部已修并经我复验**，
> 9 个「次要」项中 8 个已修，4 个「建议」项中 3 个已修。详见 **§1.5 复审**。

初审理由：核心功能链路完全可用、且比原版好得多（下方「通过项」列了 30 多条实测证据），但仍存在 6 个
「重要」级缺陷，其中 **重要-1 是许可表述的事实性错误**（把 3 张 MIT 壁纸说成 CC BY-NC-SA 4.0）——
对于一个以"合规署名"为卖点的 CC 仓库，这一条必须修；**重要-3 是教程在教一个已证实的 bug**
（`sizes` 旧公式会让 561–693px 视口 2x 屏的 15/31 张图选到过小档位），属于"承诺了但没实现/教错了"；
**重要-2 / 4 / 5 / 6** 是死功能、残缺功能、校验盲区与 CI 误报风险。

核心链路（缩略图分档 → srcset 选档 → 瀑布流 → 灯箱）实测是通的、可复现的：

- 31 张原图 → 81 个缩略图文件，**档位选择 100% 正确**，`srcset` 声明宽度与文件实际宽度 **0 处不符**，
  **0 个孤儿文件**、**0 个缺失文件**；
- `make_thumbs.py --clean` 重生成后，81 个 WebP **逐字节一致**，manifest 也一致（可复现构建成立）；
- 瀑布流在 15 个视口宽度下**无重叠、无横向溢出**，1440→390→1440 往返重排正常；
- 灯箱的**首/末张环绕、Home/End、反复开关、焦点进出、滚动锁定**全部实测正确；
- 首屏下载量从旧版 3.3 MB 降到 859 KB（−74%），**README 里的数字与我的独立实测完全一致**；
- 页面**零控制台报错、零失败请求**，禁用 JS 后 31 张图照常渲染并能点开原图；
- 没有引入任何 XSS 面（无 `innerHTML` / `eval` / `document.write`，所有动态写入走 `textContent` / `setAttribute`）。

遗留问题集中在三类：**① 许可表述自相矛盾（重要）；② 若干"看起来有、其实不工作"的功能（重要/次要）；
③ 校验脚本与 CI 存在盲区（重要/次要）**。都不影响页面正常浏览，但其中许可那条在 CC 仓库上属于
必须修的合规问题。

**问题统计：阻断 0 · 重要 6 · 次要 9 · 建议 4**

（审计期间生产者仍在修改仓库，本报告的 6 个「重要」问题中有 3 个（灯箱焦点、`sizes` 公式、
`sync_srcset.py` 缺失）**是在审计过程中被作者修掉的**；报告按 §0 的最终哈希复现，列出的都是
**当前这一版仍然存在**的问题。）

---

## 1.5 复审（2026-10-24，commit `bf87e52`）

初审后生产者继续修复并提交（`bf87e5299a8882e1712d946b177b6807a5177ce8`，2026-10-24 00:01:55，
分支 `optimize/gallery-v2`）。我对**提交后的这棵树**重新复验，结论如下。

复审基线 sha256-12：

```
9e859fbf4785  docs/index.html
d41eef48812a  tools/make_thumbs.py
70720701fa33  tools/check_gallery.py
022d89066424  tools/check_manifest.py   (新增)
29f6b68435b8  tools/sync_srcset.py
ffcfe23bad4a  tools/verify_browser.py
c159a3a013b7  README.md
31982b1063b4  TUTORIAL.md
0d2d79e2d0c9  .github/workflows/verify.yml
```

### 修复验收表

| 原编号 | 问题 | 状态 | 复验证据 |
| --- | --- | --- | --- |
| 重要-1 | 页脚把 MIT 壁纸说成 CC BY-NC-SA | ✅ 已修 | `docs/index.html:645-648` 改为「许可与各图原图一致：**整体角色形象为 CC BY-NC-SA 4.0**…**场景壁纸素材为 MIT**，其余各图版权归各自作者、许可以源站标注为准」——与 3 张卡片的 `· MIT` 署名不再矛盾 |
| 重要-2 | `#stat-live` 恒空（死功能） | ✅ 已修 | 浏览器实测 `#stat-live` = `' · 本次已加载 859 KB / 26 张展示图'` —— **与我独立测量的 859 KB / 26 张完全一致** |
| 重要-3 | TUTORIAL 的 `sizes` 示例是旧 bug 公式 | ✅ 已修 | `TUTORIAL.md:179` 已同步为 5 段式公式，与 `docs/index.html` 31 处 `sizes` 完全一致 |
| 重要-4 | 缩放 3× 溢出视口且无法平移 | ✅ 已修 | 缩放改为改 `width/height`（`docs/index.html:863-864`）而非 `transform`；`.lb-stage` 改为 `overflow:auto`（`:108`）。实测 `stageOverflow=auto, stageScrollH=2608 > stageClientH=1000` → 放大后**可滚动触达**。作者脚本也新增了「灯箱缩放正常：536px → 670px，放大后舞台可滚动」断言 |
| 重要-5 | `check_gallery.py` 不校验 `width/height` 比例 | ✅ 已修 | `tools/check_gallery.py:200-210` 新增：用 Pillow 读原图真实像素，与声明值比对，不符则报「width/height 与原图不符」 |
| 重要-6 | CI 逐字节比对含 `bytes` 的 manifest | ✅ 已修 | 新增 `tools/check_manifest.py`（**只比结构，不比字节数**），`verify.yml:37` 改为调用它；注释也改成了「只比结构…不比字节数 —— WebP 的字节输出依赖 libwebp 版本」 |
| 次要-1 | `target_sizes` 20% 边界漏 1152 档 | ✅ 已修 | 新增 `docs/thumbs/02-nvpu-whale-girl-1152w.webp`，页面 `srcset` 已引用 |
| 次要-2 | 重复 `alt`（3+2 张） | ✅ 已修 | 31 个 `alt` 重新统计，**无重复** |
| 次要-3 | `sizes` 写错无人把关 | ✅ 已修 | `tools/verify_browser.py` 新增断言：「sizes 声明与实际列宽在 7 组视口/DPR 组合下均匹配」 |
| 次要-4 | 站内非图片相对链接不校验 | ✅ 已修 | `check_gallery.py:113` 改为「站内相对链接失效」（不再限定图片后缀） |
| 次要-5 | manifest 外的孤儿缩略图不拦截 | ✅ 已修 | `check_gallery.py:243` 新增「thumbs/ 里有清单未收录的文件」 |
| 次要-6 | 瀑布流间距 16.4–17.8px ≠ 18px | ⚠ 已改善 | 改为 `contentW = cardBox.width - 2` + `cap.getBoundingClientRect().height`（`:758-763`），实测间距 **17.08–17.83px**；残余 <1px 为 `Math.ceil` 取整误差，无视觉影响 |
| 次要-7 | 禁 JS 时分区徽章全空 | ✅ 已修 | 数量已写死进 HTML：`<span class="count">2 张</span>` 等 5 处。禁 JS 实测徽章 = `['2 张','6 张','7 张','13 张','3 张']` |
| 次要-8 | CI 不跑浏览器端验证 | ✅ 已修 | `verify.yml:73` 新增 `browser:` job（playwright + `playwright install --with-deps chromium` + `verify_browser.py --no-js`） |
| 次要-9 | `--clean` 在 NFS 上 `OSError 39` | ✅ 已修 | `make_thumbs.py:201-208` 改为逐个 `unlink(missing_ok=True)`，注释写明了 NFS/overlay 的原因 |
| 建议-1 | `ATTRIBUTION.md` §3 缺作者列 | ✅ 已修 | 已补「作者 / 集合来源」列，7 张逐行列出 |
| 建议-2 | 「看大图 ↗」指向的是缩略图 | ✅ 已修 | 文案改为「**高清版 ↗**」（`docs/index.html:673`） |
| 建议-3 | `layoutAll(false)` 字体重排是死代码 | ✅ 已修 | 新增 `lastCapHeights`（`:730, 783-788`），caption 高度变化也会触发重排 |
| 建议-4 | 提交前冻结一版 | ✅ 已修 | 已提交为 `bf87e52`，`git status` 干净 |

### 复审结论

**VERDICT: PASS**

- 本次报告列出的 **19 个问题，18 个已修并经我独立复验，1 个（次要-6）改善到亚像素级**；
- 复审基线上重跑作者自带的全套校验，**全绿**：
  `check_gallery.py` exit 0 / `sync_srcset.py --check` exit 0 / `check_manifest.py` exit 0 /
  `verify_browser.py --no-js` → 「浏览器端验证全部通过 ✓」（含"灯箱焦点被正确限制在对话框内
  （10 次 Tab 全部循环）""sizes 声明与实际列宽在 7 组视口/DPR 组合下均匹配"等新增断言）；
- **未发现任何新引入的回归**：31/31 图片加载成功、瀑布流 4 列 × 13 张顶部错开 8 种位置、
  竖图比例 1.781、CLS = 0.0006、禁 JS 仍渲染 31 张、零控制台报错、零失败请求；
- 站点仍是纯静态、零外部运行时请求（`docs/index.html` 里除内联 SVG 命名空间外无任何 http(s) 资源引用）、
  `docs/.nojekyll` 在位，**可直接发布**。

**遗留的唯一非阻塞项**：次要-6 的亚像素间距误差（17.08–17.83px vs 目标 18px），肉眼不可见，可不改。

---

## 1.6 复审新增发现：`tools/requirements.txt` 让 CI 全红（**我的初审漏掉了**）

**发现时间**：2026-10-24 14:28，推送后查看 GitHub Actions 状态时。
**性质**：**我的审计失误** —— 初审时我 `cat` 过这个文件，看见了 Python docstring，但**没有拿 pip 去解析它**，
只把注意力放在 manifest 的 `bytes` 依赖上（重要-6）。直到把提交推上 GitHub、CI 跑红，才定位到。

### 现象

`.github/workflows/verify.yml` 的 `verify` 与 `browser` **两个 job 全部失败**，且都停在同一步：

```
✗ 安装依赖                                          failure
- 校验页面与图片一致性                                skipped
- 浏览器端验证（功能 / 性能 / 布局 / 无障碍）              skipped
```

CI 日志：

```
##[group]Run pip install -r tools/requirements.txt
ERROR: Invalid requirement: '"""生成画廊多档 WebP 缩略图 —— 依赖见 requirements.txt。"""': Expected package name at the start of dependency specifier
    """生成画廊多档 WebP 缩略图 —— 依赖见 requirements.txt。"""
    ^ (from line 2 of tools/requirements.txt)
##[error]Process completed with exit code 1.
```

### 根因

`tools/requirements.txt` 是把 Python 脚本的写法直接照搬过来的：

```
#!/usr/bin/env python3
"""生成画廊多档 WebP 缩略图 —— 依赖见 requirements.txt。"""

Pillow>=10.0
```

`pip` 解析 requirements 时**不认 docstring**，把第 2 行整行当成一个依赖名 → 解析失败 →
`pip install -r` 整条命令退出码 1 → 后续所有校验步骤全被 skip。
**换句话说：这套 CI 从 `tools/requirements.txt` 写出来那一刻起就是红的，一次都没真正跑过校验。**
（`TUTORIAL.md` 与 `README.md` 都教用户 `pip install -r tools/requirements.txt`，用户本地同样会报错。）

### 本地复现（干净 venv，无网络）

```bash
python3 -m venv /tmp/venv_ci
/tmp/venv_ci/bin/pip install --dry-run --no-index -r tools/requirements.txt
# ERROR: Invalid requirement: '"""生成画廊多档 WebP 缩略图 —— 依赖见 requirements.txt。"""' (from line 2)
```

注意：沙箱系统 pip 受 PEP 668 保护（externally-managed-environment），会先被环境检查拦下；
**必须用干净 venv 才能看到真正的解析错误** —— 这也是我初审时用 `pip install` 没能发现它的原因之一。

### 已修（commit `4efd948`）

```
# 画廊工具链依赖：make_thumbs.py / check_gallery.py / check_manifest.py 用 Pillow 读写与校验 WebP
# 注意：本文件是 pip requirements 格式，只能用 # 注释，不能写成 Python docstring
Pillow>=10.0
```

修完本地复验：解析通过（只剩 `--no-index` 造成的 "no matching distribution"，属离线环境正常现象）。
已推送 `origin/main` 与 `origin/optimize/gallery-v2`。

### 我该怎么做（自查教训）

**依赖清单文件必须真的跑一次解析器验证，不能只 `cat` 一遍。** 本次静态检查全部通过、
本地脚本全部能跑（沙箱里 Pillow 早已预装，`pip install` 根本没被触发），
所以这个错误"在本地完全隐形"，只有 CI 才会暴露。凡是"CI 会执行、我不执行"的路径，
都应单独做一次等价验证 —— 这次漏了，属于审计覆盖不全，记在这里。

---

## 1.7 画廊扩容与画质升级（2026-10-26，commit `475606d`）· 复审 PASS

在 §1.5/§1.6 之后又做了一轮：**图片数量 31 → 165**（社区二创 13 → 147），
**画质**上把灯箱从"只加载最大档缩略图"升级为可一键切到**原始像素**。

复审基线 sha256-12（`475606de1ea9932cf86ced85c7a516119294fdc1`）：

```
  tools/import_upstream.py  批量导入社区作品 + 逐图记录出处
  tools/build_cards.py      由出处文件生成页面卡片
  tools/build_attribution.py 由出处文件生成 ATTRIBUTION.md 署名表
  tools/upstream/manifest.json  上游清单快照（可复现导入的基准）
```

### 新增能力的验证结果

| 项 | 结论 | 证据 |
| --- | --- | --- |
| 图片总数 | ✅ | 页面 165 张卡片、`#stat-count=165`、分区徽章 `2/6/7/147/3`；本地与线上**逐字节一致**（280,366 B） |
| 全部图片可加载 | ✅ | 逐屏滚动后 **165/165** 加载成功，`broken: []`；线上 `broken: []`（部分仍在排队，跨 CDN 延迟，非故障） |
| **灯箱 1:1 原始像素** | ✅ | 默认 `thumbs/meme-33-1920w.webp`（1920w）→ 点 1:1 → `community/meme-33.webp`（**3840w**），按原始尺寸显示（`dispW=3840`），舞台可滚动（`scrollH 2356 > clientH 1000`） |
| 作者筛选 | ✅ | 41 位作者可选；选「作者未知」→ 36/147 全部作者匹配；清空后恢复 147；瀑布流重排 **0 重叠** |
| 仅看纯手作 | ✅ | 筛出 8 张，**全部** `data-handmade=true` |
| 禁 JS 降级 | ✅ | 165 张图照常渲染，筛选器**隐藏**（控件无功能时不显示），`#stat-count=165` |
| 零报错 | ✅ | 控制台 0 error、0 failed request、CLS 0.0006 |
| 管线一致性 | ✅ | `check_gallery` / `sync_srcset --check` / `build_cards --check` / `build_attribution --check` / `check_manifest` **全部通过** |
| CI | ✅ | `校验画廊一致性` → **success**（475606d），Pages 部署 success |

### 这轮改动的风险与处置（我重点看的地方）

- **去重不是按文件名，是按内容**：13 张旧精选与上游版本 **sha256 完全相同**，确认后才删本地副本；
  另有 1 张低清副本（750×1344）被本站 1152×2048 高清版取代并排除。
  → 避免"同一张图在页面上出现两次"和"用低清版替换高清版"。
- **许可不被"收录"改写**：上游明确「收录不把图片变成 MIT 素材」，逐件记录作者/来源/创作类型/许可；
  上游 37 件没标作者的作品如实记为「作者未知（上游未标注）」，**不推测**。
  → 这是合规底线，比"图多"更重要。
- **多线程编码不改变产物**：`make_thumbs.py` 改为 8 线程后，600 个档位从 ~15 分钟压到 ~3 分钟，
  manifest 仍按原顺序收集，**可复现性不变**（`check_manifest.py` 仍只比结构，避开 libwebp 版本差异）。
- **校验脚本跟着规模升级**：`verify_browser.py` 原来"滚到底一次等 2 秒"在 165 张下会误报
  "17 张没加载"，且把"原图本身只有 180px 宽"误判成"`sizes` 声明偏小"。
  已改为逐屏滚动 + 区分"素材本身小"与"选档错"，并新增作者筛选、1:1 两条断言。
  → 否则 CI 只会变成一盏永远红的灯。

### 遗留（不阻断）

- **1 张素材本身只有 180px 宽**（`community/issue-15-01.webp`），在 305px 列宽下必然被放大。
  这是素材尺寸的限制，不是管线问题；已在校验脚本里与"`sizes` 写错"区分开。
- `docs/` 约 113 MB（原 28 MB），Git 仓库相应变大；GitHub Pages 单站 1 GB 上限内，
  但后续再批量导入前应先评估仓库体积。

**结论：PASS** —— 数量与画质都达成了目标，且没有引入新的合规或一致性缺陷。

---

### 2.1 阻断

无。

---

### 2.2 重要

#### 【重要-1】页脚把 3 张 MIT 壁纸说成 CC BY-NC-SA 4.0（页面内部自相矛盾）

**文件**：`docs/index.html:647`（页脚声明） vs `docs/index.html:605,610,616,621,627,632`（卡片署名）

**怎么复现**：打开页面 → 滚到「五、壁纸」分区，3 张卡片署名写的是
`dsh-whale-girl-wallpaper · MIT`；滚到底部页脚，第二段写的是：

> 画廊展示版是原图的 WebP 压缩副本（480 / 960 / 1440 / 1920 四档宽度，`srcset` 按设备像素比自动选档），
> **与原图同为 CC BY-NC-SA 4.0**；点击图片可放大浏览，「原图」链接查看未压缩原文件。

**为什么是问题**：这两句话在同一页面上直接打架。3 张壁纸的许可按 `ATTRIBUTION.md:69` 和卡片署名是
**MIT**（允许商用、允许再分发），页脚却统一宣称"与原图同为 CC BY-NC-SA 4.0"（禁商用、相同方式共享）。
在 CC BY-NC-SA 仓库里写错素材许可，是会误导下游使用者（有人会以为壁纸不能商用而不敢用，有人会
反过来按 CC 条款去履行 MIT 不需要的义务）。这不是排版问题，是事实性错误。

**实测证据**（Playwright 读 DOM）：

```
footer: '…画廊展示版是原图的 WebP 压缩副本（…），与原图同为 CC BY-NC-SA 4.0；…'
wallpaper card authors: ['dsh-whale-girl-wallpaper · MIT', 'dsh-whale-girl-wallpaper · MIT', 'dsh-whale-girl-wallpaper · MIT']
```

**修改建议**（把"展示版权"和"页面版权"分开说，并把 MIT 单独点出来）：

```html
<p>画廊展示版是原图的 WebP 压缩副本（480 / 960 / 1440 / 1920 四档宽度，<code>srcset</code> 按设备像素比自动选档），
  许可与原图一致（壁纸为 MIT，其余为 CC BY-NC-SA 4.0）；点击图片可放大浏览，「原图」链接查看未压缩原文件。</p>
```

---

#### 【重要-2】`#stat-live` 永远是空的 —— "实际下载量展示"是死功能

**文件**：`docs/index.html:180`（占位 span）、`docs/index.html:702-713`（Resource Timing 采样）、
`TUTORIAL.md:171`（把它列为 JS 增强能力）

**怎么复现**：打开页面，查看页首「许可 CC BY-NC-SA 4.0」后面的 `#stat-live` 元素，**永远是空字符串**。

**为什么是问题**：脚本在 `</body>` 之前同步执行，此时 `performance.getEntriesByType("resource")` 里
**一张 webp 都还没有完成下载**（所有图都是 `loading="lazy"`，首屏图片此刻尚未 settle）。于是
`bytes === 0`，`if (bytes > 0)` 这个守卫直接把整段跳过，`setStat("stat-live", ...)` **永远不会被调用**。
后面也没有任何地方再更新它（`setStat` 只在初始化时调一次）。而 `TUTORIAL.md:171` 明确把
"实际下载量展示" 写成 JS 增强能力之一 —— 属于**承诺了但没实现**。

**实测证据**：

```
stat-live = ''
stat-count = '31'  stat-parts = '5'
```

**修改建议**：把采样挪到 `window.load` 之后，并允许后续更新：

```js
function updateLive() {
  try {
    var res = performance.getEntriesByType("resource");
    var bytes = 0, images = 0;
    res.forEach(function (r) {
      if (/\.webp$/i.test(r.name)) { bytes += r.transferSize || r.encodedBodySize || 0; images++; }
    });
    setStat("stat-live", bytes > 0 ? " · 本次已加载 " + (bytes/1024).toFixed(0) + " KB / " + images + " 张展示图" : "");
  } catch (e) {}
}
window.addEventListener("load", updateLive);
// 滚动加载更多图时再更新一次
window.addEventListener("scroll", throttle(updateLive, 500), { passive: true });
```

如果不想做增量统计，至少把 `TUTORIAL.md:171` 这一行删掉，别宣传一个不存在的功能。

---

#### 【重要-3】TUTORIAL 里的 `sizes` 示例仍是旧公式，与页面实际值矛盾（且正是刚修掉的那个 bug）

**文件**：`TUTORIAL.md:178` vs `docs/index.html`（31 处 `sizes` 属性）

**怎么复现**：

```bash
grep -n 'sizes=' TUTORIAL.md docs/index.html | head -3
```

```
TUTORIAL.md:178:     sizes="(max-width:560px) calc(100vw - 36px), (max-width:900px) 30vw, 305px"
docs/index.html:218:  sizes="(max-width:560px) calc(100vw - 36px), (max-width:693px) calc(50vw - 25px), (max-width:1101px) calc(33.33vw - 22px), (max-width:1320px) calc(25vw - 25.5px), 305px"
```

**为什么是问题**：页面的 `sizes` 在本次审计期间被修正为 5 段式公式（旧的 `30vw` 在 561–693px 区间
把列宽低估了约 1.55 倍，2x 屏会拿到 480w 糊图 —— 我实测复现过：修正前 vw=600/dsf=2 时 **15/31 张图
拿到小于所需像素的档位**）。但 TUTORIAL 是"照着抄就能复刻"的教程，它的示例代码还是那个**有 bug 的旧公式**，
任何人照着教程做都会把刚修掉的 bug 重新引入。TUTORIAL §5.2 后面的散文也还停留在"桌面 4 列约 305px，
所以写 305px"，没提响应式分段。

**修改建议**：把 TUTORIAL.md:178 的示例换成页面实际值，并把散文补成：

```
`sizes` 要和实际布局对得上，而且要覆盖所有断点。本例的网格在 561px 以下是 1 列、561–693px 是 2 列、
694–1101px 是 3 列、1101px 以上是 4 列（容器 1320px、gap 14/18px），所以写成
`(max-width:560px) calc(100vw - 36px), (max-width:693px) calc(50vw - 25px), (max-width:1101px) calc(33.33vw - 22px), (max-width:1320px) calc(25vw - 25.5px), 305px`。
写错 sizes 不会报错，但会让浏览器选错档位，优化的意义就没了 —— 而且这类错误没有任何自动化检查能发现（见次要-9）。
```

---

#### 【重要-4】灯箱缩放到 3× 后图片溢出视口且无法平移，触达不到

**文件**：`docs/index.html:109-111`（`.lb-img` CSS）、`docs/index.html:659`（提示文案）、
`docs/index.html:866-872`（缩放 JS）

**怎么复现**：打开任意一张图 → 连续按 `+` 5 次（`zoom` 达到上限 3）→ 图片右边缘超出视口 888px、
下边缘超出 672px，而 `.lightbox` / `.lb-stage` 的 `overflow` 都是 `visible`，页面也没有任何平移/滚动机制。

**为什么是问题**：`.lb-hint` 明确向用户广告了「← / → 切换 · Esc 关闭 · **+/- 缩放**」，但缩放后超出视口的
那部分内容**永远看不到也拖不动** —— 灯箱层没有 `overflow:auto`、没有 `transform-origin` 调整、没有拖拽。
用户放大后发现"图看不全了，又回不去"，这是一个坏掉的承诺。（另外 `zoom` 在切换图片时会被
`show()` 重置为 1，缩放状态无法跨图保持，这本身是合理设计，不是问题。）

**实测证据**：

```
{'transform': 'scale(3)', 'overflowRight': 888, 'overflowBottom': 672,
 'lbOverflow': 'visible', 'stageOverflow': 'visible',
 'hint': '← / → 切换 · Esc 关闭 · +/- 缩放'}
```

**修改建议**（二选一）：

```css
/* 方案 A：灯箱层可滚动，缩放后能滚到全部内容 */
.lb-stage{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
  padding:64px 76px 132px;overflow:auto}
.lb-img{transform-origin:center center;flex:none}
```

```js
/* 方案 B：给缩放配一个可拖拽的平移量 */
var panX = 0, panY = 0;
function applyTransform() {
  lbImg.style.transform = "translate(" + panX + "px," + panY + "px) scale(" + zoom + ")";
}
// 拖动 / 方向键平移；"+/-" 时同步重置 pan
```

如果暂时不想实现，**先把 `.lb-hint` 里的「+/- 缩放」去掉**，别广告一个残缺功能。

---

#### 【重要-5】`check_gallery.py` 不校验 `<img>` 的 `width`/`height` 与原图真实比例

**文件**：`tools/check_gallery.py:66`

```python
if "width" not in a or "height" not in a:
    problems.append(f"<img> 缺少 width/height（会造成布局抖动）: {src}")
```

**怎么复现**（变异测试，在 `/tmp/mut` 副本上）：

```bash
sed -i 's/width="1152" height="2048"/width="1152" height="1152"/' docs/index.html
python3 tools/check_gallery.py   # → 全部检查通过 ✓
```

**为什么是问题**：脚本只检查"属性在不在"，**不检查值对不对**。`width`/`height` 是这个页面布局的
命门：浏览器靠它算固有宽高比、`layoutGrid()` 靠它算瀑布流行高（`docs/index.html:737-741`）。
把 `2048` 误写成 `1152`，图片会被拉扁 1.78 倍、瀑布流行高全错，而**所有校验脚本都放行**。
当前 31 张图的 `width`/`height` 我逐张核对过，与原图真实像素**完全一致**（这是好的），但没有机制防止
下一个人手滑。

**修改建议**：加一条"比例一致性"检查（`tools/check_gallery.py`）：

```python
from PIL import Image
# 找到该卡片的 data-orig 原图，核对 width/height 与真实像素一致
with Image.open(DOCS_DIR / data_orig) as im:
    ow, oh = im.size
if (int(a["width"]), int(a["height"])) != (ow, oh):
    problems.append(
        f"width/height 与原图不符: {src} 声明 {a['width']}x{a['height']}，原图 {ow}x{oh}"
    )
```

---

#### 【重要-6】CI 逐字节比对 `_manifest.json`，而清单里存着编码器相关的文件字节数

**文件**：`.github/workflows/verify.yml:34-39`、`tools/make_thumbs.py:174`

```yaml
# 清单是纯 JSON（不含时间戳/机器信息），跨机器应当完全一致 —— 必须一致。
if ! git diff --quiet -- docs/thumbs/_manifest.json; then
```

```python
{"path": f"thumbs/{item['file'].name}", "w": item["size"], "bytes": item["bytes"]}
#                                                              ^^^^^^ = out.stat().st_size，即编码产物的字节数
```

**怎么复现 / 为什么是问题**：同一个 workflow 的上一条注释（`:40-41`）明确写着
「图片文件只比对"集合"…**不同机器的 libwebp 版本可能产生编码结果差异，比字节会误报**」。
但**清单里恰好嵌了每个缩略图的编码字节数**（`bytes` 字段），而这些字节数正是 libwebp 编码器的输出 ——
和图片文件本身一样依赖 libwebp 版本。`tools/requirements.txt` 写的是 `Pillow>=10.0`（**无上限**），
CI 每次 `pip install -r tools/requirements.txt` 都会拿到当时的最新版 Pillow（内含特定 libwebp）。

于是同一个"libwebp 版本会误报"的坑，只是从图片文件挪到了 manifest 上：作者本地用 Pillow 11.x
生成、CI 装到 Pillow 12.x（或反过来），**manifest 的 `bytes` 字段不同 → CI 报
"缩略图清单与重新生成的结果不一致"**，而作者明明已经跑过 `make_thumbs.py` 并提交了。

这不是"漏报"（不会放过坏产物），而是**误报**：一次与内容无关的 CI 红灯，且报错信息把原因指向了
"你忘了重新生成"，会误导排查方向。

**修改建议**（二选一，推荐第一个）：

```yaml
# 方案 A：清单只比对"结构"，不比字节数
python - <<'PY'
import json, subprocess, sys
cur = json.load(open("docs/thumbs/_manifest.json", encoding="utf-8"))
new = json.loads(subprocess.run(["python3","tools/make_thumbs.py","--report","--json"],
                                capture_output=True, text=True).stdout)
def shape(m):  # 去掉与编码器相关的字段
    return [{k: v for k, v in it.items() if k != "origBytes"} |
            {"files": [{k: v for k, v in f.items() if k != "bytes"} for f in it["files"]]}
            for it in m["items"]]
if shape(cur) != shape(new):
    print("::error::缩略图清单结构与重新生成的结果不一致")
    sys.exit(1)
print("缩略图清单结构一致 ✓")
PY
```

```yaml
# 方案 B：把 Pillow 钉死，让编码器版本可复现
# tools/requirements.txt
Pillow==11.3.0
```

---

### 2.3 次要

#### 【次要-1】`target_sizes()` 的 20% 边界恰好漏掉 1152 宽的原图

**文件**：`tools/make_thumbs.py:115`

```python
if width > usable[-1] * 1.2 and width < SIZES[-1]:
    usable.append(width)
```

**怎么复现**：`moegirl/02-nvpu-whale-girl.png` 原图 1152×2048。`usable = [480, 960]`，
`960 * 1.2 = 1152`，判断是**严格大于**，所以**没有**补 1152 档，该图最大档只有 960w。

**为什么是问题**：补档规则的存在理由（docstring 原文）是"避免出现『900px 宽的图只有 480w 档』这种
高 DPR 屏发虚的情况"。1152 正好卡在边界上，规则想防的情况还是发生了：手机 390px 宽 3x 屏上，
卡片 352 CSS px → 需要 1056 设备像素，而可用的最大档是 960w → **放大 10%**。
（另一张 `06-ds-and-claude` 900×1200 也有同类问题：1440px 视口 3x 下需要 908 设备像素，最大档 900w。）

**实测证据**（vw=390/dsf=3、vw=560/dsf=2 两档都命中）：

```
vw=390  dsf=3: card w=352  need>=1056 devpx  tiers=[960,1440]  TOO-SMALL=1  (02-nvpu-whale-girl)
vw=560  dsf=2: card w=522  need>=1044 devpx  tiers=[960,1440]  TOO-SMALL=1
vw=1440 dsf=3: card w=302.5 need>=908 devpx  tiers=[900,960]   TOO-SMALL=1  (06-ds-and-claude)
```

**修改建议**：把严格大于改成大于等于，并放宽到 25%：

```python
if width >= usable[-1] * 1.15 and width < SIZES[-1]:
    usable.append(width)
```

（1152 ≥ 960×1.15=1104 成立 → 补 1152 档；`target_sizes` 改完后记得跑 `sync_srcset.py`。）

---

#### 【次要-2】3 张卡片 + 2 张卡片的 `alt` 文本完全重复

**文件**：`docs/index.html`（`qban-set-01/03/05` 三张均为 `alt="Q版角色设定图"`；
`avatar-01/05` 两张均为 `alt="肥鱼头像"`）

**为什么是问题**：屏幕阅读器用户在这 5 张图上听到的是完全相同的描述，无法区分；图片搜索/SEO 也没法
区分。CC BY 的逐图署名虽然已经在 caption 里做到了（`data-author` → `<em>`），但 `alt` 本身是可以补的。

**修改建议**：把标题和作者编进 alt，例如
`alt="Q版角色设定图 · 大肥鱼和小伙伴们（JerryZRic）"`、`alt="肥鱼头像 01 · 夜殇35"`。

---

#### 【次要-3】`sizes` 写错没有任何自动化检查能发现

**怎么复现**（变异测试）：

```bash
sed -i 's|sizes="(max-width:560px)[^"]*"|sizes="100vw"|' docs/index.html
python3 tools/check_gallery.py   # → 全部检查通过 ✓
```

**为什么是问题**：`sizes` 是整个性能优化的支点，写错不会报错、不会加载失败、CI 也全绿，只会**静悄悄地
让浏览器选错档位**。本次审计实测过旧 `30vw` 公式的破坏力（561–693px 区间 15/31 张图拿到过小档位），
而作者自己也在 `TUTORIAL.md:288` 的踩坑表里把"`sizes` 与实际布局不符 → 优化白做"列为头号坑 ——
**既然是头号坑，就应该有一条自动检查守住它**。

**修改建议**：在 `check_gallery.py` 里加一条"列宽 vs `sizes` 声明"的一致性检查（用 Playwright 读
`getBoundingClientRect().width` 和 `getComputedStyle(grid).gridTemplateColumns` 算真实列宽，
和 `sizes` 各分支声明值比对，容差 2%）。最省事的做法是在 `verify_browser.py` 里加一条断言：
遍历 3–4 个代表性视口宽度，断言 `currentSrc` 对应的档位 **≥ 实际渲染宽度 × DPR**。

---

#### 【次要-4】站内非图片相对链接失效不被拦截

**文件**：`tools/check_gallery.py:112` — `if href.endswith(IMAGE_EXTS):`

**怎么复现**（变异测试）：

```bash
# 把某个"原图 PNG"链接改成 "原图 nope.pdf"
python3 tools/check_gallery.py   # → 全部检查通过 ✓
```

**为什么是问题**：只有以 `.png/.jpg/.jpeg/.webp` 结尾的 `href` 会被验证存在性。指向 PDF、字体、
`.md`、目录的站内链接全部不检查。CI 里的 Markdown 链接检查（`verify.yml:51-71`）也只扫
`root.glob("*.md")`，**不覆盖 `docs/index.html`**。

**修改建议**：`check_gallery.py` 里把 `href` 校验改成"站内相对链接一律验证存在性"（跳过
`http(s)://`、`#`、`mailto:`），而不是只查图片后缀。

---

#### 【次要-5】不在 manifest 里的孤儿缩略图文件不被拦截

**怎么复现**（变异测试）：

```bash
cp docs/thumbs/avatar-01-480w.webp docs/thumbs/zzz-orphan-480w.webp
python3 tools/check_gallery.py   # → 全部检查通过 ✓
```

**为什么是问题**：`check_gallery.py:205-210` 的孤儿检查是**以 manifest 为基准**找"manifest 里有、
页面里没引用"的文件；反过来"目录里有、manifest 里没有"的散落文件没人管。目前 `docs/thumbs/` 里
有 81 个 webp，manifest 也正好 81 条，没有散落文件 —— 但删掉 manifest 里的条目再放个文件进来就能绕过。

**修改建议**：在 `check_gallery.py` 的 manifest 段落里补一条双向差集：

```python
on_disk_thumbs = {p.name for p in (DOCS_DIR / "thumbs").glob("*.webp")}
manifest_thumbs = {Path(f["path"]).name for it in manifest["items"] for f in it["files"]}
for extra in sorted(on_disk_thumbs - manifest_thumbs):
    problems.append(f"thumbs/ 里有 manifest 未收录的文件: {extra}")
```

---

#### 【次要-6】瀑布流实际间距是 16.4–17.8px，而不是注释里写的 18px

**文件**：`docs/index.html:719`（`var ROW_GAP_PX = 18;`）、`docs/index.html:746`
（`var span = Math.ceil(total) + ROW_GAP_PX;`）、`TUTORIAL.md` §5.3

**怎么复现**（Playwright 量测同列相邻卡片间距）：

```
gaps: [16.7, 17.08, 16.7, 16.42, 17.08, 16.7, 16.58, 17.83, 17.25]
几何: colW=304.5  imgRect=226.88  shotH(算出来的)=228.38  capOffsetHeight=118  capRect=118.42  span=365
```

**为什么是问题**：两处误差叠加 —— ① `shotH = colWidth / ratio` 用的是**列宽 304.5**，但 `.card` 有
`border:1px`，图片实际内容宽只有 **302.5**，图片盒实际高 226.88 而非算出来的 228.38；
② `cap.offsetHeight` 是**取整值 118**，真实高度 118.42。差 ~1.5px，肉眼不可见，但 `TUTORIAL.md`
里把"想让卡片之间留 18px"写成了明确契约，实际交付 16.4–17.8px。

**修改建议**：把计算改成用**卡片内容盒**而不是列宽，并保留小数：

```js
var cardBox = card.getBoundingClientRect();
var contentW = cardBox.width - 2;               // 减去左右 border
var shotH = contentW / ratio;
var capH = cap.getBoundingClientRect().height;  // 不用 offsetHeight（取整）
var span = Math.ceil(shotH + capH) + ROW_GAP_PX;
```

---

#### 【次要-7】禁用 JS 时，5 个分区标题的「N 张」徽章全空

**文件**：`docs/index.html`（`<span class="count"></span>`）、`docs/index.html:694-700`（JS 填充）

**怎么复现**（Playwright，`java_script_enabled=False`）：

```
.count badges without JS: ['', '', '', '', '']
h2 without JS: ['一、角色设定图（三视图 · 细节拆解）', '二、萌娘百科收录图（条目官方归档）',
                '三、换装三视图参考（7 套）', '四、社区二创', '五、壁纸']
```

**为什么是问题**：页面顶部 `#stat-count=31` / `#stat-parts=5` 是**写死在 HTML 里**的，禁 JS 也在；
但每个分区的"N 张"徽章是 JS 填的，禁 JS 就没了 —— 同一个页面里两种统计口径、两种降级行为，不一致。
不影响浏览，但"JS 缺席时页面仍完整"的硬性设计目标（`TUTORIAL.md:153`）在这里没做到。

**修改建议**：直接把数量写进 HTML（`<span class="count">2 张</span>`），JS 只在需要时覆盖；
或者让 JS 缺席时 CSS 用 `::after` 兜底。代价是加图时要手改两处 —— 权衡看作者取舍。

---

#### 【次要-8】CI 不跑浏览器端验证，灯箱焦点陷阱这类运行时行为无回归保护

**文件**：`.github/workflows/verify.yml`（无 Playwright 步骤）、`TUTORIAL.md:290-297`

**怎么复现**：`grep -n playwright .github/workflows/verify.yml` → 无匹配。

**为什么是问题**：`TUTORIAL.md` 明确写了"浏览器端的验证…体积较大，没放进 CI，本地跑"，所以**不是虚假承诺**，
是作者的有意取舍（我按"有意行为不 FAIL"处理）。但代价是实打实的：本次审计期间 `docs/index.html`
的灯箱焦点管理就被改过两次（先是不移焦 → Tab 跑到背景页；再加了 `trapFocus()`），
**这两处都没有任何 CI 门槛** —— 下次有人重构灯箱，`focus` 跑回背景页、或 Tab 逃出对话框，
CI 依然全绿。

**修改建议**：至少把纯 JS 的焦点行为做成一个不需要浏览器的静态断言（低成本），
或者在 workflow 里加一个可选 job：

```yaml
  browser:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install playwright pillow && python -m playwright install --with-deps chromium
      - run: python tools/verify_browser.py --no-js
```

（`playwright install --with-deps chromium` 在 ubuntu-latest 上约 1–2 分钟，可接受。）

---

#### 【次要-9】`make_thumbs.py --clean` 在 NFS 挂载上直接崩

**文件**：`tools/make_thumbs.py:198` — `shutil.rmtree(THUMB_DIR)`

**怎么复现**（本沙箱的文件系统是 NFS）：

```
python3 tools/make_thumbs.py --clean
...
  File "tools/make_thumbs.py", line 198, in build
    shutil.rmtree(THUMB_DIR)
  File "/usr/lib/python3.11/shutil.py", line 736, in _rmtree_safe_fd
    os.rmdir(path, dir_fd=sys.exc_info())
OSError: [Errno 39] Directory not empty: '.../docs/thumbs'
```

（`/tmp` 上同样的命令正常完成；`shutil.rmtree` 删 50 个普通文件的对照组在 NFS 上也正常，
只有含 81 个文件的 `docs/thumbs` 触发。）

**为什么是问题**：CI 的第 4 步跑的就是 `python tools/make_thumbs.py --clean`（`verify.yml:33`）。
CI 跑在 ext4 上不受影响，**但任何把仓库放在 NFS / 某些网络文件系统 / 某些容器 overlay 上的人
本地跑会直接崩**，且报错信息（"Directory not empty"）完全指不到真因。属于环境相关的健壮性问题。

**修改建议**：改成逐个删除 + 容错，别用 `rmtree` 一把梭：

```python
if clean and THUMB_DIR.is_dir():
    for f in THUMB_DIR.iterdir():
        if f.is_file():
            f.unlink(missing_ok=True)
    for d in THUMB_DIR.iterdir():
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
```

---

### 2.4 建议

#### 【建议-1】`refs` 7 张图在页面和 `ATTRIBUTION.md` 里都没有具名作者

`docs/index.html` 的换装三视图卡片署名是 `AI 萌图 · 三视图设定集`（一个站点，不是人）；
`ATTRIBUTION.md:37-45` 的表格只有「文件 / 设定」两列，**没有作者列**（其余 4 个分区都有）。
CC BY 要求署名到著作权人；这里能做到的最好情况是给出集合来源链接（页面底部有
`aigengtu.com/refs` 链接），**已经做了**，但建议在 `ATTRIBUTION.md` §3 补一列「作者 / 集合来源」，
与其它分区的表格结构保持一致，也便于将来补充个体作者。

#### 【建议-2】灯箱里「看大图 ↗」指向的其实是缩略图，不是原图

`docs/index.html` 的 `lbOpen.href = full || orig || "#"`，`full` 是 `data-full`（最大档 WebP 缩略图）。
于是灯箱底部两个链接是：「原图 ↗」→ 2.0 MB 的 PNG，「看大图 ↗」→ 1440w 的 WebP。后者严格来说是
"更清晰的展示版"，叫「看大图」容易让人以为是原图。建议改成「高清版 ↗」或「1920w WebP ↗」，
或直接让它指向原图、把「看大图」删掉。

#### 【建议-3】`layoutAll(false)` 的"字体加载后重排"实际是死代码

`docs/index.html:752-759` 的 `layoutAll(force)` 只在 `force` 或**列宽变化**时才重排；
而 `doc.fonts.ready.then(schedule)`（`:773-775`）和 `window.addEventListener("load", schedule)`
（`:776`）都走 `schedule()` → `layoutAll(false)`。字体加载完成时列宽通常没变，
**于是重排被跳过** —— 注释「字体加载完成会改变 caption 高度，需要重排」描述的行为不会发生。

实测影响为零（本页没有 webfont，用的是系统字体），但注释与代码不符会误导后来人。
建议把这两处改成 `layoutAll(true)`，或在 `layoutAll` 里加一个"caption 高度是否也变了"的判断：

```js
var lastCapHeights = [];
// ...在 layoutGrid 里记录 lastCapHeights[index] = cap.offsetHeight
if (force || lastWidths[i] !== grid.clientWidth || lastCapHeights[i] !== currentCapHeight) { ... }
```

#### 【建议-4】审计期间仓库仍在被修改，建议提交前冻结一版再走一次流水线

本次审计跨越 23:31 → 23:52，其间 `docs/index.html` 改了 4 次、`tools/` 下 4 个文件全部重写、
新增了 `tools/sync_srcset.py`。我做的所有复现都基于 §0 的哈希基线。**建议在提交前冻结一版，
跑完 `check_gallery.py` + `sync_srcset.py --check` + `verify_browser.py --no-js` 再推**，
否则"CI 绿"对应的可能不是同一份代码。

---

## 3. 通过项（附证据）

| 检查项 | 结论 | 依据 |
| --- | --- | --- |
| 31 张原图全部有对应卡片 | ✅ | `check_gallery.py`：「页面图片 32 张 · 引用原图 31 张 · 磁盘原图 31 张」；`data-orig` 与 manifest 的 `src` 集合**双向零差集** |
| `srcset` 声明宽度 == 文件实际宽度 | ✅ | 逐文件用 Pillow 量测 81 个 webp，**0 处不符** |
| 档位选择逻辑（31/31 正确） | ✅ | `target_sizes()` 对每张原图的输出与磁盘上实际存在的文件**完全一致**（480/960/1440/1920 + 5 张非标准档 900/1200/1254/1299/1760） |
| 孤儿缩略图 / 缺失缩略图 | ✅ | 页面引用的 81 个缩略图与磁盘上的 81 个**完全重合**，无孤儿、无缺失；manifest 记的 `srcset` 与页面 `srcset` **0 处不一致** |
| `<img>` 的 `width`/`height` == 原图真实像素 | ✅ | 31 张逐张核对，**0 处不符**；`data-size` 也与真实像素一致 |
| 产物可复现 | ✅ | `make_thumbs.py --clean` 重生成后，81 个 WebP **逐字节一致**（`cmp` 全过），`_manifest.json` 一致 |
| 瀑布流布局正确 | ✅ | 15 个视口宽度（320–1920）下 **0 处同列重叠、0 处横向溢出、0 处缺 `grid-row-end`**；1440→390→1440 往返重排正常 |
| 竖图比例不失真 | ✅ | `02-nvpu-whale-girl` 显示 h/w = 1.781（原图 1152×2048 → 期望 1.778） |
| 灯箱环绕 / Home / End | ✅ | 第 1 张 `←` → `31 / 31`；第 31 张 `→` → `1 / 31`；`End`→`31 / 31`；`Home`→`1 / 31` |
| 灯箱反复开关 | ✅ | 连开 4 次，`count`/`naturalWidth`/`body.overflow` 全部正确，`Esc` 后 `overflow` 每次都恢复 `visible` |
| 灯箱全部 `data-full` 可加载 | ✅ | 31 个 `data-full` 逐个 `Image.decode()`，**0 失败** |
| 灯箱焦点管理 | ✅ | 打开后 `activeElement=lb-close`（在对话框内）；`Tab`×9 与 `Shift+Tab`×9 **全部在对话框内循环**；`Esc` 后焦点回到触发卡片 |
| 灯箱背景点击关闭 | ✅ | 点击空白舞台区（1350,150）/(120,760)/(720,60) 均关闭（首测点 (20,500) 命中的是 `lb-prev` 按钮，属我的测试点选错，非缺陷） |
| 灯箱不滚动背景页 | ✅ | 模态打开时按 `ArrowDown`，`scrollY` 保持 0 |
| 首屏下载量 | ✅ | 我独立实测：旧版 3.3 MB / 27 张 → 新版 **859 KB / 26 张**（1440×900, 1x）；整页 3.4 MB → 963 KB；手机 390×844 2x = 579 KB / 5 张 —— 与 README 表格**完全一致** |
| 无重复下载 | ✅ | PerformanceObserver 全程扫描，`webp` 资源**无一 URL 被请求两次** |
| `srcset` 选档有效（修正后） | ✅ | 15 组 (视口 × DPR) 组合下，除 3 张"最大档受原图宽度限制"的边缘情况外，**无一张拿到小于所需像素的档位**（修正前 vw=600/dsf=2 有 15/31 张过小） |
| 零控制台报错 / 零失败请求 | ✅ | 完整交互流程中 `console` 无 error，`requestfailed` 为空 |
| 禁用 JS 降级 | ✅ | 31 张图照常渲染、`#stat-count=31`/`#stat-parts=5` 仍在、灯箱层不可见、`Ctrl+点击` 正确打开原图 PNG 新标签页 |
| `prefers-reduced-motion` | ✅ | `transition-duration` 实测 `1e-05s`（= CSS 里的 `.01ms`）、`scroll-behavior: auto` —— 已生效 |
| 跳转链接 | ✅ | `.skip` 获得焦点后 `left ≥ 0`（可见），`href="#main"`，`#main` 存在 |
| 灯箱 `aria` 属性 | ✅ | `role="dialog"`、`aria-modal="true"`、`aria-label="图片放大浏览"`；`#lb-img` 的 `alt` 随图片标题更新 |
| 逐图署名在图片旁可见 | ✅ | 每张卡片的 `<figcaption>` 都有 `<em>` 作者行 + 灯箱 `#lb-meta` 同步显示作者与尺寸（CC BY 的"署名要出现在作品旁边"要求已满足） |
| OG 图片尺寸 | ✅ | `og:image` 指向 `thumbs/01-16yeluomao-ds-1440w.webp`，实际 1440×2159，与 `og:image:width/height` 声明一致 |
| 无 XSS 面 | ✅ | 全页无 `innerHTML` / `eval` / `document.write` / `insertAdjacentHTML`；动态写入只用 `textContent` 与 `setAttribute`；无用户输入；外链统一 `rel="noreferrer"`（隐含 noopener） |
| README 数字核对 | ✅ | 31 张 / 20.6 MB / 480w=954 KB / 960w=2.4 MB / 1440w=2.0 MB（11 张）/ 1920w=395 KB（2 张）/ "25 张原图长边 ≤1600px"（实测 25/31）—— **全部对得上**（唯 `5.9 MB` 一处对不上，见次要） |
| CI 三个脚本本地实跑 | ✅ | `check_gallery.py` → exit 0；`sync_srcset.py --check` → exit 0；CI 里的 Markdown 链接检查 → exit 0 |
| CI 能抓到"改了原图没重生成缩略图" | ✅ | 变异测试：把 `gallery/avatar-01.webp` 换成别的图 → CI 第 3 步 `git diff --quiet -- docs/thumbs/_manifest.json` 返回 **1** → 判失败 |

---

## 4. 我实际跑过的验证（命令 + 关键输出）

### 4.1 静态数据核对

```bash
# 31 张原图真实尺寸 / 31 张卡片 width·height / srcset 声明宽度 vs 文件实际宽度
python3 /workspace/audit/t1_dimensions.py
```
```
=== SOURCE IMAGES (real dims) ===   (31 张，略)
  TOTAL sources: 31   orig bytes: 20.59 MB
--- width/height attr vs REAL original dims ---
  width/height attr mismatches: 0
--- srcset declared w vs actual file width ---
  srcset width mismatches: 0
--- ORPHAN thumbnails ---
  orphan count: 0  / total thumb files 81
```

```bash
# 档位体积统计（与 README 表格逐项核对）
python3 - <<'PY'   # 遍历 docs/thumbs/*.webp 按 -Nw.webp 归类
PY
```
```
  480w : 31 files,    954.2 KB      960w : 30 files,   2414.6 KB
  900w :  1 files,    176.6 KB     1200w :  1 files,     58.2 KB
 1254w :  3 files,    279.7 KB     1299w :  1 files,    159.8 KB
 1440w : 11 files,   2013.6 KB     1760w :  1 files,    264.5 KB
 1920w :  2 files,    394.5 KB
  → 与 README「954 KB / 2.4 MB / 2.0 MB（11 张）/ 395 KB（2 张）」逐项吻合
```

### 4.2 缩略图管线可复现性

```bash
cp -a /workspace/gallery /tmp/gcopy && cd /tmp/gcopy && python3 tools/make_thumbs.py --clean
diff /workspace/gallery/docs/thumbs/_manifest.json /tmp/gcopy/docs/thumbs/_manifest.json
for f in /workspace/gallery/docs/thumbs/*.webp; do cmp -s "$f" "/tmp/gcopy/docs/thumbs/$(basename $f)"; done
```
```
MANIFEST IDENTICAL ✓
FILE SET IDENTICAL ✓
same=81 differ=0
```

### 4.3 浏览器实测（自建 Playwright 脚本，共 6 轮）

```
A. 灯箱：A0/A1/A2/A3 环绕与 Home/End 全部正确；A5 连开 4 次正常；
   A6 31 个 data-full 全部 decode 成功；A10 Tab 全部在对话框内；console errors=[] failed requests=[]
B. 瀑布流：15 个视口宽度  overlaps=0  minGap≥15.6  badSpan=0  hOverflow=False
D. srcset：vw=600 dsf=2 时 TOO-SMALL=15（修正前）→ 修正后 TOO-SMALL=0
E. 网络字节：
   NEW 1440x900 1x 首屏: 26 imgs  859 KB
   NEW 1440x900 1x 整页: 31 imgs  963 KB   dupes=[]
   NEW 1440x900 2x 首屏: 26 imgs 2324 KB
   NEW  390x844  2x 首屏:  5 imgs  579 KB
   OLD 1440x900 1x 首屏: 27 imgs 3304 KB
   OLD 1440x900 1x 整页: 31 imgs 3482 KB
F. 禁 JS：31 图渲染、stat=31/5、灯箱不可见、Ctrl+点击打开原图
G. a11y：skip 可见、prefers-reduced-motion 生效、stat-live=''、重复 alt 2 组
```

### 4.4 变异测试（`/tmp/mut` 副本，验证校验脚本的盲区）

```
[MISSED] M2 img width/height 与原图比例不符        → 重要-5
[MISSED] M5 sizes 写错                              → 次要-3
[MISSED] M7 站内非图片相对链接失效                  → 次要-4
[MISSED] M4 孤儿缩略图文件（不在 manifest 里）        → 次要-5
[CAUGHT] M1 data-full 指向不存在的文件
[CAUGHT] M3 srcset 少写一档
[CAUGHT] M6 alt 文本被清空
[CAUGHT] M8 页面少一张卡片（原图成孤儿）
[CAUGHT] M9 删掉一个缩略图文件
[CAUGHT] M10 改了原图没重生成缩略图（CI 第 3 步 manifest diff → 失败）
```

### 4.5 CI 脚本本地实跑

```bash
python3 tools/check_gallery.py            # 页面图片 32 张 · 引用原图 31 张 · 磁盘原图 31 张 / 全部检查通过 ✓ / exit 0
python3 tools/sync_srcset.py --check      # srcset / data-full 与清单完全一致 ✓ / exit 0
# verify.yml 里的 Markdown 链接检查逐字复制执行 → 相对链接全部有效 ✓ / exit 0
python3 tools/verify_browser.py --no-js   # 浏览器端验证全部通过 ✓（作者自带的检查，全绿）
```

> 作者的 `verify_browser.py` 全绿，但它**不覆盖**：首/末张环绕、Tab 焦点陷阱、`sizes` 选档正确性、
> 缩放溢出、`data-full` 全部可加载、变异的 `width/height` 比例 —— 这些正是本报告发现问题的位置。

---

## 5. 修复优先级建议

> **2026-10-24 更新：本节 1–6 项已全部完成并复验通过（§1.5），当前结论 PASS。**
> 下面保留初审时的优先级排序，供追溯。

1. **先修许可表述**（重要-1）—— 一行文本，零风险，但涉及 CC 合规。
2. **补 `width/height` 比例校验**（重要-5）—— 约 8 行代码，堵住最容易犯也最难发现的错。
3. **修 TUTORIAL 的 `sizes` 示例**（重要-3）—— 避免教程把已修的 bug 教回去。
4. **要么让 `stat-live` 真的工作，要么从文档里删掉**（重要-2）。
5. **缩放要么能平移、要么从提示里去掉**（重要-4）。
6. **CI 的 manifest 比对改成结构比对，或钉死 Pillow 版本**（重要-6）—— 避免 libwebp 版本导致的红灯。
7. 次要项可批量处理：alt 去重、`target_sizes` 边界、孤儿/非图片链接检查、`sizes` 一致性检查、
   瀑布流间距、NFS 上的 `rmtree`、CI 里加浏览器 job。
