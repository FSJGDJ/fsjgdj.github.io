---
title: 'WEEK13'
description: '用 rules.yaml 承载全部检测规则与阈值，rule_engine.py 只做判定与聚合——第 9 周的 Normal/Review 迁移、7 条行为规则、时间窗口计算与 20 个测试用例。'
pubDate: 2026-10-24
tags: ["Windows", "驱动", "Python", "检测"]
---

## 说明

第 12 周把四份异构数据归一化成了特征数据集，但那只是"把事实记下来"。这一周要回答的问题是：**记下来的事实里，哪些算异常？**

任务是实现一个规则检测程序：读取第 12 周的四张表，按规则逐条判定，输出告警。核心设计决策只有一个——把"什么算异常"的判断标准从代码里抽出来，变成纯数据。`rules.yaml` 存规则名、阈值、权重、告警等级；`rule_engine.py` 只做判定与聚合。以后调参不动代码。

## 生成脚本

<details>
<summary>展开查看 rules.yaml 完整配置</summary>

```yaml
# ============================================================
# rules.yaml — 第13周规则配置
# 所有规则的阈值 / 权重 / 告警等级都在这里调，改配置不改代码
# 等级从低到高: none < low < medium < high < critical
# ============================================================

rules:
  # ---------- 第9周 Normal/Review 迁移（静态规则） ----------
  - id: W9_Normal
    type: static_all            # 有效签名 且 路径不在非标准目录 = Normal
    require:
      SignatureStatus: Valid
    require_not:                # 否定条件: 字段值不得等于指定值
      PathCategory: NonStandard_Path
    weight: 0                   # 正常不产生告警，仅作标签
    level: none

  - id: W9_Review
    type: static_any            # 任一条件满足 = Review
    require_any:
      caps: nonstandard_path    # sensitive_caps 中含该能力
      SignatureStatus: [Invalid, Unknown, ""]   # 签名异常/缺失
    weight: 1
    level: low

  # ---------- 第13周新增行为规则 ----------
  - id: R1_Install_Then_Load
    type: install_then_load     # 服务安装后短时间内出现驱动加载
    window_seconds: 120
    weight: 3
    level: high

  - id: R2_Static_Combo
    type: static_combo          # 非常规路径/签名异常/首次出现 至少两项
    conditions:
      nonstandard_path: true    # sensitive_caps 含 nonstandard_path
      unsigned: true            # sensitive_caps 含 unsigned
      first_seen: true          # load_events 中出现次数 <= 1（观测期内首次出现）
    min_match: 2
    weight: 2
    level: medium

  - id: R3_Ioctl_High_Rate
    type: ioctl_rate            # IOCTL 短时间高频调用
    window_seconds: 60
    min_count: 30               # 窗口内调用次数下限（按第12周实测 64次/会话 校准）
    weight: 2
    level: medium

  - id: R4_Ioctl_Variety
    type: ioctl_variety         # 短时间内出现多种 IOCTL
    window_seconds: 60
    min_distinct: 3             # 窗口内不同 ioctl_code 数下限（实测数据共 3 种）
    weight: 2
    level: medium

  - id: R5_Buffer_Abnormal
    type: buffer_length         # 缓冲区长度超出正常范围
    max_input_len: 1024         # 实测 in_len_max = 600
    max_output_len: 8192        # 实测 out_len_max = 4096
    weight: 2
    level: medium

  - id: R6_Fail_Ratio
    type: fail_ratio            # IOCTL 失败比例超过阈值
    threshold: 0.5
    min_calls: 10               # 调用次数下限，避免小样本误报
    weight: 3
    level: high

  - id: R7_Static_Dynamic
    type: static_dynamic        # 静态敏感能力 + 动态异常行为同时出现
    depends_on:                 # 依赖这些动态规则的结果，须最后计算
      - R3_Ioctl_High_Rate
      - R4_Ioctl_Variety
      - R5_Buffer_Abnormal
      - R6_Fail_Ratio
    # 静态敏感能力: sensitive_caps 含以下任一（self_defined_driver 视为敏感）
    static_caps: [nonstandard_path, unsigned, self_defined_driver]
    weight: 4
    level: critical
```

</details>

<details>
<summary>展开查看 rule_engine.py 完整代码</summary>

