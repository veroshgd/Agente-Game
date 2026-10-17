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
参数扫描 —— 找出"那条窄带"

运行：  python sweep.py

推理推不出正确的参数，只能扫。这个脚本对每组参数跑一遍种群，
输出三个判据：

  spread  用户类型之间的性格差距   目标 > 8    ← 核心卖点
  peaks   性格类型的数量（有效）   目标 >= 3   ← 多峰
  death   死亡率                  目标 < 10%
"""

import statistics
from collections import Counter

import sim


def evaluate(pw, drift, hunger, pop=300, days=30):
    sim.PERSONALITY_WEIGHT = pw
    sim.TRAIT_DRIFT = drift
    sim.HUNGER_RATE = hunger
    sim.SIM_DAYS = days

    names = list(sim.USER_ARCHETYPES)
    agents = [sim.Agent(seed=n, archetype=names[n % len(names)]).run()
              for n in range(pop)]
    alive = [a for a in agents if a.alive]
    if len(alive) < pop * 0.4:
        return {"spread": 0.0, "peaks": 0, "death": 1 - len(alive) / pop,
                "sigma": 0.0, "styles": Counter()}

    # 用户类型之间的最大性格差距
    spread = 0.0
    for t in sim.TRAITS:
        means = [statistics.mean([a.traits[t] for a in alive if a.archetype == n])
                 for n in names]
        spread = max(spread, max(means) - min(means))

    styles = Counter(a.dominant_style() for a in alive)
    peaks = sum(1 for _, n in styles.items() if n >= len(alive) * 0.08)
    sigma = statistics.pstdev([a.traits["caution"] for a in alive])

    return {"spread": spread, "peaks": peaks,
            "death": 1 - len(alive) / pop, "sigma": sigma, "styles": styles}


def main():
    grid = [(pw, dr, hr)
            for pw in (8, 18, 30, 45)
            for dr in (0.55, 1.2)
            for hr in (2.2, 1.2, 0.7)]

    print("=" * 74)
    print(" 参数扫描  ——  目标: spread>8, peaks>=3, death<10%")
    print("=" * 74)
    print(f"{'PW':>4} {'drift':>6} {'hunger':>7} | {'spread':>7} {'peaks':>6} "
          f"{'death':>7} {'sigma':>6} |")
    print("-" * 74)

    results = []
    for pw, dr, hr in grid:
        r = evaluate(pw, dr, hr)
        results.append(((pw, dr, hr), r))
        ok = "  ★" if (r["spread"] > 8 and r["peaks"] >= 3
                       and r["death"] < 0.10) else ""
        print(f"{pw:>4} {dr:>6.2f} {hr:>7.1f} | {r['spread']:>7.1f} "
              f"{r['peaks']:>6} {r['death']:>6.1%} {r['sigma']:>6.1f} |{ok}")

    winners = [(p, r) for p, r in results
               if r["spread"] > 8 and r["peaks"] >= 3 and r["death"] < 0.10]

    print("\n" + "=" * 74)
    if winners:
        winners.sort(key=lambda x: -x[1]["spread"])
        print(f" 找到 {len(winners)} 组可用参数。最佳：")
        (pw, dr, hr), r = winners[0]
        print(f"   PERSONALITY_WEIGHT = {pw}")
        print(f"   TRAIT_DRIFT        = {dr}")
        print(f"   HUNGER_RATE        = {hr}")
        print(f"\n   spread={r['spread']:.1f}  peaks={r['peaks']}  "
              f"death={r['death']:.1%}")
        print("   自发形成的类型：")
        for s, n in r["styles"].most_common():
            print(f"     {s:<8} {n:4d}")
    else:
        print(" 没有一组参数同时满足三个判据 —— 说明是结构问题，不是调参问题。")
        best = max(results, key=lambda x: x[1]["spread"])
        print(f" 最接近的： PW={best[0][0]} drift={best[0][1]} "
              f"hunger={best[0][2]}  spread={best[1]['spread']:.1f}")


if __name__ == "__main__":
    main()
