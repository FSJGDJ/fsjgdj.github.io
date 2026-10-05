# 博客美化方案（第二轮）

> 状态：**待确认**，本轮不写代码
> 整理日期：2026-10-05
> 前置文档：`docs/blog-redesign-plan.md`（毛玻璃、明暗主题、Landing 首屏、文章页目录 / 灯箱 / 复制按钮等均已在第一轮落地）
> 本轮定位：在现有底子上做增量美化，不推翻已有设计，不重复造已有功能。

---

## 一、现状盘点（已具备的能力）

审阅 `src/` 全部源码后的结论：第一轮重设计完成度很高，以下能力均已存在，本轮方案**不涉及**它们：

| 模块 | 现状 |
| --- | --- |
| 视觉基调 | 背景照片 + 毛玻璃面板 + 漂移光斑，明暗双主题（系统跟随 + 手动切换 + 防闪烁） |
| 首页 | 全屏 Landing（头像 / 名言 / 社交图标 / 下滑箭头）+ 作者名片卡（统计、社交、图标导航）+ 文章卡片流（字数、阅读时长、标签、进场动画） |
| 文章页 | 左侧 sticky 目录（滚动高亮）+ 移动端折叠目录、代码复制按钮、图片 Lightbox（键盘 / 手势 / 计数）、衬线标题、阅读时长 |
| 归档页 | 按年分组 + hover 动效 |
| 其他 | RSS、标签云（对数插值字号）、`prefers-reduced-motion` 全覆盖 |

当前肉眼可见的两个**硬伤**：

1. 中文衬线标题实际回退到宋体（见下文 A1）；
2. `<head>` 没有 description / OG 标签，分享到微信、Telegram 等没有卡片（见下文 D1）。

---

## 二、方案分四层

### A. 字体与排版 —— 最值得投入的一层

全站气质的地基，也是当前最大的短板。