```python
# -*- coding: utf-8 -*-
r"""
rule_engine.py — 第13周规则检测引擎
读取第12周特征数据 (driver_metadata / load_events / ioctl_events / session_features)
按 rules.yaml 中的规则逐条判定, 输出 rule_alerts.csv

运行: py -3.14 rule_engine.py [数据目录，默认脚本所在目录]
"""
import sys
import yaml
import pandas as pd
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
LEVEL_ORDER = ["none", "low", "medium", "high", "critical"]


# ---------------- 配置与数据加载 ----------------

def load_rules(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["rules"]


def load_data(in_dir: Path) -> dict:
    io = pd.read_csv(in_dir / "ioctl_events.csv")
    io["timestamp"] = pd.to_datetime(io["timestamp"], utc=True, format="mixed", errors="coerce")
    io["status_ok"] = io["status_ok"].astype(str).str.lower() == "true"

    load = pd.read_csv(in_dir / "load_events.csv")
    load["timestamp"] = pd.to_datetime(load["timestamp"], errors="coerce")

    meta = pd.read_csv(in_dir / "driver_metadata.csv").fillna("")
    sess = pd.read_csv(in_dir / "session_features.csv")
    return {"io": io, "load": load, "meta": meta, "sess": sess}


def caps_of(row) -> set:
    """把 sensitive_caps 字符串拆成集合"""
    return {c for c in str(row.get("sensitive_caps", "")).split(";") if c and c != "none"}


# ---------------- 各规则判定函数 ----------------
# 每个 check 返回命中列表: [{"driver":..., "session":..., "evidence":...}]
# session 为 None 表示驱动级命中（不属于某个会话）

def check_static_all(rule, data):
    """W9_Normal: require 全部相等 且 require_not 全部不等"""
    req = rule.get("require", {})
    req_not = rule.get("require_not", {})
    m = data["meta"]
    mask = pd.Series(True, index=m.index)
    for col, val in req.items():
        mask &= m[col].astype(str) == str(val)
    for col, val in req_not.items():
        mask &= m[col].astype(str) != str(val)
    return [{"driver": r["file_hash"], "session": None,
             "evidence": f"driver_metadata.csv hash={r['file_hash'][:12]}.."}
            for _, r in m[mask].iterrows()]


def check_static_any(rule, data):
    """W9_Review: 任一条件满足（sensitive_caps 含指定能力 或 签名状态异常）"""
    m = data["meta"]
    hits = []
    caps_cfg = rule["require_any"].get("caps", [])
    if isinstance(caps_cfg, str):          # yaml 里写成单个字符串时兼容
        caps_cfg = [caps_cfg]
    sig_bad_list = rule["require_any"].get("SignatureStatus", [])
    for _, r in m.iterrows():
        cs = caps_of(r)
        sig_bad = str(r["SignatureStatus"]) in sig_bad_list
        cap_hit = any(c in cs for c in caps_cfg)
        if sig_bad or cap_hit:
            hits.append({"driver": r["file_hash"], "session": None,
                         "evidence": f"driver_metadata.csv hash={r['file_hash'][:12]}.. "
                                     f"caps={r['sensitive_caps']} sig={r['SignatureStatus'] or 'N/A'}"})
    return hits


def check_install_then_load(rule, data):
    """R1: 同一 ServiceName, 安装事件后 window 秒内出现驱动加载"""
    win = rule["window_seconds"]
    load = data["load"].dropna(subset=["ServiceName"]).sort_values("timestamp")
    hits = []
    for svc, g in load.groupby("ServiceName"):
        rows = g.to_dict("records")
        for i in range(len(rows) - 1):
            a, b = rows[i], rows[i + 1]
            if "install" not in str(a["EventType"]).lower():
                continue
            if "load" not in str(b["EventType"]).lower():
                continue
            dt = (b["timestamp"] - a["timestamp"]).total_seconds()
            if 0 <= dt <= win:
                h = b.get("file_hash", "") or f"unknown({b.get('ImagePath', '')})"
                hits.append({"driver": h, "session": None,
                             "evidence": f"load_events.csv 行{i+2},{i+3} 服务={svc} 间隔={dt:.0f}s"})
    return hits


def check_static_combo(rule, data):
    """R2: 非常规路径 / 签名异常(unsigned) / 首次出现 至少 min_match 项"""
    cond = rule["conditions"]
    load_counts = data["load"]["file_hash"].value_counts()
    hits = []
    for _, r in data["meta"].iterrows():
        cs = caps_of(r)
        matched = []
        if cond.get("nonstandard_path") and "nonstandard_path" in cs:
            matched.append("nonstandard_path")
        if cond.get("unsigned") and "unsigned" in cs:
            matched.append("unsigned")
        if cond.get("first_seen") and load_counts.get(r["file_hash"], 0) <= 1:
            matched.append("first_seen")
        if len(matched) >= rule["min_match"]:
            hits.append({"driver": r["file_hash"], "session": None,
                         "evidence": f"driver_metadata.csv hash={r['file_hash'][:12]}.. "
                                     f"命中[{'+'.join(matched)}]"})
    return hits


def _rolling_window_stat(io, fn, window_seconds):
    """按 (driver, session) 在滚动时间窗口上做统计, 返回 {(driver, session): stat}"""
    out = {}
    for (h, s), g in io.groupby(["file_hash", "session_id"]):
        g = g.dropna(subset=["timestamp"]).set_index("timestamp").sort_index()
        if g.empty:
            continue
        out[(h, int(s))] = fn(g.rolling(f"{window_seconds}s"))
    return out


def check_ioctl_rate(rule, data):
    """R3: 滚动窗口内调用次数 >= min_count"""
    win = rule["window_seconds"]
    stats = _rolling_window_stat(data["io"], lambda r: r["ioctl_code"].count().max(), win)
    return [{"driver": h, "session": s,
             "evidence": f"ioctl_events.csv session={s} 峰值{int(v)}次/{win}s"}
            for (h, s), v in stats.items() if v >= rule["min_count"]]


def check_ioctl_variety(rule, data):
    """R4: 滑动窗口内不同 ioctl_code 数 >= min_distinct（双指针, 兼容字符串编号）"""
    win = pd.Timedelta(seconds=rule["window_seconds"])
    hits = []
    for (h, s), g in data["io"].groupby(["file_hash", "session_id"]):
        g = g.dropna(subset=["timestamp"]).sort_values("timestamp")
        ts, codes = g["timestamp"].tolist(), g["ioctl_code"].tolist()
        best, j, cur = 0, 0, {}
        for i in range(len(ts)):
            cur[codes[i]] = cur.get(codes[i], 0) + 1
            while ts[j] < ts[i] - win:
                cur[codes[j]] -= 1
                if cur[codes[j]] == 0:
                    del cur[codes[j]]
                j += 1
            best = max(best, len(cur))
        if best >= rule["min_distinct"]:
            hits.append({"driver": h, "session": int(s),
                         "evidence": f"ioctl_events.csv session={s} 窗口内{best}种IOCTL"})
    return hits


def check_buffer_length(rule, data):
    """R5: input_length / output_length 超出正常范围"""
    io = data["io"]
    bad = io[(io["input_length"] > rule["max_input_len"]) |
             (io["output_length"] > rule["max_output_len"])]
    return [{"driver": r["file_hash"], "session": int(r["session_id"]),
             "evidence": f"ioctl_events.csv 行{i+2} in={r['input_length']} out={r['output_length']}"}
            for i, r in bad.iterrows()]


def check_fail_ratio(rule, data):
    """R6: 会话级失败比例 >= threshold 且调用次数 >= min_calls"""
    sess = data["sess"]
    bad = sess[(sess["fail_ratio"] >= rule["threshold"]) &
               (sess["ioctl_count"] >= rule["min_calls"])]
    return [{"driver": r["file_hash"], "session": int(r["session_id"]),
             "evidence": f"session_features.csv session={r['session_id']} "
                         f"fail_ratio={r['fail_ratio']} calls={r['ioctl_count']}"}
            for _, r in bad.iterrows()]


def check_static_dynamic(rule, data, hits_by_rule):
    """R7: 静态敏感能力 + (depends_on 中任一动态规则命中)"""
    dyn_drivers = {h["driver"] for rid in rule["depends_on"] for h in hits_by_rule.get(rid, [])}
    static_sensitive = {}   # file_hash -> caps 描述
    for _, r in data["meta"].iterrows():
        cs = caps_of(r)
        if cs & set(rule["static_caps"]):
            static_sensitive[r["file_hash"]] = "+".join(sorted(cs))
    for _, r in data["sess"].iterrows():
        cap = str(r["sensitive_caps"])
        if cap in rule["static_caps"]:
            static_sensitive.setdefault(r["file_hash"], cap)

    return [{"driver": h, "session": None,
             "evidence": f"静态能力[{static_sensitive[h]}] + 动态规则命中"}
            for h in sorted(dyn_drivers & set(static_sensitive))]


# ---------------- 分数聚合与输出 ----------------

def build_alerts(rules, hits_by_rule, data):
    """按 (driver, session) 聚合: score=权重之和, level=最高等级"""
    rule_map = {r["id"]: r for r in rules}
    agg = {}   # (driver, session_key) -> dict

    for rid, hits in hits_by_rule.items():
        r = rule_map[rid]
        for h in hits:
            key = (h["driver"], h["session"] if h["session"] is not None else "-")
            a = agg.setdefault(key, {"driver": h["driver"], "session_id": h["session"],
                                     "hit_rules": [], "score": 0,
                                     "levels": [], "evidence": []})
            a["hit_rules"].append(rid)
            a["score"] += r.get("weight", 0)
            a["levels"].append(r.get("level", "low"))
            a["evidence"].append(h["evidence"])

    rows = []
    for a in agg.values():
        rows.append({
            "driver": a["driver"],
            "session_id": "" if a["session_id"] is None else a["session_id"],
            "hit_rules": ";".join(sorted(set(a["hit_rules"]))),
            "score": a["score"],
            "level": max(a["levels"], key=LEVEL_ORDER.index),
            "evidence": " | ".join(a["evidence"][:5]),   # 证据最多保留5条防爆炸
        })
    rows.sort(key=lambda x: (-x["score"], x["driver"]))
    return pd.DataFrame(rows, columns=["driver", "session_id", "hit_rules",
                                       "score", "level", "evidence"])


# 每种 type 对应的判定函数; static_dynamic 需要 hits_by_rule, 特殊处理
CHECKS = {
    "static_all": check_static_all,
    "static_any": check_static_any,
    "install_then_load": check_install_then_load,
    "static_combo": check_static_combo,
    "ioctl_rate": check_ioctl_rate,
    "ioctl_variety": check_ioctl_variety,
    "buffer_length": check_buffer_length,
    "fail_ratio": check_fail_ratio,
}


def main():
    in_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else SCRIPT_DIR
    rules = load_rules(SCRIPT_DIR / "rules.yaml")
    data = load_data(in_dir)

    hits_by_rule = {}
    for rule in rules:   # 按 yaml 顺序执行, R7 声明依赖故天然排在动态规则之后
        rtype = rule["type"]
        if rtype == "static_dynamic":
            hits = check_static_dynamic(rule, data, hits_by_rule)
        else:
            hits = CHECKS[rtype](rule, data)
        hits_by_rule[rule["id"]] = hits
        print(f"[{rule['id']:<22}] 命中 {len(hits)} 条")

    alerts = build_alerts(rules, hits_by_rule, data)
    out = SCRIPT_DIR / "rule_alerts.csv"
    alerts.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\n共 {len(alerts)} 条告警 -> {out}")
    if not alerts.empty:
        print(alerts.drop(columns="evidence").head(15).to_string(index=False))


if __name__ == "__main__":
    main()
```

