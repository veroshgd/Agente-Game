"""
028 统计层 —— joint same-seed bootstrap + validity gates
=========================================================

自检：  python stats028.py

★★ 唯一正确的推断方式 ★★
五个臂来自**同一批配对种子**，彼此高度相关。所以 `G` 的 CI **必须**在
**每个 bootstrap replicate 内部**完整重算：

    每个 replicate b：
        idx = 重采样一次种子下标（★五臂共用同一组 idx★）
        E_A^(b), E_Bp^(b), E_Bm^(b), E_Cp^(b), E_Cm^(b)  ← 都用这组 idx
        G^(b)  = min(|E_Cp^(b)|, |E_Cm^(b)|) − |E_A^(b)|
        R_B^(b)= min(|E_Bp^(b)|, |E_Bm^(b)|)
    CI 直接取自 {G^(b)} 与 {R_B^(b)} 的分布

⛔ **两类等价的错误做法，本模块用对抗性测试显式让它们失败：**
   ① 分别算 A / C+ / C− 的 marginal CI，再拿端点相减
   ② 先对各臂求 bootstrap 均值，再套 abs() / min()
   两者都忽略了臂间相关，而 `G` 含 `abs` 与 `min`，是**非线性**的 ——
   非线性函数必须逐 replicate 施加，不能施加在汇总量上。

★ validity gates（跑前冻结）★
    support gate           raw 越界 ≤ 2.0%  且  boundary mass ≤ 2.0%
    budget-transport gate  |μ_j − μ_A|/SD_A ≤ 10%  且  |SD_j − SD_A|/SD_A ≤ 10%
    ⚠ μ_A / SD_A 必须是**同一批 confirmatory population 上实际跑出来的 A 臂**，
      不是 calibration 的 A —— 这样 population shift 自动被消掉。

★ gate 失败的分层处理 ★
    C+ 或 C− 任一失败 → primary G **invalid / not cleanly interpretable**，
                        既不许声称 breadth gain，也不许声称 no-gain
    B+ 或 B− 失败     → R_B secondary invalid；**若 C± 都通过，G 不受影响**
    A 没有 mapping transport gate（它就是 contemporaneous reference），
                        仍做 027 exact-replication 与 sampling-level replication

★ 判读顺序 ★ **gates 必须先于 task outcome 打印和判定** ——
  哪怕代码已经把 outcome 算出来了，也要先判 validity，
  避免看到结果之后产生解释自由度。
"""

import random
import statistics as st
import sys

SUPPORT_GATE = 0.02        # raw 越界比例 / boundary mass 上限
BUDGET_GATE = 0.10         # |Δμ| 与 |ΔSD| 相对 SD_A 的上限
N_BOOT = 10000
BOOT_SEED = 20260817

CLOSURE_TEXT = (
    "Frozen coupling normalization did not transport adequately to the "
    "confirmatory population; breadth contrast is not cleanly interpretable "
    "under the preregistered equal-budget assumption.")


# ------------------------------------------------------------------ gates
def check_gates(diag, muA, sdA):
    """diag[arm] = {'oos':比例, 'boundary':比例, 'mu':均值, 'sd':标准差}"""
    out = {}
    for arm, d in diag.items():
        sup_ok = d["oos"] <= SUPPORT_GATE and d["boundary"] <= SUPPORT_GATE
        dmu = abs(d["mu"] - muA) / sdA
        dsd = abs(d["sd"] - sdA) / sdA
        bud_ok = dmu <= BUDGET_GATE and dsd <= BUDGET_GATE
        out[arm] = {"support": sup_ok, "budget": bud_ok,
                    "ok": sup_ok and bud_ok, "dmu": dmu, "dsd": dsd}
    primary_valid = all(out[a]["ok"] for a in ("Cp", "Cm") if a in out)
    secondary_valid = all(out[a]["ok"] for a in ("Bp", "Bm") if a in out)
    return out, primary_valid, secondary_valid


# ------------------------------------------------- joint same-seed bootstrap
def joint_bootstrap(d, n_boot=N_BOOT, seed=BOOT_SEED):
    """d[arm] = 逐种子的配对差（五臂等长、按种子对齐）。

    ★每个 replicate 只抽一次下标，五臂共用★ —— 这是唯一正确利用
    same-seed 设计的方式。`G` 的非线性在**每个 replicate 内部**施加。
    """
    arms = list(d)
    n = len(d[arms[0]])
    assert all(len(d[a]) == n for a in arms), "各臂长度不一致"
    rng = random.Random(seed)
    G, RB, E = [], [], {a: [] for a in arms}
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]          # ★共用★
        e = {a: st.mean(d[a][i] for i in idx) for a in arms}
        for a in arms:
            E[a].append(e[a])
        if {"Cp", "Cm", "A"} <= set(arms):
            G.append(min(abs(e["Cp"]), abs(e["Cm"])) - abs(e["A"]))
        if {"Bp", "Bm"} <= set(arms):
            RB.append(min(abs(e["Bp"]), abs(e["Bm"])))
    return {"G": G, "RB": RB, "E": E}


def ci(vals, lo=0.025, hi=0.975):
    v = sorted(vals)
    n = len(v)
    return v[int(lo * n)], v[int(hi * n)]


def point_G(d):
    """点估计：同样在【原始样本】上完整施加非线性，不走任何汇总量"""
    e = {a: st.mean(d[a]) for a in d}
    return min(abs(e["Cp"]), abs(e["Cm"])) - abs(e["A"])


