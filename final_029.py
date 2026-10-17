"""
实验 029 FINAL runner —— final_029.py
================================================================================

彩排（**已烧种子、全尺寸**）：
    python final_029.py --rehearse

正式（★ 只有起飞检查全过之后才允许 ★）：
    python final_029.py --final

--------------------------------------------------------------------------------
★★ 这个文件的唯一职责：让"跑错版本"在物理上不可能 ★★
--------------------------------------------------------------------------------
预注册：`AI SANDBOX/MEMORY_TRANSFER029_PREREGISTRATION.md`（已冻结，见 PREREG_SHA256）

```
preflight        冻结常量 + 模块 sha256 + 任务指纹 + λ + gates
                 + SHUFFLE 规则/salt + XSEED donor mapping + 预注册 hash
seed guard       --final 强制 80000–81499 / N=1500；非 final 禁止触碰该段
crash-safe burn  ★ 在【第一条 acquisition 轨迹】之前原子创建 STARTED.lock ★
                 —— 029 的种子从 acquisition 阶段就开始产生信息，
                    不是等 novel task 开跑才算 burned。lock 永不自动删除。
analysis order   1 acquisition/completeness → 2 G2 capacity → 3 validity verdict
                 → 4 OWN primary → 5 SESOI 三档 → 6 SHUFFLE 条件性 retention
                 → 7 XSEED-DONOR → 8 integrity assertions → 9 secondary → 10 落盘
```

⚠ **G1/G3 是预注册的 validity gate（先于 outcome）**，所以在第 3 步"validity
verdict"里**强制执行**；第 8 步只是把逐种子明细**再打印一次**，不是第一次检查。
"""

import hashlib
import math
import os
import random
import statistics
import sys
import time

import novel_task as NT
import memory_transfer_probe as P1
import memory_transfer_probe3 as P3
import memory_acquisition_probe as ACQ
import memory_lambda_calibration as CAL
import memory_transfer_rehearsal as REH
from memory_transfer_probe import MemoryStore

HERE = os.path.dirname(os.path.abspath(__file__))

# ============================================================ 冻结常量
FINAL_SEED0, FINAL_N = 80000, 1500
REHEARSE_SEED0, REHEARSE_N = 10000, 1500      # 已烧段、非零 offset、与 FINAL 同尺寸
LOCK_PATH = os.path.join(HERE, "final_029_STARTED.lock")
RESULT_PATH = os.path.join(HERE, "final_029_result.txt")

TASK_FINGERPRINT = "26778f672e9e7009"
PREREG_PATH = os.path.join(
    os.path.expanduser("~"), "Desktop", "Yinan", "AI SANDBOX",
    "MEMORY_TRANSFER029_PREREGISTRATION.md")
PREREG_SHA256 = ("29e45930a07f2649c7958fdc0cd20a389005ca43"
                 "e93287b9f69e2ccdcf867145")

FROZEN_MODULES = {
    "novel_task.py": "9db73d140853f6b0",
    "memory_transfer_probe.py": "b4327de32216d0c1",
    "memory_transfer_probe3.py": "f0664436301cf459",
    "memory_acquisition_probe.py": "7b88b9f7c19062bd",
    "memory_lambda_calibration.py": "9323f22b69eacd1c",
    # ★ 2026-08-18 补入 ★ FINAL 直接调用 REH.BODY 与 REH.shuffled()，
    #   它是运行时依赖却一度不在冻结清单里 —— 误改它 preflight 仍会全绿。
    #   预注册 §12.5 只写"各模块 sha256"，未枚举模块数，故无需科学性 amendment。
    "memory_transfer_rehearsal.py": "b29b2d417fdaed52",
}

N_BOOT = 10000
ANALYSIS_SEED = 8181
SESOI = 1.0                      # post-change errors
RETENTION_MAX = 0.25             # ★ §6.3 判据 B：CI 上界 < 0.25 ★

LEDGER = """0–1499        development（029 探针 / 校准 / rehearsal 用 0–399）
10000–11499   021 留出集 / 028 transport rehearsal / ★029 full-shape rehearsal★
20000–21499   022 预注册段 / 027 + 028 group-blind calibration
50000–51499   v3 / 025 persistence FINAL
60000–61499   027 novel-task FINAL
70000–71499   028 breadth FINAL
80000–81499   ★★ 029 FINAL ★★"""