</details>

<details>
<summary>展开查看 test_rule_engine.py 完整代码</summary>

```python
# -*- coding: utf-8 -*-
r"""
test_rule_engine.py — 每条规则的命中/不命中用例
用手工构造的迷你 DataFrame 直接注入各 check 函数, 不依赖真实数据

运行: py -3.14 test_rule_engine.py
"""
import pandas as pd
from rule_engine import (CHECKS, check_static_dynamic, load_rules,
                         build_alerts, LEVEL_ORDER)

RULES = {r["id"]: r for r in load_rules(__import__("pathlib").Path("rules.yaml").resolve())}
PASS, FAIL = [], []


def expect(rule_id, hits, should_hit, desc):
    ok = bool(hits) == should_hit
    (PASS if ok else FAIL).append(f"{rule_id} {'命中' if should_hit else '不命中'}用例: {desc}")
    print(f"  {'PASS' if ok else 'FAIL'}  [{rule_id} | {'命中' if should_hit else '不命中'}] {desc}")


def meta_row(hash_="a" * 64, sig="Valid", pc="Standard_Path", caps="none"):
    return {"file_hash": hash_, "path": "C:\\x.sys", "Signature": "X",
            "SignatureStatus": sig, "PathCategory": pc, "sensitive_caps": caps}


def sess_row(hash_="a" * 64, sid=1, calls=64, fail=0.0, caps="none"):
    return {"driver": "X.sys", "file_hash": hash_, "session_id": sid,
            "load_count": 0, "in_baseline": 0, "ioctl_count": calls,
            "ioctl_rate_per_sec": 10.0, "distinct_ioctl": 1, "in_len_max": 8,
            "in_len_mean": 8, "out_len_max": 8, "out_len_mean": 8,
            "fail_ratio": fail, "sensitive_caps": caps}


def io_rows(n=1, code="0x80002004", in_len=8, out_len=8, status="0x00000000",
            hash_="a" * 64, sid=1, t0="2026-10-17 06:00:00+00:00", step_sec=1.0):
    ts = pd.date_range(t0, periods=n, freq=f"{step_sec}s")
    return pd.DataFrame({
        "timestamp": ts, "pid": 8848, "ioctl_code": code, "device_type": 0x8000,
        "function": 2049, "method": 0, "access": 0, "input_length": in_len,
        "output_length": out_len, "completion_status": status, "session_id": sid,
        "status_ok": status == "0x00000000", "file_hash": hash_, "driver": "X.sys"})


def data(**kw):
    d = {"io": io_rows(), "load": pd.DataFrame(columns=[
            "timestamp", "EventType", "ServiceName", "ImagePath", "file_hash",
            "SignatureStatus", "DriverState"]),
         "meta": pd.DataFrame([meta_row()]), "sess": pd.DataFrame([sess_row()])}
    d.update(kw)
    return d


T = lambda s: pd.Timestamp(s)

# ---------- W9_Normal ----------
print("\n== W9_Normal (static_all) ==")
expect("W9_Normal", CHECKS["static_all"](RULES["W9_Normal"], data()), True, "标准路径+有效签名")
d2 = data(); d2["meta"] = pd.DataFrame([meta_row(pc="NonStandard_Path")])
expect("W9_Normal", CHECKS["static_all"](RULES["W9_Normal"], d2), False, "非标准路径")

# ---------- W9_Review ----------
print("\n== W9_Review (static_any) ==")
d3 = data(); d3["meta"] = pd.DataFrame([meta_row(pc="NonStandard_Path", caps="nonstandard_path")])
expect("W9_Review", CHECKS["static_any"](RULES["W9_Review"], d3), True, "sensitive_caps=nonstandard_path")
expect("W9_Review", CHECKS["static_any"](RULES["W9_Review"], data()), False, "标准路径+Valid+none")

# ---------- R1 ----------
print("\n== R1_Install_Then_Load (install_then_load) ==")
def load_df(rows):
    return pd.DataFrame(rows)
hit_load = load_df([
    {"timestamp": T("2026-05-13 20:30:00"), "EventType": "Service_Install", "ServiceName": "SVC1",
     "ImagePath": "c:\\x.sys", "file_hash": "a" * 64, "SignatureStatus": "Valid", "DriverState": "Installed"},
    {"timestamp": T("2026-05-13 20:31:00"), "EventType": "ImageLoaded", "ServiceName": "SVC1",
     "ImagePath": "c:\\x.sys", "file_hash": "a" * 64, "SignatureStatus": "Valid", "DriverState": "Running"}])
miss_load = hit_load.copy()
miss_load.loc[1, "timestamp"] = T("2026-05-13 20:35:00")   # 间隔300s > 窗口120s
expect("R1", CHECKS["install_then_load"](RULES["R1_Install_Then_Load"], data(load=hit_load)),
       True, "安装后60s出现ImageLoaded")
expect("R1", CHECKS["install_then_load"](RULES["R1_Install_Then_Load"], data(load=miss_load)),
       False, "安装后300s才加载(超出窗口)")

# ---------- R2 ----------
print("\n== R2_Static_Combo (static_combo) ==")
d4 = data(); d4["meta"] = pd.DataFrame([meta_row(pc="NonStandard_Path", caps="nonstandard_path;unsigned")])
d4["load"] = pd.DataFrame([{"file_hash": "a" * 64}])       # 出现1次=first_seen
expect("R2", CHECKS["static_combo"](RULES["R2_Static_Combo"], d4), True, "非常规路径+unsigned+首次出现(3项)")
d5 = data(); d5["meta"] = pd.DataFrame([meta_row(pc="NonStandard_Path", caps="nonstandard_path")])
d5["load"] = pd.DataFrame([{"file_hash": "a" * 64}, {"file_hash": "a" * 64}])  # 已出现2次≠首次
expect("R2", CHECKS["static_combo"](RULES["R2_Static_Combo"], d5), False, "仅1项成立且非首次出现")

# ---------- R3 ----------
print("\n== R3_Ioctl_High_Rate (ioctl_rate) ==")
busy = io_rows(n=40, step_sec=0.5)                          # 40次/20s
calm = io_rows(n=10, step_sec=5.0)                          # 10次/45s
expect("R3", CHECKS["ioctl_rate"](RULES["R3_Ioctl_High_Rate"], data(io=busy)), True, "20s内40次调用")
expect("R3", CHECKS["ioctl_rate"](RULES["R3_Ioctl_High_Rate"], data(io=calm)), False, "45s内仅10次调用")

# ---------- R4 ----------
print("\n== R4_Ioctl_Variety (ioctl_variety) ==")
many = io_rows(n=6, step_sec=1.0)
many["ioctl_code"] = [f"0x8000200{i}" for i in range(6)]    # 6种
one = io_rows(n=6, code="0x80002004", step_sec=1.0)         # 1种
expect("R4", CHECKS["ioctl_variety"](RULES["R4_Ioctl_Variety"], data(io=many)), True, "60s内6种IOCTL")
expect("R4", CHECKS["ioctl_variety"](RULES["R4_Ioctl_Variety"], data(io=one)), False, "60s内仅1种重复调用")

# ---------- R5 ----------
print("\n== R5_Buffer_Abnormal (buffer_length) ==")
big = io_rows(in_len=8192)
norm = io_rows(in_len=600, out_len=4096)                    # 实测数据的最大值
expect("R5", CHECKS["buffer_length"](RULES["R5_Buffer_Abnormal"], data(io=big)), True, "input_length=8192超限")
expect("R5", CHECKS["buffer_length"](RULES["R5_Buffer_Abnormal"], data(io=norm)), False, "600/4096在正常范围")

# ---------- R6 ----------
print("\n== R6_Fail_Ratio (fail_ratio) ==")
d6 = data(); d6["sess"] = pd.DataFrame([sess_row(calls=20, fail=0.6)])
d7 = data(); d7["sess"] = pd.DataFrame([sess_row(calls=100, fail=0.12)])
expect("R6", CHECKS["fail_ratio"](RULES["R6_Fail_Ratio"], d6), True, "20次调用失败60%")
expect("R6", CHECKS["fail_ratio"](RULES["R6_Fail_Ratio"], d7), False, "100次调用失败12%")

# ---------- R7 ----------
print("\n== R7_Static_Dynamic (static_dynamic) ==")
d8 = data()
d8["sess"] = pd.DataFrame([sess_row(caps="self_defined_driver")])
hits_dyn = {"R3_Ioctl_High_Rate": [{"driver": "a" * 64, "session": 1, "evidence": "x"}]}
expect("R7", check_static_dynamic(RULES["R7_Static_Dynamic"], d8, hits_dyn),
       True, "self_defined_driver + 命中R3")
expect("R7", check_static_dynamic(RULES["R7_Static_Dynamic"], d8, {}),
       False, "有静态能力但无动态命中")
d9 = data()
d9["sess"] = pd.DataFrame([sess_row(caps="none")])
expect("R7", check_static_dynamic(RULES["R7_Static_Dynamic"], d9, hits_dyn),
       False, "命中R3但无静态敏感能力")

# ---------- 端到端: 分数聚合与等级 ----------
print("\n== 端到端聚合 ==")
rules = list(RULES.values())
hbr = {"R3_Ioctl_High_Rate": [{"driver": "a" * 64, "session": 1, "evidence": "e1"}],
       "R6_Fail_Ratio": [{"driver": "a" * 64, "session": 1, "evidence": "e2"}]}
alerts = build_alerts(rules, hbr, d8)
a = alerts.iloc[0]
ok = (a["driver"] == "a" * 64 and a["score"] == 2 + 3      # R3权重2 + R6权重3
      and a["level"] == "high" and "R3_Ioctl_High_Rate" in a["hit_rules"])
(PASS if ok else FAIL).append("端到端: score=5, level=high")
print(f"  {'PASS' if ok else 'FAIL'}  端到端聚合 score={a['score']} level={a['level']}")

print(f"\n========== 结果: {len(PASS)} PASS / {len(FAIL)} FAIL ==========")
if FAIL:
    for f in FAIL:
        print("  FAIL:", f)
    raise SystemExit(1)
```

