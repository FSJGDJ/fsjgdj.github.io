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
    for rule in rules:  
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
