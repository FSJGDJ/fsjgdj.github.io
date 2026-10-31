---
title: 'WEEK-14'
description: '用第 12 周特征训练 Isolation Forest 异常检测模型：7 个特征的选取与泄露排查、只喂正常会话的无监督训练、decision_function 取负定阈值，以及与第 13 周规则引擎的同口径对比。'
pubDate: 2026-10-31
tags: ["Windows", "驱动", "Python", "机器学习"]
---

## 说明

第 13 周的规则引擎回答了"写死的阈值能抓到什么"，这一周换一条路：**不写规则，让模型自己从数据里学"正常长什么样"**。

任务是用第 12 周的特征数据集训练异常检测模型，再和第 13 周的规则结果做同口径对比。选的是 Isolation Forest（孤立森林）——无监督方法，不用任何标签，只喂正常样本，偏离"正常分布"的会话就是异常。数据集还是 train.csv：TEST.sys 驱动在 VM 内 10 轮压测采集的 IOCTL 遥测。

整体分两个脚本、两个阶段：

```
train_iforest.py（训练阶段）                predict_iforest.py（预测阶段）
─────────────────────────────            ─────────────────────────────
train.csv + iforest_features.json
        ↓ fit() 训练
iforest_model.joblib  ──────────────────→  joblib.load() 加载模型
train_params.json     ──────────────────→  读特征清单 + 判定阈值
                                           ↓ decision_function 逐会话打分
                                           predictions_<来源>.csv
```

模型和参数全部落盘，预测阶段不接触训练代码——以后换数据只需要重跑 predict。

## 一、iforest_features.json：7 个特征及其依据

特征不是拍脑袋选的，每一个都对应第 13 周规则里验证过有意义的信号：

| 特征 | 含义 | 取值范围 | 选择理由 |
| --- | --- | --- | --- |
| `load_count` | 观测期加载次数 | 0–N 整数 | 恶意驱动常反复加载 |
| `ioctl_count` | IOCTL 总调用数 | ≥0 整数 | 总量最直接的强度信号 |
| `ioctl_rate_per_sec` | 每秒调用频率 | ≥0 浮点 | 对应规则 R3，时间归一化后跨会话可比 |
| `distinct_ioctl` | 不同 IOCTL 种类数 | 1–N 整数 | 对应 R4，行为多样性 |
| `in_len_max` | 输入缓冲区最大长度 | ≥0 | 对应 R5，超长缓冲区异常 |
| `out_len_max` | 输出缓冲区最大长度 | ≥0 | 同上，输出侧 |
| `fail_ratio` | IOCTL 失败比例 | 0–1 | 对应 R6，异常行为常导致失败 |

### 特征泄露排查

第 12 周的特征表里还有 `in_baseline` 这类列，它存在**结构性泄露**：所有正常会话的取值恒定不变，模型若用了它，等于把"in_baseline == 某个常数"当成了正常定义，测试数据稍有偏离就被误判。

处理走"识别 → 排除 → 消融验证"三步：`iforest_features.json` 里用 `excluded` 列表显式声明哪些列是泄露特征、排除理由是什么；`train_iforest.py` 只从 JSON 的 7 特征清单读数据，`in_baseline` 结构上进不了模型。

## 二、train_iforest.py：训练阶段

```python
# 关键骨架
ap.add_argument("--n-estimators", type=int, default=100)    # 树数量可配
ap.add_argument("--contamination", type=float, default=0.1) # 异常比例可配
ap.add_argument("--seed", type=int, default=42)             # 固定种子
df = pd.read_csv("session_features.csv")
train = df[(df.label == "normal") & (df.session_id.isin(train_sessions))]  # 只用正常会话
if len(train) < 20:
    print("[WARN] 正常训练样本少于 20，Isolation Forest 结果不稳定")
model = IsolationForest(n_estimators=..., contamination=..., random_state=...)
model.fit(train[FEATURES])
joblib.dump(model, "iforest_model.joblib")
json.dump({"features": FEATURES, "params": {...}}, open("train_params.json","w"))
```

三个设计点：

- **超参数全部 argparse 化**：`--n-estimators`（树数量，默认 100）、`--contamination`（异常比例，默认 0.1）、`--seed`（随机种子，默认 42），调参不动代码；
- **固定种子保证可复现**：Isolation Forest 建树时要随机抽样本、随机选特征、随机选切分点，`random_state` 固定后这条随机序列每次都一样，运行结果完全可复现；
- **只用 label == normal 的会话训练**，样本少于 20 打 WARN——小样本下森林的分割不稳定，宁可提醒也不静默出错。

训练完模型存 `iforest_model.joblib`，特征清单与参数存 `train_params.json`——后者是 predict 阶段判断定阈值的唯一依据。

## 三、predict_iforest.py：打分与判定

核心三行：