</details>

## 附件

- [📥 rules.yaml：9 条规则的阈值与等级配置](/rules.yaml)
- [📥 rule_engine.py：规则检测引擎](/rule_engine.py)
- [📥 test_rule_engine.py：20 个测试用例](/test_rule_engine.py)
- [📥 rule_alerts.csv：真实数据检测结果（131 行）](/rule_alerts.csv)

## 一、rules.yaml：条件迁移与统一结构

第 9 周的 Normal/Review 判定原本写在脚本里，这次迁移成两条静态规则：

```yaml
rules:
  - id: W9_Normal
    type: static_all            # 有效签名 且 路径不在非标准目录 = Normal
    require:
      SignatureStatus: Valid
    require_not:                # 否定条件: 字段值不得等于指定值
      PathCategory: NonStandard_Path
    weight: 0                   # 正常不产生告警，仅作标签
    level: none

  - id: W9_Review
    type: static_any            # 任一条件满足 = Review
    require_any:
      caps: nonstandard_path
      SignatureStatus: [Invalid, Unknown, ""]
    weight: 1
    level: low
```

迁移时发现一个语义问题：真实数据里 `PathCategory` 的取值是 `System32_Drivers` / `System32_Other` / `NonStandard_Path`，**根本没有 `Standard_Path` 这个值**。"标准路径"没法用正向枚举表达，所以加了 `require_not` 否定式字段——不在非标准目录 + 签名有效 = Normal。迁移后 117 个驱动被正确标记。

