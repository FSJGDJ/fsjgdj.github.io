---
title: '向量数据库没死，只是不再是默认： Claude Code 弃用 RAG'
description: 'Anthropic 在 2025 年 5 月把向量检索从 Claude Code 里删掉，只留 grep。这篇文章梳理这次转向的四个理由、即时上下文加载范式、benchmark 证据与五种变体，并算一算我自己这套小站在这个范式下的账。'
pubDate: 2026-10-03
tags: ['AI', 'Agent', '检索']
---

## 前言

昨天我排查一个「改了样式但页面没变化」的问题，走了这么几步：

1. `grep` 构建产物 CSS，确认新规则**确实被编译进去了**
2. 对比选择器优先级，发现布局的 `.container[data-astro-cid]` 是 `(0,2,0)`，我写的是 `(0,1,1)` —— 数字上输了
3. 修掉，浏览器读 `computed style` 复验，确认左边距真的变成了 440px

如果第 1 步就收工，我会得出「改好了」的结论，然后被用户打回。

昨天下午刷到一篇讲 Claude Code 的文章，标题很唬人：*向量数据库已死*。核心是一个我**每天都在用、却没意识到它是个架构决策**的东西——`grep`。Anthropic 在 2025 年 5 月把向量检索整个从 Claude Code 里拿掉了，换成一堆「刻意无聊」的 shell 工具。这篇文章想把这套转向讲清楚，并算一算它对我这个小博客站到底意味着什么。

## 一、一次没引起足够重视的删除

2025 年 5 月，Anthropic 删掉了 Claude Code 里的嵌入管线、本地向量库和分块启发式。Claude Code 的作者 Boris Cherny 后来在 Latent Space 播客里说，结果是 `outperformed everything, by a lot, and this was surprising`。

他们原本**预期**工具驱动的检索会更差，做好了为运维简单性牺牲质量的准备，结果反了。

给出的理由收敛成四条：

| 理由 | 关键点 |
| --- | --- |
| 准确 | 一个驱动 `grep` 迭代的模型能不断精炼查询、看相邻文件、跟随 import、自我纠错；单次 embedding 查找做不到 |
| 新鲜 | 读文件系统就是读当前字节，改完 100ms 后问就是新内容；向量索引要等下一轮重新嵌入 |
| 安全 | 私有代码的向量索引就是这份代码的另一个副本，躺在别的设施上，访问控制通常比源仓库更弱 |
| 可靠 | 组件更少：没有会漂移的嵌入模型、没有会挂的向量库、没有滞后的重建管线 |

Cat Wu 的总结最干净：Claude 非常擅长 agentic 检索，你用它能拿到同样的准确度，而部署故事干净得多。

## 二、向量检索在代码上为什么会翻车

SWE-bench 最早那个 RAG baseline 是最简单的三件套：分块、嵌入、取 top-k、改代码。它拿到 **1.96%**。第一个工具化的 agent（SWE-agent，用 `open_file` / `scroll_down` / `edit_lines`）跳到 **12.47%**。到 2026 年，榜单前列全是 80% 以上的 agentic 系统，**没有一个靠向量检索**。

原文归纳了五条失败模式，我认为是这套论证里最有价值的部分：

1. **语义相似 ≠ 相关。** embedding 把 import、类型定义、调用图这些显式结构全压平了，而代码里最重要的关系恰恰是结构性的。
2. **标识符本身就是搜索。** 问「`processPayment` 在哪定义」要的是精确匹配，向量会召回 `handlePayment` 这种误报，也可能把真正的定义挤下去。
3. **索引永远是错的。** 代码在漂移，每次提交让一部分索引失效；持续重建又贵又追不上。
4. **索引是一笔负债。** 见上面安全那条。
5. **单次检索是脆弱的。** top-k 只给一次机会，第一次没命中，它就会自信地生成错代码。

第 2 条和第 5 条合起来是最致命的：**代码检索里「精确定位」是主任务，「语义泛化」是次要任务**，而 top-k 把两者的优先级搞反了。

## 三、即时上下文加载：检索从系统变成行为

Anthropic 在 2025 年 9 月的工程博客里给这个做法起了名字：**just-in-time context loading（即时上下文加载）**。它和传统 RAG 划了一条很清晰的界线：

