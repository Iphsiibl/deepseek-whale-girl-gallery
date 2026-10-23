# DeepSeek 鲸鱼娘 · 角色图集

「吃白饭的蓝色大肥鱼」——社区共同养出来的 DeepSeek 拟人形象（鲸鱼娘）角色图集。

## 在线预览

**https://iphsiibl.github.io/deepseek-whale-girl-gallery/**

由 GitHub Pages 发布（分支 `main` → 目录 `/docs`）。

本地直接双击 `docs/index.html` 即可离线浏览：无需服务器、无外部请求、无跟踪脚本，禁用 JS 也能看全部图片。

## 目录结构

```
.
├── README.md           # 本文件
├── TUTORIAL.md         # 案例教程：静态画廊发布到 GitHub Pages 全流程
├── LICENSE             # CC BY-NC-SA 4.0 全文（适用于本仓库的整理与页面代码）
├── ATTRIBUTION.md      # 每张图片的作者与出处（CC BY 要求署名）
├── .github/workflows/  # CI：校验页面与图片一致性
├── tools/
│   ├── make_thumbs.py  # 生成多档展示版 WebP（480 / 960 / 1440 / 1920 宽）
│   ├── sync_srcset.py  # 把清单里的档位同步进页面 srcset / data-full
│   ├── check_gallery.py# 校验页面引用、缩略图清单、原图孤儿
│   ├── check_manifest.py # 比对清单结构（不比字节，避开 libwebp 版本差异）
│   ├── verify_browser.py # Playwright 浏览器端验证（功能 / 性能 / 布局 / 无障碍）
│   └── requirements.txt
└── docs/               # GitHub Pages 发布根目录
    ├── index.html      # 画廊页面（单文件，内联 CSS/JS）
    ├── .nojekyll       # 关闭 Jekyll 处理，图片原样发布
    ├── thumbs/         # 展示版 WebP（多档，按设备像素比选档）
    ├── sheets/         # 角色设定图原图（Q 版 / 成熟比例三视图）
    ├── moegirl/        # 萌娘百科「DeepSeek娘」条目收录原图
    ├── refs/           # 换装三视图原图（7 套）
    ├── gallery/        # 社区二创原图
    └── wallpaper/      # 场景壁纸原图
```

## 内容一览

| 分区 | 数量 | 说明 |
| --- | --- | --- |
| 角色设定图 | 2 | Q 版三视图、成熟比例三视图，均附完整生成 Prompt |
| 萌娘百科收录图 | 6 | 含流传最广的「女仆鲸鱼娘」原立绘（1152×2048）与条目头图（2732×4096） |
| 换装三视图 | 7 | 黑礼服人鱼 / 简约短裙 / 长裙 / 细节洛丽塔短裙 / Q 版 / 黑绿 / 黑红 |
| 社区二创 | 13 | Q 版设定图、素材扩展包、表情包、头像、变体 |
| 场景壁纸 | 3 | 1008×576 静帧 |
| **合计** | **31** | 原图 20.6 MB |

## 页面性能

展示版不压成单一尺寸，而是**按宽度分四档**，页面用 `srcset` + `sizes`
让浏览器按自己的屏幕和像素比挑一档：

| 档位 | 全量体积 | 典型用途 |
| --- | --- | --- |
| 480w | **954 KB** | 1x 屏（手机 / 桌面）首屏 |
| 960w | 2.4 MB | 2x 屏、灯箱 |
| 1440w | 2.0 MB | 灯箱高清（仅 11 张大图有此档） |
| 1920w | 395 KB | 灯箱高清（仅 2 张超大图有此档） |

Chromium 实测（1440×900 视口）：

| 场景 | 旧版 | 新版 | 降幅 |
| --- | --- | --- | --- |
| 1x 首屏 | 3.3 MB / 27 张 | **859 KB** / 26 张 | −74% |
| 1x 整页 | 3.4 MB / 31 张 | **963 KB** / 31 张 | −72% |
| 2x 首屏 | — | 2.3 MB / 26 张 | — |
| 手机 390×844 2x 首屏 | — | 579 KB / 5 张 | — |

旧版只发一种尺寸（长边 1600px），其中 **25 张原图长边本就 ≤1600px**，
所谓"缩略图"其实是原图重编码，一分钱没省；新版按宽度分档，
浏览器按自己的屏幕和像素比挑一档，画质反而更锐利。