每条规则统一五个字段：`id`（告警里的标识）、`type`（决定引擎路由到哪个判定函数）、阈值参数（每类规则不同）、`weight`（命中加多少分）、`level`（单条规则的等级）。最终告警的 `score` 是命中规则权重之和，`level` 取命中规则中最高的。

阈值不是拍脑袋，全部按第 12 周实测分布校准，yaml 注释里刻意保留了依据：

| 阈值 | 依据 |
|---|---|
| R3 `min_count: 30` / 窗口 60s | 实测每会话 64 次调用、最高 32000 次/秒 |
| R4 `min_distinct: 3` | 实测整个数据集只有 3 种 ioctl_code，设 4 就永远不命中 |
| R5 `1024 / 8192` | 实测 in_len_max=600、out_len_max=4096，留余量 |
| R6 `0.5 + min_calls: 10` | 实测失败率 6.25%；min_calls 防"1 次失败 1 次 = 100%"的小样本误报 |

## 二、rule_engine.py：加载层与主流程

### 2.1 加载层的三个细节

```python
def load_data(in_dir: Path) -> dict:
    io = pd.read_csv(in_dir / "ioctl_events.csv")
    io["timestamp"] = pd.to_datetime(io["timestamp"], utc=True, format="mixed", errors="coerce")
    io["status_ok"] = io["status_ok"].astype(str).str.lower() == "true"
    load = pd.read_csv(in_dir / "load_events.csv")
    load["timestamp"] = pd.to_datetime(load["timestamp"], errors="coerce")
    meta = pd.read_csv(in_dir / "driver_metadata.csv").fillna("")
    sess = pd.read_csv(in_dir / "session_features.csv")
    return {"io": io, "load": load, "meta": meta, "sess": sess}
```