- **传统 RAG = pre-inference retrieval**：一切都预先嵌入、存库、查询时取，把「模型可能需要的所有东西」提前预测好并建索引。
- **JIT 加载**：agent 只维护轻量标识符（文件路径、查询、链接），运行时用工具把引用动态拉进上下文。**什么都不预载。**

更深一层的变化是**上下文窗口的形状**变了。RAG 里 token 花在你**猜**相关的 chunk 上；JIT 里 token 只花在 agent 判断相关的 chunk 上，其余全部跳过。

代价是 JIT 最终仍会填满窗口，所以 Claude Code 配了一条五层压缩管道兜底：

```text
budget reduction → snip → microcompact → context collapse → auto-compact
   先丢最不相关的     去掉冗余工具输出  逐条总结过长消息   折叠早期轮次      最终总结
```

### 控制循环长什么样

整个模式的形状朴素得有点反直觉：

```text
plan → glob/grep → read candidates → refine query
     → repeat（或 spawn subagent）→ compact → answer
```

和 Self-RAG、CRAG 这类 agentic RAG 是同一个形状，唯一的区别是：**agent 和字节之间没有预建索引**。检索器就是 agent 当时选中的那个 shell 命令。

## 四、一套刻意无聊的工具

Claude Code 暴露给模型的检索面小得出奇：

- **Glob** —— 路径模式匹配，token 成本近乎为零
- **Grep** —— 基于 ripgrep 的正则内容搜索
- **Read** —— 把文件完整或部分读进上下文
- **Bash** —— 兜底，处理长尾（`tail`、`head`、`jq`、`git log`、带谓词的 `find`）
- **Explore 子代理** —— 只读的独立 agent，有自己的上下文窗口，用于并行探索

设计原则被总结成几条很硬的话：工具要自包含、抗错、用途极其清晰；**如果一个人类工程师都说不清某场景该用哪个工具，就别指望 AI 做得更好**。模型永远不需要在 `find_file_by_name` / `search_file_by_path` / `locate_file` 之间做选择——每种问题形状只有一个工具。

一篇对 Claude Code 源码的逆向研究给了个更有意思的数字：54 个内置工具里，**只有 1.6% 是 AI 决策逻辑**，其余 98.4% 是运维基础设施、上下文管理、权限、派发、压缩。决策层很小，检索与上下文管理层很大。

## 五、证据

最严谨的公开对比来自 Subramanian 等人的《Keyword Search Is All You Need》（AAAI 2026）：同样的模型、同样的六个数据集、同样的评测框架，唯一区别是检索器——一边是知识库 + Titan 文本嵌入，一边是一个只调用 `pdfmetadata` / `rga` / `pdfgrep` 的 ReAct agent。

| 指标 | 分数 | 相当于向量 RAG 的 |
| --- | --- | --- |
| Faithfulness | 0.81 vs 0.86 | 94.5% |
| Context Recall | 0.68 vs 0.77 | 88.0% |
| Answer Correctness | 0.59 vs 0.65 | 91.5% |

结论一句话：向量数据库对高质量检索**不是必需的**。

架构层面意义更大的一个结果来自 Search-R1：把检索策略本身用强化学习训出来，模型在推理中途发出 `<search>query</search>`，用结果奖励塑造「何时搜、搜什么、何时够」。Qwen2.5-7B 上七个 QA 数据集平均 EM **0.431**，RAG 基线 0.304，相对提升 24%。

这一步的分量在于：**一旦检索是工具调用，它就成了可学习策略**。你能用造推理模型的那套 RL 机器把 agent 训成更好的检索器——这在冻结的嵌入模型上做不到。

至于 Anthropic 自家的多 agent 研究系统「比单个 Opus 高 90.2%」这个数字，我建议连着它的限定条件一起记：它比的是广度优先的任务（研究、跨来源找所有东西），代价约 15 倍 token，而且**对编码这类强串行依赖的任务效果更差**。

## 六、五种变体