```python
X = df[features].astype(float)                       # 挑出和训练时完全相同的 7 列
df["decision_function"] = model.decision_function(X) # 每个会话一个原始分数
df["anomaly_score"] = -df["decision_function"]       # 取负号，越大越异常
```

判定直接复用训练时保存的阈值：

```python
df["verdict"] = (df["decision_function"] < threshold).map(
    {True: "anomaly", False: "normal"})
```

有个容易搞反的细节：sklearn 的 `decision_function` **越大越正常**，所以判定条件是"小于阈值 = anomaly"。为了不让自己每次都绕一遍，输出里同时存了 `anomaly_score = -decision_function`（越大越异常），查训练参数时一眼能看出方向。

阈值怎么来的：训练后对**训练集自身**算 decision_function，取 10% 低分位作为判定线——测试数据全程不参与训练与调参。

## 四、运行结果

![train_iforest.py 训练输出](/images/week14-train.png)

对三组数据分别预测——训练集自评、正常测试集、合成数据：

![训练集自评](/images/week14-train-selfeval.png)

![正常测试集预测](/images/week14-normal-test.png)

![合成数据预测](/images/week14-synthetic.png)

合并输出 `detection_comparison.csv`，把规则分数和模型分数放到同一张表里：

![合并运行输出](/images/week14-comparison-run.png)

![detection_comparison.csv 内容](/images/week14-comparison-csv.png)

Synthetic 部分是构造的极端数据，充当一组"已知异常"的参照——检验模型学到的正常边界是不是真能把偏离正常行为的会话分出来。

## 五、分数分布与规则 vs 模型散点

![Isolation Forest anomaly score 分布直方图](/images/week14-hist.png)

直方图把三组数据的 `anomaly_score` 画在一起：train（蓝，n=7）聚在 −0.2 ~ −0.14，normal_test（绿，n=3）落在 −0.14 附近——和训练分布几乎重叠，说明正常测试会话确实落在模型学到的"正常"范围内；Synthetic（红，n=3）全部跳到 0.2 一侧，与正常群体完全分离，另有一个 train 会话（约 10% 分位点，正是阈值所在）也落在这一侧——它就是阈值校准的来源。

![规则分数 vs 模型分数散点图](/images/week14-scatter.png)

散点图是更扎心的那张：x 轴是第 13 周规则引擎的分数，y 轴是模型分数。**所有会话的规则分数都是 4（x 轴上没有区分度）**，模型分数也只有 session 1（y=0.199）显著分离——蓝色 agree 点只有它一个，其余全是红色 disagree。

两条曲线拼起来的结论：**模型学到的"正常边界"本质上由 `ioctl_rate_per_sec` 单一维度决定**——调用频率和训练数据同水平的会话判正常，频率明显偏离的判异常。规则引擎对同源会话零区分度，模型的区分度也仅来自这一个特征。

## 六、两个诚实的注意点

1. **对比表里的训练会话要分开陈述**。目前 `detection_comparison.csv` 包含训练会话（session 3–8），它们也被算成了"不一致"（规则 4 分、模型 normal）。但严格说，规则 vs 模型的公平对比只应看测试集——训练集是模型"见过"的数据。正式结论是**测试集不一致 3/3**；训练集那 6 个只是自评参考。`data_source` 列已经把两组分开，报告里分开引用即可。
2. **散点图上没有 Synthetic 的点不是丢了**。规则侧没有给 Synthetic 打分，x 轴无值可画，所以散点图上缺席；它们在分布直方图里有完整的 3 个红柱。

## 七、总结

- **主模型定位**：Isolation Forest，无监督异常检测。不用任何标签，只喂正常样本让模型学"正常行为的分布"，偏离即异常——和第 13 周规则引擎的"人写阈值"形成方法论对照；
- **数据与流程**：train.csv 为 TEST.sys 在 VM 内 10 轮压测的 IOCTL 遥测；流程是读 `iforest_features.json` 特征清单 → 只取正常会话 7 列 → `fit()` 建森林 → 对训练集自身算分取 10% 低分位定阈值 → 模型与参数落盘，预测阶段只做加载与打分；
- **输出含义**：每个会话一个 decision_function 分数（越大越正常）与 verdict 判定（低于阈值 = anomaly）；
- **诚实结论**：当前数据下，模型与规则引擎高度趋同——区分度都来自调用频率这一个维度。这是压测剧本同源导致的：10 轮采集是同一套剧本，特征天然缺乏多样性。等 normal/error 模式重采完成后，`distinct_ioctl`、`fail_ratio` 这些特征才可能真正参与划界，模型相对规则引擎的增量价值才能显现。

> 环境：宿主机 Windows 11 x64 + Python（scikit-learn / pandas / joblib）；上游数据为第 12 周特征数据集与第 13 周 rule_alerts.csv。
