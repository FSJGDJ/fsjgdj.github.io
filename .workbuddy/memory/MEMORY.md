# 项目长期笔记（my-blog）

- 展示结果时给真实界面（dev server localhost 预览），不要给 dist 构建产物 HTML 文件——用户明确提出，必须遵守。
- 提交 git 由用户自己完成，AI 不提交。
- 头像/昵称/邮箱等个人信息集中在 `src/config.ts`；邮箱 fsjdg2025@163.com；昵称 FSJDG；站名"fsjdg的空间"。
- 参考风格来源：diary.fulitower.art（毛玻璃+背景图）、springbot.top / blog.ttdr.top（Argon 主题目录交互）。明确不要：鼠标拖拽动画、花瓣特效。
- 站点基线风格（优先于外部方案）：背景图 + 毛玻璃卡片 + 靛蓝强调色、标题用衬线字体、首屏整屏居中 Landing、文章页正文不套卡片。外部美化方案（如桌面《fsjgdj美化方案v2.md》的纯色卡片/无衬线标题/左右分栏）与之冲突时必须先问用户，不要直接照搬。
- 站点变量体系在 `Layout.astro`：--bg/--card/--text/--muted/--accent/--border/--code-bg/--code-text/--font-mono/--font-serif（沿用此命名，不要另起 --color-* 一套）。
- Astro 样式陷阱：跨组件覆盖 scoped 规则（如 Layout 的 `.container[data-astro-cid-*]`，优先级 0,2,0）必须叠加选择器提优先级；`.glass-panel` 的 backdrop-filter 会劫持后代 fixed 定位。grid 用 `align-items:start` 时 sticky 必须放在 grid item 本身（包含块是整行高的 grid area），放内部子元素会失效。同一文件的多个 Edit 必须串行，并行会被静默覆盖。
