"""⚠ 已废弃（实验 018）
⚠ 已废弃（DEPRECATED）—— 被 param_sweep.py 取代。保留作实验历史，不要用于新分析。
=====================
两个原因：
  1. 判据 `spread > 8` 在自己的种群规模下低于噪声地板
     （pop=300 时噪声 95 分位是 10.48，pop=450 是 9.18）→ 会给纯噪声打 ★
  2. 分组比较已被 paired.py 的配对实验取代，后者灵敏度高得多

保留文件只为历史可追溯。请改用：
    python paired.py     数值层
    python behavior.py   行为层
    python ablation.py   机制贡献
"""

raise SystemExit(__doc__)

"""
扫描食物经济 —— 找"球活得下去，但活得不好"的那个点

核心张力：
  自给自足程度太高 → 用户是多余的 → 无归因（spread=6）
  自给自足程度太低 → 放养型的球会死 → 留存崩掉

目标：放养型活下来，但过得很紧；溺爱型有大量余裕。
"""

import statistics
from collections import Counter

import sim


def evaluate(regen, pop=450, days=30):
    sim.LOCAL_FOOD_REGEN = regen
    sim.SIM_DAYS = days

    names = list(sim.USER_ARCHETYPES)
    agents = [sim.Agent(seed=n, archetype=names[n % len(names)]).run()
              for n in range(pop)]
    alive = [a for a in agents if a.alive]
    if len(alive) < pop * 0.3:
        return None

    spread = 0.0
    for t in sim.TRAITS:
        means = [statistics.mean([a.traits[t] for a in alive if a.archetype == n])
                 for n in names]
        spread = max(spread, max(means) - min(means))

    # 每种用户类型的死亡率 —— 现在这个比总死亡率重要
    death_by = {}
    for n in names:
        grp = [a for a in agents if a.archetype == n]
        death_by[n] = sum(1 for a in grp if not a.alive) / len(grp)

    styles = Counter(a.dominant_style() for a in alive)
    peaks = sum(1 for _, c in styles.items() if c >= len(alive) * 0.08)

    return {
        "spread": spread,
        "death_total": 1 - len(alive) / pop,
        "death_by": death_by,
        "peaks": peaks,
        "starve_flag": sum(1 for a in alive if "fears_hunger" in a.flags) / len(alive),
        "sigma": statistics.pstdev([a.traits["caution"] for a in alive]),
    }


def main():
    print("=" * 78)
    print(" 食物经济扫描   每天需求 ≈ 2.64 份")
    print(" 目标: spread>8, 总死亡率<10%, 放养型死亡率<20%")
    print("=" * 78)
    print(f"{'regen':>6} | {'spread':>7} {'σ':>6} {'peaks':>6} | "
          f"{'死亡总':>7} {'溺爱':>6} {'平衡':>6} {'放养':>6} | {'饿怕了':>7}")
    print("-" * 78)

    best = None
    for regen in (2.0, 2.2, 2.4, 2.6, 2.8, 3.0, 3.4):
        r = evaluate(regen)
        if r is None:
            print(f"{regen:>6.1f} |  ——  全灭")
            continue
        d = r["death_by"]
        ok = (r["spread"] > 8 and r["death_total"] < 0.10
              and d["放养型"] < 0.20 and r["peaks"] >= 3)
        mark = "  ★" if ok else ""
        print(f"{regen:>6.1f} | {r['spread']:>7.1f} {r['sigma']:>6.1f} "
              f"{r['peaks']:>6} | {r['death_total']:>6.1%} "
              f"{d['溺爱型']:>6.1%} {d['平衡型']:>6.1%} {d['放养型']:>6.1%} | "
              f"{r['starve_flag']:>6.1%}{mark}")
        if ok and (best is None or r["spread"] > best[1]["spread"]):
            best = (regen, r)

    print("=" * 78)
    if best:
        print(f" ★ 最佳: LOCAL_FOOD_REGEN = {best[0]}   "
              f"spread={best[1]['spread']:.1f}   "
              f"总死亡率={best[1]['death_total']:.1%}")
    else:
        print(" 没有同时满足的点 —— 说明生存与分化还在互相挤压，"
              "需要给球一条不靠用户也能自救的路（但要有代价）。")


if __name__ == "__main__":
    main()
