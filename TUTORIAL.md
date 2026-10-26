# 静态角色图集发布到 GitHub Pages · 全流程案例

这份教程记录了这个仓库从"一堆原图"到"一个可分享的在线画廊"的完整做法。
纯静态、零构建、零依赖、零外部请求 —— 克隆下来双击 `docs/index.html` 就能看。

适合：想把 AI 角色图、二创稿、壁纸之类整理成公开画廊的人。

---

## 0. 最终效果

- 在线：GitHub Pages 直接托管
- 离线：双击 `docs/index.html` 就能浏览，不联网也能用
- 隐私：没有任何外部请求、没有统计脚本、没有第三方字体
- 体积：31 张图，原图 20.6 MB；1x 屏整页下载 963 KB（旧版单尺寸方案是 3.4 MB）

---

## 1. 目录怎么摆

关键决策：**仓库根目录放工具和文档，`docs/` 整个目录就是网站根**。

```
.
├── README.md
├── TUTORIAL.md          # 你正在读的这个
├── ATTRIBUTION.md       # 每张图的作者与出处（CC BY 要求）
├── LICENSE
├── tools/               # 脚本，不参与发布
│   ├── make_thumbs.py   # 生成多档缩略图
│   ├── sync_srcset.py   # 把清单里的档位同步进页面 srcset / data-full
│   ├── check_gallery.py # 校验页面与图片一致
│   ├── check_manifest.py# 比对缩略图清单结构（不比字节）
│   ├── verify_browser.py# 浏览器端验证（功能 / 性能 / 布局 / 无障碍）
│   └── requirements.txt # Pillow
└── docs/                # ← 整个目录 = GitHub Pages 的站点根
    ├── index.html
    ├── .nojekyll        # 关键：让 GitHub 跳过 Jekyll 处理
    ├── thumbs/          # 生成的展示版 WebP
    ├── sheets/          # 原图（按分区分子目录）
    ├── moegirl/
    ├── refs/
    ├── gallery/
    └── wallpaper/
```

`.nojekyll` 这个空文件别漏。GitHub Pages 默认会用 Jekyll 构建，
遇到某些文件名或下划线开头的目录会直接构建失败。加上它，静态文件原样发布。

原图按分区分子目录放，是为了让缩略图脚本能按目录分组扫描，
也方便以后加新分区时只改一处配置。

---

## 2. 本地预览

直接双击 `docs/index.html` 就能看 —— 页面不依赖任何网络资源。

需要本地服务器的话（想测试 http 环境下的行为）：

```bash
cd docs && python3 -m http.server 8000
# 然后打开 http://localhost:8000
```

---

## 3. 准备原图

### 3.1 尺寸

原图分辨率差异很大（从 1008×576 的壁纸到 2732×4096 的立绘），
这正是后面要做**多档缩略图**的原因 —— 统一压成一种尺寸必然有一头浪费。

### 3.2 版权（这一步别偷懒）

CC BY-NC-SA 要求**逐图署名**。建一个 `ATTRIBUTION.md`，表格形式：

| 文件 | 说明 | 作者 / 出处 |
| --- | --- | --- |
| `01-xxx.webp` | 某某设定图 | 某某（来源链接） |

页面每张卡片上也要显示作者。只在 ATTRIBUTION.md 里写是不够的 ——
**署名要出现在作品旁边**，这是 CC BY 的硬要求。

同时在页面顶部挂一个醒目的许可提示框，说明角色形象本身的来源和限制。
本例中「溟月 → 女仆装鲸鱼娘」的形象谱系就必须写清楚，否则容易让人误以为是官方形象。

---

## 4. 生成多档缩略图

这是整套流程里最值得花时间的一步。

### 4.1 为什么要多档

最初的版本只生成一种尺寸（长边 1600px），实测发现两个问题：

1. **25 张图原图长边本来就 ≤1600px** —— 所谓的"缩略图"其实是原图重编码，
   一分钱没省，还多了编码损耗。
2. **显示尺寸只有约 305px 宽**，却发 1024–1600px 的图，
   超采样 4–6 倍，手机上更是白下载。

