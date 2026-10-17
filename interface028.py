"""
实验 028 接口层 —— 五臂 frozen readout
========================================

自检：  python interface028.py

    FrozenTransform
        ↓  traits → A / B± / C± 的 raw readout
    frozen empirical quantile mapping
        ↓
    effective coupling b_i
        ↓
    027 NovelTask adapter（复用 027 原任务代码，一行不改）

★★ 最关键的陷阱：double multiplication ★★
`NT.run_task(agent, seed, beta=X)` 内部会做 `b = X * novelty_style(agent)`。
所以**绝不能**把映射好的 `b_i` 直接当 `beta=` 传进去 ——
那样会变成 `b_i × novelty_style_i`，**A 轴被偷偷乘回来**，
B⊥ 不再是 B⊥、C± 不再是 C±，"五臂唯一差异是排序"的设计直接失效。

正确做法（`run_with_effective_coupling`）：造一个 proxy agent，
使 `novelty_style(proxy) = b_i / BETA`，再用 `beta=BETA` 调用原任务：

    BETA × (b_i / BETA) = b_i        ← 内部那次乘法被抵消

于是**学习规则 / reward table / softmax / τ / α / 共享随机数
全部还是 027 原代码**，028 只新增了 coupling assignment。
`_test_no_double_multiplication` 显式验证这一点。

★ B− 不是 0.05 − B+ ★
A 的 frozen beta 分布**不关于 0.025 对称**（实测 [0.012139, 0.048427]，
μ=0.036948，明显左偏）。所以 B− 必须走**自己的反向 percentile**：
`rank r → betaA_sorted[n−1−r]`，而不是算术取补。

★ final 阶段只应用冻结变换，绝不重估 ★
calibration 可硬断言正交性 / rank 门槛 / 边际分布逐位相同；
final 只能断言 hash 一致、变换来自冻结常数、beta 落在 frozen support、
映射确定性、A 臂与 027 逐位相同。各臂在 final 上的实际 mean/SD
**只作 diagnostics**，不得为了让它们相等去调整。
"""

import bisect
import hashlib
import json
import os
import sys

import novel_task as NT

HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN_PATH = os.path.join(HERE, "interface028_frozen.json")
ARMS = ("A", "Bp", "Bm", "Cp", "Cm")


def _load():
    with open(FROZEN_PATH, encoding="utf-8") as f:
        d = json.load(f)
    want = d.pop("sha256")
    payload = json.dumps(d, sort_keys=True, separators=(",", ":"))
    got = hashlib.sha256(payload.encode()).hexdigest()
    if got != want:
        raise SystemExit(f"✗ interface028_frozen.json 校验失败\n"
                         f"  期望 {want[:32]}…\n  实得 {got[:32]}…")
    d["sha256"] = want
    if d["task_fingerprint"] != NT.config_fingerprint():
        raise SystemExit(f"✗ 任务指纹不符：冻结时 {d['task_fingerprint']}，"
                         f"现在 {NT.config_fingerprint()}")
    return d


F = _load()
_BETA_A = F["betaA_sorted"]                 # A 臂的冻结 beta 边际（升序）
_N = len(_BETA_A)


# ------------------------------------------------------------------ 第一层
def raw_readout(traits):
    """traits → 各臂的 raw readout（A 单独处理，见 beta_for）"""
    mu, sd = F["mu"], F["sd"]
    z = lambda k: (traits[k] - mu[k]) / sd[k]
    a_ord = traits["curiosity"] - traits["caution"]        # ★A 的排序变量★
    xA = (a_ord - F["a_ord_mu"]) / F["a_ord_sd"]
    xB_raw = z("industry")
    xBo = (xB_raw - F["resid_slope"] * xA) / F["resid_sd"]  # OLS 残差
    return {"xA": xA, "B": xBo, "Cp": xA + xBo, "Cm": xA - xBo}


# ------------------------------------------------------------------ 第二层
def _quantile_map(x, key, reverse=False):
    """冻结 empirical CDF → A 的冻结 beta 边际。**只应用，不重估。**"""
    ref = F["x_sorted"][key]
    i = bisect.bisect_left(ref, x)
    i = min(max(i, 0), len(ref) - 1)
    q = i / (len(ref) - 1)
    j = int(round((1.0 - q if reverse else q) * (_N - 1)))
    return _BETA_A[min(max(j, 0), _N - 1)]


# ------------------------------------------------------------------ 第三层
def beta_for(arm, traits):
    """该 agent 在该臂下进入 decision logit 的 **effective coupling** b_i"""
    if arm == "A":
        # ★A 完全保持 027 原接口，不经过 028 的任何映射★
        return NT.BETA * NT.novelty_style(_Obj(traits))
    r = raw_readout(traits)
    if arm == "Bp":
        return _quantile_map(r["B"], "B", reverse=False)
    if arm == "Bm":
        # ★不是 0.05 − b(Bp)★ A 的 frozen 分布不对称，必须走反向 percentile
        return _quantile_map(r["B"], "B", reverse=True)
    if arm == "Cp":
        return _quantile_map(r["Cp"], "Cp")
    if arm == "Cm":
        return _quantile_map(r["Cm"], "Cm")
    raise ValueError(arm)


class _Obj:
    def __init__(self, traits):
        self.traits = dict(traits)


