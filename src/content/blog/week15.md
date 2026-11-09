---
title: 'WEEK-15'
description: '把第 9—14 周各自独立的检测脚本串成一条 BYOVD 检测流水线。'
pubDate: 2026-11-09
tags: ["Python", "BYOVD", ]
---

## 复用，而非重写

第 9—14 周各自产出了独立的检测环节：时间线、特征表、规则引擎、Isolation Forest 模型。但它们散落在不同的脚本里，没有统一入口。本周的任务只有一句话：把这些脚本串成一个入口，输出统一告警与可视化——已有脚本一行不改，检测智能全部留在原处。

最终产物是 `byovd_detector.py`：它只负责读配置、凑数据、调既有函数、合并输出。加上单文件离线的 `dashboard.html`，第 9—14 周的散件被串成了一条可重复运行的 BYOVD（Bring Your Own Vulnerable Driver）检测流水线。

## 一、总体流程

```
replay 子命令              byovd_detector.py (统一入口)
─────────────────────    ─────────────────────────────
第10周时间线 load_events.csv ─┐
第12周四张表(CSV)        ─┼─→ ①时间线 ②特征(已有CSV直读)
ioctl_events_run*.jsonl ─┘   ③规则: import rule_engine(复用)
                             ④模型: joblib 加载第14周模型(复用)
                             ⑤告警合并 → alerts.csv/.jsonl
                             ⑥dashboard.html (单文件离线)

live 子命令
  ①轮询 Sysmon EventID 6 + System 7045 (PowerShell Get-WinEvent)
  ②调第11周 telemetry_collector.exe 读 test.sys Ring Buffer → jsonl
  ③④⑤⑥ 同上，逐轮追加

场景: replay --scenario normal | rules | model
```

两个子命令、两条通路，最后汇入同一条检测管线：

- **replay**：离线回放已有产物——时间线、四张特征表、IOCTL jsonl；
- **live**：实时轮询 Sysmon Event ID 6 和 System 7045 事件日志，同时子进程调用第 11 周的 `telemetry_collector.exe` 读 test.sys 的 Ring Buffer，新会话现场聚合特征。

所有路径与参数收进 `config.yaml`——它是唯一配置来源，`load_cfg()` 读入后把 `paths` 各项统一转成 `Path` 对象。

## 二、replay 管线的五步

```
① 时间线构建
   读取 load_events.csv（第10/12周产物）
   └─ 若文件缺失，子进程调用 build_features.py 重建
② 特征读取
   读取 session_features.csv（真实 10 会话）
   叠加 synthetic_sessions.csv（合成 3 条）
   按 train_params.json 的 train_sessions 给每个会话标 data_source
③ 规则检测
   import 复用第13周 rule_engine.py，逻辑零重写
   load_rules 读 rules.yaml，按 yaml 顺序执行 CHECKS 各判定函数
   └─ R7_Static_Dynamic 最后算（依赖 R3–R6 的命中结果）
   build_alerts 按 (驱动, 会话) 聚合：分数 = 权重和，等级 = 最高档
④ 模型打分
   joblib 加载第14周 iforest_model.joblib
   按 train_params.json 的 7 特征列构造矩阵
   调用 decision_function（越大越正常）
   model_score = -decision_function；低于阈值判 anomaly
⑤ 告警合并
   规则告警行（含 session 为空的静态行）补上模型分与判定
   └─ 模型判异常但规则未命中的会话 → 单独成行，hit_rules 记 "-"
   合成样本：无原始事件，仅模型侧有分（与第14周口径一致）
```

两个点：

- **③ 里 R7 的执行顺序是有讲究的**。`R7_Static_Dynamic` 是"静态敏感 + 动态异常"的组合规则，它依赖 R3–R6 的命中结果，所以必须放在最后算——这也正是第 13 周 rule_engine 的原始顺序，复用时天然保持了口径一致；
- **⑤ 里规则和模型不是各输出各的**。规则告警行会补上模型分与判定；反过来，模型判异常但规则没命中的会话单独成行，`hit_rules` 记 `"-"`。这样每条告警都能同时看到两套视角的结论。

## 三、live 通路

live 每轮（间隔 `poll_seconds`）只接两路输入：

1. **PowerShell 轮询** `Get-WinEvent` 抓 Sysmon Event ID 6（驱动加载）+ System 7045（服务安装），7045 事件追加进本地时间线；
2. **子进程调用**第 11 周 `telemetry_collector.exe` 读 test.sys Ring Buffer，解析产出的 jsonl → 新会话（session_id 递增），现场聚合会话特征。

