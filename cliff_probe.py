"""
悬崖探针 —— 一次采样同时回答三个问题
========================================

运行：  python cliff_probe.py

3g 节留了个待办："先扫 58/60/62/65/68/70 把悬崖测出来"。
但扫描只能确认悬崖在哪，不能解释它**为什么**在那里，也答不上审稿人
那句"为什么是 65"。而且扫描漏掉了一个更要紧的风险（问题 3）。

所以这里不扫阈值，改成一次采样出三样东西：

  ① 饥饿度的逐 tick 分布
     悬崖可以直接从分布**算**出来，不用扫：
         净体质/tick(T) = COND_RECOVER·P(饿<T) − COND_DRAIN·P(饿>70)
     一次分布 → 整条曲线的预测 → 再挑 2–3 点验证就够了。

  ② 分布的**支撑宽度**
     饥饿是锯齿：每 tick +2.2，一次进食 −20。所以支撑区只有约 20 分宽，
     而两个阶跃阈值（COND_DRAIN_AT=70 和 COND_RECOVER_AT）都卡在这 20 分里。
     ★如果支撑区确实只有 20 分宽，悬崖就是结构性的★ ——
     任何平移锯齿的参数（HUNGER_RATE / FOOD_NUTRITION / 食物再生）
     都会让死亡率阶跃。扫描无法消除它，只能记录它。

  ③ ⚠ hardship 通道还在不在 —— 判据表测不到的那个风险
     sim.py:936  hardship += (100−condition)/100 / 24
     sim.py:941  trait_floor ← hardship_norm × 22          ← 棘轮在这
     sim.py:890  condition ≥ 99.5 时 hardship 反而**遗忘**
     抬高恢复阈值 = 体质常驻高位 = deficit≈0 = **棘轮被掐掉**。
     而这条棘轮正是 021 第 3 节和 022 在研究的东西。
     判据表看不到：无地板那一列本来就把地板关了。

只跑贫瘠世界 → 第 30 天移植到基准（规则 47 的那个设定），
统计一律只取移植之后（day ≥ 30）的 tick。
"""

import statistics
import sys
from collections import Counter

import sim
import scenarios
import persistence_ablation as PA

WB, COMMON = "贫瘠世界", "基准"
N = 60
SPLIT, TOTAL = 30, 120
BIN = 2.5                      # 饥饿直方图分辨率
NBINS = int(100 / BIN) + 1

# (标签, 恢复阈值, 死区恢复, 住所恢复)
VARIANTS = [
    ("现状",          30.0, 0.00, 0.00),
    ("① 阈值 55",     55.0, 0.00, 0.00),
    ("① 阈值 60",     60.0, 0.00, 0.00),
    ("① 阈值 65",     65.0, 0.00, 0.00),
    ("③ 住所 +0.10",  30.0, 0.00, 0.10),
]


def run_one(seed, floor_off):
    """跑 120 天。返回 (死亡日 or None, 饥饿直方图, 末态字典)"""
    scenarios.make = PA.patched_make(False, floor_off)
    try:
        life = scenarios.make(seed, WB)
    finally:
        scenarios.make = PA._orig_make
    agent = life.agent
    hist = [0] * NBINS

    def phase(d0, d1, record):
        for day in range(d0, d1):
            for t in range(sim.TICKS_PER_DAY):
                life.world.tick(day, t)
                for inf in life.influences:
                    inf(life.world, agent, day, t, life.inf_rng)
                agent.tick(day, t)
                if record:
                    hist[min(NBINS - 1, int(agent.hunger / BIN))] += 1
                if not agent.alive:
                    return day
            agent.daily(day)
        return None

    d = phase(0, SPLIT, False)
    if d is not None:
        return d, hist, snapshot(agent, floor_off)
    w = sim.World(seed, **scenarios.WORLDS[COMMON])
    life.world = w
    agent.world = w
    d = phase(SPLIT, TOTAL, True)
    return d, hist, snapshot(agent, floor_off)


def snapshot(agent, floor_off):
    """末态：hardship 通道的三个读数 + 体质"""
    lift = 0.0
    if not floor_off:      # 地板关了的话 trait_floor 是 FrozenZero，抬升无意义
        lift = max(agent.trait_floor[t] - agent.trait_identity[t]
                   for t in sim.TRAITS)
    return dict(condition=agent.condition,
                hardship=agent.hardship,
                hnorm=agent.hardship_norm,
                lift=lift,
                fears="fears_hunger" in agent.flags)


def net_budget(hist, T):
    """从直方图算净体质/tick：+COND_RECOVER·P(饿<T) − COND_DRAIN·P(饿>70)"""
    tot = sum(hist) or 1
    lo = sum(hist[i] for i in range(NBINS) if (i + 0.5) * BIN < T)
    hi = sum(hist[i] for i in range(NBINS) if (i + 0.5) * BIN > sim.COND_DRAIN_AT)
    return (sim.COND_RECOVER * lo - sim.COND_DRAIN * hi) / tot, lo / tot, hi / tot


