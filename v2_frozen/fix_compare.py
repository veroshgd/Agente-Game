"""
三种改法对比 —— 治得了死亡率，会不会顺手抹平差异？
======================================================

运行：  python fix_compare.py

规则 43 有三种候选改法。单看死亡率会选错：**任何让所有球都拼命觅食的改动，
都会同时压缩世界之间的行为差异** —— 死亡率降到 0 而比值也塌到 1，是失败。

所以每一档同时报四个数：

    死亡率(120天, 完整)   死亡率(120天, 地板全关)   ← 要降
    头条比值(60天, 完整)  比值(60天, 地板全关)      ← 不能塌

★ 判据 ★
  好的改法 = 两个死亡率都 <15%，且两个比值都不显著低于现状。
  规则 44：地板全关那一列尤其重要 —— 它现在的 53.9% 死亡率正是污染源。
"""

import random
import statistics
import sys

import sim
import scenarios
import persistence_ablation as PA
from transplant import run_phased, window_tv
from p1_test import shuffled_base, BASE_K

WA, WB, COMMON = "丰富世界", "贫瘠世界", "基准"
N_RATIO = 500      # 比值用（60 天）
N_DEATH = 300      # 死亡率用（120 天，更贵）
# 400 次足够给这张对比表定位；shuffled_base 每次要重算 ~2500 个 TV，
# 上到 1500 次的话八档要跑将近一小时，不值得。
N_BOOT = 400


def ratio_and_death(floor_off, days=60, n=N_RATIO):
    """返回 (比值, CI, 死亡率)。days=120 时只取死亡率有意义。"""
    sim.SIM_DAYS = days
    import transplant as T
    old_total = T.TOTAL
    T.TOTAL = days
    scenarios.make = PA.patched_make(False, floor_off)
    try:
        ca = [run_phased(s, WA, COMMON, split=30, total=days) for s in range(n)]
        cb = [run_phased(s, WB, COMMON, split=30, total=days) for s in range(n)]
    finally:
        scenarios.make = PA._orig_make
        T.TOTAL = old_total

    live = [i for i in range(n) if ca[i][0] is not None and cb[i][0] is not None]
    dead = 1 - len(live) / n
    if len(live) < 50:
        return None, (0, 0), dead
    wa = [ca[i][1] for i in live]
    wb = [cb[i][1] for i in live]
    rng = random.Random(777)
    treat = [window_tv(wa[k], wb[k]) for k in range(len(live))]
    base = shuffled_base(wa, BASE_K, rng) + shuffled_base(wb, BASE_K, rng)
    ratio = statistics.mean(treat) / statistics.mean(base)
    boots = []
    for _ in range(N_BOOT):
        pick = [rng.randrange(len(live)) for _ in range(len(live))]
        boots.append(statistics.mean(treat[i] for i in pick) /
                     statistics.mean(shuffled_base([wa[i] for i in pick], BASE_K, rng) +
                                     shuffled_base([wb[i] for i in pick], BASE_K, rng)))
    boots.sort()
    return ratio, (boots[int(.025*N_BOOT)], boots[int(.975*N_BOOT)]), dead


def setfix(a, b, c):
    sim.SLEEP_SUPPRESS, sim.HUNGER_URGENCY, sim.SLEEP_EFF_FLOOR = a, b, c


FIXES = [
    ("现状（无改法）",       0.0,  0.0, 0.35),
    ("A 压睡眠 0.5",        0.5,  0.0, 0.35),
    ("A 压睡眠 1.0",        1.0,  0.0, 0.35),
    ("B 抬急迫 25",         0.0, 25.0, 0.35),
    ("B 抬急迫 50",         0.0, 50.0, 0.35),
    ("C 睡眠下限 0.60",      0.0,  0.0, 0.60),
    ("C 睡眠下限 0.80",      0.0,  0.0, 0.80),
    ("A0.5 + C0.6 合用",    0.5,  0.0, 0.60),
]


def main():
    k_on = "--k-off" not in sys.argv
    sim.KNOWLEDGE_WEIGHT = 12.0 if k_on else 0.0
    sim.KNOWLEDGE_GOAL_WEIGHT = 0.25 if k_on else 0.0
    sim.KNOWLEDGE_FORGET = 0.02 if k_on else 0.0

    print("=" * 104)
    print(f" 三种改法对比   022 {'打开' if k_on else '关闭'}   "
          f"比值 N={N_RATIO}(60天)   死亡率 N={N_DEATH}(120天)")
    print("=" * 104)
    print(f"  {'改法':<18}{'死亡%完整':>11}{'死亡%无地板':>12}"
          f"{'比值 完整':>22}{'比值 无地板':>22}")
    print("  " + "-" * 100)

    for label, a, b, c in FIXES:
        setfix(a, b, c)
        r_full, ci_full, _ = ratio_and_death(False, 60)
        r_abl,  ci_abl,  _ = ratio_and_death(True, 60)
        _, _, d_full = ratio_and_death(False, 120, N_DEATH)
        _, _, d_abl = ratio_and_death(True, 120, N_DEATH)
        f_ok = "" if d_full < 0.15 else "⚠"
        a_ok = "" if d_abl < 0.15 else "⚠"
        print(f"  {label:<18}{d_full:>10.1%}{f_ok:<1}{d_abl:>11.1%}{a_ok:<1}"
              f"{r_full:>10.3f} [{ci_full[0]:.3f},{ci_full[1]:.3f}]"
              f"{r_abl:>10.3f} [{ci_abl[0]:.3f},{ci_abl[1]:.3f}]")

    print("\n  判据：两个死亡率都 <15%（无 ⚠），且两个比值都不显著低于「现状」那一行")
    print("  ⚠ 治死亡率的代价常常是抹平差异 —— 比值塌了就是失败，哪怕死亡率降到 0")


if __name__ == "__main__":
    main()
