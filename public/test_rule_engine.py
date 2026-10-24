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
