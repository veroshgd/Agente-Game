"""
goal-pair 小审计 —— Probe C「离家失修」的放行前提
==================================================

运行：  python goal_pair_audit.py --seeds 300

capacity audit 测到「99.3% 的球用过 ≥2 种 goal」，
**但那不能自动说明 `see_the_world` 与 `improve_home` 这两个特定目标够普遍**
—— 里面可能大部分是 `stock_food` / `recover`。

Probe C 的整条设计都建立在这一对目标的冲突上，所以先只确认三件事：

  ① 各有多少 agent 真正立过
  ② 各占多少 goal-days
  ③ 有多少 agent **两种都经历过**（冲突才有对象）

★ group-blind ★ 只输出 pooled 量与跨个体方差。种子 `20000+`。
**不碰 `60000–61499`。** 不实现任何机制，不改 v3。
"""

import argparse
import multiprocessing as mp
import os
import statistics
from collections import Counter

WA, WB, COMMON = "丰富世界", "贫瘠世界", "基准"
DEV_DAYS, OBS_DAYS = 30, 30
CHUNK = 25
PAIR = ("see_the_world", "improve_home")


def task(job):
    world, seed0, n = job
    import novel_situation as NS
    sim = NS.sim
    sim.COND_RECOVER_AT = 65.0
    sim.COND_DEADZONE_RECOVER = sim.COND_SHELTER_RECOVER = 0.0
    sim.SLEEP_SUPPRESS = sim.HUNGER_URGENCY = 0.0
    sim.SLEEP_EFF_FLOOR = 0.35
    sim.KNOWLEDGE_WEIGHT, sim.KNOWLEDGE_GOAL_WEIGHT, sim.KNOWLEDGE_FORGET = 12.0, 0.25, 0.02

    out = []
    for s in range(seed0, seed0 + n):
        life = NS.scenarios.make(s, world)
        ok, _ = NS.run_window(life, 0, DEV_DAYS)
        if not ok:
            continue
        NS.level_state(life.agent)
        c = NS.fork(life, False)
        w = sim.World(s, **NS.scenarios.WORLDS[COMMON])
        NS.run_window(c, DEV_DAYS, OBS_DAYS, world=w)
        days = c.agent.goal_by_day[DEV_DAYS:DEV_DAYS + OBS_DAYS]
        seq = [g for g in days if g]
        switches = sum(1 for i in range(1, len(seq)) if seq[i] != seq[i - 1])
        out.append({"days": days, "switches": switches,
                    "counts": dict(Counter(seq)), "n_days": len(seq)})
    return out


def _dispatch(j):
    return task(j[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=300)
    ap.add_argument("--seed0", type=int, default=20000)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    a = ap.parse_args()

    jobs = [(task, (w, s0, min(CHUNK, a.seed0 + a.seeds - s0)))
            for w in (WA, WB) for s0 in range(a.seed0, a.seed0 + a.seeds, CHUNK)]
    pool = []
    with mp.Pool(a.workers) as p:
        for recs in p.imap_unordered(_dispatch, jobs):
            pool.extend(recs)
    if not pool:
        raise SystemExit("✗ 池子为空 —— 故障")
    n = len(pool)

    import novel_situation as NS
    goals = list(NS.sim.GOAL_ACTIONS)
    total_days = sum(r["n_days"] for r in pool) or 1

    print("=" * 96)
    print(f" goal-pair 小审计（group-blind）  common garden {OBS_DAYS} 天  n={n}")
    print("=" * 96)
    print(f"  {'goal':<18}{'立过的 agent':>14}{'占 goal-days':>14}"
          f"{'人均天数':>10}{'个体占比 p90−p10':>18}")
    print("  " + "-" * 92)
    for g in goals:
        held = sum(1 for r in pool if r["counts"].get(g, 0) > 0) / n
        days = sum(r["counts"].get(g, 0) for r in pool)
        shares = sorted(r["counts"].get(g, 0) / (r["n_days"] or 1) for r in pool)
        sp = shares[int(.90 * n)] - shares[int(.10 * n)]
        star = "  ★" if g in PAIR else ""
        print(f"  {g:<18}{held:>13.1%}{days/total_days:>14.1%}"
              f"{days/n:>10.1f}{sp:>18.3f}{star}")

    both = sum(1 for r in pool
               if all(r["counts"].get(g, 0) > 0 for g in PAIR)) / n
    either = sum(1 for r in pool
                 if any(r["counts"].get(g, 0) > 0 for g in PAIR)) / n
    pair_days = sum(r["counts"].get(g, 0) for r in pool for g in PAIR) / total_days
    sw = [r["switches"] for r in pool]

    print(f"\n  ★ Probe C 依赖的那一对：{PAIR[0]} ↔ {PAIR[1]} ★")
    print(f"    两种【都】经历过的 agent ： {both:>6.1%}   ← 冲突才有对象")
    print(f"    至少经历过一种          ： {either:>6.1%}")
    print(f"    这一对合计占 goal-days  ： {pair_days:>6.1%}")
    print(f"    目标切换次数（30 天）    ： 中位 {statistics.median(sw):.0f}"
          f"  p10 {sorted(sw)[int(.1*n)]}  p90 {sorted(sw)[int(.9*n)]}")

    ok = both >= 0.50 and pair_days >= 0.30
    print("\n" + "=" * 96)
    if ok:
        print(" ★ 放行条件满足（建议线：两种都经历 ≥50%，合计 goal-days ≥30%）")
        print(" → 可以正式实现 Probe C「离家失修」。")
    else:
        print(" ✗ 这一对目标在 common garden 里不够普遍 —— 不该硬做 Probe C。")
        print("   按排序改去 knowledge 通道（严格避开 books 来源）。")
    print("=" * 96)
    print(" ⚠ 放行线 50% / 30% 是我拟的，需拍板。")


if __name__ == "__main__":
    mp.freeze_support()
    main()