- `utc=True, format="mixed"`：ioctl 时间戳带 `+00:00` 时区且格式不统一，`errors="coerce"` 把坏值变 NaT 而不是崩掉；
- `status_ok`：CSV 里的布尔值可能被读成字符串，统一转小写再比较；
- `fillna("")`：driver_metadata 里签名字段有空值（Edge 更新服务），空字符串比 NaN 好处理。

还有一个全文件复用的小函数 `caps_of`：把 `"nonstandard_path;unsigned"` 这种分号拼接拆成集合。所有涉及敏感能力的判断都走它，格式变了只改一处。

### 2.2 主流程

```
读 yaml → 读四张表 → 按 yaml 顺序逐条判定 → 聚合 → 写 CSV → 控制台摘要
```

两个设计点：

- **按 yaml 顺序执行是刻意的**。R7 组合规则写在配置最后，等它跑的时候前面的 R3–R6 命中结果已经在内存里了，依赖关系靠文件顺序而非代码调度实现；
- 每条规则跑完立即打印命中数，运行过程可观察：

```
[W9_Normal             ] 命中 117 条
[W9_Review             ] 命中 3 条
[R1_Install_Then_Load  ] 命中 0 条
[R2_Static_Combo       ] 命中 2 条
[R3_Ioctl_High_Rate    ] 命中 10 条
[R4_Ioctl_Variety      ] 命中 10 条
[R5_Buffer_Abnormal    ] 命中 0 条
[R6_Fail_Ratio         ] 命中 0 条
[R7_Static_Dynamic     ] 命中 1 条
```

