# DeepSeek 鲸鱼娘 · 角色图集

「吃白饭的蓝色大肥鱼」——社区共同养出来的 DeepSeek 拟人形象（鲸鱼娘）角色图集。
一个纯静态、离线可浏览的网页画廊，通过 GitHub Pages 发布。

## 在线预览

**https://iphsiibl.github.io/deepseek-whale-girl-gallery/**

由 GitHub Pages 发布（分支 `main` → 目录 `/docs`）。

本地直接双击 `docs/index.html` 即可离线浏览，无需服务器、无外部请求、无跟踪脚本。

## 目录结构

```
.
├── README.md           # 本文件
├── LICENSE             # CC BY-NC-SA 4.0 全文（适用于本仓库的整理与页面代码）
├── ATTRIBUTION.md      # 每张图片的作者与出处（CC BY 要求署名）
├── tools/
│   └── make_thumbs.py  # 生成画廊展示版 WebP（长边 1600px / 质量 80）
└── docs/               # GitHub Pages 发布根目录
    ├── index.html      # 画廊页面
    ├── .nojekyll       # 关闭 Jekyll 处理，图片原样发布
    ├── thumbs/         # 展示版 WebP 缩略图（31 张，3.4 MB）
    ├── sheets/         # 角色设定图原图（Q 版 / 成熟比例三视图）
    ├── moegirl/        # 萌娘百科「DeepSeek娘」条目收录原图
    ├── refs/           # 换装三视图原图（7 套）
    ├── gallery/        # 社区二创原图
    └── wallpaper/      # 场景壁纸原图
```

> 页面展示 `thumbs/` 下的 WebP 副本（原图 20.6 MB → 3.4 MB，压缩 6.1 倍），
> 点击图片或「原图」链接可打开未压缩原文件。重新生成缩略图：
> `python tools/make_thumbs.py`

## 内容一览

| 分区 | 数量 | 说明 |
| --- | --- | --- |
| 角色设定图 | 2 | Q 版三视图、成熟比例三视图，均附完整生成 Prompt |
| 萌娘百科收录图 | 6 | 含流传最广的「女仆鲸鱼娘」原立绘（2732×4096） |
| 换装三视图 | 7 | 黑礼服人鱼 / 简约短裙 / 长裙 / 细节洛丽塔短裙 / Q 版 / 黑绿 / 黑红 |
| 社区二创 | 13 | Q 版设定图、素材扩展包、表情包、头像、变体 |
| 场景壁纸 | 3 | 2560×1440 静帧 |
| **合计** | **31** | 约 20 MB |

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
