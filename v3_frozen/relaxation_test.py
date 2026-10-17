"""
弛豫检验 —— 移植后剩下的 1.04，是持久性还是"还没漂回去"？
================================================================

运行：  python relaxation_test.py

P2（[[实验022 预注册 —— 记忆接入决策]]）留下的问题：
移植那刻把语义 + 情节 + flags 全删光，比值仍有 **1.040（p=0.0707 n.s.）**。
两种解释：

    持久     性状向量真的定型了，再给多久也回不去
    弛豫     地板已关，性状在慢慢往回漂，30 天只是还没漂完

做法：移植后不止跑 30 天，跑 90 天，**分三个独立窗口**各测一次：

    [30,60)   [60,90)   [90,120)

弛豫 → 逐窗下降，最后一窗回到 1.0。
持久 → 三窗持平。

★ 规则 32：逐点结算存活集合 ★
不能用"活到 120 天那批"统一算全表 —— 幸存者恰好是"没跑掉的球"，
而那正是被测的性质。每个窗口各自算自己的有效配对，并报损失率。
实验 020 实测 120 天损失 24.5%，所以最后一窗大概率要打问号。
"""

import random
import statistics
from collections import Counter

import sim
import scenarios
import persistence_ablation as PA
from transplant import window_tv
from p1_test import shuffled_base, BASE_K
from p2_test import wipe_at_transplant

WA, WB, COMMON = "丰富世界", "贫瘠世界", "基准"
N_SEEDS = 1500
SEED0 = 20000
SPLIT = 30
CHECKS = (60, 90, 120)          # 窗口右端；窗口 = 前 30 天
N_BOOT = 2000
LOSS_WARN = 0.15


def run_long(seed, first, wipe_what):
    """跑到 120 天，返回三个窗口各自的逐时辰计数（死了之后的窗口为 None）"""
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
        return [None] * len(CHECKS)

    w = sim.World(seed, **scenarios.WORLDS[COMMON])
    life.world = w
    agent.world = w
    wipe_at_transplant(agent, wipe_what)

    out = []
    prev = [Counter(c) for c in agent.action_by_hour]
    start = SPLIT
    for end in CHECKS:
        if not phase(start, end):
            out += [None] * (len(CHECKS) - len(out))
            return out
        cur = [Counter(c) for c in agent.action_by_hour]
        out.append([cur[h] - prev[h] for h in range(len(cur))])
        prev = cur
        start = end
    return out


def analyse(label, wipe_what):
    scenarios.make = PA.patched_make(False, True)      # 地板全关
    try:
        seeds = range(SEED0, SEED0 + N_SEEDS)
        ca = [run_long(s, WA, wipe_what) for s in seeds]
        cb = [run_long(s, WB, wipe_what) for s in seeds]
    finally:
        scenarios.make = PA._orig_make

    print(f"\n  ── {label} ──")
    for wi, end in enumerate(CHECKS):
        live = [i for i in range(N_SEEDS)
                if ca[i][wi] is not None and cb[i][wi] is not None]
        n = len(live)
        loss = 1 - n / N_SEEDS
        if n < 50:
            print(f"    第{end-30}–{end}天   样本不足")
            continue
        wa = [ca[i][wi] for i in live]
        wb = [cb[i][wi] for i in live]
        rng = random.Random(777)
        treat = [window_tv(wa[k], wb[k]) for k in range(n)]
        base = shuffled_base(wa, BASE_K, rng) + shuffled_base(wb, BASE_K, rng)
        ratio = statistics.mean(treat) / statistics.mean(base)
        boots = []
        for _ in range(N_BOOT):
            pick = [rng.randrange(n) for _ in range(n)]
            boots.append(statistics.mean(treat[i] for i in pick) /
                         statistics.mean(
                             shuffled_base([wa[i] for i in pick], BASE_K, rng) +
                             shuffled_base([wb[i] for i in pick], BASE_K, rng)))
        boots.sort()
        lo, hi = boots[int(.025 * N_BOOT)], boots[int(.975 * N_BOOT)]
        flag = " ⚠损失>15%" if loss > LOSS_WARN else ""
        sig = "≠1" if lo > 1.0 else "含1.0"
        print(f"    第{end-30:>3}–{end:>3}天   n={n:>5}  损失{loss:>6.1%}  "
              f"比值 {ratio:.3f}  [{lo:.3f}, {hi:.3f}]  {sig}{flag}")


def main():
    sim.KNOWLEDGE_WEIGHT, sim.KNOWLEDGE_GOAL_WEIGHT, sim.KNOWLEDGE_FORGET = 12.0, 0.25, 0.02
    print("=" * 92)
    print(f" 弛豫检验   seeds {SEED0}–{SEED0+N_SEEDS-1}   N={N_SEEDS}"
          f"   022 打开 + 地板全关   三个独立 30 天窗口")
    print("=" * 92)
    analyse("① 什么都不删", set())
    analyse("⑤ 移植那刻删光 语义+情节+flags", {"semantic", "episodic", "flags"})
    print("\n  逐窗下降并回到 1.0 → 弛豫，那 1.040 是残留假象，不能写进论文")
    print("  三窗持平            → 真持久，性状向量定型了")


if __name__ == "__main__":
    main()
