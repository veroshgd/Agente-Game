"""
死亡率诊断 —— 120 天里到底是谁在死、什么时候死、为什么死
============================================================

运行：  python mortality_diagnose.py

规则 42 的直接待办。弛豫检验（实验 022）在 120 天上损失 44.5%，
任何长时程结论都变成选择效应的函数。**修之前先搞清楚死因。**

实验 019 有过一次同类问题：死掉的球 46% 的时间在探索、2% 在采集，
是"在没饭吃的时候还立去远处看看这个志向"在杀它们，
用 slack 门（规则 27）压到了 7.0%。现在地板全关 + 120 天，它又回来了。

四个问题：
  1. 什么时候死（死亡的时间分布）
  2. 死前在干什么（动作剖面 vs 幸存者）
  3. 近因是什么（饿死 / 体质垮 / 两者）
  4. 是地板全关特有的，还是完整架构也这样
"""

import statistics
from collections import Counter

import sim
import scenarios
import persistence_ablation as PA

WA, WB, COMMON = "丰富世界", "贫瘠世界", "基准"
N = 400
SPLIT, TOTAL = 30, 120


def run_probe(seed, first):
    """跑到 120 天。返回死亡日（活着 = None）、死前 10 天动作剖面、末态"""
    life = scenarios.make(seed, first)
    agent = life.agent
    trace = []          # 每天结束时的快照

    def phase(d0, d1):
        for day in range(d0, d1):
            before = Counter(agent.action_log)
            for t in range(sim.TICKS_PER_DAY):
                life.world.tick(day, t)
                for inf in life.influences:
                    inf(life.world, agent, day, t, life.inf_rng)
                agent.tick(day, t)
                if not agent.alive:
                    trace.append((day, dict(Counter(agent.action_log) - before),
                                  agent.hunger, agent.condition,
                                  agent.inventory["food"], agent.goal))
                    return False
            agent.daily(day)
            trace.append((day, dict(Counter(agent.action_log) - before),
                          agent.hunger, agent.condition,
                          agent.inventory["food"], agent.goal))
        return True

    if not phase(0, SPLIT):
        return None, trace, agent
    w = sim.World(seed, **scenarios.WORLDS[COMMON])
    life.world = w
    agent.world = w
    alive = phase(SPLIT, TOTAL)
    return (None if alive else trace[-1][0]), trace, agent


def profile_last(trace, days=10):
    acc = Counter()
    for _, acts, _, _, _, _ in trace[-days:]:
        acc.update(acts)
    tot = sum(acc.values()) or 1
    return {a: acc[a] / tot for a in sim.ACTIONS}


def study(label, floor_off, k_on):
    sim.KNOWLEDGE_WEIGHT = 12.0 if k_on else 0.0
    sim.KNOWLEDGE_GOAL_WEIGHT = 0.25 if k_on else 0.0
    sim.KNOWLEDGE_FORGET = 0.02 if k_on else 0.0
    scenarios.make = PA.patched_make(False, floor_off)
    try:
        res = [run_probe(s, w) for w in (WA, WB) for s in range(N)]
    finally:
        scenarios.make = PA._orig_make

    dead = [(d, t, a) for d, t, a in res if d is not None]
    alive = [(d, t, a) for d, t, a in res if d is None]
    rate = len(dead) / len(res)
    print(f"\n  ── {label} ──   死亡 {rate:.1%}  ({len(dead)}/{len(res)})")
    if not dead:
        return

    # 1. 什么时候死
    days = sorted(d for d, _, _ in dead)
    buckets = Counter((d // 15) * 15 for d in days)
    print("    死亡时间分布：" + "  ".join(
        f"{b}-{b+14}天:{buckets[b]}" for b in sorted(buckets)))

    # 2/3. 死前状态
    print(f"    死时中位：饥饿 {statistics.median(t[-1][2] for _, t, _ in dead):.0f}"
          f"  体质 {statistics.median(t[-1][3] for _, t, _ in dead):.0f}"
          f"  存粮 {statistics.median(t[-1][4] for _, t, _ in dead):.1f}")

    dp = [profile_last(t) for _, t, _ in dead]
    ap = [profile_last(t) for _, t, _ in alive] if alive else []
    print(f"    {'动作':<18}{'死者':>8}{'幸存':>8}   死前 10 天占比")
    for act in sim.ACTIONS:
        d_ = statistics.mean(p[act] for p in dp)
        a_ = statistics.mean(p[act] for p in ap) if ap else 0.0
        mark = "  ←" if d_ - a_ > 0.05 else ""
        print(f"    {act:<18}{d_:>7.1%}{a_:>8.1%}{mark}")

    goals = Counter(t[-1][5]["type"] if t[-1][5] else "无" for _, t, _ in dead)
    print("    死时在追求：" + "  ".join(
        f"{g}:{c/len(dead):.0%}" for g, c in goals.most_common(4)))


def main():
    print("=" * 84)
    print(f" 死亡率诊断   {N} 种子 × 2 世界 × {TOTAL} 天   移植到基准")
    print("=" * 84)
    study("完整架构 + 022 打开", floor_off=False, k_on=True)
    study("地板全关 + 022 打开（= 弛豫检验那一档）", floor_off=True, k_on=True)
    study("地板全关 + 022 关闭", floor_off=True, k_on=False)
    study("完整架构 + 022 关闭（= 实验 020 基准）", floor_off=False, k_on=False)


if __name__ == "__main__":
    main()
