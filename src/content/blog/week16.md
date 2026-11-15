---
title: 'WEEK-16'
description: '对 v0.1 原型做单版本验证与性能基线：虚拟机内驱动加载与 Ring Buffer 导出链路打通、宿主机逐项功能核对、三场景 × 3 次性能测量，以及一个很典型的采数踩坑——采到了 py.exe 启动器而不是 python.exe。'
pubDate: 2026-11-16
tags: ["Windows", "驱动", "BYOVD", "性能测试"]
---

## 说明

第 15 周把检测流水线串成了统一入口，这周的问题变成：**这条流水线在整个链路上真的能跑通吗？跑起来要吃多少资源？**

本周任务：在 Win10 与 Win11 上验证同一版本原型，并测量资源开销。实际执行的是**单版本验证**——所有 Win10/Win11 跨版本对比项均标注"未测"，不做超出数据支撑的结论。

分工很清楚：虚拟机侧只负责一件事——驱动运行 + 采集器持续导出遥测到共享目录；检测与性能测量全部在宿主机完成。

## 一、虚拟机侧：驱动加载与遥测导出

```
bcdedit /set testsigning on      (自签名驱动, 重启生效)
→ sc.exe create TEST type= kernel binPath= C:\telemetry\TEST.sys
→ sc.exe start TEST             (STATE : 4 RUNNING 即加载成功)
→ 循环: ioctl_stress_test.exe(发流量)
        → telemetry_collector.exe(导出)
        → copy 到 VMware 共享目录
→ 宿主机经 D:\share 读取 ioctl_events.jsonl
```

`sc.exe query TEST` 确认驱动以内核驱动身份运行（STATE : 4 RUNNING），采集器导出 64 条事件：

![虚拟机内 TEST 驱动运行状态与采集器导出](/images/week16-vm-driver-running.png)

压测客户端每轮发 313 次请求——309 成功、4 失败。4 个失败是**预设的失败用例**：未定义 IOCTL、输出缓冲过小、输入过长、查询缓冲过小，各自对应不同的 gle 错误码。失败不是 bug，是剧本的一部分：

![压测客户端输出：313 次请求与 4 种预设失败](/images/week16-vm-stress-test.png)

采集器是**一次性导出**程序，每次导出后打印 Ring Buffer 统计：

```
stats: totalWrites=3779  overwriteCount=3715  validCount=64
stats: totalWrites=4093  overwriteCount=4029  validCount=64
stats: totalWrites=4407  overwriteCount=4343  validCount=64
```

三个统计量怎么读：

- `totalWrites` / `overwriteCount` 是驱动内的**累计**计数器，单轮值要取相邻两轮的差值（4093 − 3779 = 314）；
- `validCount` 恒为 64——**Ring Buffer 容量就是 64 槽位，且始终满载**。每轮 314 次写入全部覆盖旧事件，只保留最后 64 条，与导出 jsonl 恰好 64 行互相印证。

由此可以量化第 11 周就埋下的容量问题：每轮事件留存率约 64 / 314 ≈ **20.4%**，覆盖率约 79.6%。64 槽位在压测流量下是硬瓶颈——这是本周拿到的最扎实的一个数字。

宿主机侧验证共享目录数据通道，一张截图同框看到两端：上面旧控制台是虚拟机侧 `copy` 到共享目录，下面 PowerShell 是宿主机 `Get-Content D:\share\ioctl_events.jsonl | Measure-Object -Line` 数出 64 行：

![共享目录数据通道：虚拟机侧拷贝与宿主机侧读取同框](/images/week16-share-channel.png)

## 二、宿主机侧：功能验证

单版本验证，只在本机跑同一份回放数据（第 12 周四张表 + 10 个 ioctl_events_run*.jsonl），逐项核对：

| 检查项 | 结果 |
| --- | --- |
| 时间线输出 | alerts.csv / alerts.jsonl 正常生成，含时间/会话/驱动/命中规则/证据链字段 |
| 会话数与特征数 | session_features.csv：10 个会话 × 14 列（含 7 个模型特征与 sensitive_caps 等） |
| 规则告警数量与级别分布 | 共 134 条：critical 1 / medium 12 / low 1 / none 120（none 为静态标签非告警），与第 15 周一致 |
| 模型分数排序（前 5 名） | 会话 101/102/103（合成）与会话 1（真实）均为 0.199 判 anomaly；第 5 名为会话 4（−0.1326，normal） |
| dashboard 渲染 | dashboard.html 正常生成，单文件离线、无 CDN，支持按驱动与级别筛选 |

