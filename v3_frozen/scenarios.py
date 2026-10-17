"""
实验配置 —— 这里才知道"用户"是什么
====================================

`sim.py` 是 Life Engine，它不知道用户存在。
所有"谁在照顾它、照顾得多勤、世界里有没有书"都定义在这里。

这条分界线是故意的：
把 USER_ARCHETYPES 留在模型里，实验就会一直被拉回"投喂频率"这一个维度。

两组实验：

  FEEDING  —— 旧的对照组（投喂频率）。保留，因为它已经积累了 011–017 的历史。
  WORLDS   —— 新的主线（环境）。同一颗种子、同样的初始性格，只换世界。
"""

import statistics
from collections import Counter

import sim
from sim import Life, World

# ============================================================
# 一、投喂频率（旧对照组）
# ============================================================
# ⚠ 这三个不是 Agent 的属性，是**实验组的定义**。
#    Agent 那边只会看到"今天世界里多了食物"。

FEEDING = {
    "溺爱型":  1.0,   # 一饿就投喂
    "平衡型":  3.0,
    "放养型":  8.0,   # 经常几天不上线
}

# ============================================================
# 二、环境（新主线）
# ============================================================
# 笔记 ⑥：不要再比较溺爱 vs 放养。改成同一个 Agent 放进不同的世界。
#
#   丰富环境 vs 贫瘠环境 / 有书 vs 没书 / 有音乐 vs 安静 /
#   常下雨 vs 天气稳定 / 材料丰富 vs 材料稀缺
#
# 每个世界都配同样的中等投喂，这样"用户勤不勤"被控制住，
# 变化的只有环境本身。

_BASE_FEED = 3.0

WORLDS = {
    # --- 对照 ---
    "基准":       dict(),
    # --- 资源 ---
    "食物丰富":   dict(food_regen=3.2),
    "食物贫瘠":   dict(food_regen=1.8),
    "材料丰富":   dict(material_yield=2.0),
    "材料稀缺":   dict(material_yield=0.5),
    # --- 天气 ---
    "常下雨":     dict(storm_chance=0.16),
    "天气稳定":   dict(storm_chance=0.0),
    # --- 物件 ---
    "有书":       dict(objects=("book",)),
    "有音乐":     dict(objects=("music",)),
    # --- 组合：note 里的 Experiment A / B ---
    "丰富世界":   dict(food_regen=3.2, material_yield=2.0,
                       objects=("book", "music"), storm_chance=0.02),
    "贫瘠世界":   dict(food_regen=1.8, material_yield=0.5,
                       objects=(), storm_chance=0.10),
}


# ============================================================
# 构造
# ============================================================

def make(seed, name, *, world_seed=None, days=None):
    """按名字造一次生命。名字可以是 FEEDING 的键，也可以是 WORLDS 的键。"""
    if name in FEEDING:
        world = World(seed if world_seed is None else world_seed)
        infl = [sim.give_food(2.0, FEEDING[name])]
    elif name in WORLDS:
        world = World(seed if world_seed is None else world_seed, **WORLDS[name])
        infl = [sim.give_food(2.0, _BASE_FEED)]
    else:
        raise KeyError(f"未知实验组: {name}")
    return Life(seed, world=world, influences=infl)


def run(seed, name, **kw):
    """造 + 跑，返回 agent。分析脚本用这个。

    返回的 agent 上会挂一个 `.scenario` 标签 —— 那是**实验台账**，
    给分析脚本分组用的，模型在跑的时候完全不读它。
    （对比 v1：那时 `archetype` 是 Agent 的构造参数，会直接决定它的行为。）
    """
    days = kw.pop("days", None)
    agent = make(seed, name, **kw).run(days)
    agent.scenario = name
    return agent


# ============================================================
# 种群报告（原来在 sim.py 的 main）
# ============================================================

def histogram(values, lo=0, hi=100, bins=20, width=46):
    counts = [0] * bins
    for v in values:
        counts[min(bins - 1, int((v - lo) / (hi - lo) * bins))] += 1
    peak = max(counts) or 1
    for b in range(bins):
        print(f"  {lo + (hi - lo) * b / bins:5.0f} | "
              f"{'█' * int(counts[b] / peak * width)} {counts[b]}")


def main(population=999):
    names = list(FEEDING)
    print("=" * 62)
    print(f" 种群报告   {population} 只球 × {sim.SIM_DAYS} 天")
    print(f" PERSONALITY_WEIGHT={sim.PERSONALITY_WEIGHT}  "
          f"TRAIT_DRIFT={sim.TRAIT_DRIFT}")
    print("=" * 62)

    agents = [run(n, names[n % len(names)]) for n in range(population)]
    alive = [a for a in agents if a.alive]
    dead = len(agents) - len(alive)
    print(f"\n存活 {len(alive)}/{len(agents)}   死亡 {dead} "
          f"({dead / len(agents):.1%})")
    for i, name in enumerate(names):
        grp = [a for n, a in enumerate(agents) if n % len(names) == i]
        d = sum(1 for a in grp if not a.alive) / len(grp)
        print(f"    {name}: 死亡率 {d:5.1%}")

    print("\n【按实验组】性格均值")
    print(f"  {'实验组':<8} {'谨慎':>14} {'好奇':>14} {'勤劳':>14}")
    for i, name in enumerate(names):
        grp = [a for n, a in enumerate(agents)
               if n % len(names) == i and a.alive]
        cells = "".join(
            f"{statistics.mean([a.traits[t] for a in grp]):9.1f}"
            f"±{statistics.pstdev([a.traits[t] for a in grp]):4.1f}"
            for t in sim.TRAITS)
        print(f"  {name:<8}{cells}")

    print("\n【谨慎度分布】")
    histogram([a.traits["caution"] for a in alive])
    print(f"  σ = {statistics.pstdev([a.traits['caution'] for a in alive]):.1f}")

    print("\n【自发形成的性格类型】")
    for style, n in Counter(a.dominant_style() for a in alive).most_common():
        print(f"  {style:<8} {n:4d}  {'▇' * int(n / len(alive) * 44)}")

    print("\n【关键经历触发率】")
    for flag, label in [("fears_hunger", "熬过挨饿"),
                        ("fears_storm", "被暴雨掀翻屋顶"),
                        ("loves_exploring", "发现了远方的宝地"),
                        ("reads", "读到了新东西")]:
        n = sum(1 for a in alive if flag in a.flags)
        print(f"  {label:<16} {n:4d}  ({n / len(alive):5.1%})")


if __name__ == "__main__":
    main()
