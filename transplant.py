"""
移植实验 —— 把因去掉，差异还在不在？
=====================================

实验 018 证明了：同一颗种子放进两个世界，30 天后行为差异 > 基线（比值 1.56）。
但那时候两只球**还待在不同的世界里**。所以那个数字无法区分：

    (A) 经历塑造了它        → 差异写进了性格/记忆，换回同一个世界也还在
    (B) 只是当前条件不同     → 差异是环境的即时投影，环境一样就消失

产品文档里那句「以前有一次下很大的雨…从那以后我就不太喜欢没有准备」
要求的是 (A)。这个脚本直接检验。

做法：
    第 0–29 天   丰富世界  /  贫瘠世界        ← 造成差异
    第 30–59 天  两边都换成「基准」世界        ← 把因去掉
    只在第 30–59 天这个窗口上测行为差异

对照组「持续」：第 30–59 天留在原来的世界（因还在）。

    持续组比值高、移植组比值塌 → 是 (B)，是温度计不是性格
    两个都高                   → 是 (A)，经历真的留下来了
"""

import statistics
from collections import Counter

import sim
import scenarios
from behavior import ACTIONS, GLANCE

SEEDS = 250
SPLIT = 30
TOTAL = 60
WA, WB = "丰富世界", "贫瘠世界"
COMMON = "基准"


def run_phased(seed, first, second, split=SPLIT, total=TOTAL):
    """前半生在 first 世界，后半生在 second 世界。返回 (agent, 窗口内的逐时辰计数)"""
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

    if not phase(0, split):
        return None, None
    snap = [Counter(c) for c in agent.action_by_hour]   # 第 30 天的快照

    if second != first:                                 # 换世界
        w = sim.World(seed, **scenarios.WORLDS[second])
        life.world = w
        agent.world = w

    if not phase(split, total):
        return None, None

    window = [Counter(c) - snap[h] for h, c in enumerate(agent.action_by_hour)]
    return agent, window


def window_tv(wa, wb):
    """只看窗口内的逐时辰动作分布差异"""
    tot = 0.0
    for ha, hb in zip(wa, wb):
        na, nb = sum(ha.values()) or 1, sum(hb.values()) or 1
        tot += 0.5 * sum(abs(ha[x] / na - hb[x] / nb) for x in ACTIONS)
    return tot / len(wa)


def cohort(first, second):
    out = []
    for s in range(SEEDS):
        a, w = run_phased(s, first, second)
        out.append((s, a, w))
    return out


def analyse(label, cohA, cohB):
    pairs = [(a, wa, b, wb) for (s, a, wa), (_, b, wb) in zip(cohA, cohB)
             if a is not None and b is not None]
    if not pairs:
        print(f"  {label}: 全灭")
        return None
    live_seeds = {s for (s, a, _), (_, b, _) in zip(cohA, cohB)
                  if a is not None and b is not None}

    tv_user = statistics.mean(window_tv(wa, wb) for _, wa, _, wb in pairs)

    # 基线：同一条路径、不同种子。★只用两边都活下来的那些种子★
    # （environment.py 是按各自 cohort 内的存活者配对的，贫瘠世界的存活者
    #   被筛选过 → 组内方差偏小 → 基线偏小 → 比值被抬高。这里堵掉。）
    base = []
    for coh in (cohA, cohB):
        al = [w for (s, a, w) in coh if a is not None and s in live_seeds]
        base += [(al[i], al[i + 1]) for i in range(0, len(al) - 1, 2)]
    tv_base = statistics.mean(window_tv(x, y) for x, y in base)

    eye = sum(1 for a, _, b, _ in pairs
              if any(t(a) != t(b) for _, t in GLANCE)) / len(pairs)
    dtr = {t: statistics.mean(b.traits[t] - a.traits[t] for a, _, b, _ in pairs)
           for t in sim.TRAITS}
    dead = 1 - len(pairs) / SEEDS

    print(f"  {label:<10} {tv_user:>8.3f} {tv_base:>8.3f} {tv_user / tv_base:>7.2f}"
          f" {eye:>10.1%} {dead:>8.1%}   "
          + " ".join(f"{t[:2]}{dtr[t]:+6.1f}" for t in sim.TRAITS))
    return tv_user / tv_base


def main():
    print("=" * 96)
    print(f" 移植实验   {SEEDS} 颗种子   第 0–{SPLIT-1} 天分化，第 {SPLIT}–{TOTAL-1} 天测量")
    print(f" {WA} ↔ {WB}，测量窗口只取后 {TOTAL-SPLIT} 天")
    print("=" * 96)
    print(f"  {'条件':<10} {'窗口TV':>8} {'基线':>8} {'比值':>7} {'一眼可辨':>10} {'死亡':>8}"
          "   性格差（后−前）")
    print("  " + "-" * 92)

    stayA, stayB = cohort(WA, WA), cohort(WB, WB)
    r_stay = analyse("持续", stayA, stayB)

    movA, movB = cohort(WA, COMMON), cohort(WB, COMMON)
    r_move = analyse("移植", movA, movB)

    print()
    if r_stay and r_move:
        keep = r_move / r_stay
        print(f"  持续 {r_stay:.2f} → 移植 {r_move:.2f}   保留了 {keep:.0%}")
        print()
        if r_move >= 1.0:
            print("  ★ 移植后比值仍 > 1：差异不依赖环境继续存在 → 经历真的塑造了它")
        elif keep >= 0.6:
            print("  ~ 移植后比值 < 1 但保留了大部分：有真实的持久成分，但不足以自己站住")
        else:
            print("  ✗ 移植后塌了：差异主要是环境的即时投影，不是性格")


if __name__ == "__main__":
    main()
