"""
R52 判据的可判定性检查 —— 在烧掉 final block 之前先问一句
============================================================

运行：  python r52_precision.py [--n 1500] [--reps 8]

★ 为什么要有这个脚本 ★
彩排（开发种子 N=1500）里 R52 落在
    1.037 [1.000, 1.084]
判据是「bootstrap 95% CI 下界 **> 1.00**」。下界打印出来正好是 1.000 ——
也就是说"过/不过"取决于这个 bootstrap 分位数的第 4 位小数。

而 bootstrap 分位数本身带蒙特卡洛误差：换一个分析层随机种子，
下界就会抖动。如果抖动幅度 > |下界 − 1.00|，那么这条预注册判据
**在这个效应量上根本不可判定** —— 跑 final 得到的"✓/✗"是掷硬币。

**这必须在跑 final 之前知道**，因为 final block 只能烧一次。

本脚本只用**已经烧掉的开发种子**，不碰 50000 段。
它不改判据、不改模型，只回答一个问题：**这条判据决定得了吗？**
"""

import argparse
import multiprocessing as mp
import os
import random
import statistics

import final_confirm as FC

R52_CI = 4          # CONDITIONS 里 R52 的下标


def boot_lo_hi(wa, wb, seed):
    """按 final_confirm 完全相同的算法，只换分析层随机种子"""
    n = len(wa)
    rng = random.Random(seed)
    treat = [FC.mat_tv(wa[k], wb[k]) for k in range(n)]
    boots = []
    for _ in range(FC.N_BOOT):
        pick = [rng.randrange(n) for _ in range(n)]
        b = (FC.shuffled_base([wa[i] for i in pick], FC.BASE_K, rng) +
             FC.shuffled_base([wb[i] for i in pick], FC.BASE_K, rng))
        boots.append(statistics.mean(treat[i] for i in pick) / statistics.mean(b))
    boots.sort()
    return boots[int(.025 * FC.N_BOOT)], boots[int(.975 * FC.N_BOOT)]


def _job(args):
    wa, wb, seed = args
    return seed, boot_lo_hi(wa, wb, seed)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1500)
    ap.add_argument("--reps", type=int, default=8)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    a = ap.parse_args()

    FC.verify_frozen()
    print(f"R52 可判定性检查   开发种子 0–{a.n-1}   bootstrap {FC.N_BOOT} × {a.reps} 个分析种子")

    sims = [(FC.task_sim, (R52_CI, w, s0, min(FC.CHUNK, a.n - s0)))
            for w in (FC.WA, FC.WB) for s0 in range(0, a.n, FC.CHUNK)]
    store = {FC.WA: [None] * a.n, FC.WB: [None] * a.n}
    with mp.Pool(a.workers) as pool:
        for ci, w, s0, res in pool.imap_unordered(FC._dispatch, sims):
            store[w][s0:s0 + len(res)] = res

    live = [i for i in range(a.n)
            if store[FC.WA][i] is not None and store[FC.WB][i] is not None]
    wa = [store[FC.WA][i] for i in live]
    wb = [store[FC.WB][i] for i in live]
    print(f"有效 n = {len(wa)}\n")

    jobs = [(_job, (wa, wb, 777 + 1000 * r)) for r in range(a.reps)]
    los = []
    with mp.Pool(min(a.workers, a.reps)) as pool:
        for seed, (lo, hi) in pool.imap_unordered(_job, [j[1] for j in jobs]):
            los.append((seed, lo, hi))
    los.sort()

    print(f"  {'分析种子':<10}{'CI 下界':>12}{'CI 上界':>12}{'判据':>10}")
    print("  " + "-" * 44)
    for seed, lo, hi in los:
        print(f"  {seed:<10}{lo:>12.5f}{hi:>12.5f}{'✓ 过' if lo > 1.0 else '✗ 不过':>10}")

    vals = [lo for _, lo, _ in los]
    spread = max(vals) - min(vals)
    n_pass = sum(1 for v in vals if v > 1.0)
    print(f"\n  下界范围 [{min(vals):.5f}, {max(vals):.5f}]   抖动幅度 {spread:.5f}")
    print(f"  {n_pass}/{len(vals)} 个分析种子判「过」")
    print(f"  |中位下界 − 1.00| = {abs(statistics.median(vals) - 1.0):.5f}"
          f"   vs 抖动 {spread:.5f}")
    if n_pass not in (0, len(vals)):
        print("\n  ⚠⚠ 判据不可判定：仅仅换一个**分析层**随机种子，结论就翻。")
        print("     在这个效应量上，「CI 下界 > 1.00」这条 bright line 是掷硬币。")
    else:
        print("\n  ✓ 判据在这个效应量上是稳的（所有分析种子给出同一结论）。")


if __name__ == "__main__":
    mp.freeze_support()
    main()