> 仓库里 `docs/thumbs/` 存着**全部档位**（约 5.9 MB），访客只会下载其中一档。
> 档位多的意义在于高像素密度屏幕和灯箱能拿到更清晰的图，代价只是仓库体积。

页面本身还做了这些：

- `<img>` 全部带 `width`/`height`，零布局抖动（实测 CLS 0.0006）
- 灯箱支持键盘（`←` `→` `Esc` `Home` `End`）、触摸滑动、相邻图预加载
- 瀑布流按图片真实宽高比排布，竖构图立绘不再被压成小方块
- 移动端适配、`prefers-reduced-motion`、触摸设备不残留 hover 态
- Open Graph / Twitter 卡片、`sitemap.xml`、`robots.txt`

## 重新生成缩略图

```bash
pip install -r tools/requirements.txt

python tools/make_thumbs.py            # 增量生成
python tools/make_thumbs.py --clean    # 强制全量重建
python tools/make_thumbs.py --report   # 只看体积报告
python tools/sync_srcset.py            # 把清单里的档位同步进页面 srcset
python tools/check_gallery.py          # 校验页面与图片一致（CI 里跑的就是它）
python tools/check_manifest.py         # 比对清单结构与已提交版本
python tools/verify_browser.py --no-js # 浏览器端验证（需 pip install playwright）
```

加图流程：原图放进 `docs/<分区>/` → 在 `docs/index.html` 里加一张卡片 →
运行 `make_thumbs.py` 和 `sync_srcset.py` → 提交。
`check_gallery.py` 会挡住"加了图忘了生成缩略图""srcset 漏了档位"
"width/height 与原图不符""原图没进页面""缩略图生成了没人用"这五种情况。

完整做法见 [TUTORIAL.md](TUTORIAL.md)。

## 角色设定备忘

蓝色渐变长发（发根深海蓝 → 发尾浅青蓝）、头顶呆毛、头侧一对横向展开的**鲸鱼鳍状耳朵**、
深蓝白女仆装（白色蕾丝发箍、深蓝领结 + 椭圆蓝宝石胸针、围裙小鲸鱼刺绣、深蓝玛丽珍鞋）、
身后一条大鲸尾。人设标签为「傲娇嘴甜、聪明但懒、主食白饭、绝对拒绝被叫胖」，管用户叫「鱼片」。

## 形象谱系

1. **2025.06** — B 站 UP「上善无形」AI 创作原创角色「**溟月**」，确立蓝渐变发、呆毛、鲸鳍、鲸尾等基础特征
2. **2026.04** — UP「ZipZipPipe」以 GPT Image 2 融入 DeepSeek 元素，换上深蓝白女仆装，**女仆鲸鱼娘**成型
3. **2026.08.15** — DeepSeek 模型开始自行加载「鲸鱼娘」人格标签，官方半承认

> 注：该形象并非深度求索官方发布，立绘最初甚至是用竞品模型画的。

## 许可与署名

- 本仓库的**页面代码与整理工作**采用 [CC BY-NC-SA 4.0](LICENSE)（署名 — 非商业性使用 — 相同方式共享）。
- 仓库内的**每一张图片版权归各自作者所有**，许可条件以源站标注为准，详见 [ATTRIBUTION.md](ATTRIBUTION.md)。
- 整体角色形象源自「溟月」（CC BY-NC-SA 4.0）：需署名、**禁止商用**、衍生作品须以相同协议开放。
- 本仓库为社区同人整理，与深度求索公司无隶属或背书关系。
- 如你是相关权利人并希望移除内容，请提 issue。

## 主要来源

- [鲸鱼娘开源资产库](https://treapgogo.github.io/deepseek-whale-girl/) — 126 张社区画廊、Prompt、ComfyUI 工作流
- [萌娘百科「DeepSeek娘」](https://mzh.moegirl.org.cn/DeepSeek%E5%A8%98) — 条目与图片归档
- [AI 萌图 · 大肥鱼娘三视图设定集](https://aigengtu.com/refs?lang=zh-Hant) — 7 套换装参考
- [dsh-whale-girl-wallpaper](https://github.com/QWEQ-CELL-DEL/dsh-whale-girl-wallpaper) — DeepSeek Harness 社区皮肤壁纸
- [Civitai · DeepSeek 鲸鱼娘 LoRA](https://civitai.red/models/2697171) — Krea 2 / IllustriousXL / Anima 三版本
- [PixAI 作品集](https://pixai.art/uk/artwork/2048994181303798139)