def pct(hist, q):
    tot = sum(hist)
    if not tot:
        return float("nan")
    target, acc = tot * q, 0
    for i in range(NBINS):
        acc += hist[i]
        if acc >= target:
            return (i + 0.5) * BIN
    return 100.0


def run_variant(label, rec_at, dz, sh, floor_off):
    sim.COND_RECOVER_AT, sim.COND_DEADZONE_RECOVER, sim.COND_SHELTER_RECOVER = rec_at, dz, sh
    hist = [0] * NBINS
    dead, snaps = 0, []
    for s in range(N):
        d, h, snap = run_one(s, floor_off)
        if d is not None:
            dead += 1
        else:
            snaps.append(snap)         # hardship 只统计幸存者，避免濒死态污染
        hist = [a + b for a, b in zip(hist, h)]
    return dead / N, hist, snaps


def main():
    sim.KNOWLEDGE_WEIGHT, sim.KNOWLEDGE_GOAL_WEIGHT, sim.KNOWLEDGE_FORGET = 12.0, 0.25, 0.02

    for floor_off in (False, True):
        arch = "地板全关（规则 44 的污染源）" if floor_off else "完整架构"
        print("=" * 100)
        print(f" 悬崖探针 · {arch} · N={N} 种子 · 贫瘠→基准@30 · 统计 day≥30 的 tick")
        print("=" * 100)

        rows = []
        for label, rec_at, dz, sh in VARIANTS:
            rows.append((label, rec_at) + run_variant(label, rec_at, dz, sh, floor_off))

        # ---- ① 饥饿分布 + 支撑宽度 ----
        print(f"\n  【饥饿分布】锯齿支撑区有多宽？（宽度 ≈ FOOD_NUTRITION = "
              f"{sim.FOOD_NUTRITION:.0f} 就是结构性悬崖）")
        print(f"  {'修法':<14}{'死亡%':>8}{'p5':>7}{'p25':>7}{'中位':>7}{'p75':>7}"
              f"{'p95':>7}{'p5–p95宽':>10}{'P(饿>70)':>10}")
        print("  " + "-" * 88)
        for label, _, dead, hist, _ in rows:
            p5, p95 = pct(hist, .05), pct(hist, .95)
            _, _, hi = net_budget(hist, 30)
            print(f"  {label:<14}{dead:>7.1%}{p5:>7.1f}{pct(hist,.25):>7.1f}"
                  f"{pct(hist,.5):>7.1f}{pct(hist,.75):>7.1f}{p95:>7.1f}"
                  f"{p95-p5:>10.1f}{hi:>10.1%}")

        # ---- 悬崖预测：净收支 vs 阈值 ----
        Ts = [30, 40, 45, 50, 55, 58, 60, 62, 65, 68, 70]
        print(f"\n  【悬崖预测】净体质/tick = {sim.COND_RECOVER}·P(饿<T) − "
              f"{sim.COND_DRAIN}·P(饿>70)，用「现状」的分布外推")
        print("  " + " " * 8 + "".join(f"{t:>7}" for t in Ts))
        for label, _, _, hist, _ in rows[:1] + rows[-1:]:
            print(f"  {label:<8}" + "".join(
                f"{net_budget(hist,t)[0]:>7.3f}" for t in Ts))
        print("  （>0 才有稳态；符号翻转的位置就是悬崖。各档自身的分布见下方逐档预测）")
        print("  " + " " * 8 + "".join(f"{t:>7}" for t in Ts))
        for label, _, _, hist, _ in rows:
            print(f"  {label:<8}" + "".join(
                f"{net_budget(hist,t)[0]:>7.3f}" for t in Ts))

        # ---- ③ hardship 通道 ----
        print(f"\n  【hardship 棘轮】⚠ 判据表测不到的那个风险（只算幸存者）")
        print(f"  {'修法':<14}{'末体质':>8}{'hardship':>10}{'hnorm':>8}"
              f"{'地板抬升':>10}{'fears_hunger%':>14}")
        print("  " + "-" * 66)
        for label, _, _, _, snaps in rows:
            if not snaps:
                print(f"  {label:<14}{'—— 全灭 ——':>50}")
                continue
            m = lambda k: statistics.mean(s[k] for s in snaps)
            fr = sum(s["fears"] for s in snaps) / len(snaps)
            lift = f"{m('lift'):>10.2f}" if not floor_off else f"{'n/a':>10}"
            print(f"  {label:<14}{m('condition'):>8.1f}{m('hardship'):>10.2f}"
                  f"{m('hnorm'):>8.3f}{lift}{fr:>13.0%}")
        print("\n  hnorm → 地板抬升 = HARDSHIP_MAX_BOOST(22) × hnorm（sim.py:941）")
        print("  hnorm 塌了 = 棘轮被掐掉 = 021 第 3 节 / 022 研究的机制本身被改掉\n")

    sim.COND_RECOVER_AT, sim.COND_DEADZONE_RECOVER, sim.COND_SHELTER_RECOVER = 30.0, 0.0, 0.0


if __name__ == "__main__":
    main()
