---
title: '把静态分析、加载时间线和 IOCTL 遥测合成一张特征表'
description: '用 build_features.py 把三周积累的异构 CSV/JSONL 归一化成四张标准表，再用 validate_dataset.py 把关——附完整实现细节与踩坑记录。'
pubDate: 2026-10-17
tags: ["Windows", "驱动", "Python", "分析"]
---

## 说明

前几周的产物是散的：第 9 周是 Sysmon 的驱动加载事件（`driver_events.csv`）和当前驱动快照（`current_drivers.csv`），第 10 周是合并后的驱动时间线（`driver_timeline.csv`），第 11 周是自己写的驱动导出的 IOCTL 遥测（`ioctl_events.jsonl`）。四份数据字段名不同、粒度不同、编码不同，甚至不是同一种文件格式。

这一周的任务是把它们**归一化成一套统一的特征数据集**：写 `build_features.py` 做转换，写 `validate_dataset.py` 做质量门禁，最后按实验会话划分训练集和测试集。三个脚本构成一条"构建 → 校验 → 划分"的流水线。

## 附件

- [📥 driver_metadata.csv：驱动哈希、签名与静态能力（CSV）](/driver_metadata.csv)
- [📥 load_events.csv：驱动加载与服务状态事件（CSV）](/load_events.csv)
- [📥 ioctl_events.csv：单次 IOCTL 遥测记录（CSV）](/ioctl_events.csv)
- [📥 session_features.csv：会话级聚合特征（CSV）](/session_features.csv)

## 一、整体流水线

```
输入（多源原始记录）
├─ driver_events.csv     第 9 周 Sysmon ImageLoaded（哈希/签名/路径）
├─ current_drivers.csv   正常基线（当前已加载驱动清单，中文表头）
├─ driver_timeline.csv   第 10 周服务安装/状态时间线
└─ ioctl_events_run*.jsonl  第 11 周 IOCTL 遥测（10 个采集文件，每文件 = 1 个会话）
        │
        │  build_features.py
        ↓
├─ driver_metadata.csv    驱动级元数据（哈希、签名、路径、静态敏感能力）
├─ load_events.csv        加载/服务/状态事件表
├─ ioctl_events.csv       IOCTL 明细表（640 条 / 10 会话）
└─ session_features.csv   会话级聚合特征（10 行）
        │
        │  validate_dataset.py（五项校验）
        │  split_dataset.py（按会话 70/30 划分）
        ↓
   train.csv / test.csv
```

## 二、build_features.py 详解

### 2.1 目录策略：输入与输出分离

```python
SCRIPT_DIR = Path(__file__).resolve().parent          # 脚本所在目录
IN_DIR = SCRIPT_DIR if (SCRIPT_DIR / "driver_events.csv").exists() else Path(r"D:\my-blog\public")
OUT_DIR = SCRIPT_DIR
```

输入目录优先在脚本所在处找，找不到才回退到历史数据目录；输出**永远**写在脚本目录。

这个分离是被 bug 逼出来的：最初输入输出共用一个目录变量，`D:\test` 里没有输入文件 → 整个脚本回退到旧数据目录 → 新采集的 10 个 run 文件在另一个目录，glob 一个都找不到 → 合并静默退化成旧的单文件模式，输出还是"64 条记录，1 个会话"，而脚本不报任何错。**输入找不到可以回退，输出不能跟着跑**——这是拆分变量的直接理由。

### 2.2 目标驱动配置

```python
TARGET_NAME = "TEST.sys"
TARGET_PATH = r"c:\windows\system32\driverstore\filerepository\test.inf_amd64_bb27026a8e84a5cd\test.sys"
TARGET_HASH = "e05e004cbcc70d5e05fbc2a3086a900463ad8edfd7be6124f59ca895640f247a"
```

IOCTL 遥测本身**不带驱动标识**（内核只知道有人调了这个设备），所以要先回答"这是哪个驱动"。两个字段各有用处：

