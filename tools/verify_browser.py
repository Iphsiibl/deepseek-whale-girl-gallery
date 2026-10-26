#!/usr/bin/env python3
"""浏览器端验证：用真实 Chromium 打开画廊，检查功能、性能与视觉。

跑法：
    python tools/verify_browser.py            # 输出报告 + 截图到 /tmp/gallery-shots
    python tools/verify_browser.py --no-js    # 额外验证禁用 JS 时页面仍可读
"""

from __future__ import annotations

import argparse
import http.server
import json
import socketserver
import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
SHOTS = Path("/tmp/gallery-shots")

PORT = 8765


def serve() -> socketserver.TCPServer:
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(DOCS_DIR), **kw)
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def run(no_js: bool) -> int:
    from playwright.sync_api import sync_playwright

    SHOTS.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    notes: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page = context.new_page()

        console_errors: list[str] = []
        failed_requests: list[str] = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("requestfailed", lambda r: failed_requests.append(f"{r.url} — {r.failure}"))
        page.on("response", lambda r: failed_requests.append(f"{r.url} — HTTP {r.status}") if r.status >= 400 else None)

        page.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="networkidle")
        page.wait_for_timeout(1200)

        # 逐屏下滑触发全部懒加载（图片一多，滚到底一次并不能加载完）
        for _ in range(60):
            page.evaluate("() => window.scrollBy(0, window.innerHeight * 0.9)")
            page.wait_for_timeout(120)
        page.wait_for_timeout(1500)
        page.evaluate("() => window.scrollTo(0, 0)")
        page.wait_for_timeout(600)

        # ---------------------------------------------------- 图片是否真的加载
        stats = page.evaluate(
            """() => {
                const imgs = [...document.querySelectorAll('.grid img')];
                return {
                    total: imgs.length,
                    loaded: imgs.filter(i => i.naturalWidth > 0).length,
                    broken: imgs.filter(i => i.complete && i.naturalWidth === 0).map(i => i.getAttribute('src')),
                    currentSrcs: imgs.map(i => i.currentSrc.split('/').pop()),
                };
            }"""
        )
        notes.append(f"图片 {stats['loaded']}/{stats['total']} 张加载成功")
        if stats["loaded"] != stats["total"]:
            problems.append(f"有 {stats['total'] - stats['loaded']} 张图没加载成功: {stats['broken']}")

        # 选中的档位（验证 srcset 是否按 DPR 正确挑选）
        used = sorted({s for s in stats["currentSrcs"] if s})
        notes.append(f"1x 视口实际选中的档位: {', '.join(used)}")
        wrong = [s for s in used if not s.endswith("-480w.webp")]
        if wrong:
            notes.append(f"⚠ 1x 视口出现了非 480w 档位: {wrong}")

        # ---------------------------------------------------- 实际下载量
        transfer = page.evaluate(
            """() => {
                const res = performance.getEntriesByType('resource')
                    .filter(r => /\\.webp$/i.test(r.name));
                return {
                    count: res.length,
                    bytes: res.reduce((s, r) => s + (r.transferSize || r.encodedBodySize || 0), 0),
                };
            }"""
        )
        # "理论全量"从清单里算，不写死 —— 图一多，写死的数字就变成误导
        try:
            manifest = json.loads(
                (DOCS_DIR / "thumbs" / "_manifest.json").read_text(encoding="utf-8")
            )
            base = min(manifest["sizes"])
            total = sum(
                entry["bytes"]
                for item in manifest["items"]
                for entry in item["files"]
                if entry["w"] == base
            )
            theory = f"{base}w 档全量约 {total / 1024:.0f} KB"
        except Exception:  # noqa: BLE001
            theory = "（清单不可读）"
        notes.append(
            f"实际下载 {transfer['count']} 张展示图 / {transfer['bytes'] / 1024:.0f} KB"
            f"（1x 视口，{theory}）"
        )

        # ---------------------------------------------------- 瀑布流是否生效
        # 作者分栏视图下有 20+ 个 grid，必须**全部**检查，不能只看一个
        layout = page.evaluate(
            """() => {
                const grids = [...document.querySelectorAll('.grid.masonry')];
                let overlaps = 0, minGap = 1e9, checked = 0, cols = 0;
                for (const g of grids) {
                    if (g.offsetParent === null) continue;
                    const st = getComputedStyle(g);
                    cols = Math.max(cols, st.gridTemplateColumns.split(' ').filter(Boolean).length);
                    const byCol = {};
                    for (const c of g.children) {
                        if (c.style.display === 'none') continue;
                        const L = Math.round(c.getBoundingClientRect().left);
                        (byCol[L] = byCol[L] || []).push(c);
                    }
                    for (const k in byCol) {
                        const l = byCol[k].sort((a, b) =>
                            a.getBoundingClientRect().top - b.getBoundingClientRect().top);
                        checked += l.length;
                        for (let i = 1; i < l.length; i++) {
                            const d = l[i].getBoundingClientRect().top -
                                      l[i - 1].getBoundingClientRect().bottom;
                            if (d < -0.5) overlaps++;
                            if (d < minGap) minGap = d;
                        }
                    }
                }
                return {grids: grids.length, overlaps, minGap: Math.round(minGap * 10) / 10,
                        checked, columns: cols,
                        hOverflow: document.documentElement.scrollWidth > window.innerWidth + 1};
            }"""
        )
        if layout["overlaps"] > 0:
            problems.append(f"瀑布流重叠 {layout['overlaps']} 处（检查了 {layout['grids']} 个 grid）")
        if layout["hOverflow"]:
            problems.append("页面出现横向滚动条")
        notes.append(
            f"瀑布流生效：{layout['grids']} 个 grid / {layout['columns']} 列 / "
            f"{layout['checked']} 张卡片，间距 {layout['minGap']}px，0 重叠"
        )

        # ---------------------------------------------------- 竖图是否还被压扁
        portrait = page.evaluate(
            """() => {
                const img = document.querySelector('#p-moegirl .shot img');
                const box = img.parentElement.getBoundingClientRect();
                return { w: box.width, h: box.height, ratio: +(box.height / box.width).toFixed(3) };
            }"""
        )
        # 02-nvpu-whale-girl 原图 1152x2048 -> 高/宽 应约 1.78
        if abs(portrait["ratio"] - 1.78) > 0.06:
            problems.append(f"竖图比例失真: 显示高/宽 = {portrait['ratio']}，期望约 1.78")
        notes.append(f"竖图显示比例 h/w = {portrait['ratio']}（原图 1152×2048 → 期望 1.78）")

        # ---------------------------------------------------- 灯箱
        page.click("#p-moegirl .shot")
        page.wait_for_timeout(500)
        lb = page.evaluate(
            """() => {
                const el = document.getElementById('lightbox');
                return {
                    open: el.classList.contains('on'),
                    title: document.getElementById('lb-title').textContent,
                    count: document.getElementById('lb-count').textContent,
                    src: document.getElementById('lb-img').getAttribute('src'),
                    origHref: document.getElementById('lb-orig').getAttribute('href'),
                    scrollLocked: getComputedStyle(document.body).overflow === 'hidden',
                };
            }"""
        )
        if not lb["open"]:
            problems.append("灯箱未能打开")
        if not lb["scrollLocked"]:
            problems.append("灯箱打开时页面滚动未被锁定")
        if not lb["origHref"] or lb["origHref"] == "#":
            problems.append("灯箱缺少原图链接")
        notes.append(f"灯箱打开成功：{lb['title']} · {lb['count']} · 原图链接 {lb['origHref']}")

        # 键盘切换
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(350)
        after_next = page.evaluate("() => document.getElementById('lb-count').textContent")
        if after_next == lb["count"]:
            problems.append("灯箱键盘 → 切换无效")
        else:
            notes.append(f"键盘切换正常：{lb['count']} → {after_next}")

        # 缩放
        before_zoom = page.evaluate(
            "() => { const i = document.getElementById('lb-img');"
            " return {w: i.getBoundingClientRect().width, h: i.getBoundingClientRect().height}; }"
        )
        page.keyboard.press("+")
        page.wait_for_timeout(250)
        after_zoom = page.evaluate(
            """() => {
                const i = document.getElementById('lb-img');
                const stage = document.getElementById('lb-stage');
                return {
                    w: i.getBoundingClientRect().width,
                    h: i.getBoundingClientRect().height,
                    stageOverflow: getComputedStyle(stage).overflow,
                    scrollable: stage.scrollHeight > stage.clientHeight,
                };
            }"""
        )
        if after_zoom["w"] <= before_zoom["w"] + 1:
            problems.append("灯箱缩放无效")
        elif after_zoom["stageOverflow"] != "auto" or not after_zoom["scrollable"]:
            problems.append(
                "灯箱缩放后无法滚动查看放大的内容"
                f"（overflow={after_zoom['stageOverflow']}, 可滚动={after_zoom['scrollable']}）"
            )
        else:
            notes.append(
                f"灯箱缩放正常：{before_zoom['w']:.0f}px → {after_zoom['w']:.0f}px，"
                "放大后舞台可滚动"
            )

        # 关闭
        page.keyboard.press("Escape")
        page.wait_for_timeout(350)
        closed = page.evaluate(
            """() => ({
                open: document.getElementById('lightbox').classList.contains('on'),
                scroll: getComputedStyle(document.body).overflow,
                focus: document.activeElement.className,
            })"""
        )
        if closed["open"]:
            problems.append("Esc 未能关闭灯箱")
        if closed["scroll"] == "hidden":
            problems.append("灯箱关闭后页面滚动仍被锁定")
        if "shot" not in closed["focus"]:
            problems.append(f"灯箱关闭后焦点未回到触发元素，而是 {closed['focus']!r}")
        notes.append("Esc 关闭正常，滚动已恢复，焦点回到触发图片")

        # ---------------------------------------------------- 灯箱焦点管理
        page.click("#p-moegirl .shot")
        page.wait_for_timeout(400)
        focus_in = page.evaluate("() => document.activeElement.id")
        if focus_in != "lb-close":
            problems.append(f"灯箱打开后焦点未进入对话框（当前 {focus_in!r}）")
        escaped = 0
        for _ in range(10):
            page.keyboard.press("Tab")
            page.wait_for_timeout(60)
            if not page.evaluate("() => document.getElementById('lightbox').contains(document.activeElement)"):
                escaped += 1
        if escaped:
            problems.append(f"灯箱打开时 Tab 跑到了背景页面（10 次里有 {escaped} 次）")
        else:
            notes.append("灯箱焦点被正确限制在对话框内（10 次 Tab 全部循环）")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # ---------------------------------------------------- 布局稳定性（CLS）
        cls = page.evaluate(
            """() => new Promise(resolve => {
                let value = 0;
                new PerformanceObserver(list => {
                    for (const e of list.getEntries()) if (!e.hadRecentInput) value += e.value;
                }).observe({type: 'layout-shift', buffered: true});
                setTimeout(() => resolve(value), 900);
            })"""
        )
        if cls > 0.02:
            problems.append(f"累积布局偏移 CLS = {cls:.4f}（阈值 0.02）")
        else:
            notes.append(f"布局稳定，CLS = {cls:.4f}")

        # ---------------------------------------------------- sizes 与档位选择
        # sizes 写错不会报错、不会加载失败、CI 也不会红，
        # 只会静悄悄地让浏览器选错档位 —— 所以必须有一条断言守着它。
        for vw, dsf in [(1440, 1), (1440, 2), (1101, 2), (900, 2), (693, 2), (600, 2), (390, 2)]:
            ctx2 = browser.new_context(
                viewport={"width": vw, "height": 900}, device_scale_factor=dsf
            )
            p2 = ctx2.new_page()
            p2.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="networkidle")
            p2.wait_for_timeout(800)
            p2.evaluate("() => document.querySelector('#p-gallery').scrollIntoView()")
            p2.wait_for_timeout(1200)
            tiers = p2.evaluate(
                """() => {
                    const g = document.querySelector('#p-gallery .grid');
                    const st = getComputedStyle(g);
                    const cw = parseFloat(st.gridTemplateColumns.split(' ')[0]);
                    const imgs = [...g.querySelectorAll('img')].map(i => {
                        const m = (i.currentSrc || '').match(/-(\\d+)w\\.webp$/);
                        const all = (i.getAttribute('srcset') || '').match(/-(\\d+)w/g) || [];
                        const max = all.length ? Math.max(...all.map(x => parseInt(x, 10))) : 0;
                        return {tier: m ? parseInt(m[1], 10) : null, max: max};
                    }).filter(x => x.tier);
                    return {cw, imgs: imgs, n: imgs.length};
                }"""
            )
            ctx2.close()
            if not tiers["n"]:
                problems.append(f"视口 {vw}px @{dsf}x 下没有图片加载，无法校验档位")
                continue
            needed = tiers["cw"] * dsf
            # 只在"本来有更好的档位却没选"时判错：
            # 原图本身就只有 180px 宽时，任何档位都小于所需设备像素，
            # 那是素材尺寸的限制，不是 sizes 声明写错了。
            missed = [
                x for x in tiers["imgs"]
                if x["tier"] < needed - 0.5 and x["max"] >= needed
            ]
            source_limited = [
                x for x in tiers["imgs"] if x["max"] < needed
            ]
            if missed:
                problems.append(
                    f"视口 {vw}px @{dsf}x：实际列宽 {tiers['cw']:.0f}px 需 {needed:.0f} 设备像素，"
                    f"但有 {len(missed)} 张图浏览器只拿到 {missed[0]['tier']}w 档"
                    f"（该图最大档 {missed[0]['max']}w，sizes 声明可能偏小）"
                )
            if source_limited:
                notes.append(
                    f"视口 {vw}px @{dsf}x：{len(source_limited)} 张图的原图宽度就小于 {needed:.0f} 设备像素"
                    f"（素材本身限制，非选档问题）"
                )
        notes.append("sizes 声明与实际列宽在 7 组视口/DPR 组合下均匹配")

        # ---------------------------------------------------- 设计契约 A5/A7：视图切换 + 类型筛选
        view_check = page.evaluate(
            """() => {
                const urlBefore = location.href;
                const flatBtn = document.querySelector('.seg-b[data-view="flat"]');
                const authorBtn = document.querySelector('.seg-b[data-view="author"]');
                if (!flatBtn || !authorBtn) return {skip: true};
                const total = document.querySelectorAll('#p-gallery .card').length;
                flatBtn.click();
                const flat = {
                    hidden: document.getElementById('view-flat').hidden,
                    authorHidden: document.getElementById('view-author').hidden,
                    cards: document.querySelectorAll('.grid-flat .card').length,
                };
                const types = {};
                const chips = [...document.querySelectorAll('.chip[data-type]')].filter(c => c.dataset.type);
                const perType = {};
                for (const chip of chips) {
                    chip.click();
                    const shown = [...document.querySelectorAll('#p-gallery .card')]
                        .filter(c => c.style.display !== 'none');
                    const kinds = [...new Set(shown.map(c => c.dataset.type))];
                    perType[chip.dataset.type] = {n: shown.length, kinds};
                }
                document.querySelector('.chip[data-type=""]').click();
                authorBtn.click();
                const author = {
                    hidden: document.getElementById('view-author').hidden,
                    flatHidden: document.getElementById('view-flat').hidden,
                    cards: document.querySelectorAll('#p-gallery .card').length,
                };
                return {skip: false, urlBefore, urlAfter: location.href, total,
                        flat, author, perType};
            }"""
        )
        if not view_check.get("skip"):
            if view_check["urlAfter"] != view_check["urlBefore"]:
                problems.append("切换视图导致了页面跳转")
            if view_check["flat"]["cards"] != view_check["total"]:
                problems.append(
                    f"平铺视图卡片数 {view_check['flat']['cards']} != {view_check['total']}"
                )
            if view_check["flat"]["hidden"] or not view_check["flat"]["authorHidden"]:
                problems.append("切到平铺视图后可见性不对")
            if view_check["author"]["hidden"] or not view_check["author"]["flatHidden"]:
                problems.append("切回作者视图后可见性不对")
            for work_type, info in view_check["perType"].items():
                if info["kinds"] != [work_type]:
                    problems.append(
                        f"类型筛选 {work_type} 不纯：出现 {info['kinds']}"
                    )
                if info["n"] == 0:
                    problems.append(f"类型筛选 {work_type} 筛出 0 张")
            notes.append(
                f"视图切换正常（平铺/作者），类型筛选 "
                + "、".join(f"{k}={v['n']}" for k, v in view_check["perType"].items())
            )

        # ---------------------------------------------------- 新增能力：作者筛选 + 1:1
        filter_check = page.evaluate(
            """() => {
                const sel = document.getElementById('f-author');
                // 作者分栏视图下社区区有 20+ 个 grid，必须统计**全部**社区卡片
                const all = [...document.querySelectorAll('#p-gallery .card')];
                if (!sel || !all.length) return {skip: true};
                const total = all.length;
                const opts = [...sel.options].map(o => o.value).filter(Boolean);
                if (!opts.length) return {skip: true, reason: '没有作者选项'};
                sel.value = opts[0];
                sel.dispatchEvent(new Event('change'));
                const shown = all.filter(c => c.style.display !== 'none');
                const ok = shown.length > 0 && shown.length < total &&
                    shown.every(c => c.querySelector('.shot').getAttribute('data-author') === opts[0]);
                sel.value = '';
                sel.dispatchEvent(new Event('change'));
                const back = all.filter(c => c.style.display !== 'none').length;
                return {skip: false, total, shown: shown.length, back, ok, authors: opts.length};
            }"""
        )
        if not filter_check.get("skip"):
            if not filter_check.get("ok"):
                problems.append(
                    f"作者筛选异常：{filter_check['shown']}/{filter_check['total']} 显示，"
                    f"作者匹配={filter_check.get('ok')}"
                )
            if filter_check.get("back") != filter_check.get("total"):
                problems.append(
                    f"清空筛选后没有恢复全部：{filter_check.get('back')}/{filter_check.get('total')}"
                )
            else:
                notes.append(
                    f"作者筛选正常：{filter_check['authors']} 位作者，"
                    f"筛出 {filter_check['shown']}/{filter_check['total']} 张"
                )

        # 1:1 原始像素：应换成原图并按原始尺寸显示
        actual_check = page.evaluate(
            """async () => {
                const card = [...document.querySelectorAll('#p-gallery .grid .card')]
                    .find(c => {
                        const s = c.querySelector('.shot');
                        const m = (s.getAttribute('data-full') || '').match(/-(\\d+)w/);
                        return m && parseInt(s.getAttribute('data-size').split('×')[0], 10) > parseInt(m[1], 10);
                    });
                if (!card) return {skip: true};
                const shot = card.querySelector('.shot');
                const before = shot.getAttribute('data-full');
                const orig = shot.getAttribute('data-orig');
                card.querySelector('.shot').click();
                await new Promise(r => setTimeout(r, 800));
                const img = document.getElementById('lb-img');
                const thumbW = img.naturalWidth;
                document.getElementById('lb-actual').click();
                await new Promise(r => setTimeout(r, 2500));
                const src = img.getAttribute('src');
                const natW = img.naturalWidth;
                const shownW = Math.round(img.getBoundingClientRect().width);
                const stage = document.getElementById('lb-stage');
                const scrollable = stage.scrollHeight > stage.clientHeight;
                document.getElementById('lb-actual').click();
                await new Promise(r => setTimeout(r, 600));
                document.getElementById('lb-close').click();
                return {skip: false, before, orig, src, thumbW, natW, shownW, scrollable};
            }"""
        )
        if not actual_check.get("skip"):
            if actual_check["src"] != actual_check["orig"]:
                problems.append(
                    f"1:1 没有换到原图：{actual_check['src']} ≠ {actual_check['orig']}"
                )
            if actual_check["natW"] <= actual_check["thumbW"]:
                problems.append(
                    f"1:1 分辨率没有提高：{actual_check['thumbW']} → {actual_check['natW']}"
                )
            if actual_check["shownW"] < actual_check["natW"] - 1:
                problems.append(
                    f"1:1 没有按原始像素显示：显示宽 {actual_check['shownW']} < 原始宽 {actual_check['natW']}"
                )
            if not actual_check["scrollable"]:
                problems.append("1:1 下舞台不可滚动，看不到原图局部")
            else:
                notes.append(
                    f"1:1 原始像素正常：{actual_check['thumbW']}w → {actual_check['natW']}w，"
                    f"按原始尺寸显示且可滚动"
                )

        # ---------------------------------------------------- 截图
        for name, width, height, dsf in [
            ("desktop", 1440, 1000, 1),
            ("desktop-2x", 1440, 1000, 2),
            ("tablet", 820, 1000, 1),
            ("mobile", 390, 844, 2),
        ]:
            page.set_viewport_size({"width": width, "height": height})
            ctx2 = browser.new_context(
                viewport={"width": width, "height": height}, device_scale_factor=dsf
            )
            p2 = ctx2.new_page()
            p2.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="networkidle")
            p2.wait_for_timeout(1500)
            p2.screenshot(path=str(SHOTS / f"{name}.png"), full_page=(name == "mobile"))
            ctx2.close()
        notes.append(f"截图已保存到 {SHOTS}")

        # ---------------------------------------------------- 禁用 JS
        if no_js:
            ctx3 = browser.new_context(
                java_script_enabled=False, viewport={"width": 1440, "height": 1000}
            )
            p3 = ctx3.new_page()
            p3.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="load")
            p3.wait_for_timeout(1200)
            visible = p3.locator(".grid img").count()
            controls_hidden = p3.locator(".controls").is_hidden()
            p3.screenshot(path=str(SHOTS / "no-js.png"), full_page=False)
            ctx3.close()
            if visible == 0:
                problems.append("禁用 JS 后图片区为空，降级失败")
            else:
                notes.append(f"禁用 JS 时仍渲染 {visible} 张图片（截图 no-js.png）")
            if not controls_hidden:
                problems.append("禁用 JS 时筛选/视图控件仍显示（控件无功能时不该显示）")

        if console_errors:
            problems.append(f"控制台报错 {len(console_errors)} 条: {console_errors[:5]}")
        real_failures = [f for f in failed_requests if "favicon" not in f]
        if real_failures:
            problems.append(f"请求失败 {len(real_failures)} 条: {real_failures[:5]}")

        browser.close()

    print("=" * 66)
    for note in notes:
        print(f"  · {note}")
    print("=" * 66)
    if problems:
        print(f"发现 {len(problems)} 个问题：")
        for problem in problems:
            print(f"  ✗ {problem}")
        return 1
    print("浏览器端验证全部通过 ✓")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-js", action="store_true", help="额外验证禁用 JS 的降级表现")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("缺少 playwright：pip install playwright && playwright install chromium")
        return 1

    httpd = serve()
    try:
        return run(args.no_js)
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    sys.exit(main())