## 三、新增行为规则：yaml 与脚本各管一半

任务要求的 7 条行为规则，配置和逻辑分开放：

**rules.yaml 里是规则 ID 和阈值：**

| 任务原文 | yaml 中对应 id |
| --- | --- |
| 服务安装后短时间内出现驱动加载 | `R1_Install_Then_Load` |
| 非常规路径/签名异常/首次出现至少两项 | `R2_Static_Combo` |
| IOCTL 短时间高频调用 | `R3_Ioctl_High_Rate` |
| 短时间内出现多种 IOCTL | `R4_Ioctl_Variety` |
| 缓冲区长度超出正常范围 | `R5_Buffer_Abnormal` |
| IOCTL 失败比例超过阈值 | `R6_Fail_Ratio` |
| 静态敏感能力与动态异常同时出现 | `R7_Static_Dynamic` |

**rule_engine.py 里是判定逻辑，按 type 分发：**

| 函数 | 逻辑 |
| --- | --- |
| `check_install_then_load` | 同一 ServiceName，安装事件后 window 秒内出现加载事件 |
| `check_static_combo` | 数 nonstandard_path / unsigned / first_seen 满足几项，≥2 命中 |
| `check_ioctl_rate` | 按（驱动，会话）滚动 60s 时间窗口统计调用次数峰值 |
| `check_ioctl_variety` | 双指针滑动窗口统计 distinct ioctl_code 峰值 |
| `check_buffer_length` | 逐行比对 input_length / output_length 是否超 yaml 上限 |
| `check_fail_ratio` | 查 session_features 的 fail_ratio ≥ 阈值且调用次数达标 |
| `check_static_dynamic` | 复用 R3–R6 命中结果 + 静态敏感能力做组合判定 |

所有判定函数遵守同一个契约：返回命中列表，每条命中是 `{driver, session, evidence}` 字典，session 为 None 表示驱动级命中。这个统一契约是后面聚合能一把算完的前提。

两个有代表性的实现：

**R3 用 pandas 滚动时间窗口**——把时间列做成索引后 `rolling("60s")`，对每个时间点统计"过去 60 秒内有多少条"，取全程峰值：

```python
stats = _rolling_window_stat(data["io"], lambda r: r["ioctl_code"].count().max(), win)
```

**R4 手写双指针滑动窗口**——本想同样用 Rolling 的 `apply` 统计窗口内不同 code 数，但 pandas 的 Rolling **不接受字符串列**（ioctl_code 是 `"0x80002004"`）。改成双指针：`i` 是窗口右端，`j` 是左端，字典 `cur` 实时维护窗口内每种 code 的计数，左端滑出就减一、减到 0 删键，`len(cur)` 即当前窗口种类数。

## 四、运行结果与 rule_alerts.csv

对真实数据运行后，TEST.sys 的告警排最前面（按 score 降序）：

```
driver                       session_id  hit_rules                        score  level
e05e004cbcc7...(TEST.sys)    1           R3_Ioctl_High_Rate;R4_Variety    4      medium
e05e004cbcc7...(TEST.sys)    ...         ...                              4      medium
e05e004cbcc7...(TEST.sys)                R7_Static_Dynamic                4      critical
0222b9a2...(Defender驱动)     (空)        R2_Static_Combo;W9_Review        3      medium
09c1e9a0...(Defender驱动)     (空)        R2_Static_Combo;W9_Review        3      medium
e845e428...(Defender驱动)     (空)        W9_Review                        1      low
```

