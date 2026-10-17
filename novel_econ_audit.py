"""
行为经济审计 —— ★ group-blind ★ 选新赛道之前先量速率
=========================================================

运行：  python novel_econ_audit.py --seeds 300

★ 为什么先做这个 ★
Probe A 失败的根因（规则 64）是：我从代码结构读出"explore 绕开 world.food
→ 存在第二条食物路线"，**没有验证速率**。实测 explore 期望产出 0.14/tick、
维持饥饿需 0.11/tick，余量 27%，扣掉睡觉时间后净收支为负 → 探索派全死。

**规则 49 之前的悬崖、规则 64 的冻土，都是同一型错误：
从结构推出"可能性"，没有量"量级"。**

所以在选下一条赛道之前，先把各条行为经济的**实际速率与个体差异幅度**量出来：
哪几个动作在 common garden 里既有足够占比、又有足够的**跨个体方差**，
才可能承载"策略分岔"。没有方差的动作，再novel 也投影不出个体差异。

★ group-blind ★ 只输出 pooled 量与跨个体方差，**不按发育世界分组**。
种子 `20000+`。**不碰 `60000–61499`。**
"""

import argparse
import multiprocessing as mp
import os
import statistics
from collections import Counter

WA, WB, COMMON = "丰富世界", "贫瘠世界", "基准"
DEV_DAYS, OBS_DAYS = 30, 30
CHUNK = 25


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
        alive, win = NS.run_window(c, DEV_DAYS, OBS_DAYS, world=w)
        acc = Counter()
        for h in win:
            acc.update(h)
        tot = sum(acc.values()) or 1
        # ★ 不含任何世界标签 ★
        out.append({a: acc[a] / tot for a in sim.ACTIONS} | {"_alive": alive})
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

    import novel_situation as NS
    acts = NS.sim.ACTIONS
    n = len(pool)
    print("=" * 92)
    print(f" 行为经济审计（group-blind）  common garden {OBS_DAYS} 天  "
          f"n={n}（两世界混合）  存活 {sum(r['_alive'] for r in pool)/n:.1%}")
    print("=" * 92)
    print(f"  {'动作':<18}{'均值占比':>10}{'跨个体SD':>11}{'变异系数':>10}"
          f"{'p10':>8}{'p90':>8}{'p90−p10':>10}{'>0 的球':>9}")
    print("  " + "-" * 88)
    rows = []
    for act in acts:
        v = sorted(r[act] for r in pool)
        mu = statistics.mean(v)
        sd = statistics.stdev(v) if len(v) > 1 else 0.0
        p10, p90 = v[int(.10 * len(v))], v[int(.90 * len(v))]
        nz = sum(1 for x in v if x > 0) / len(v)
        cv = sd / mu if mu > 1e-9 else float("nan")
        rows.append((act, mu, sd, cv, p90 - p10, nz))
        print(f"  {act:<18}{mu:>10.3f}{sd:>11.4f}{cv:>10.2f}"
              f"{p10:>8.3f}{p90:>8.3f}{p90-p10:>10.3f}{nz:>9.1%}")

    print("\n  【判读】能承载策略分岔的动作，必须同时满足：")
    print("    · 均值占比够大（有操作空间）   · p90−p10 够宽（个体差异真实存在）")
    print("    · >0 的球够多（不是少数球的专利）")
    ok = [r for r in rows if r[1] >= 0.05 and r[4] >= 0.05 and r[5] >= 0.5]
    print(f"\n  同时满足三条的动作：{[r[0] for r in ok] or '（无）'}")

    print("\n  ⚠ read 的占比应为 0 —— 基准世界没有书"
          f"（实测 {statistics.mean(r['read'] for r in pool):.4f}）")
    print("  ⚠ 这意味着：往 novel 世界里放书 = 对丰富世界出身的球是【旧经验】，")
    print("     对贫瘠世界出身的球才是【新事物】—— 不是对双方都 novel。")


if __name__ == "__main__":
    mp.freeze_support()
    main()