模型分数前 5 名明细（decision_function 越大越正常，model_score 越高越异常，阈值≈0）：

| 排名 | 会话 | 来源 | model_score | 判定 |
| --- | --- | --- | --- | --- |
| 1 | 101 | synthetic | 0.199 | anomaly |
| 2 | 102 | synthetic | 0.199 | anomaly |
| 3 | 103 | synthetic | 0.199 | anomaly |
| 4 | 1 | real(train) | 0.199 | anomaly |
| 5 | 4 | real(train) | −0.1326 | normal |

结论与第 14/15 周口径完全一致：3 条合成样本全部被判异常；会话 1 被判 anomaly 属小样本阈值边界现象——已知问题，不调整。

![宿主机回放运行：134 条告警与场景输出](/images/week16-host-replay.png)

跨版本对比（两台机器时间线/告警/模型排序/dashboard 差异）：**未测（单版本验证）**。

## 三、性能测量：三场景 × 3 次

性能采集固化为 `perf_test.ps1`：每场景跑 3 次，原始值写 `perf_results/perf_raw.csv`，均值写 `perf_results/perf_summary.csv`，每次运行的 stdout/stderr 日志一并保留。

**指标采集方式**：

| 指标 | 采集方式 |
| --- | --- |
| CPU 均值 | 进程 TotalProcessorTime ÷ 墙钟时间 ÷ 逻辑核数 |
| CPU 峰值 | 200ms 采样窗口内 CPU 时间增量的瞬时百分比最大值 |
| 内存峰值 | 200ms 采样 WorkingSet64 最大值 |
| 每秒处理记录数 | replay：输入事件 CSV 数据行数 ÷ 回放耗时；live：采集器 jsonl 行数增量 ÷ 耗时 |
| 告警输出延迟 | 进程启动时间 → output/alerts.csv 最后写入时间 |
| Ring Buffer 覆盖数 | 取虚拟机采集器 stats 的 overwriteCount 轮间增量（比宿主机行数增量更准） |

**测量结果（均值，原始值见 perf_raw.csv）**：

| 场景 | CPU均值% | CPU峰值% | 内存峰值MB | 每秒处理记录数 | 告警延迟s | Ring Buffer覆盖数 |
| --- | --- | --- | --- | --- | --- | --- |
| 空闲 | 1.07（1.1/0.6/1.5） | 3.67（3/2/6） | 10142.4 | 不适用 | 不适用 | 不适用 |
| live 采集 | 0（0/0/0） | 0.12（0/0.36/0） | 8.4（启动器口径） | 未测 | 未测 | 314 次/轮（314/314/314） |
| 全量回放 | ≈0 | 1.43（1.44/1.78/1.07） | 162.87（164.3/161.6/162.7） | 283.71（64.75/392.78/393.59） | 4.50（10.365/1.572/1.563） | 不适用（回放不经 Ring Buffer） |

### 冷启动：均值掩盖的两副面孔

回放首轮耗时 10.718s——冷启动，模块导入与磁盘缓存未热；第 2、3 轮热启动稳定在约 1.77s。均值 283.71 条/秒被首轮拉低，**热启动下实际吞吐约 393 条/秒、告警延迟约 1.57s**。均值口径与热启动口径同时保留——报一个数字会误导，报两个才有信息量。

### 本周最典型的坑：采错了进程

CPU/内存最初采样的是 `py.exe` 启动器进程——它只负责拉起子进程然后等着，本身内存恒为 8.4MB、CPU≈0，而真正干活的 `python.exe` 子进程完全没被覆盖。perf_test.ps1 改为直接启动 python.exe（路径取 `sys.executable`）后重测，回放内存峰值 162.87MB、峰值 CPU 1.43% 才是真实口径。

下面这张运行汇总截图就是旧口径的现场证据——replay 一行 MemPeak 8.4MB，一眼假：

![perf_test.ps1 三场景运行汇总（py.exe 旧口径，replay 内存 8.4MB 即采样错进程的证据）](/images/week16-perf-raw.png)

live 场景数值仍为启动器口径，但它本身以 15 秒间隔轮询 + 睡眠为主（每轮约 65 秒 = 5 轮 × 15 秒），CPU 接近 0 符合预期。perf_raw.csv 里 live 的三次运行原始值：