# ------------------------------------------------------------ 对抗性回归测试
def _wrong_endpoint_subtraction(d, n_boot=N_BOOT, seed=BOOT_SEED):
    """⛔ 错误做法①：各臂分别 bootstrap 出 marginal CI，再拿端点相减"""
    rng = random.Random(seed)
    n = len(d["A"])
    marg = {a: [] for a in d}
    for a in d:                                   # ★各臂各抽各的★ ← 错在这
        for _ in range(n_boot):
            idx = [rng.randrange(n) for _ in range(n)]
            marg[a].append(st.mean(d[a][i] for i in idx))
    mc = {a: ci([abs(x) for x in marg[a]]) for a in ("Cp", "Cm")}
    ma = ci([abs(x) for x in marg["A"]])
    lo = min(mc["Cp"][0], mc["Cm"][0]) - ma[1]
    hi = min(mc["Cp"][1], mc["Cm"][1]) - ma[0]
    return lo, hi


def _wrong_abs_after_average(boot):
    """⛔ 错误做法②：先对各臂求 bootstrap 均值，再套 abs()/min()"""
    e = {a: st.mean(v) for a, v in boot["E"].items()}
    return min(abs(e["Cp"]), abs(e["Cm"])) - abs(e["A"])


def _test_joint_vs_endpoint_subtraction():
    """★对抗性测试★ 构造 A 与 C 高度相关的数据，让端点相减显式失败"""
    rng = random.Random(4242)
    n = 800
    base = [rng.gauss(0.5, 1.0) for _ in range(n)]        # 共同成分（很大）
    d = {
        "A": [b + rng.gauss(0, 0.05) for b in base],
        "Cp": [b + rng.gauss(0, 0.05) for b in base],
        "Cm": [b + rng.gauss(0, 0.05) for b in base],
        "Bp": [rng.gauss(0, 1.0) for _ in range(n)],
        "Bm": [rng.gauss(0, 1.0) for _ in range(n)],
    }
    boot = joint_bootstrap(d, n_boot=4000, seed=7)
    jlo, jhi = ci(boot["G"])
    wlo, whi = _wrong_endpoint_subtraction(d, n_boot=4000, seed=7)
    jw, ww = jhi - jlo, whi - wlo
    assert jw < 0.5 * ww, (
        f"✗ 对抗性构造失败：joint 宽度 {jw:.4f} 未显著窄于端点相减 {ww:.4f}")
    # 端点相减必须包含 joint CI 明确排除的值
    outside = [x for x in (wlo, whi) if x < jlo or x > jhi]
    assert outside, "✗ 端点相减未给出 joint CI 排除的值"
    print(f"  ✓ 对抗性测试：joint CI 宽 {jw:.4f}，端点相减宽 {ww:.4f}"
          f"（{ww/jw:.1f}× 虚宽）—— 旧方法已显式失败")


def _test_abs_after_average_is_wrong():
    """abs/min 必须逐 replicate 施加，不能施加在汇总量上"""
    rng = random.Random(99)
    n = 500
    d = {"A": [rng.gauss(0.0, 1.0) for _ in range(n)],     # 真值 ≈ 0 → abs 有偏
         "Cp": [rng.gauss(0.0, 1.0) for _ in range(n)],
         "Cm": [rng.gauss(0.0, 1.0) for _ in range(n)]}
    boot = joint_bootstrap(d, n_boot=4000, seed=11)
    right = st.mean(boot["G"])
    wrong = _wrong_abs_after_average(boot)
    assert abs(right - wrong) > 1e-6, "两种做法竟然一致？构造无效"
    print(f"  ✓ 逐 replicate 施加非线性 {right:+.5f}"
          f" ≠ 先平均再 abs/min {wrong:+.5f}（差 {abs(right-wrong):.5f}）")


def _test_shared_indices():
    """五臂必须共用同一组重采样下标 —— 用完全相同的数据验证"""
    n = 300
    same = [float(i) for i in range(n)]
    d = {"A": list(same), "Cp": list(same), "Cm": list(same)}
    boot = joint_bootstrap(d, n_boot=500, seed=5)
    for a in ("Cp", "Cm"):
        assert boot["E"][a] == boot["E"]["A"], \
            "✗ 相同数据在不同臂上给出不同 bootstrap 轨迹 —— 下标没共用"
    assert all(abs(g) < 1e-12 for g in boot["G"]), "✗ G 应恒为 0"
    print("  ✓ 五臂共用同一组重采样下标（相同数据 → 逐 replicate 相同）")


def _test_gates():
    sdA, muA = 0.0122, 0.0367
    good = {"Cp": {"oos": 0.001, "boundary": 0.002, "mu": muA + 0.0003,
                   "sd": sdA - 0.0002}}
    _, pv, _ = check_gates(good, muA, sdA)
    assert pv
    bad = {"Cp": dict(good["Cp"], mu=muA + 0.0020)}       # Δμ = 16% SD_A
    g, pv2, _ = check_gates(bad, muA, sdA)
    assert not pv2 and not g["Cp"]["budget"]
    # B 失败不得拖累 primary
    mix = {"Cp": good["Cp"], "Cm": good["Cp"],
           "Bp": dict(good["Cp"], oos=0.05), "Bm": good["Cp"]}
    g3, pv3, sv3 = check_gates(mix, muA, sdA)
    assert pv3 and not sv3, "✗ B 臂失败不应使 primary G 失效"
    print("  ✓ gates：C± 失败 → primary invalid；B± 失败 → 仅 secondary invalid")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("028 统计层自检")
    _test_shared_indices()
    _test_joint_vs_endpoint_subtraction()
    _test_abs_after_average_is_wrong()
    _test_gates()
    print(f"\n冻结阈值：support ≤ {SUPPORT_GATE:.0%}  boundary ≤ {SUPPORT_GATE:.0%}"
          f"  |Δμ|,|ΔSD| ≤ {BUDGET_GATE:.0%} × SD_A")
    print("全部通过。")