- **TEST.sys**：10 个会话全部命中 R3（60s 窗口峰值 64 次调用）+ R4（3 种 IOCTL），score 4 / medium；R7 组合规则判 critical；
- 2 个 Defender 驱动命中 R2 + W9_Review（非常规路径 + 首次出现），1 个仅 W9_Review；117 个正常驱动被 W9_Normal 标记；
- **R1/R5/R6 无命中，原因明确**：时间线全是 Service_Install、没有 ImageLoaded 事件（R1 无从触发）；缓冲区长度 600/4096 在正常范围（R5）；失败率 6.25% 远低于 0.5（R6）。

## 五、告警记录字段

| 要求字段 | csv 列名 | 内容示例 |
| --- | --- | --- |
| 驱动 | `driver` | SHA256 哈希 |
| 会话 | `session_id` | 1–10；空白表示驱动级告警 |
| 命中规则 | `hit_rules` | 分号拼接，可能多个 |
| 分数 | `score` | 命中规则 weight 之和 |
| 等级 | `level` | none / low / medium / high / critical |
| 原始数据位置 | `evidence` | `ioctl_events.csv session=1 峰值64次/60s` |

`evidence` 在每个判定函数命中时就地生成，格式是"CSV 文件名 + 行号或会话号"，聚合时最多保留 5 条防止单条告警携带几百条证据。

**session_id 有数字和空白是两类告警**：有数字 = 由某次具体采集会话的动态行为触发，能定位到时间窗口；空白 = 描述的是驱动固有的静态属性（路径、签名、首次出现），数据来源是 `driver_metadata.csv`——这张表一驱动一行，根本没有会话维度。R7 虽然用到了动态结果，但结论落在"这个驱动危险吗"，所以也是驱动级。

## 六、测试用例：20 PASS / 0 FAIL

`test_rule_engine.py` 为每条规则构造一对命中/不命中用例，思路是**手工构造迷你 DataFrame 直接注入判定函数**，不依赖真实数据——想要什么结果就造什么数据，完全可控：

| 规则 | 命中用例 | 不命中用例 |
| --- | --- | --- |
| W9_Normal | 标准路径 + 有效签名 | 非标准路径 |
| W9_Review | sensitive_caps 含 nonstandard_path | 标准路径 + Valid + none |
| R1 | 安装后 60s 出现 ImageLoaded | 安装后 300s 才加载（超 120s 窗口） |
| R2 | 三项条件全成立 | 仅 1 项成立且已出现 2 次 |
| R3 | 20s 内 40 次调用 | 45s 内仅 10 次 |
| R4 | 60s 内 6 种 IOCTL | 60s 内仅 1 种重复调用 |
| R5 | input_length=8192 超限 | 600/4096 在正常范围 |
| R6 | 20 次调用失败 60% | 100 次调用失败 12% |
| R7 | 自研驱动 + 命中 R3 | 有静态能力但无动态命中 / 命中 R3 但无静态能力 |
| 端到端 | R3+R6 同命中 → score=5、level=high | — |

两组值得说的设计：R6 的不命中用例失败**次数**（12 次）比命中用例还多，但比例 12% 且样本 100 次，两个门槛都没过——专门验证 `min_calls` 防小样本误报；R7 是组合规则，必须验证"缺一边都不行"，所以比别的规则多一个反例。用例失败时逐条打印 FAIL 描述并以退出码 1 结束，可以当 CI 门禁。

## 七、踩坑记录

1. **Rolling 没有 `.size`**：pandas 的滚动窗口对象没有 size 方法，统计次数要用 `count().max()`；
2. **Rolling.apply 不支持字符串列**：ioctl_code 是十六进制字符串，直接 `apply` 抛 `DataError`。R4 改手写双指针，顺带比 Rolling+apply 快；
3. **yaml 里单个字符串会退化成逐字符迭代**：`caps: nonstandard_path` 写成字符串后，`for c in caps` 迭代的是每个字符，第一条 Review 用例直接失败。兼容处理：是字符串就包成列表；
4. **PathCategory 没有 `Standard_Path`**：正向枚举"标准路径"在真实数据里永远为空，改 `require_not: NonStandard_Path` 否定式表达。

## 八、总结

- **配置驱动是这个引擎的地基**：`type` 字符串是配置与代码的接口，yaml 里永远不写逻辑；CHECKS 分发表让主流程不写一串 if。第 14 周加规则 = yaml 加一段 + 代码加一个函数 + 表里加一行；
- **统一命中契约聚合异构规则**：静态的、时间窗口的、组合的规则都汇成 `{driver, session, evidence}`，聚合器一把算完分数与等级；
- **阈值必须有数据依据**：每个阈值都对照第 12 周实测分布校准，并在 yaml 注释里保留依据，调参时可追溯；
- **诚实结论**：R3/R4 对 TEST.sys 全命中，本质是压测剧本的调用密度导致的，不代表真实威胁——10 个会话还是第 12 周说的同一套剧本。等 normal/error 模式重采完成后，R5/R6 这类规则才能真正拉开正常与异常的区分度。

> 环境：宿主机 Windows 11 x64 + Python 3.14（pandas 3.x、PyYAML）；数据与脚本目录 `D:\test`；上游数据为第 12 周特征数据集四张表。