然后进与 replay 完全相同的 ③规则 → ④模型 → ⑤合并 管线。alerts 按（会话 + 驱动 + 规则 + 等级 + 判定）去重后追加写入，同时刷新 dashboard——静态规则跨轮重复命中不会刷屏。达到 `--rounds` 轮数退出，0 表示持续轮询。

## 四、三个演示场景

三个场景本质是 replay 的不同数据口径：

- **normal** → 剔除目标驱动 TEST.sys 后全量跑规则，断言 high 及以上告警 = 0（阴性对照）；
- **rules** → 全量数据跑规则引擎，输出命中规则与证据链；
- **model** → 真实 + 合成会话打分，取 decision_function 最低 3 个会话写入 `model_low3.json`。

全流程回放：时间线 → 特征 → 规则 → 模型 → 告警 → 面板：

![全流程回放：时间线到面板](/images/week15-pipeline.png)

场景 1：正常数据回放，验证 high 级告警为 0：

![场景1 正常数据回放](/images/week15-scenario-normal.png)

场景 2：规则告警回放，看证据链：

![场景2 规则告警与证据链](/images/week15-scenario-rules.png)

场景 3：模型分数展示，最低分 3 个会话：

![场景3 模型分数最低的3个会话](/images/week15-scenario-model.png)

## 五、134 条告警说明了什么

`alerts.csv` 共 134 条记录，检测链路端到端跑通，分级符合预期：

| 级别 | 条数 | 构成 |
| --- | --- | --- |
| critical | 1 | test.sys 命中 R7（静态敏感 + 动态异常） |
| medium | 12 | TEST.sys 10 个会话，2 个 Defender 驱动（R2+29_Review） |
| low | 1 | 单条 W9_Review |
| none | 120 | 117 个正常驱动和 3 条合成样本 |

none 不是告警，是静态标签。

**规则与模型的"一致"与"分歧"同时显现**：

- **一致**：模型把 3 条合成样本全部判 anomaly（model_score 0.199）——规则和模型都认为"偏离正常"的东西有问题；
- **分歧**：真实会话 2–10 规则判 medium、模型却判 normal（model_score 为负），因为这些会话和训练数据同分布，模型认为"正常"。

这精确复现了第 14 周的结论：模型学到的正常边界基本由 `ioctl_rate_per_sec` 单一维度决定。两组结果验证了"规则管可解释、模型管泛化、合并后互补"的设计目标，同时暴露出问题：模型区分度依赖单一频率特征、小样本阈值存在边界误判。

csv 与 json 的部分输出：

![alerts.csv 输出截图](/images/week15-alerts-csv.png)

![alerts.jsonl 输出截图](/images/week15-alerts-json.png)

## 六、dashboard.html

单文件离线面板：数据以 JSON 内嵌，无 CDN，支持按驱动与级别筛选；显示事件总数、告警数、级别分布，有合成样本时额外显示其占比。

![dashboard.html 界面](/images/week15-dashboard.png)

## 七、总结

1. **统一入口** `byovd_detector.py`：提供 replay（回放已有数据）和 live（实时采集）两个子命令，所有路径与参数收进 config.yaml，三个演示场景（normal / rules / model）作为 replay 的不同数据口径。
2. **复用而非重写**：规则检测直接 `import` 第 13 周 `rule_engine.py` 的判定函数；模型打分直接加载第 14 周训练好的 `iforest_model.joblib` 和阈值；时间线缺失时子进程调第 12 周 `build_features.py` 重建。原脚本一行没改，检测口径与之前完全一致。
3. **live 通路**：只接两路输入——轮询 Sysmon Event ID 6 与 System 7045 事件日志，以及调用第 11 周 telemetry_collector 读 test.sys Ring Buffer 的 IOCTL 遥测；采集到的新会话进同一条检测管线。
4. **统一告警与可视化**：输出 alerts.csv / alerts.jsonl（每条含会话、驱动、命中规则、规则分与等级、模型分与判定、数据来源、证据链）和单文件离线的 dashboard.html；完成三个演示场景并编写 README。

## 附：README 里的已知问题

1. VM 未运行 test.sys 时，live 的 Ring Buffer 一路无数据（事件日志两路不受影响）；
2. Sysmon Event 6 的 Properties 下标按常见布局（ImageLoaded=4, SignatureStatus=7），schema 版本不同需改 poll_events 的 prop_map；
3. 正常训练样本仅 7 个，阈值取训练集 10% 分位，session 1 被判 anomaly 属边界现象（第 14 周已记录），场景 3 解读需注意；
4. 合成样本无原始事件，规则侧无分、仅参与模型打分，与第 14 周口径一致。

> 环境：宿主机 Windows + Python 3.10（pandas / pyyaml / scikit-learn / joblib）；上游为第 10—14 周全部脚本与产物；live 模式事件轮询用系统自带 PowerShell，无额外依赖。