- `TARGET_HASH`：`certutil -hashfile TEST.sys SHA256` 算出来的 SHA256。`pkg\`、`x64\Debug\TEST\`、`x64\Debug\` 三处构建产物哈希完全一致，证实是同一次构建的同一个文件；
- `TARGET_PATH`：VM 里 `sc qc TEST` 输出的 `BINARY_PATH_NAME`，即 INF 安装后 DriverStore 里的真实路径。

注意 DriverStore 那个 `test.inf_amd64_bb27026a8e84a5cd` 哈希目录名**每次重装 INF 都可能变**，所以这个值要在安装后重新确认，不能硬编码后不管。

### 2.3 多轮采集：为什么必须先解决"只有一个会话"

首次跑完只有一个会话（64 条记录全在 9 毫秒内），按会话划分训练/测试集直接无从下手。解决办法是在 VM 里用 bat 把"压测 → 导出 → 改名"循环 10 轮：

```bat
@echo off
cd /d C:\drivers
for /L %%i in (1,1,10) do (
    echo ===== round %%i / 10 =====
    ioctl_stress_test.exe
    telemetry_collector.exe
    ren ioctl_events.jsonl ioctl_events_run%%i.jsonl
    ping -n 3 127.0.0.1 >nul
)
echo ===== ALL DONE =====
```

几个细节：多行循环**必须存成 .bat 文件**（交互式命令行里 cmd 会停在 `more?` 等你闭合括号，看起来就是"一直不结束"）；`ping -n 3 127.0.0.1 >nul` 代替 `timeout /t 2`，后者在某些控制台环境下会等待输入；每轮改名是因为采集器用 `"wb"` 打开输出文件，**每轮都会覆盖**，忘改名就丢数据。

![VM 中 bat 批量采集 10 轮]

采集完先验证数据没串轮——10 个文件各 64 条、时间范围互不重叠：

```
ioctl_events_run1.jsonl   64  06:04:45.172 → 06:04:45.174
ioctl_events_run10.jsonl  64  06:05:09.078 → 06:05:09.093
ioctl_events_run2.jsonl   64  06:04:47.832 → 06:04:47.840
...
```

### 2.4 第 9 周静态数据 → driver_metadata.csv

```python
ev9["file_hash"] = ev9["Hashes"].str.extract(r"SHA256=([0-9A-Fa-f]{64})")[0].str.lower()
```

原始字段是 `SHA256=xxx` 的复合串，正则提取后**统一转小写**。哈希是贯穿四张表的主键，第 10 周时间线里是大写、第 9 周是混合大小写，不统一的话 join 会大面积落空。

敏感能力归类把"静态特征"转成结构化类别：

```python
def caps(r):
    c = []
    if str(r["PathCategory"]).strip() == "NonStandard_Path":
        c.append("nonstandard_path")     # 藏在常规系统目录之外
    if not r["signed"]:
        c.append("unsigned")             # 无有效签名，来源不可信
    return ";".join(c) or "none"
```

最后 `drop_duplicates("file_hash")`——一次加载事件一行，一个驱动只留一行，得到 120 个驱动。

### 2.5 正常基线：只能按路径匹配

`current_drivers.csv` 是中文表头的驱动清单，**只有路径没有哈希**，所以 `in_baseline` 只能按路径（小写后精确匹配）：

```python
try:
    base = pd.read_csv(IN_DIR / "current_drivers.csv", encoding="utf-8-sig")
except UnicodeDecodeError:
    base = pd.read_csv(IN_DIR / "current_drivers.csv", encoding="gbk")
base_paths = set(base["路径"].astype(str).str.strip().str.lower())
in_baseline = int(TARGET_PATH.lower() in base_paths)
```

编码先试 utf-8-sig 再退 GBK——这类工具导出的中文 CSV 编码不统一是常态。结果 `in_baseline = 0`：自研测试驱动不在正常基线里，这本身就是有判别力的特征，而不是错误。

### 2.6 第 10 周时间线 → load_events.csv

```python
tl.loc[~tl["file_hash"].str.fullmatch(r"[0-9a-f]{64}"), "file_hash"] = ""   # N/A 置空
```

时间线里混着 `N/A` 这类无效哈希（比如 Edge 更新服务），用 `fullmatch` 卡死格式后置空，保证该列要么是合法 64 位哈希、要么为空，脏值不会流进下游。加载次数用双条件匹配兜底：

```python
n_load = int(((tl["file_hash"] == TARGET_HASH) |
              tl_name.str.endswith("\\" + TARGET_NAME.lower())).sum())
```

哈希为主、文件名为辅——因为时间线并非每条都有哈希。

### 2.7 第 11 周遥测合并 → ioctl_events.csv

```python
files = sorted(list(SCRIPT_DIR.glob("ioctl_events_run*.jsonl")) or ...,
               key=lambda p: int(re.search(r"run(\d+)", p.name).group(1)))