改成按宽度分档（480 / 960 / 1440 / 1920），配合 `<img srcset>`，
浏览器按设备像素比自己挑一档：

| 场景 | 实际需要的宽度 | 浏览器选 |
| --- | --- | --- |
| 手机 1x | ~330px | 480w |
| 手机 2x | ~660px | 960w |
| 桌面 1x | ~305px | 480w |
| 桌面 2x | ~610px | 960w |
| 灯箱大图 | 全屏 | 1440w / 1920w |

实测（1440×900 视口，Chromium）：1x 首屏 3.3 MB → **859 KB**，
整页 3.4 MB → **963 KB**，画质反而更锐利（因为不再拉伸）。

### 4.2 关键实现细节

**`srcset` 的 `w` 描述符是图片宽度，不是长边。**
竖构图（2732×4096）如果按长边算 480，出来的图只有 320px 宽，
但你声明成 `480w`，浏览器会按 480px 渲染 —— 图被拉糊了。必须按宽度算。

**不要生成超过原图尺寸的档位。** 放大既失真又徒增体积。

**保留 alpha 通道。** 带透明背景的 PNG 转 WebP 时如果 `convert("RGB")`，
透明区域会变成黑底。

**路径基于脚本自身解析。** 别写死绝对路径：

```python
DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
```

否则脚本只在作者自己那台机器上能跑。

**增量生成。** 目标文件不比源文件旧就跳过，重复运行很快。

### 4.3 用法

```bash
pip install -r tools/requirements.txt

python tools/make_thumbs.py           # 生成（增量）
python tools/make_thumbs.py --clean   # 强制全量重建
python tools/make_thumbs.py --report  # 只看体积报告
python tools/sync_srcset.py           # 把清单里的档位同步进页面 srcset
```

脚本会输出各档位体积报告，并生成 `docs/thumbs/_manifest.json`
（记录每张图有哪些档位、多大、原始尺寸），供 CI 校验使用。

**档位和页面要保持同步。** `make_thumbs.py` 可能给某张图补出一档
（比如原图 1200 宽，标准档只有 480/960，就再补一档 1200w），
如果页面里的 `srcset` 没写上这一档，那个文件就永远不会被下载 ——
既是浪费仓库空间，也让高像素密度屏幕拿不到本该有的清晰度。
`sync_srcset.py` 就是干这个的，幂等，可以随时跑。

### 4.4 批量导入：让画廊"最全面"

一张张手工加图，加到一百张就做不下去了。本例的解法是**找一个已经维护好的上游资产库**，
再把它机器可读的清单一起拿过来。

`TreapGoGo/deepseek-whale-girl`（鲸鱼娘开源资产库）就是这样的上游：它维护了一份
`site/assets/gallery/manifest.json`，每件作品都记着标题、作者、来源、投稿 issue、
创作类型、尺寸和许可。拿到清单，导入就变成了可脚本化的事：

```bash
python tools/import_upstream.py --dry-run   # 先看计划
python tools/import_upstream.py             # 下载原图 + 写出处文件
python tools/make_thumbs.py                 # 给新图生成档位
python tools/build_cards.py                 # 生成页面卡片
python tools/build_attribution.py           # 生成 ATTRIBUTION.md 署名表
```

四个工具的分工：

| 工具 | 职责 | 产物 |
| --- | --- | --- |
| `import_upstream.py` | 按清单下载原图，记录逐图出处 | `docs/community/*.webp`、`docs/community/_meta.json` |
| `make_thumbs.py` | 给所有原图生成多档缩略图 | `docs/thumbs/`、`_manifest.json` |
| `build_cards.py` | 由出处文件生成页面卡片 | `docs/index.html` 的社区分区 |
| `build_attribution.py` | 由出处文件生成署名表 | `ATTRIBUTION.md` |

**手写 HTML 在这个量级必然失控**：140 多张卡片，人工同步 `srcset`、宽高、作者、
出处链接，迟早会漏。生成器让"页面 = 出处文件 = 缩略图清单"三者永远一致，
CI 里跑 `--check` 就能挡住任何漂移。

三条要守住的规矩：