![perf_raw.csv 中 live 场景三次运行的原始值与 Note 记录](/images/week16-perf-summary.png)

### 四个"未测"，各有各的原因

1. **live 每秒处理记录数**：虚拟机侧是"一次性导出 + 覆盖式拷贝"（每次 64 行覆盖旧文件），宿主机按行数增量统计恒为 0——**该口径在此架构下失效**，不是测量失败，是架构不匹配。可注明虚拟机侧每轮导出 64 条；
2. **live 告警输出延迟**：轮询期间无新增告警，alerts.csv 未刷新，无从测起；
3. **Ring Buffer 覆盖数不采用宿主机行数增量**：直接取虚拟机侧 collector stats，每轮覆盖 314 次（三轮原始值 314/314/314）；
4. live 场景 CPU/内存如需精确口径，可在虚拟机侧补测采集器与驱动开销。

live 均值一行（summary 口径）：

![perf_summary.csv 中 live 场景的均值行](/images/week16-perf-live.png)

## 四、release/v0.1/ 归档与问题记录

目录 `release/v0.1/` 归档原型代码、配置、性能结果与验证报告（VALIDATION.md），`perf_test.ps1` 一并收录——第 20 周回归时同场景同指标直接复用，数据可与本周基线对比。

单版本验证，无跨版本问题。本周实际遇到的问题与修复：

| 编号 | 问题 | 修复/处置 |
| --- | --- | --- |
| 1 | collector_output 原指向不存在的 D:/vmshare，live 读不到采集产物 | 改为 VMware 共享目录宿主机侧实际路径 D:/share/ioctl_events.jsonl |
| 2 | perf_test.ps1 解析 config.yaml 时把行内 # 注释吃进路径，持续报 collector output unreachable | 解析逻辑先截掉 # 注释再去引号 |
| 3 | 导出 perf_summary.csv 报"文件被另一进程占用" | CSV 被 Excel/WPS 打开所致；回归前先关闭已打开的 CSV |
| 4 | VMware 共享目录在虚拟机频繁覆盖写同一文件时，宿主机侧短暂读不到 | 已知同步抖动，不影响结论；关键指标改取虚拟机侧 stats |
| 5 | CPU/内存采样到 py.exe 启动器而非 python.exe 子进程 | 改为直接启动 python.exe 后重测，162.87MB / 1.43% 为真实口径 |

**数据局限（解读一切性能与检测结果的前提）**：10 个 run 文件是同一压测脚本的 10 次重复——仅 PID/时间戳不同，每文件 64 条中约 9 条不同记录，大量同毫秒重复。回放吞吐数字因此偏理想化；规则阈值（R3=30 次/60s 等）按本数据校准，回放必然触发规则。**本周验证的结论是"链路通、输出稳定"，不代表规则在真实数据上的区分度。**

## 五、总结

1. **链路打通**：虚拟机内 TEST.sys 加载、压测、Ring Buffer 导出全链路跑通，宿主机经共享目录读取遥测，同一份回放数据的功能输出与第 15 周逐项一致；
2. **性能基线建立**：空闲系统 CPU 约 1.07%；live 轮询开销极低（CPU≈0、内存 8.4MB，启动器口径）；全量回放内存峰值 162.87MB、CPU 峰值 1.43%、均值吞吐 283.71 条/秒（热启动约 393）、告警延迟均值 4.50s（热启动约 1.57s）；Ring Buffer 覆盖 314 次/轮、留存率约 20.4%，**64 槽位容量瓶颈得到量化确认**；
3. **可复现**：性能采集固化为 perf_test.ps1，release/v0.1/ 归档完成，第 20 周回归同场景同指标，数据可与本周基线直接对比；
4. **遗留**：live 吞吐与告警延迟受"覆盖式导出"架构限制标注未测——后续若采集器改为持续追加输出可补全；live 场景 CPU/内存如需精确口径，可在虚拟机侧补测采集器与驱动开销。

> 环境：宿主机 Windows + Python 3.14（pandas / pyyaml / scikit-learn / joblib）+ PowerShell 性能采集；虚拟机 Windows 10/11 x64 + TEST.sys（KMDF）+ telemetry_collector.exe；遥测通道为 VMware 共享目录 D:\share。上游为第 10—15 周全部脚本与产物，验证与性能基线归档于 release/v0.1/。