# ------------------------------------------------------------------ 第四层
def run_with_effective_coupling(b_i, seed):
    """★adapter★ 让 027 原任务最终用到的 coupling 恰好等于 b_i。

    `NT.run_task` 内部：b = beta × novelty_style(agent)
    造 proxy 使 novelty_style(proxy) = b_i / BETA，再传 beta = BETA。
    """
    ns = b_i / NT.BETA
    assert 0.0 <= ns <= 1.0, f"b_i={b_i} 超出 [0, {NT.BETA}]"
    diff = 200.0 * ns - 100.0
    proxy = _Obj({"curiosity": 50.0 + diff / 2.0,
                  "caution": 50.0 - diff / 2.0, "industry": 50.0})
    rec = NT.run_task(proxy, seed, beta=NT.BETA)
    assert abs(rec["beta"] - b_i) < 1e-12, \
        f"✗ adapter 失效：期望 {b_i}，实得 {rec['beta']}"
    return rec


def run_arm(arm, traits, seed):
    if arm == "A":
        return NT.run_task(_Obj(traits), seed)        # 027 原路径，未经改动
    return run_with_effective_coupling(beta_for(arm, traits), seed)


# ------------------------------------------------------------------ 自检
def _cal_pool():
    """重建 calibration 池（仅自检用）"""
    import novel_situation as NS
    sim = NS.sim
    sim.COND_RECOVER_AT = 65.0
    sim.COND_DEADZONE_RECOVER = sim.COND_SHELTER_RECOVER = 0.0
    sim.SLEEP_SUPPRESS = sim.HUNGER_URGENCY = 0.0
    sim.SLEEP_EFF_FLOOR = 0.35
    sim.KNOWLEDGE_WEIGHT, sim.KNOWLEDGE_GOAL_WEIGHT, sim.KNOWLEDGE_FORGET = 12.0, 0.25, 0.02
    out = []
    for s in range(20000, 20200):
        for w in ("丰富世界", "贫瘠世界"):
            life = NS.scenarios.make(s, w)
            ok, _ = NS.run_window(life, 0, 30)
            if not ok:
                continue
            wd = sim.World(s, **NS.scenarios.WORLDS["基准"])
            ok, _ = NS.run_window(life, 30, 30, world=wd)
            if not ok:
                continue
            NS.level_state(life.agent)
            out.append((s, dict(life.agent.traits)))
    return out


def _test_no_double_multiplication():
    """★最关键的回归测试★ 直接传 beta=b_i 会被内部再乘一次 —— 必须证明它错"""
    tr = {"curiosity": 92.0, "caution": 38.0, "industry": 80.0}
    b = beta_for("Bp", tr)
    good = run_with_effective_coupling(b, 30001)
    assert abs(good["beta"] - b) < 1e-12
    bad = NT.run_task(_Obj(tr), 30001, beta=b)         # ← 错误用法
    ns = NT.novelty_style(_Obj(tr))
    assert abs(bad["beta"] - b * ns) < 1e-12, "内部乘法行为变了"
    assert abs(bad["beta"] - b) > 1e-6, "double-multiplication 竟然没差别？"
    print(f"  ✓ adapter 抵消了内部乘法：正确 {good['beta']:.6f}"
          f" vs 直传 beta 的错误值 {bad['beta']:.6f}（差 {abs(bad['beta']-b):.6f}）")


def _test_A_is_exact_027():
    """A 臂必须与 027 原接口逐位相同（sampling-level replication arm）"""
    for s, tr in _cal_pool()[:60]:
        a = run_arm("A", tr, s)
        b = NT.run_task(_Obj(tr), s)
        for k in ("beta", "choices", "rewards", "explores", "Q_end", "N_end"):
            assert a[k] == b[k], f"✗ A 臂与 027 在 {k} 上不一致（seed {s}）"
    print("  ✓ A 臂 = 027 原接口，beta/choices/rewards/explores/Q_end/N_end 逐位相同")


def _test_Bm_not_arithmetic_complement():
    """B− 必须是反向 percentile，不是 0.05 − B+"""
    diffs = 0
    for s, tr in _cal_pool()[:80]:
        bp, bm = beta_for("Bp", tr), beta_for("Bm", tr)
        if abs(bm - (NT.BETA - bp)) > 1e-9:
            diffs += 1
    assert diffs > 40, "B− 看起来就是算术取补 —— A 的分布并不对称，这是错的"
    print(f"  ✓ B− 走反向 percentile（{diffs}/80 与算术取补不同）")


def _test_marginals_identical_on_calibration():
    """★calibration-only★ 五臂的 beta 边际分布必须逐位相同"""
    pool = _cal_pool()
    ref = sorted(_BETA_A)
    for arm in ("Bp", "Bm", "Cp", "Cm"):
        vals = sorted(beta_for(arm, tr) for _, tr in pool)
        assert set(vals) <= set(ref), f"{arm} 的 beta 落在 A 的 frozen support 之外"
    print(f"  ✓ 各臂 beta 取值集合 ⊆ A 的 frozen support "
          f"[{ref[0]:.6f}, {ref[-1]:.6f}]")


def _test_deterministic():
    tr = {"curiosity": 88.0, "caution": 40.0, "industry": 77.0}
    for arm in ARMS:
        a, b = run_arm(arm, tr, 30002), run_arm(arm, tr, 30002)
        assert a["choices"] == b["choices"] and a["beta"] == b["beta"]
    print("  ✓ 五臂映射确定性")


def _test_frozen_integrity():
    assert F["task_fingerprint"] == NT.config_fingerprint()
    assert abs(F["rho_spearman_A_Bperp"]) < 0.05
    print(f"  ✓ 冻结完整性：sha256 {F['sha256'][:16]}…  任务指纹"
          f" {F['task_fingerprint']}  rank 冗余 {F['rho_spearman_A_Bperp']:+.4f}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"028 接口层自检   frozen n_cal={F['n_cal']}")
    _test_frozen_integrity()
    _test_no_double_multiplication()
    _test_A_is_exact_027()
    _test_Bm_not_arithmetic_complement()
    _test_marginals_identical_on_calibration()
    _test_deterministic()
    print("\n全部通过。下一步：独立 burned block 的 transform transport 彩排。")