- **不改变作品许可。** 上游明确声明「收录不把图片变成 MIT 素材」——收录行为
  不会把别人的作品变成你的许可证能覆盖的东西。逐图许可照实记录。
- **资料缺失就如实记录，不猜。** 上游有 37 件作品没标作者，就写「作者未知
  （上游未标注）」，不要从画风去猜作者是谁。
- **去重要按内容，不是按文件名。** 同一张图可能以不同文件名出现在本地和上游。
  本例用 16×16 灰度平均哈希（aHash）比对，汉明距离 ≤4 视为同一张，
  确认后删掉低清的那份。

---

## 5. 写页面

### 5.1 保留"无 JS 也能看"

这是个硬性设计目标：**双击打开、禁用 JS，依然能正常浏览全部图片**。

所以卡片 HTML 是静态写死的，JS 只做增强：

- 瀑布流布局（JS 缺席时退化成普通网格，仍然正确）
- 灯箱放大浏览
- 统计数字自动填充
- 实际下载量展示

### 5.2 图片标签的完整写法

```html
<img src="thumbs/xxx-960w.webp"
     srcset="thumbs/xxx-480w.webp 480w, thumbs/xxx-960w.webp 960w, thumbs/xxx-1440w.webp 1440w"
     sizes="(max-width:560px) calc(100vw - 36px), (max-width:693px) calc(50vw - 25px), (max-width:1101px) calc(33.33vw - 22px), (max-width:1320px) calc(25vw - 25.5px), 305px"
     width="1448" height="1086" alt="…" loading="lazy" decoding="async" />
```

四个属性各有各的作用，少一个都出问题：

- `src` —— 不支持 srcset 的老浏览器的兜底
- `srcset` + `sizes` —— 按 DPR 选档
- `width` + `height` —— **必须**。浏览器靠它算出固有宽高比，
  没有它图片加载完会把页面顶下去（CLS），瀑布流布局更是直接散架
- `loading="lazy"` —— 长列表必需

**`sizes` 必须覆盖所有断点，而且要和真实列宽对得上。**
本例的网格在 561px 以下是 1 列、561–693px 是 2 列、694–1101px 是 3 列、
1101px 以上是 4 列（容器 1320px、gap 14/18px），所以 `sizes` 要分段写。

如果偷懒只写一个 `30vw` 会怎样？在 561–693px 这段是 2 列布局，
真实列宽 255–321px，而 `30vw` 只有 168–208px —— **低估了 1.5 倍**。
浏览器以为只要 180px 宽就够了，2x 屏上就会去拿 480w 档，
然后拉伸到 590 设备像素去显示，糊。

写错 `sizes` 不会报错、不会加载失败、CI 也不会红，只会静悄悄地让浏览器选错档位。
所以这类错误必须有自动化断言守着（见 §6）。

### 5.3 瀑布流

CSS Grid 的 `masonry` 至今没有浏览器支持，可用方案：

```css
.grid.masonry { grid-auto-rows: 1px; gap: 0 18px; }
```

注意 `gap: 0 18px` 的含义：**行间距 0、列间距 18px**。行高被压到 1px，
竖直方向的留白就要靠 `grid-row: span N` 多吃的行数来制造。

```js
var ROW_GAP_PX = 18;                        // 想让卡片之间留 18px
var total = shotH + cap.offsetHeight;       // 图片盒高 + 说明区高
var span  = Math.ceil(total) + ROW_GAP_PX;  // 多吃 18 行 = 多出 18px 竖距
card.style.gridRowEnd = "span " + span;
```

两个容易踩的坑：

- **必须先算数字再拼字符串。** `"span " + n + 1` 会被 JS 当成字符串拼接，
  变成 `"span 7011"` 而不是 `7012`，grid 会老老实实创建七千多行隐式行，
  页面被撑到几千像素高。用 `Math.ceil(total) + ROW_GAP_PX` 先算出数字再拼。
- **`<figure>` 有浏览器默认 `margin: 1em 40px`。** 用 `<figure>` 当卡片时
  不清掉 margin，卡片宽度会比列宽少 80px，而且整列都左偏 40px，
  看起来像布局坏掉了。`.card { margin: 0 }` 别忘。