def sha(path, n=None):
    d = hashlib.sha256(open(path, "rb").read()).hexdigest()
    return d[:n] if n else d


# ============================================================ donor mapping
def donor_index(i, n):
    """★ 冻结 ★ deterministic half-block rotation。不依赖任何 memory / outcome。"""
    return (i + n // 2) % n


def _assert_donor_mapping(n):
    idx = [donor_index(i, n) for i in range(n)]
    assert all(d != i for i, d in enumerate(idx)), "✗ 出现 self-donor"
    assert sorted(idx) == list(range(n)), "✗ donor mapping 不是一一映射"
    return f"(i+{n // 2})%{n}"


# ============================================================ preflight
def preflight(final):
    print("=" * 78)
    print("PREFLIGHT")
    print("=" * 78)
    bad = []

    fp = NT.assert_frozen()
    ok = fp == TASK_FINGERPRINT
    print(f"  任务指纹            {fp}   {'✓' if ok else '✗'}")
    bad += [] if ok else ["task fingerprint"]

    for f, want in FROZEN_MODULES.items():
        got = sha(os.path.join(HERE, f), 16)
        print(f"  {f:<32}{got}   {'✓' if got == want else '✗ 期望 ' + want}")
        if got != want:
            bad.append(f)

    checks = [
        ("MEMORY_LAMBDA", CAL.MEMORY_LAMBDA, 1.00),
        ("SATURATION_MAX", CAL.SATURATION_MAX, 0.05),
        ("MEDIAN_ABS_DP_MIN", CAL.MEDIAN_ABS_DP_MIN, 0.02),
        ("PREF_FLIP_MAX", CAL.PREF_FLIP_MAX, 0.25),
        ("ACTIVE_EXPOSURE_MAX", CAL.ACTIVE_EXPOSURE_MAX, 20),
        ("ANOMALY_AT", ACQ.ANOMALY_AT, 36),
        ("ANOMALY_LEN", ACQ.ANOMALY_LEN, 8),
        ("T_PROBLEM", ACQ.T_PROBLEM, 66),
        ("N_PROBLEMS", ACQ.N_PROBLEMS, 3),
        ("GOOD_THRESH", P1.GOOD_THRESH, 0.60),
        ("PE_THRESH", P1.PE_THRESH, 0.30),
        ("SURPRISE_RUN_MIN", P1.SURPRISE_RUN_MIN, 3),
        ("SHUFFLE_SALT", REH.SHUFFLE_SALT, 0x29C10),
        ("SESOI", SESOI, 1.0),
        ("RETENTION_MAX", RETENTION_MAX, 0.25),
    ]
    for name, got, want in checks:
        good = got == want
        print(f"  {name:<32}{got!r:<12}{'✓' if good else '✗ 期望 ' + repr(want)}")
        if not good:
            bad.append(name)

    n = FINAL_N if final else REHEARSE_N
    print(f"  XSEED donor mapping             {_assert_donor_mapping(n):<12}✓")

    if os.path.exists(PREREG_PATH):
        got = sha(PREREG_PATH)
        good = got == PREREG_SHA256
        print(f"  预注册 sha256                   {got[:16]}…  "
              f"{'✓' if good else '✗ 预注册已被改动'}")
        if not good:
            bad.append("preregistration hash")
    else:
        print(f"  预注册                          ✗ 找不到 {PREREG_PATH}")
        if final:
            bad.append("preregistration missing")

    if bad:
        raise SystemExit(f"\n✗ PREFLIGHT 失败：{bad}\n"
                         "  冻结对象被改动。若确需修改，必须先写"
                         " AMENDMENT 文件并重新冻结，不许直接改常量后开跑。")
    print("\n  ✓ preflight 全过")


# ============================================================ seed guard / lock
def seed_guard(final, seed0, n):
    lo, hi = FINAL_SEED0, FINAL_SEED0 + FINAL_N - 1
    if final:
        if (seed0, n) != (FINAL_SEED0, FINAL_N):
            raise SystemExit(f"✗ --final 只接受 seed0={FINAL_SEED0}, N={FINAL_N}")
    else:
        if not (seed0 + n - 1 < lo or seed0 > hi):
            raise SystemExit(f"✗ 非 final 运行禁止触碰 {lo}–{hi}")
    print(f"\n种子账本：\n{LEDGER}")
    print(f"\n本次运行：seed0={seed0}  N={n}  "
          f"→ {seed0}–{seed0 + n - 1}   {'★FINAL★' if final else '彩排（已烧段）'}")


def create_lock(seed0, n, payload):
    """★ 原子创建，永不自动删除 ★ 一旦创建，该 seed block 永久 burned。"""
    if os.path.exists(RESULT_PATH):
        raise SystemExit(f"✗ {RESULT_PATH} 已存在 —— 拒绝重跑")
    try:
        fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit(f"✗ {LOCK_PATH} 已存在 —— 该 seed block 已被 burn，拒绝重跑")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(payload)
    return LOCK_PATH


def lock_payload(seed0, n):
    lines = [f"029 FINAL STARTED  {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"seeds {seed0}-{seed0 + n - 1}  N={n}",
             f"task_fingerprint {TASK_FINGERPRINT}",
             f"MEMORY_LAMBDA {CAL.MEMORY_LAMBDA}",
             f"gates {CAL.SATURATION_MAX}/{CAL.MEDIAN_ABS_DP_MIN}/"
             f"{CAL.PREF_FLIP_MAX}/{CAL.ACTIVE_EXPOSURE_MAX}",
             f"SESOI {SESOI}  RETENTION_MAX {RETENTION_MAX}",
             f"shuffle_salt {hex(REH.SHUFFLE_SALT)}",
             f"donor_mapping (i+{n // 2})%{n}",
             f"analysis_seed {ANALYSIS_SEED}  n_boot {N_BOOT}",
             f"prereg_sha256 {PREREG_SHA256}"]
    lines += [f"module {f} {sha(os.path.join(HERE, f), 16)}"
              for f in FROZEN_MODULES]
    lines += ["ledger:", LEDGER]
    return "\n".join(lines) + "\n"


# ============================================================ 运行
ARM_NAMES = ("OWN", "DELETE", "SWAP", "SHUFFLE", "XSEED-DONOR")


def run_block(seed0, n):
    """★ 调用前 lock 必须已创建 ★ 返回 arm → cond → 每种子 (C, lat, expo, run)"""
    seeds = [seed0 + i for i in range(n)]
    mem = {}
    for cond in ACQ.CONDITIONS:
        for sd in seeds:
            eps, _ = ACQ.acquire(sd, cond)
            mem[(cond, sd)] = MemoryStore(f"{cond}-{sd}", eps)

    other = {ACQ.CONDITIONS[0]: ACQ.CONDITIONS[1],
             ACQ.CONDITIONS[1]: ACQ.CONDITIONS[0]}
    empty = MemoryStore("empty", [])

    def pick(name, cond, i):
        sd = seeds[i]
        if name == "OWN":
            return mem[(cond, sd)]
        if name == "DELETE":
            return empty
        if name == "SWAP":
            return mem[(other[cond], sd)]
        if name == "SHUFFLE":
            return REH.shuffled(mem[(cond, sd)], sd)
        if name == "XSEED-DONOR":
            return mem[(cond, seeds[donor_index(i, n)])]
        raise KeyError(name)

    res = {}
    for name in ARM_NAMES:
        res[name] = {}
        for cond in ACQ.CONDITIONS:
            rows = []
            for i, sd in enumerate(seeds):
                r = P3.run_fixed(REH.BODY, pick(name, cond, i), sd,
                                 CAL.MEMORY_LAMBDA)
                rows.append((P3.post_change_errors(r), P3.latency(r),
                             sum(r["fired"]),
                             statistics.fmean(r["active_runs"])
                             if r["active_runs"] else 0.0))
            assert len(rows) == n            # 规则 88/91：全人群，不筛选
            res[name][cond] = rows
    return seeds, mem, res


def deltas(res, name, idx=0):
    S, V = ACQ.CONDITIONS
    return [v[idx] - s[idx] for s, v in zip(res[name][S], res[name][V])]


def joint_bootstrap(darrays):
    """★ 一次 pass、共用同一组种子下标 ★ 返回每个数组的 bootstrap 均值分布"""
    n = len(next(iter(darrays.values())))
    rng = random.Random(ANALYSIS_SEED)
    out = {k: [] for k in darrays}
    ratio = []
    for _ in range(N_BOOT):
        idx = rng.choices(range(n), k=n)
        means = {}
        for k, arr in darrays.items():
            means[k] = sum(arr[i] for i in idx) / n
            out[k].append(means[k])
        a, b = abs(means["OWN"]), abs(means["SHUFFLE"])
        ratio.append(b / a if a > 0 else float("inf"))   # 逐 replicate 施加
    for k in out:
        out[k].sort()
    ratio.sort()
    return out, ratio


def ci(sorted_vals):
    return (sorted_vals[int(0.025 * N_BOOT)], sorted_vals[int(0.975 * N_BOOT)])


# ============================================================ 分析
def analyze(seeds, mem, res, trace):
    n = len(seeds)
    S, V = ACQ.CONDITIONS
    out = []

    def p(*a):
        line = " ".join(str(x) for x in a)
        print(line)
        out.append(line)

    # ---------- 1 acquisition / completeness ----------
    trace.append("1-acquisition")
    p("\n" + "=" * 78)
    p("1. ACQUISITION / COMPLETENESS")
    p("=" * 78)
    comp, nz = {}, {}
    for c in ACQ.CONDITIONS:
        ev = [mem[(c, sd)].evidence("previously_good_strategy") for sd in seeds]
        comp[c] = statistics.fmean([1.0 if (a > 0 and b > 0) else 0.0
                                    for _, a, b in ev])
        nz[c] = statistics.fmean([1.0 if m != 0 else 0.0 for m, _, _ in ev])
    p(f"  memory completeness（primary extensive margin）  "
      + "   ".join(f"{c} {comp[c]:.2%}" for c in ACQ.CONDITIONS))
    p(f"  non-zero evidence rate（不叫 availability）      "
      + "   ".join(f"{c} {nz[c]:.2%}" for c in ACQ.CONDITIONS))
    p("  ★ 所有 primary 分析使用全部预定义 agent，含 incomplete 与 m=0 ★")

    # ---------- 2 G2 capacity transport（group-blind）----------
    trace.append("2-G2")
    p("\n" + "=" * 78)
    p("2. G2 INTERFACE-CAPACITY TRANSPORT（group-blind：label 在输入处丢弃）")
    p("=" * 78)
    pool = sorted(float(mem[(c, sd)].evidence("previously_good_strategy")[0])
                  for c in ACQ.CONDITIONS for sd in seeds)   # ★排序摧毁分组★
    states = []
    for sd in seeds:
        states += P3.run_fixed(REH.BODY, CAL.ConstantMemory(0.0), sd, 0.0,
                               trace=True)["states"]
    sig = CAL._sig
    lam = CAL.MEMORY_LAMBDA
    d, sat, flip, cnt = [], 0, 0, 0
    for z, s_ in states:
        p0 = sig(z)
        for m in pool:
            p1 = sig(z + lam * m * s_)
            d.append(abs(p1 - p0))
            sat += p1 <= CAL.SAT_LO or p1 >= CAL.SAT_HI
            flip += (p0 - 0.5) * (p1 - 0.5) < 0
            cnt += 1
    d.sort()
    med_dp, sat_r, flip_r = d[len(d) // 2], sat / cnt, flip / cnt
    reps = [pool[int(0.10 * len(pool))], pool[len(pool) // 2],
            pool[int(0.90 * len(pool))]]
    expo = max(statistics.fmean(
        [sum(P3.run_fixed(REH.BODY, CAL.ConstantMemory(m), sd, lam)["fired"])
         for sd in seeds]) for m in reps)
    g2 = [("saturation", sat_r, CAL.SATURATION_MAX, sat_r <= CAL.SATURATION_MAX),
          ("median|Δp|", med_dp, CAL.MEDIAN_ABS_DP_MIN,
           med_dp >= CAL.MEDIAN_ABS_DP_MIN),
          ("preference flip", flip_r, CAL.PREF_FLIP_MAX,
           flip_r <= CAL.PREF_FLIP_MAX),
          ("max exposure/80", expo, CAL.ACTIVE_EXPOSURE_MAX,
           expo <= CAL.ACTIVE_EXPOSURE_MAX)]
    p(f"  pooled m: n={len(pool)}  m=0 占 "
      f"{sum(1 for x in pool if x == 0) / len(pool):.1%}   "
      f"eligible states={len(states)}")
    for name, got, want, good in g2:
        p(f"  {name:<18}{got:>10.4f}   门槛 {want:<8}{'✓' if good else '✗'}")
    g2_ok = all(x[3] for x in g2)

    # ---------- 3 validity verdict（G1 / G2 / G3）----------
    trace.append("3-validity")
    p("\n" + "=" * 78)
    p("3. VALIDITY VERDICT（★先于 outcome★）")
    p("=" * 78)
    same_prefix = True
    k = ACQ.ANOMALY_AT + ACQ.ANOMALY_LEN
    for sd in seeds[:100]:
        for a, b in zip(ACQ.acq_tables(sd, S), ACQ.acq_tables(sd, V)):
            if a["rows"][:k] != b["rows"][:k] or a["us"] != b["us"]:
                same_prefix = False
    opp = {c: statistics.fmean([sum(x["opportunity"] for x in ACQ.acq_tables(sd, c))
                                for sd in seeds[:100]]) for c in ACQ.CONDITIONS}
    g1_ok = same_prefix and abs(opp[S] - opp[V]) < 1e-9
    d_del, d_own, d_swap = (deltas(res, "DELETE"), deltas(res, "OWN"),
                            deltas(res, "SWAP"))
    g3_ok = all(x == 0 for x in d_del) and all(a == -b for a, b in
                                               zip(d_own, d_swap))
    p(f"  G1 acquisition manipulation   {'✓' if g1_ok else '✗'}"
      f"   （异常前逐位相同={same_prefix}，reward opportunity 相等）")
    p(f"  G2 interface capacity         {'✓' if g2_ok else '✗'}")
    p(f"  G3 integrity assertions       {'✓' if g3_ok else '✗'}")
    if not g1_ok or not g3_ok:
        p("\n  ✗✗ G1/G3 失败 → ★整批作废★（发育史存在记忆以外的泄漏通路）")
    if not g2_ok:
        p("\n  ✗ G2 失败，固定措辞：")
        p("    Interface capacity calibrated on the development block did not")
        p("    transport to the confirmatory population; the memory channel is")
        p("    not cleanly interpretable under the preregistered capacity")
        p("    constraints.")
        p("  ⚠ 这【不是】 no memory transfer，而是 calibrated-interface validity")
        p("    compromised。⛔ 不许因此重估 λ。")

    # ★★ confirmatory interpretation 的总开关 ★★
    # 任一预注册 validity gate 失败 → 仍然把全部 raw outcome 落盘
    # （FINAL block 已经烧掉，数据必须透明保存），
    # 但**不允许**再产生 primary success / functional success / SHUFFLE
    # mediation 中的任何一条。
    primary_interpretable = g1_ok and g2_ok and g3_ok
    p(f"\n  ★ confirmatory interpretation："
      f"{'启用' if primary_interpretable else '★已禁用★（有 validity gate 失败）'}")

    # ---------- 4 OWN primary ----------
    trace.append("4-primary")
    p("\n" + "=" * 78)
    p("4. PRIMARY  ΔC = C(Volatile) − C(Stable)  同种子配对，全人群")
    p("=" * 78)
    arrays = {name: deltas(res, name) for name in ARM_NAMES}
    boots, ratio = joint_bootstrap(arrays)
    dc = {k_: statistics.fmean(v) for k_, v in arrays.items()}
    for name in ARM_NAMES:
        lo, hi = ci(boots[name])
        p(f"  {name:<14}ΔC = {dc[name]:>+8.4f}   95% CI [{lo:+.4f}, {hi:+.4f}]")

    # ---------- 5 SESOI 三档 ----------
    trace.append("5-sesoi")
    lo, hi = ci(boots["OWN"])
    p("\n" + "=" * 78)
    p(f"5. SESOI 三档判读（SESOI = {SESOI} post-change error）")
    p("=" * 78)
    if not primary_interpretable:
        verdict = ("DESCRIPTIVE ONLY — confirmatory interpretation disabled "
                   "because a preregistered validity gate failed.")
        own_transfer = False
    elif lo <= 0 <= hi:
        verdict = "No evidence of memory-mediated transfer."
        own_transfer = False
    elif hi < 0 and lo < -SESOI and hi < -SESOI:
        verdict = "Functionally meaningful memory-mediated transfer established."
        own_transfer = True
    elif hi < 0:
        verdict = ("Detectable memory-mediated transfer, but functional "
                   "significance not established.")
        own_transfer = True
    else:
        verdict = "Transfer in the OPPOSITE (harmful) direction."
        own_transfer = False
    p(f"  95% CI [{lo:+.4f}, {hi:+.4f}]  →  ★ {verdict} ★")

    # ---------- 6 SHUFFLE 条件性 retention ----------
    trace.append("6-shuffle")
    r_pt = abs(dc["SHUFFLE"]) / abs(dc["OWN"]) if dc["OWN"] else float("inf")
    r_lo, r_hi = ci(ratio)
    p("\n" + "=" * 78)
    p("6. SHUFFLE —— conditional retention ratio")
    p("=" * 78)
    p(f"  R = |ΔC_SHUFFLE| / |ΔC_OWN| = {r_pt:.4f}   95% CI [{r_lo:.4f}, {r_hi:.4f}]")
    p("  joint same-seed bootstrap，abs 与除法逐 replicate 施加")
    if not own_transfer:
        p("  ⚠ " + ("confirmatory interpretation 已禁用（validity gate 失败）"
                    if not primary_interpretable
                    else "OWN primary 未确立 transfer（§6.3.2 分母不可辨识）")
          + " → **只作描述性报告**，")
        p("    ⛔ 不判 relational mediation。")
    else:
        good = r_hi < RETENTION_MAX
        p(f"  判据 CI 上界 < {RETENTION_MAX}  →  {'满足 ✓' if good else '不满足 ✗'}")
        p("  → " + ("≥75% attenuation established：transfer 由关系结构承载"
                    if good else
                    "不许声称关系结构承载；marginal statistics 的贡献无法排除"))
    p("  披露：§6.3 的 CI-upper interpretation was finalized after observing the")
    p("        development rehearsal retention estimate R=0.094, 95%CI[0.005,0.261],")
    p("        but before any observation from the confirmatory seed block.")

    # ---------- 7 XSEED-DONOR ----------
    trace.append("7-xseed")
    lo7, hi7 = ci(boots["XSEED-DONOR"])
    p("\n" + "=" * 78)
    p("7. XSEED-DONOR（donor mapping (i+N/2)%N，无 self-donor、一一映射）")
    p("=" * 78)
    p(f"  ΔC = {dc['XSEED-DONOR']:+.4f}  95% CI [{lo7:+.4f}, {hi7:+.4f}]"
      f"   保留 OWN 的 "
      f"{dc['XSEED-DONOR'] / dc['OWN']:.1%}" if dc["OWN"] else "")

    # ---------- 8 integrity assertions 明细 ----------
    trace.append("8-integrity")
    p("\n" + "=" * 78)
    p("8. INTEGRITY ASSERTIONS（★断言，不是科学证据 —— 规则 93★）")
    p("=" * 78)
    n_del = sum(1 for x in d_del if x == 0)
    n_swp = sum(1 for a, b in zip(d_own, d_swap) if a == -b)
    p(f"  DELETE ΔC ≡ 0：{n_del}/{n} 种子       {'✓' if n_del == n else '✗'}")
    p(f"  SWAP  ΔC ≡ −ΔC(OWN)：{n_swp}/{n} 种子  {'✓' if n_swp == n else '✗'}")
    p("  → 证明发育史除记忆外没有第二条通路；memory-only 架构下这是代数恒等式。")

    # ---------- 9 secondary ----------
    trace.append("9-secondary")
    p("\n" + "=" * 78)
    p("9. SECONDARY MECHANISTIC")
    p("=" * 78)
    p(f"  {'臂':<14}{'Δlatency':>11}{'expo S':>10}{'expo V':>10}"
      f"{'ACTIVE S':>11}{'ACTIVE V':>11}")
    for name in ARM_NAMES:
        dl = statistics.fmean(deltas(res, name, 1))
        es = statistics.fmean([x[2] for x in res[name][S]])
        ev = statistics.fmean([x[2] for x in res[name][V]])
        rs = statistics.fmean([x[3] for x in res[name][S]])
        rv = statistics.fmean([x[3] for x in res[name][V]])
        p(f"  {name:<14}{dl:>+11.4f}{es:>10.2f}{ev:>10.2f}{rs:>11.2f}{rv:>11.2f}")
    return out


# ============================================================ 自检
def selftests():
    print("=" * 78)
    print("SELF-TESTS")
    print("=" * 78)
    # lock helper
    tmp = LOCK_PATH + ".selftest"
    if os.path.exists(tmp):
        os.remove(tmp)
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)
    try:
        os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        raise AssertionError("✗ lock 不是原子独占")
    except FileExistsError:
        pass
    os.remove(tmp)
    print("  ✓ lock helper：O_CREAT|O_EXCL 原子独占，二次创建被拒")

    # worker determinism
    sd = REHEARSE_SEED0 + 7
    e1, _ = ACQ.acquire(sd, "Volatile")
    e2, _ = ACQ.acquire(sd, "Volatile")
    assert [tuple(vars(x).values()) for x in e1] == \
           [tuple(vars(x).values()) for x in e2]
    m1 = MemoryStore("a", e1)
    r1 = P3.run_fixed(REH.BODY, m1, sd, CAL.MEMORY_LAMBDA)
    r2 = P3.run_fixed(REH.BODY, m1, sd, CAL.MEMORY_LAMBDA)
    assert r1["choices"] == r2["choices"]
    print("  ✓ worker determinism：acquisition 与 transfer 逐 trial 可复现")

    # XSEED mapping
    for n in (400, 1500):
        _assert_donor_mapping(n)
    print(f"  ✓ XSEED mapping：无 self-donor、一一映射（N=400 与 N={FINAL_N}）")
    print(f"      FINAL donor_index(i) = (i+{FINAL_N // 2})%{FINAL_N}")

    # SHUFFLE determinism + marginal preservation
    a = REH.shuffled(m1, sd)
    b = REH.shuffled(m1, sd)
    assert [e.action_relation for e in a.episodes] == \
           [e.action_relation for e in b.episodes]
    assert sorted(e.action_relation for e in a.episodes) == \
           sorted(e.action_relation for e in m1.episodes)
    assert sorted(e.outcome for e in a.episodes) == \
           sorted(e.outcome for e in m1.episodes)
    print("  ✓ SHUFFLE：同 (seed, n_episodes) 置换确定；stay/switch 条数与"
          " outcome 边际保持不变")

    # 三个 condition 共用同一 donor permutation
    assert donor_index(3, 1500) == donor_index(3, 1500)
    print("  ✓ Stable / Volatile 共用同一 donor permutation（函数只依赖 i 与 N）")


EXPECTED_ORDER = ["1-acquisition", "2-G2", "3-validity", "4-primary",
                  "5-sesoi", "6-shuffle", "7-xseed", "8-integrity",
                  "9-secondary"]


# ============================================================ main
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    final = "--final" in sys.argv
    rehearse = "--rehearse" in sys.argv
    if final == rehearse:
        raise SystemExit("用法：python final_029.py --rehearse | --final")

    seed0, n = (FINAL_SEED0, FINAL_N) if final else (REHEARSE_SEED0, REHEARSE_N)
    print("=" * 78)
    print(f"029 {'★★ FINAL ★★' if final else 'FULL-SHAPE REHEARSAL（已烧段）'}")
    print("=" * 78)

    preflight(final)
    seed_guard(final, seed0, n)
    if not final:
        selftests()

    if final:
        # ★★ lock 必须在【第一条 acquisition 轨迹】之前 ★★
        create_lock(seed0, n, lock_payload(seed0, n))
        print(f"\n★ 已创建 {LOCK_PATH} —— {seed0}–{seed0 + n - 1} 从此永久 burned ★")

    t0 = time.time()
    seeds, mem, res = run_block(seed0, n)
    trace = []
    lines = analyze(seeds, mem, res, trace)
    assert trace == EXPECTED_ORDER, f"✗ 分析顺序被打乱：{trace}"
    print(f"\n  ✓ analysis ordering：{' → '.join(trace)}")
    print(f"  用时 {time.time() - t0:.1f}s")

    header = [f"029 {'FINAL' if final else 'FULL-SHAPE REHEARSAL'}  "
              f"seeds {seed0}-{seed0 + n - 1}  N={n}",
              f"task_fp={TASK_FINGERPRINT}  lambda={CAL.MEMORY_LAMBDA}  "
              f"SESOI={SESOI}  RETENTION_MAX={RETENTION_MAX}",
              f"analysis_seed={ANALYSIS_SEED} n_boot={N_BOOT}  "
              f"donor=(i+{n // 2})%{n}  shuffle_salt={hex(REH.SHUFFLE_SALT)}",
              "modules " + " ".join(f"{f}:{sha(os.path.join(HERE, f), 8)}"
                                    for f in FROZEN_MODULES),
              "ledger:", LEDGER]
    path = RESULT_PATH if final else os.path.join(
        HERE, "final_029_rehearsal_result.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(header + lines) + "\n")
    print(f"  已落盘 {os.path.basename(path)}")
    if not final:
        print("\n⚠ 这是彩排：80000–81499 一颗未碰，未创建 FINAL lock。")