```

两个关键决策：

1. **按数字排序**：文件名 run1–run10 没补零，直接 `sorted()` 的字典序是 run1 → run10 → run2，会话编号直接错乱且不报错。从文件名抽出数字再排才对应真实轮次。
2. **一个采集文件 = 一个会话**：比"时间间隔 > 300 秒就切一个会话"的启发式可靠得多——不依赖系统时钟，也不受采集间隔影响，VM 时钟漂移不会影响结果。

### 2.8 会话级聚合

```python
for sid, g in io.groupby("session_id"):
    dur = max((g["timestamp"].max() - g["timestamp"].min()).total_seconds(), 1e-9)
```

`1e-9` 是必要的下限：单条记录构成会话时 max−min 为 0，直接相除得到 inf 会污染整列。时长按**导出样本的首末时间**计算，不是整轮压测的真实时长——Ring Buffer 只保留最近 64 条，所以 `ioctl_rate_per_sec` 描述的是"尾部样本的调用密度"。

## 三、validate_dataset.py 详解

校验脚本不信任 build 的自检，读的是最终落盘文件，五项检查任意一项失败退出码 1，可以直接当 CI 门禁。

### 3.1 必填字段

```python
REQ = {
    "driver_metadata.csv":  ["file_hash", "path", "Signature", "SignatureStatus", "sensitive_caps"],
    "load_events.csv":      ["timestamp", "EventType", "ServiceName", "ImagePath", "file_hash", "DriverState"],
    "ioctl_events.csv":     ["timestamp", "file_hash", "ioctl_code", "input_length", "output_length",
                             "completion_status", "session_id"],
    "session_features.csv": ["driver", "file_hash", "session_id", "load_count", "in_baseline", ...],
}
```

作用是防止上游改了表结构、下游静默产出错数据——这类错误在特征工程里往往要到模型训完才发现。

### 3.2 格式检查与缺失值放行

```python
s = dfs[name][col].fillna("").astype(str)
bad = s[~s.str.match(pat) & ~(allow_empty & (s == ""))]
```

这里的 `fillna("")` 不是随手写的。踩过的坑：**pandas 3.x 的字符串列里缺失值是真 NA，`astype(str)` 不再把它转成 `'nan'` 字符串**，于是"把 nan 当空值放行"的旧写法彻底失效，26 条合法置空的哈希被误报成"不符合哈希格式"。

`allow_empty=True` 只授予 `load_events.file_hash`——只有这一列允许为空（时间线本就存在 N/A），其他表的哈希缺失都是数据问题。

### 3.3 查重要分表语义

```python
for name in ["driver_metadata.csv", "session_features.csv"]:   # 只查实体表
```

- **实体表**（一驱动一行、一会话一行）出现重复 = 构建逻辑错误，必须报；
- **事件表**（load/ioctl）的全行重复是**真实行为**——同一个 IOCTL 在同一毫秒被反复调用，记录自然一模一样。查重会误报 545 条，而这不是任何数据质量问题。

宽容度按表语义设定，而不是一刀切。

### 3.4 聚合一致性

```python
if s["ioctl_count"].sum() != len(io):
    errors.append(f"聚合不一致: {s['ioctl_count'].sum()} != {len(io)}")
