# 项目长期笔记（my-blog / Astro + Tailwind 博客）

## 硬性约束（用户明确要求）
- 展示结果一律给 **dev server 的 localhost 真实界面**，绝不给 dist 构建产物 HTML 文件。
- **git 操作由用户自己执行**，AI 不做任何 add / commit / push / stash / reset。
- 标题字体保持项目原规范，不要自作主张换 web 字体：`--font-serif` = `Source Han Serif SC / Noto Serif SC / Songti SC / STSong / SimSun`（Windows 上实际回退宋体，用户 2026-10-17 明确要求维持原状）。2026-10-05 曾装过霞鹜文楷 Lite 自托管分包（`public/fonts/lxgw/`，4.2MB），同日按用户要求**已全部撤销**，字体资源与安装脚本均已删除。
- 若日后确需自托管中文字体：`lxgw-wenkai-lite-webfont` npm 包本身就是按 unicode-range 切好的 97 个 woff2，可绕开本机不可达的 GitHub releases 与 20MB 源字体。
- 站点变量体系在 `Layout.astro` 的 `:root`：`--bg / --card / --text / --muted / --accent / --border / --code-bg / --code-text / --font-mono / --font-serif` 与三档动效 `--dur-fast(0.15s) / --dur-base(0.2s) / --dur-slow(0.3s) / --ease`。沿用此命名，不要另起一套。
- 站点基线风格：背景图 + 毛玻璃卡片 + 靛蓝强调色、标题衬线、首屏整屏居中 Landing、文章页正文不套卡片。明确不要：鼠标拖拽动画、花瓣特效。外部方案与之冲突必须先问。

## 环境事实（本机）
- GitHub（仓库与 releases）不可达；npm 走 `registry.npmmirror.com` 镜像；unpkg / jsDelivr / npmmirror 的 https 可达（经 `http_proxy`），**Node 22 的 `fetch` 也能走该代理**。
- Astro 入口：`node_modules/astro/bin/astro.mjs`（**不是** astro.js）；本机 PATH 里 npx 不可靠，直接用托管 node 跑这个文件。
- 托管 node 路径会变（出现过 `22.22.2-3` → `22.22.2-6`），用前先 `ls .workbuddy/binaries/node/versions/`。
- 浏览器自动化：`playwright-core` 已装在 `.workbuddy/binaries/node/workspace`，用本机 Chrome（`C:/Program Files/Google/Chrome/Application/chrome.exe`）驱动；**不要往博客项目里加任何依赖**。

## Astro / CSS 踩坑记录
- `.glass-panel` 的 `backdrop-filter` 会劫持后代 `fixed` 定位 → 阅读进度条、桌面 TOC 这类"相对视口"的元素必须渲染到 `glass-panel` 之外（命名插槽）。
- 跨组件覆盖 scoped 规则要用更高优先级选择器叠加（如 `:global(main.container.container-article)`）。
- 伪元素（`::-webkit-scrollbar`、`::selection`）写在组件 scoped `<style>` 里会因属性选择器落到伪元素上而**失效**，必须 `:global()` 包裹。
- **`grid-template-rows: 0fr` 折叠手风琴在"高度不定"的 grid 容器里不生效**：`0fr` 会被解析成 max-content，多个子项时只有第一行归零、其余隐式行原样保留。正确做法是 `max-height: 0 / <实测 scrollHeight px>` + `overflow: hidden`，并把实测高度写进 CSS 变量（如 `--toc-sub-h`）让过渡时长与内容高度匹配。
- grid/flex 折叠容器收起时要给内容加 `inert`（不只是 `aria-hidden`），否则键盘用户会 Tab 进不可见链接；展开时同步移除。
- 验证产物时的两个坑：① 页面样式会被抽离成 `dist/_astro/*.css`，只 grep HTML 会误判"样式没生效"；② Astro 会往标签属性里注入 `data-astro-cid-*`，`grep 'class="x">'` 这类精确匹配会漏。
- 测试脚本里：DOM 属性 `href="#中文"` 是原始中文，而 `a.hash` 属性返回**百分号编码**后的值，用 CSS 选择器按 hash 匹配会找不到元素——改用序号定位。