"""
P1 —— 接线后，无地板档比值还能不能 > 1
==========================================

运行：  python p1_test.py

预注册 [[实验022 预注册 —— 记忆接入决策]] 第 4 节：

    P1：接线后无地板档移植比值 > 1，N=1500，bootstrap 95% CI 下界 > 1.00

基准（021，022 关闭）：−全部地板①② = 1.044 [0.996, 1.094]，p≈0.07 n.s.

★ 种子：20000–21499 ★ 预注册第 6 节保留给 022 确认，此前从未使用。
★ 基线：K=5 随机配对（规则 35），不是相邻配对。
★ 同时给 bootstrap CI 和符号置换 p（规则 34 + 021 第 5 节的方法）。
"""

import random
import statistics

import sim
import scenarios
import persistence_ablation as PA
from transplant import run_phased, window_tv
from significance_main import per_seed_delta, sign_perm_p, cohen_dz

WA, WB, COMMON = "丰富世界", "贫瘠世界", "基准"
N_SEEDS = 1500
SEED0 = 20000
BASE_K = 5
N_BOOT = 3000
N_PERM = 10000


def shuffled_base(windows, k, rng):
    out = []
    idx = list(range(len(windows)))
    for _ in range(k):
        rng.shuffle(idx)
        out += [window_tv(windows[idx[j]], windows[idx[j + 1]])
                for j in range(0, len(idx) - 1, 2)]
    return out


def cohorts(cfg):
    sat_backup = sim.TRAIT_SATURATION
    if "sat" in cfg:
        sim.TRAIT_SATURATION = cfg["sat"]
    scenarios.make = PA.patched_make(cfg.get("ident", False), cfg.get("floor", False))
    try:
        seeds = range(SEED0, SEED0 + N_SEEDS)
        ca = [run_phased(s, WA, COMMON) for s in seeds]
        cb = [run_phased(s, WB, COMMON) for s in seeds]
    finally:
        sim.TRAIT_SATURATION = sat_backup
        scenarios.make = PA._orig_make
    return ca, cb


def analyse(label, cfg):
    ca, cb = cohorts(cfg)
    live = [i for i in range(N_SEEDS)
            if ca[i][0] is not None and cb[i][0] is not None]
    n = len(live)
    wa = [ca[i][1] for i in live]
    wb = [cb[i][1] for i in live]
    rng = random.Random(777)

    treat = [window_tv(wa[k], wb[k]) for k in range(n)]
    base = shuffled_base(wa, BASE_K, rng) + shuffled_base(wb, BASE_K, rng)
    ratio = statistics.mean(treat) / statistics.mean(base)

    # cluster bootstrap：按 agent 重采样
    boots = []
    for _ in range(N_BOOT):
        pick = [rng.randrange(n) for _ in range(n)]
        t = [treat[i] for i in pick]
        b = (shuffled_base([wa[i] for i in pick], BASE_K, rng) +
             shuffled_base([wb[i] for i in pick], BASE_K, rng))
        boots.append(statistics.mean(t) / statistics.mean(b))
    boots.sort()
    lo, hi = boots[int(.025 * N_BOOT)], boots[int(.975 * N_BOOT)]

    got = per_seed_delta(ca, cb, N_SEEDS, random.Random(12345))
    deltas = got[0]
    obs, p = sign_perm_p(deltas, N_PERM, random.Random(999))
    dz = cohen_dz(deltas)
    dead = 1 - n / N_SEEDS
    star = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "n.s."
    ok = "✓ 过" if lo > 1.0 else "✗ 不过"
    print(f"  {label:<20}{n:>6}{dead:>8.1%}{ratio:>8.3f}  [{lo:.3f}, {hi:.3f}]"
          f"{obs:>+9.4f}{dz:>7.2f}{p:>9.4f} {star:<5}{ok}")
    return ratio, lo, hi


def main():
    print("=" * 108)
    print(f" P1 确认   seeds {SEED0}–{SEED0+N_SEEDS-1}（预注册保留段，首次使用）"
          f"   N={N_SEEDS}   基线 K={BASE_K} 随机配对")
    print("=" * 108)
    print(f"  {'条件':<20}{'n':>6}{'死亡':>8}{'比值':>8}  {'95% CI':<18}"
          f"{'δ均值':>9}{'dz':>7}{'p':>9}      P1")
    print("  " + "-" * 104)

    for tag, (w, gw, f) in [("022 关闭", (0.0, 0.0, 0.0)),
                            ("022 打开", (12.0, 0.25, 0.02))]:
        sim.KNOWLEDGE_WEIGHT, sim.KNOWLEDGE_GOAL_WEIGHT, sim.KNOWLEDGE_FORGET = w, gw, f
        print(f"\n  ── {tag}  (W={w} GW={gw} FORGET={f}) ──")
        analyse("完整架构", dict())
        analyse("−全部地板①②", dict(floor=True))

    print("\n  P1 判据：【022 打开 + −全部地板①②】那一行的 CI 下界 > 1.00")
    print("  基准（022 关闭）：1.044 [0.996, 1.094]，p≈0.07 n.s.")


if __name__ == "__main__":
    main()