因为 `<img>` 有 `width`/`height` 属性，图片盒高度在加载前就能算出来，
不需要等图片下载完再重排，布局不会跳动。

### 5.4 灯箱

纯 CSS 做不了，用 `<dialog>` 或一个 fixed 定位的容器都行。至少要有：

- 键盘：`←` `→` 切换、`Esc` 关闭、`Home`/`End` 跳首尾
- 触摸：左右滑动切换
- 预加载相邻两张，切换不闪
- 打开时锁住页面滚动，关闭后恢复焦点
- **焦点要进对话框并在内部循环**。否则用户按 Tab 会跑到背后的页面去
  （本例实测要点 60 多次才够到关闭按钮）；打开时把焦点放到关闭按钮上，
  关闭后还给触发的那张图。
- 显示作者与原图链接（CC BY 署名在灯箱里也要能看见）

缩放有个容易踩的坑：**用 `transform: scale()` 缩放，图片超出视口的部分永远滚不到** ——
`transform` 只是视觉变换，不会撑开布局盒，容器的可滚动区域根本没变大。
要么改成直接改 `width` / `height`（布局跟着变，配合 `overflow:auto` 就能滚），
要么自己实现拖拽平移。

另外 flex 居中的容器要设 `margin:auto` 而不是 `justify-content:center`：
后者在内容溢出时会把内容推到负方向，左上角被裁掉且滚不到。

---

## 6. 校验

手抄 `srcset` 极易出错 —— 本例中就出现过 `03-long-skirt-maid` 写成
`03-long-skirt` 的笔误，靠肉眼看不出来。

写个脚本自动查：

```bash
python tools/check_gallery.py
```

它检查：

- 每个 `<img>` 的 `src` / `srcset` 文件是否存在
- `srcset` 声明的宽度 == 文件实际宽度
- `width` / `height` / `alt` 是否齐全
- **`width` / `height` 的值 == 原图真实像素**（写错图片会被拉扁，布局全错）
- 磁盘上的原图是否都在页面里出现（漏加卡片）
- 原图是否都有对应的缩略图记录
- `srcset` 是否漏了清单里的档位、是否引用了清单外的档位
- 灯箱的 `data-full` 是否指向该图最高档
- 有没有"生成了但页面从不引用"的孤儿缩略图
- 站内相对链接是否失效（不限图片后缀）
- `thumbs/` 目录里有没有清单未收录的散落文件

另有 `tools/check_manifest.py`：比对清单的**结构**与仓库里已提交的是否一致。
注意只能比结构、不能比字节 —— 清单里的 `bytes` 字段是 WebP 编码产物的字节数，
依赖 libwebp 版本，不同机器编出来会差几十字节，比字节会误报。

批量导入的作品还多两层校验（`tools/build_cards.py --check`、
`tools/build_attribution.py --check`）：页面卡片与 `ATTRIBUTION.md` 署名表
都从 `docs/community/_meta.json` 生成，两者一旦与出处文件不一致就失败。
这样"加了一张图却忘了写署名"或"改了出处没重新生成页面"都会在 CI 里被挡住。

`sizes` 写错是所有性能错误里最隐蔽的一种（不会报错、不会红、只会静悄悄选错档位），
所以由 `tools/verify_browser.py` 在浏览器里守住：它遍历多组视口宽度与 DPR，
断言浏览器实际选中的档位 **≥ 渲染宽度 × 设备像素比**。

建议都接进 CI，push 上去自动跑。

---

## 7. 发布到 GitHub Pages

1. 仓库 Settings → Pages → Source 选 **Deploy from a branch**，
   分支 `main`，目录 `/docs`
2. 推代码，等待 1–2 分钟
3. 访问 `https://<用户名>.github.io/<仓库名>/`

`.nojekyll` 必须在 `docs/` 根下，否则构建可能失败。

仓库根目录也会被发布成 `https://<用户名>.github.io/<仓库名>/` 的
下级路径（本例中 README、ATTRIBUTION.md 等在 `/` 下，
页面在 `/docs/` 下），所以页面里引用 `ATTRIBUTION.md` 时
用相对路径 `../ATTRIBUTION.md` 是打不开的 —— 页面里统一写
"见仓库 ATTRIBUTION.md"并给出仓库链接。

