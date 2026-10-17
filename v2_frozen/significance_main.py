"""
主结论的置换检验 —— 移植后的差异显著吗？
===============================================

运行：  python significance_main.py

`significance.py` 测的是老的**投喂 spread 轴**（400 次置换），
`behavior.py` 的 2000 次符号置换测的也是投喂轴。
**移植比值 1.13 / 1.04 这两个核心数字，此前一个 p 值都没有。**（实验 021 第 5 节）

★ 怎么绕开"TV 恒为正不能用符号置换"（笔记 804 行）★
-------------------------------------------------------
TV 距离恒为正，直接对它翻符号没有意义。但**比值的分子和分母之差**可正可负。
所以把统计量下放到【每颗种子】：

    d_i = TV(A_i, B_i)                     同种子、两个世界   ← 世界效应
    b_i = mean_j TV(A_i, A_j), TV(B_i, B_j)  同世界、不同种子   ← 种子效应
    δ_i = d_i − b_i                        这颗种子上，世界比种子多解释了多少

H0：世界不比种子更有力 → E[δ] = 0，且 δ_i 的符号是对称的。
于是**符号置换合法了**：随机翻转 δ_i 的正负号 N 次，得到零假设分布。

这同时也是效应量的正确形式 —— δ 的均值带单位（TV），
比"比值"少一层 Jensen 偏差。

⚠ 已知局限：b_i 复用了其他种子的球，所以 δ_i 之间有弱相关。
   严格做法是 cluster bootstrap；符号置换在这里略偏乐观，
   但 p 值小到 1e-4 量级时这个修正无关紧要。
"""

import math
import random
import statistics
import sys

import sim
import scenarios
import persistence_ablation as PA
from transplant import run_phased, window_tv

WA, WB, COMMON = "丰富世界", "贫瘠世界", "基准"
N_PERM = 10000
BASE_K = 5          # 每颗种子的 b_i 用几个随机对手求平均


def per_seed_delta(cohA, cohB, n_seeds, rng):
    """返回逐种子的 δ_i，以及分子/分母的均值（用来对齐旧的比值口径）"""
    live = [i for i in range(n_seeds)
            if cohA[i][0] is not None and cohB[i][0] is not None]
    wa = [cohA[i][1] for i in live]
    wb = [cohB[i][1] for i in live]
    n = len(live)
    if n < 30:
        return None

    deltas, ds, bs = [], [], []
    for k in range(n):
        d = window_tv(wa[k], wb[k])
        opp = []
        for _ in range(BASE_K):
            j = rng.randrange(n - 1)
            j = j if j < k else j + 1          # 排除自己
            opp.append(window_tv(wa[k], wa[j]))
            j = rng.randrange(n - 1)
            j = j if j < k else j + 1
            opp.append(window_tv(wb[k], wb[j]))
        b = statistics.mean(opp)
        deltas.append(d - b)
        ds.append(d)
        bs.append(b)
    return deltas, statistics.mean(ds), statistics.mean(bs)


def sign_perm_p(deltas, n_perm, rng):
    """符号置换：H0 下 δ_i 的符号对称"""
    obs = statistics.mean(deltas)
    hits = 0
    for _ in range(n_perm):
        m = statistics.mean(d if rng.random() < 0.5 else -d for d in deltas)
        if abs(m) >= abs(obs):
            hits += 1
    return obs, (hits + 1) / (n_perm + 1)      # +1 修正，p 永远不报 0


def cohen_dz(deltas):
    sd = statistics.stdev(deltas)
    return statistics.mean(deltas) / sd if sd else 0.0


def run(label, cfg, n_seeds, seed0):
    sat_backup = sim.TRAIT_SATURATION
    if "sat" in cfg:
        sim.TRAIT_SATURATION = cfg["sat"]
    scenarios.make = PA.patched_make(cfg.get("ident", False), cfg.get("floor", False))
    try:
        seeds = range(seed0, seed0 + n_seeds)
        ca = [run_phased(s, WA, COMMON) for s in seeds]
        cb = [run_phased(s, WB, COMMON) for s in seeds]
    finally:
        sim.TRAIT_SATURATION = sat_backup
        scenarios.make = PA._orig_make

    rng = random.Random(12345)
    got = per_seed_delta(ca, cb, n_seeds, rng)
    if got is None:
        print(f"  {label:<16} 样本不足")
        return
    deltas, md, mb = got
    obs, p = sign_perm_p(deltas, N_PERM, rng)
    dz = cohen_dz(deltas)
    frac = sum(1 for d in deltas if d > 0) / len(deltas)
    star = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "n.s."
    print(f"  {label:<16}{len(deltas):>6}{md:>9.4f}{mb:>9.4f}{md/mb:>8.3f}"
          f"{obs:>+10.4f}{dz:>8.2f}{frac:>8.1%}{p:>10.4f}  {star}")


def main():
    n_seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
    print("=" * 104)
    print(f" 主结论置换检验   逐种子 δ = TV(同种子跨世界) − TV(同世界跨种子)"
          f"   符号置换 {N_PERM} 次")
    print("=" * 104)
    print(f"  {'条件':<16}{'n':>6}{'分子TV':>9}{'基线TV':>9}{'比值':>8}"
          f"{'δ均值':>10}{'dz':>8}{'δ>0':>8}{'p':>10}")
    print("  " + "-" * 100)

    for seed0, tag in ((0, "开发集 seeds 0+"), (10000, "留出集 seeds 10000+")):
        print(f"\n  ── {tag}，N={n_seeds} ──")
        run("完整架构", dict(), n_seeds, seed0)
        run("−全部地板①②", dict(floor=True), n_seeds, seed0)

    print("\n  δ均值 = 世界效应比种子效应多出来的 TV（带单位，无 Jensen 偏差）")
    print("  dz    = Cohen's dz（配对效应量）    δ>0 = 有多少颗种子上世界赢了")


if __name__ == "__main__":
    main()
