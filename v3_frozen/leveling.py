"""
状态拉平 —— caution 那条继续拉开的曲线，是发现还是伪影？
============================================================

运行：  python leveling.py

## 要区分的两件事

移植到同一个中立世界之后，caution 的差距**还在继续扩大**：

    第30天  +30    +60    +90
     19.4   26.9   30.9   33.2      （增速 +7.5 / +4.0 / +2.3，像收敛到 35）

两种解释，价值差一个量级：

    强解释  分化会自我维持。贫瘠分身带着 knowledge / goal / 性格，
            在中立世界里继续制造抬高 caution 的经历 → 路径依赖
    弱解释  状态混淆。它只是还没缓过来 —— 体质更差、存粮更少、没房子，
            所以持续遭遇让它更谨慎的事 → 这是恢复曲线，不是性格

## 区分方法

移植的那一刻，把**状态**强行拉平（两边完全一样），
只留下**性格 / 记忆 / 目标**不同。然后看 caution 还会不会继续拉开。

    继续拉开  → 强解释。差异靠内部结构自我维持
    立刻走平  → 弱解释。之前那条曲线是状态恢复的投影

⚠ 拉平会给"探索型"分身一套它本来没有的家当（房子/存粮）。
   这是有意的：我们要问的正是"**除了家当之外**，它们还剩什么不同"。
"""

import statistics

import sim
import scenarios
from paired import pad

SEEDS = 200
SPLIT = 30
CHECKS = (30, 60, 90, 120)
WA, WB = "丰富世界", "贫瘠世界"
COMMON = "基准"

# 拉平到哪个状态。取一个中等偏舒适的点，两边完全一致
LEVEL = {"hunger": 30.0, "energy": 80.0, "shelter": 50.0,
         "condition": 100.0, "food": 3.0, "material": 0.0}


def apply_level(agent):
    agent.hunger = LEVEL["hunger"]
    agent.energy = LEVEL["energy"]
    agent.shelter = LEVEL["shelter"]
    agent.condition = LEVEL["condition"]
    agent.inventory = {"food": LEVEL["food"], "material": LEVEL["material"]}
    # 受苦累积是"经历"，不是"状态" —— 故意不清掉，它属于记忆那一侧


def run_tracked(seed, first, second, level):
    """跑到 max(CHECKS) 天，在每个检查点记一次性格和状态"""
    life = scenarios.make(seed, first)
    agent = life.agent
    snaps = {}
    for day in range(max(CHECKS)):
        if day == SPLIT:
            w = sim.World(seed, **scenarios.WORLDS[second])
            life.world = w
            agent.world = w
            if level:
                apply_level(agent)
        for t in range(sim.TICKS_PER_DAY):
            life.world.tick(day, t)
            for inf in life.influences:
                inf(life.world, agent, day, t, life.inf_rng)
            agent.tick(day, t)
            if not agent.alive:
                return snaps          # ★保留死亡前已记录的检查点★
        agent.daily(day)
        if day + 1 in CHECKS:
            snaps[day + 1] = {
                **{t: agent.traits[t] for t in sim.TRAITS},
                "condition": agent.condition, "shelter": agent.shelter,
                "food": agent.inventory["food"], "hardship": agent.hardship,
            }
    return snaps


def curve(level):
    """★每个检查点各自算存活集合★

    如果统一用"活到 120 天的那批"，所有行都被同一批幸存者主导，
    而幸存者恰好是"没跑掉的球" —— 那正是 caution 这条曲线在讲的东西，
    等于用结论筛样本。改成逐点结算：第 60 天那行用活到第 60 天的所有配对。
    """
    A = [run_tracked(s, WA, COMMON, level) for s in range(SEEDS)]
    B = [run_tracked(s, WB, COMMON, level) for s in range(SEEDS)]
    out = {}
    for d in CHECKS:
        live = [i for i in range(SEEDS) if d in A[i] and d in B[i]]
        if not live:
            continue
        out[d] = {k: statistics.mean(B[i][d][k] - A[i][d][k] for i in live)
                  for k in A[live[0]][d]}
        out[d]["loss"] = 1 - len(live) / SEEDS
        out[d]["n"] = len(live)
    return out, None