| # | 项目 | 内容 | 工作量 |
| --- | --- | --- | --- |
| A1 | 中文衬线字体落地 | `--font-serif` 栈里的 Source Han Serif SC / Noto Serif SC 大多数访客没装，**实际渲染成宋体**。用 [cn-font-split](https://github.com/KonghaYao/cn-font-split) 把开源字体按需子集化成 woff2 自托管（按需分包，首屏增量约 1–2MB 且只加载用到的分片）。候选：**思源宋体**（杂志感，延续现有设计意图）或**霞鹜文楷 LXGW WenKai**（中文博客圈当下最流行的楷体感，更柔和） | 中 |
| A2 | 中英文混排间距 | Chrome 120+ 支持 CSS `text-autospace: normal`，一行代码让「用 ffmpeg 和 Node.js」这类混排自动加空隙，正文立刻精致（渐进增强，老浏览器忽略） | 极小 |
| A3 | 等宽字体落位 | `--font-mono` 里 JetBrains Mono / Cascadia Code 多数机器没有，会掉到 Consolas。代码块是拉丁字符集，子集化一份 JetBrains Mono woff2 仅几十 KB | 小 |

### B. 视觉细节打磨 —— 小改动，整体观感上台阶

| # | 项目 | 内容 | 工作量 |
| --- | --- | --- | --- |
| B1 | 滚动条 | Windows 默认宽滚动条很破坏毛玻璃气质；`::-webkit-scrollbar` + `scrollbar-width: thin` 定制为细圆角条 | 10 分钟 |
| B2 | `::selection` | 选中文字是浏览器默认蓝，改为 accent 半透明 | 10 分钟 |
| B3 | 阅读进度条 | 顶部 2px 细线随滚动填充 accent 色，长文阅读很需要 | 30 分钟 |
| B4 | 代码块语言徽章 | 右上角显示 `bash` / `js` 小标签（Shiki 已输出语言元数据，可低成本提取），与复制按钮并排 | 1 小时 |
| B5 | 代码块行号 | 长代码加行号，配合站内大量「逐行解释」型文章 | 1–2 小时 |
| B6 | 表格横向滚动 | 窄屏时表格会挤爆容器，包一层 `overflow-x: auto`（首列 nowrap 已处理，缺滚动容器） | 20 分钟 |
| B7 | 首屏打磨 | `config.ts` 的 `motto` 为空，首屏略单薄；填一句或加打字机 / 渐变色效果 | 30 分钟 |
| B8 | 暗色背景 | 暗色模式复用同一张亮色云海图 + 深色蒙纱；可给暗色单独压暗或换一张暗色背景图 | 1 小时 |

### C. 阅读体验增强 —— 文章页功能

| # | 项目 | 内容 | 工作量 |
| --- | --- | --- | --- |
| C1 | 上一篇 / 下一篇 | 现在文末只有「← 返回首页」，读完一篇就断头 | 小 |
| C2 | 相关文章 | 按标签重合度取 2–3 篇放文末 | 小 |
| C3 | 标签落地页 `/tags/[tag]` | `TagCloud.astro` 注释里已预留「供将来的 /tags 页共用」，现在点标签无反应——**最明显的半成品** | 小 |
| C4 | KaTeX + Mermaid | 数学公式与图表；Mermaid 建议构建期渲染成 SVG，不增加运行时 JS | 中 |
| C5 | 提示块 | GitHub 风格 `> [!NOTE]` / `> [!WARNING]` 渲染成彩色 callout，写踩坑记录好用 | 小 |
| C6 | 文章封面图 | schema 加可选 `cover` 字段，首页卡片与 OG 分享用；不填不显示，向后兼容 | 中 |
| C7 | 置顶 + 更新时间 | schema 加 `pinned` / `updated`，卡片显示「更新于」 | 小 |

### D. 站点级补全 —— 外部可见的品质

| # | 项目 | 内容 | 工作量 |
| --- | --- | --- | --- |
| D1 | SEO / 分享 meta（**建议必做**） | `Layout.astro` 的 `<head>` 现在只有 title 和 favicon——没有 `meta description`、没有 `og:title / og:description / og:image`。补齐后分享才有卡片 | 小 |
| D2 | 自动 OG 分享图 | 配合 C6，用 [satori](https://github.com/vercel/satori) 或 astro-og-canvas 给每篇文章生成标题卡片图 | 中 |
| D3 | 404 页面 | GitHub Pages 默认 404 是白页，做一个与站点同风格的 | 小 |
| D4 | 站内搜索 | [Pagefind](https://pagefind.app/) 是静态站搜索事实标准：构建时建索引、纯静态托管、支持中文分词 | 中 |
| D5 | 评论区 | [Giscus](https://giscus.app/zh-CN)（GitHub Discussions 驱动，零成本）或 Waline（需部署后端） | 中 |
| D6 | 页面过渡 | Astro `<ClientRouter />`（View Transitions），站内跳转平滑过渡，与毛玻璃风格很搭 | 小 |
| D7 | Sitemap + robots.txt | `@astrojs/sitemap` 一个集成的事 | 10 分钟 |
| D8 | 图片优化 | `bg.jpg` / 头像走 `astro:assets` 转 WebP/AVIF + 预加载；正文图片懒加载 | 中 |

---

## 三、建议实施顺序

- **第一轮（性价比最高，一天内）**：A1 字体子集化 → D1 meta/OG → B1–B3（滚动条 / 选中色 / 进度条）→ B6 表格滚动 → D3 404 → C3 标签页 + C1 上下篇导航。
  解决「宋体回退」和「分享无卡片」两个硬伤，其余全是小刀。
- **第二轮**：A3 等宽字体、B4–B5 代码块增强、C5 callout、D5 Giscus、D4 Pagefind、D6 View Transitions、B7–B8。
- **第三轮（随写文需要）**：C6 封面图 → D2 自动分享图、C4 KaTeX/Mermaid、C2 相关文章、C7 置顶、D7–D8。

---

## 四、参考资料

- [cn-font-split — 中文字体子集化](https://github.com/KonghaYao/cn-font-split)
- [Pagefind 官网](https://pagefind.app/) ／ [静态 Astro 站搜索实践（Reddit）](https://www.reddit.com/r/javascript/comments/1dov3eo/adding_search_to_static_astro_sites/)
- [Giscus](https://giscus.app/zh-CN)
- [satori — Vercel](https://github.com/vercel/satori)
- 2026 设计趋势参考：[DevInterface](https://www.devinterface.com)、[ZipWP](https://zipwp.com)（要点：bold minimalism、暗色模式已是默认预期、microinteractions）