| 变体 | 代表 | 赌的是什么 |
| --- | --- | --- |
| 纯 agentic | Claude Code、Devin | 在持续变化的代码库上，循环里的 ripgrep 胜过任何冻结的嵌入 |
| 混合 lexical + semantic | Cursor、Sourcegraph Amp | 精确符号用 grep，概念查询用语义，agent 按查询形态选 |
| 结构 / AST 感知 | Cline、Probe、ast-grep | 按语法模式而非字符串搜，`fetch().then(...)` 改 `await` 这类查询 grep 表达不出 |
| 专用检索模型 | Windsurf SWE-grep、Chroma Context-1 | 用小模型换延迟，检索快 10 倍 |
| RL 检索策略 | Search-R1、CoSearch | 训练出「何时搜、搜什么」 |

五种变体共享同一个架构前提：**agent 拥有检索**。区别只在工具背后是什么。

## 七、什么时候别急着扔向量库

这部分比前面的赞美更有价值，因为这个模式不免费：

- **Token 成本**：多 agent 研究比聊天贵 15 倍；Milvus 甚至专门写了《Why I'm Against Claude Code's Grep-Only Retrieval》。提示缓存能补回一大块，补不回全部。
- **延迟**：一次查询 5–10 次工具调用，是秒级不是毫秒级。交互式编码没问题，亚秒级对话不行。
- **超大语料**：千万文件的 monorepo 上 grep 不是免费的，PB 级仍是预计算索引的战场。
- **真正的语义查询**：「这个库对重试策略都说了什么？」——答案可能散在从没用过 `retry` 这个词、只写了 `backoff` / `circuit_breaker` 的文件里。
- **紧耦合任务**：多 agent 在强串行任务上是负收益。
- **确定性与缓存**：向量查找确定、便宜、可缓存，agent 循环不是。评测和 SLA 执行都更难做。

## 八、MCP：把模式变成生态默认

如果 agent-as-retriever 是模式，MCP 就是把这个模式从「Claude Code 的特性」变成「生态默认」的协议：任何 LLM host 都能接任意 MCP server，把文件系统、数据库、可观测性、工单、SaaS 变成统一的可调用工具集合。

**一旦检索是工具调用，每个数据源都成了候选检索器，无需人为它建向量索引。** 这句话是整套范式最有杠杆的地方。

## 九、算一算我自己的账

我这个博客站目前 4 篇文章、几千行代码。这个体量下，**建索引的收益是负的**——建了就是文章里说的「一笔负债」：每次提交都要重建，而且重建永远追不上。所以纯 agentic 检索对我就是终点，不存在要不要混合、要不要 AST 的选择题。

真正有共鸣的是**成本那一侧**。这次加一个复制按钮，20 多次工具调用，一半以上花在验证上：构建、造 file:// 副本、注入内联、三条剪贴板路径各测一遍、四个状态截图、再补一轮窄屏。Milvus 那篇批评说的「5–30 倍 token」在这个小任务上是成立的。

但那次验证抓到了一个**只会靠索引误导你的问题**：脚本变大后被抽成独立 ES module，`file://` 下被 CORS 拦截，页面上按钮一个都没有。DOM 查询返回 0——如果我当时信任「代码写进去了」这个结论，就会把一个环境问题当成实现问题继续改。**多打的那一次 grep（抓 console）才是修复的来源。**

这大概就是这套范式的真实形状：不是「grep 比向量准」，而是**你能不能在同一个问题上多迭代几轮**。索引给不了这个，循环给得了。

## 结语

文章标题说向量数据库已死，更准确的说法是：它没死，但从默认选项降级成了备选。

2026 年的默认值是：**先给工具，把工具设计好，让它即时检索**；只有在语义泛化、超大稳定语料、亚秒级对话这些真正需要嵌入的工作负载上，再把向量加回来。

对个人博客这种小语料，这句话可以直接翻译成更简单的版本：**别急着建索引，先老老实实 grep。**

## 参考资料

以下资料转引自原文，我未逐条核对原始论文，引用前建议自行验证。

- Anthropic — Effective context engineering for AI agents
- Anthropic — How we built our multi-agent research system
- Latent Space — Claude Code: Anthropic's Agent in Your Terminal（Boris Cherny & Cat Wu, 2025-05）
- Subramanian et al. — Keyword Search Is All You Need（AAAI 2026）
- Jin et al. — Search-R1: Training LLMs to Reason and Leverage Search Engines with RL
- Dive into Claude Code（arXiv）
- Milvus — Why I'm Against Claude Code's Grep-Only Retrieval