---

## 8. 自动化

`.github/workflows/verify.yml` 在每次 push / PR 时：

1. 装 Python + Pillow
2. 跑 `check_gallery.py`，有错就失败（挡住"加了图忘了生成缩略图"）
3. 跑 `sync_srcset.py --check`，页面 srcset 与清单不一致就失败
4. 重新生成缩略图，比对**文件集合**与提交的清单
   （注意：不要比对 WebP 字节 —— 不同机器的 libwebp 版本会产生编码差异，
   比字节会误报）
5. 检查 Markdown 里的相对链接有没有失效

浏览器端的验证（`tools/verify_browser.py`）依赖 Playwright + Chromium，
体积较大，没放进 CI，本地跑：

```bash
pip install playwright && playwright install chromium
python tools/verify_browser.py --no-js
```

它会检查图片是否真的加载、srcset 档位选择是否正确、瀑布流是否排开、
竖图比例是否失真、灯箱的键盘/缩放/关闭、累积布局偏移 CLS、
以及禁用 JS 时的降级表现，并输出各视口截图。

---

## 9. 顺手可以加的东西

- **Open Graph / Twitter 卡片** —— 分享到 X、微信、Discord 时有预览图。
  用一张 1440w 的图当 `og:image`，传播效果差别很大。
- **sitemap.xml / robots.txt** —— 静态文件直接扔进 `docs/` 即可。
- **分区锚点导航** —— `position:sticky` 顶栏，图片多的时候很实用。
- **触摸设备别残留 hover 态** —— 用 `@media (hover:hover)` 把 hover 效果包起来，
  否则手机上点一下会"粘"住高亮。
- **`prefers-reduced-motion`** —— 关掉动画，尊重系统设置。

---

## 10. 踩过的坑清单

| 坑 | 表现 | 解法 |
| --- | --- | --- |
| 漏了 `.nojekyll` | Pages 构建失败 | `docs/.nojekyll` 建空文件 |
| `srcset` 用长边算 | 竖图被拉糊 | `w` 描述符是宽度，按宽度分档 |
| `sizes` 只写一个值 | 某些断点下选错档位，2x 屏发糊 | 按真实列宽分段写，并加浏览器断言 |
| `width`/`height` 写错 | 图片被拉扁、瀑布流全错 | 加校验脚本比对原图真实像素 |
| `<img>` 缺 `width`/`height` | 图片加载后页面跳动 | 必填 |
| 用 `<figure>` 当卡片忘了清 margin | 卡片比列宽窄 80px、整列左偏 | `.card { margin: 0 }` |
| `"span " + n + 1` 字符串拼接 | span 变成 "span 7011"，页面被撑到几千 px 高 | 先算数字再拼 |
| 缩略图 `convert("RGB")` | 透明背景变黑底 | 检测真实透明像素再转 |
| 脚本写死绝对路径 | 换台机器就废 | 基于 `__file__` 解析 |
| `shutil.rmtree` 删大批文件 | NFS / overlay 上抛 "Directory not empty" | 逐个删除 + 容错 |
| 硬编码统计数字 | 加图后忘了改 | 让 JS 从 DOM 统计 |
| Resource Timing 在 `load` 时取 | 懒加载图还没下载，统计永远是 0 | 用 PerformanceObserver 持续观察 |
| 灯箱不锁滚动 | 背景跟着滚 | `body { overflow:hidden }` |
| 灯箱不设焦点陷阱 | Tab 跑到背景页面，要点 60+ 次才够到关闭按钮 | 打开时聚焦对话框并循环 |
| `transform: scale()` 做缩放 | 放大后超出视口的部分滚不到 | 改 `width`/`height` + `overflow:auto` |
| 移动端 hover 粘滞 | 点完高亮不消失 | `@media (hover:hover)` 包裹 |
| CI 里比对缩略图字节 | 换台机器 libwebp 版本不同就误报 | 只比对文件集合与清单结构 |