def show(title, data, n):
    print(f"\n{title}")
    keys = list(sim.TRAITS) + ["condition", "shelter", "food", "hardship"]
    print(f"  {pad('天', 8)}" + "".join(pad(k[:9], 12, True) for k in keys)
          + pad("有效配对", 11, True) + pad("损失", 9, True))
    for d in CHECKS:
        if d not in data:
            continue
        tag = f"第{d}天" + ("（移植点）" if d == SPLIT else "")
        flag = "  ⚠" if data[d]["loss"] > 0.15 else ""
        print(f"  {pad(tag, 8)}"
              + "".join(pad(f"{data[d][k]:+.1f}", 12, True) for k in keys)
              + pad(f"{data[d]['n']}", 11, True)
              + pad(f"{data[d]['loss']:.1%}", 9, True) + flag)
    caut = [data[d]["caution"] for d in CHECKS if d in data]
    gains = [caut[i + 1] - caut[i] for i in range(len(caut) - 1)]
    print(f"  caution 增量：" + "  ".join(f"{g:+.1f}" for g in gains))
    return gains


def main():
    print("=" * 104)
    print(f" 状态拉平实验   {SEEDS} 颗种子   {WA} ↔ {WB}，"
          f"第 {SPLIT} 天两边都进【{COMMON}】")
    print("=" * 104)
    print("  差值 = 贫瘠分身 − 丰富分身。移植点之后，caution 还会不会继续拉开？")

    raw, n_raw = curve(level=False)
    g_raw = show("【对照】不拉平（= 之前那条曲线）", raw, n_raw)

    lev, n_lev = curve(level=True)
    g_lev = show("【处理】移植时把状态拉平（只留性格/记忆/目标不同）", lev, n_lev)

    print("\n" + "=" * 104)
    print(" 判定  ★只用配对损失 ≤15% 的检查点★")
    print("=" * 104)
    # 幸存者恰好是"没跑掉的球"，而那正是这条曲线在讲的东西 —— 污染的点必须踢掉
    clean = [d for d in CHECKS if d in raw and d in lev
             and raw[d]["loss"] <= 0.15 and lev[d]["loss"] <= 0.15]
    dropped = [d for d in CHECKS if d not in clean]
    print(f"  采用的检查点：{clean}"
          + (f"   剔除（幸存者污染）：{dropped}" if dropped else ""))

    def total(data):
        return data[clean[-1]]["caution"] - data[clean[0]]["caution"]

    tot_raw, tot_lev = total(raw), total(lev)
    print(f"\n  移植后 caution 增长（第 {clean[0]}→{clean[-1]} 天）")
    print(f"    不拉平  {tot_raw:+.1f}")
    print(f"    拉平后  {tot_lev:+.1f}   （相对 {tot_lev / tot_raw:.0%}）")

    # 弱解释的核心预言：贫瘠分身状态更差，所以持续遭遇让它更谨慎的事
    cond = lev[clean[-1]]["condition"]
    print(f"\n  弱解释的检验：拉平后第 {clean[-1]} 天，贫瘠分身的体质差 {cond:+.1f}")
    print("    弱解释预言这里应该是【负的】（它还没缓过来）。")

    print()
    if tot_lev >= 0.6 * tot_raw and tot_lev > 1.0:
        print("  ★ 强解释成立：状态拉平后差距照样扩大 → 分化靠内部结构自我维持")
        if cond > 0:
            print("    而且贫瘠分身的体质【更好】—— 它不是还没缓过来，是活得更好。")
    elif tot_lev <= 0.25 * tot_raw:
        print("  ✗ 弱解释：拉平后就不长了 → 之前那条曲线是状态恢复的投影")
    else:
        print("  ~ 两者都有：一部分自我维持，一部分状态恢复")


if __name__ == "__main__":
    main()
