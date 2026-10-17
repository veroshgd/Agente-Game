"""
P2 —— 移植那一刻单独删 knowledge（保留 flags），比值塌不塌
==============================================================

运行：  python p2_test.py

预注册第 4 节：

    P2：删除档比 P1 档低 ≥ 0.05，且两者 95% CI 不重叠

★ 为什么必须【单独】删 ★（预注册第 2 节）
`landmark()` 同时写 flags 和 knowledge（`sim.py:458`），两者完全相关 ——
这就是实验 020 机制表里"语义记忆差"和"关键经历差"两列数字一模一样的原因。
`deletion.py` 原来的阶梯是嵌套的（②③④ 层层叠加），测不出归因。
这里改成**非嵌套**：每一档只删一样东西。

★ P2 的逻辑 ★
如果 P1 通过（接线后无地板档 > 1），那个持久性必须**来自 knowledge**。
移植那刻把 knowledge 抹掉、其他一律保留 —— 比值应该塌回 1 附近。
如果不塌，说明持久性来自别处，**不能声称 knowledge 通路**。
"""

import random
import statistics
from collections import Counter

import sim
import scenarios
import persistence_ablation as PA
from transplant import window_tv, SPLIT, TOTAL
from significance_main import per_seed_delta, sign_perm_p
from p1_test import shuffled_base, BASE_K, N_BOOT

WA, WB, COMMON = "丰富世界", "贫瘠世界", "基准"
N_SEEDS = 1500
SEED0 = 20000          # 与 P1 同一段（预注册保留段）


def wipe_at_transplant(agent, what):
    """★非嵌套★ 每一档只删一样。trait_floor / trait_identity 永不在此处删
    —— 它们由 floor 消融负责，混在一起就分不清归因。"""
    if "semantic" in what:
        agent.knowledge = {}
        agent.knowledge_strength = {}      # 022：强度才是 know() 读的东西
    if "episodic" in what:
        agent.memories = []
    if "flags" in what:
        agent.flags = set()
    if "hardship" in what:
        agent.hardship = 0.0
        agent._hardship_anchor = None


def run_phased_wipe(seed, first, wipe_what):
    """前 30 天 first 世界 → 抹掉指定层 → 后 30 天基准世界"""
    life = scenarios.make(seed, first)
    agent = life.agent

    def phase(d0, d1):
        for day in range(d0, d1):
            for t in range(sim.TICKS_PER_DAY):
                life.world.tick(day, t)
                for inf in life.influences:
                    inf(life.world, agent, day, t, life.inf_rng)
                agent.tick(day, t)
                if not agent.alive:
                    return False
            agent.daily(day)
        return True

    if not phase(0, SPLIT):
        return None, None
    snap = [Counter(c) for c in agent.action_by_hour]

    w = sim.World(seed, **scenarios.WORLDS[COMMON])
    life.world = w
    agent.world = w
    wipe_at_transplant(agent, wipe_what)       # ★就在这一刻★

    if not phase(SPLIT, TOTAL):
        return None, None
    window = [Counter(c) - snap[h] for h, c in enumerate(agent.action_by_hour)]
    return agent, window


def analyse(label, wipe_what, floor_off=True):
    scenarios.make = PA.patched_make(False, floor_off)
    try:
        seeds = range(SEED0, SEED0 + N_SEEDS)
        ca = [run_phased_wipe(s, WA, wipe_what) for s in seeds]
        cb = [run_phased_wipe(s, WB, wipe_what) for s in seeds]
    finally:
        scenarios.make = PA._orig_make

    live = [i for i in range(N_SEEDS)
            if ca[i][0] is not None and cb[i][0] is not None]
    n = len(live)
    wa = [ca[i][1] for i in live]
    wb = [cb[i][1] for i in live]
    rng = random.Random(777)

    treat = [window_tv(wa[k], wb[k]) for k in range(n)]
    base = shuffled_base(wa, BASE_K, rng) + shuffled_base(wb, BASE_K, rng)
    ratio = statistics.mean(treat) / statistics.mean(base)

    boots = []
    for _ in range(N_BOOT):
        pick = [rng.randrange(n) for _ in range(n)]
        boots.append(statistics.mean(treat[i] for i in pick) /
                     statistics.mean(shuffled_base([wa[i] for i in pick], BASE_K, rng) +
                                     shuffled_base([wb[i] for i in pick], BASE_K, rng)))
    boots.sort()
    lo, hi = boots[int(.025 * N_BOOT)], boots[int(.975 * N_BOOT)]

    deltas = per_seed_delta(ca, cb, N_SEEDS, random.Random(12345))[0]
    _, p = sign_perm_p(deltas, 10000, random.Random(999))
    star = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "n.s."
    print(f"  {label:<24}{n:>6}{1-n/N_SEEDS:>8.1%}{ratio:>8.3f}"
          f"  [{lo:.3f}, {hi:.3f}]{p:>9.4f} {star}")
    return ratio, lo, hi


def main():
    sim.KNOWLEDGE_WEIGHT, sim.KNOWLEDGE_GOAL_WEIGHT, sim.KNOWLEDGE_FORGET = 12.0, 0.25, 0.02
    print("=" * 96)
    print(f" P2 非嵌套删除   seeds {SEED0}–{SEED0+N_SEEDS-1}   N={N_SEEDS}"
          f"   022 打开 + 地板全关")
    print("=" * 96)
    print(f"  {'移植那刻删掉什么':<24}{'n':>6}{'死亡':>8}{'比值':>8}  {'95% CI':<18}{'p':>9}")
    print("  " + "-" * 92)

    base_r = analyse("① 什么都不删（=P1）", set())
    sem = analyse("② 只删语义 knowledge", {"semantic"})
    epi = analyse("③ 只删情节 memories", {"episodic"})
    flg = analyse("④ 只删 flags", {"flags"})
    allm = analyse("⑤ 删语义+情节+flags", {"semantic", "episodic", "flags"})

    print(f"\n  P2 判据：② 比 ① 低 ≥ 0.05 且 CI 不重叠")
    drop = base_r[0] - sem[0]
    overlap = not (sem[2] < base_r[1] or base_r[2] < sem[1])
    print(f"    ①{base_r[0]:.3f} → ②{sem[0]:.3f}   落差 {drop:+.3f}   "
          f"CI {'重叠' if overlap else '不重叠'}   "
          f"{'✓ P2 过' if drop >= 0.05 and not overlap else '✗ P2 不过'}")
    print("\n  ③④ 是对照：如果删情节/flags 也掉一样多，说明不是 knowledge 特有的。")


if __name__ == "__main__":
    main()