```

验证"明细表 → 聚合表"无丢失无重复（640 == 640）。这是特征工程里最容易**静默**出错的一环：分组键写错、类型不匹配，都会让一部分会话被悄悄丢掉，而表看起来完全正常。

### 3.5 校验结果

```
ALL CHECKS PASSED
```

![validate_dataset.py 校验通过](/images/week11-validate.png)

`session_features.csv` 的 10 行聚合结果：

![session_features.csv](/images/week11-session-features.png)

## 四、生成的数据文件

### driver_metadata.csv：驱动级元数据

哈希、签名、路径与静态敏感能力，一驱动一行，由第 9 周加载事件去重而来。

- 字段：`file_hash` / `path` / `Signature` / `SignatureStatus` / `PathCategory` / `sensitive_caps`
- 共 120 个驱动；`sensitive_caps` 取值 `nonstandard_path`、`unsigned`、`none`，多个用分号拼接

### load_events.csv：加载、服务与状态事件

第 10 周时间线的标准化形态，事件类型、服务名、驱动状态一应俱全。

- 字段：`timestamp` / `EventType` / `ServiceName` / `ImagePath` / `file_hash` / `SignatureStatus` / `DriverState`
- 共 54 条，按时间排序；`file_hash` 为空表示原始记录是 `N/A`

### ioctl_events.csv：单次 IOCTL 记录

10 轮采集合并后的明细表，640 条，每行一次 IOCTL 请求。

- 字段：`timestamp` / `pid` / `ioctl_code` / `device_type` / `function` / `method` / `access` / `input_length` / `output_length` / `completion_status` / `session_id` / `status_ok` / `file_hash` / `driver`
- `status_ok` 由 `completion_status == 0x00000000` 推出；`session_id` 对应采集文件编号

### session_features.csv：按驱动和时间窗口聚合的特征

整个流水线的核心产物，一会话一行，共 10 行。

| 特征 | 含义 |
|---|---|
| `load_count` | 观测期内该驱动的加载次数 |
| `in_baseline` | 是否存在于正常基线（按路径匹配） |
| `ioctl_count` / `ioctl_rate_per_sec` | IOCTL 请求次数与每秒频率 |
| `distinct_ioctl` | 不同 IOCTL 编号数量（行为多样性） |
| `in_len_max` / `in_len_mean` | 输入长度最大值与均值 |
| `out_len_max` / `out_len_mean` | 输出长度最大值与均值 |
| `fail_ratio` | IOCTL 失败比例（1 − 成功率） |
| `sensitive_caps` | 静态敏感能力类别 |

长度类特征是行为画像的关键：正常调用稳定在约定长度，而试探性利用往往表现为异常大的输入或输出请求。

## 五、按实验会话划分训练集与测试集

```python
session_ids = feats["session_id"].unique()
shuffled = rng.permutation(session_ids)          # 固定种子 42
train_sessions = sorted(int(s) for s in shuffled[:n_train])
test_sessions  = sorted(int(s) for s in shuffled[n_train:])

assert not set(train_sessions) & set(test_sessions)      # 会话零重叠
assert set(train_sessions) | set(test_sessions) == set(session_ids)   # 零遗漏
```

**必须按会话整组划分，不能按行随机切。** 同一会话里的 64 条记录描述的是同一次采集运行的同一批行为，模型只要在训练集见过其中一条，测试集里"同一会话的另一条"就被间接背过，指标会虚高。随机种子固定则保证每次运行划分一致，实验可复现。

结果：训练集 7 个会话（session 1/3/4/5/6/7/8），测试集 3 个会话（session 2/9/10）。

![训练集划分](/images/week11-train-split.png)

![测试集划分](/images/week11-test-split.png)

## 六、踩坑记录

1. **目录回退把合并结果退化成单会话**：输入输出共用一个目录变量，回退后找不到新采集文件，脚本不报错、结果静默错误。拆分 IN_DIR/OUT_DIR 解决。
2. **run10 排在 run2 前面**：`sorted()` 对未补零文件名按字典序排，会话编号错乱且无任何提示。改成提取数字排序。
3. **bat 循环"一直不结束"**：交互式命令行里敲多行 for 循环，cmd 会停在 `more?` 等闭合括号。必须存成 .bat 文件，`%%i` 才是正确的变量写法。
4. **pandas 3.x 的 NA 语义**：`astype(str)` 不再把缺失值转成 `'nan'` 字符串，靠字符串等值判断放行空值的写法全部失效，改用 `fillna("")`。
5. **查重误报 545 条**：对事件表做全行查重，把"同一 IOCTL 反复调用"这种真实行为当成了数据错误。查重只对实体表生效。
6. **Ring Buffer 只留最近 64 条**：内核 Ring 容量 64、单轮 313 次请求，导出的是尾部 64 条，会话时长和频率是尾部样本的统计——结论里必须写明这个语义，否则会高估调用持续时长。

## 七、总结

- **统一主键是整条流水线的地基**：SHA256（统一小写）贯穿四张表；基线数据没有哈希时，路径只能作为辅助匹配手段。
- **会话定义优先于时间启发式**：用"一次采集运行"定义会话，规避 VM 时钟漂移，也让划分逻辑与物理实验一一对应。
- **校验独立于构建**：门禁读最终落盘文件，任何一项失败退出码 1，能挂进自动化流程。
- **宽容度按表语义设定**：事件表的重复是行为，实体表的重复是 bug；缺失值同理。
- **当前数据集的诚实结论**：结构完备、校验通过，但 10 个会话由同一套固定剧本压测产生，除调用频率外特征高度一致——判别信息量不足。下一步要给压测程序加 normal/error 模式参数，按配比重采 20–30 轮，让会话之间真正产生差异。

> 环境：宿主机 Windows 11 x64 + Python（pandas 3.x）；VM Windows x64（测试签名模式）运行 `TEST.sys` 驱动与配套压测/采集程序；特征脚本运行目录 `D:\test`。
