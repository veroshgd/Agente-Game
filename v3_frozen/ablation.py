"""
消融实验 —— 每个机制到底贡献了多少
====================================

运行：  python ablation.py

方法来自 Generative Agents（UIST '23）第 6 节：
把架构里的每个部件依次关掉，看指标掉多少。
他们证明的是"每个部件都是必要的"，这里证明的是同一件事——
**分化不是某一个旋钮的功劳，也不是随机的**。

和那篇论文的两点不同：
  1. 他们的因变量是"可信度"（人类评分）；这里是"用户归因"（配对效应量）
  2. 他们只跑了一次模拟，没有零假设基线；这里最后一行就是零假设

★ 最后一行是负对照：把三种用户的投喂间隔调成一样。
  这时同一颗种子的两次模拟完全确定性地相同 → 差值必须精确为 0。
  如果不是 0，说明测量管道里有别的东西在漏，所有上面的数字都不可信。
"""

import statistics

import sim
import scenarios

SEEDS = 300
DAYS = 30
A_NAME, B_NAME = "溺爱型", "放养型"
VISIBLE_DELTA = 5.0

# 每个条件关掉一个机制。键是 sim 里的模块级参数名
# "world:" 前缀 = 世界参数（v2 之后季节属于 World，不再是模块级全局）
CONDITIONS = [
    ("完整架构",            {}),
    ("− 性格权重",          {"PERSONALITY_WEIGHT": 0.0}),
    ("− 正反馈循环",        {"TRAIT_DRIFT": 0.0}),
    ("− 棘轮（经历不留痕）", {"HARDSHIP_MAX_BOOST": 0.0, "LANDMARK_BONUS": 0.0}),
    ("− 季节波动",          {"world:season_amplitude": 0.0}),
    ("− 食物缺口",          {"EXPLORE_FOOD_YIELD": 2.0}),   # 实验 013 之前的状态
    ("− 用户差异（零假设）", {"__same_user__": True}),
]

TUNABLE = ["PERSONALITY_WEIGHT", "TRAIT_DRIFT", "LANDMARK_BONUS",
           "HARDSHIP_MAX_BOOST", "EXPLORE_FOOD_YIELD"]


def apply_override(key, value):
    if key.startswith("world:"):
        sim.WORLD_DEFAULTS[key.split(":", 1)[1]] = value
    else:
        setattr(sim, key, value)


def evaluate():
    """跑一遍配对实验，返回这一组参数下的几个关键指标"""
    sim.SIM_DAYS = DAYS
    world = {(s, a): scenarios.run(s, a)
             for s in range(SEEDS) for a in (A_NAME, B_NAME)}

    pairs = [(world[(s, A_NAME)], world[(s, B_NAME)]) for s in range(SEEDS)
             if world[(s, A_NAME)].alive and world[(s, B_NAME)].alive]
    dead = 1 - sum(1 for s in range(SEEDS) if world[(s, B_NAME)].alive) / SEEDS
    if not pairs:
        return None

    def stat(get):
        d = [get(b) - get(a) for a, b in pairs]
        sd = statistics.pstdev(d)
        return statistics.median(d), (statistics.mean(d) / sd if sd else 0.0)

    ind_med, ind_dz = stat(lambda a: a.traits["industry"])
    con_med, con_dz = stat(lambda a: a.condition)
    carriers = [lambda a: a.traits["industry"], lambda a: a.condition,
                lambda a: a.traits["caution"], lambda a: a.traits["curiosity"],
                lambda a: a.shelter]
    untouched = sum(1 for a, b in pairs
                    if all(abs(g(b) - g(a)) < VISIBLE_DELTA for g in carriers)
                    and a.flags == b.flags) / len(pairs)
    return {"ind_dz": ind_dz, "ind_med": ind_med, "con_dz": con_dz,
            "untouched": untouched, "dead": dead, "n": len(pairs)}


def main():
    print("=" * 84)
    print(f" 消融实验   {SEEDS} 颗种子 × {DAYS} 天   配对：{A_NAME} → {B_NAME}")
    print("=" * 84)
    print(f"{'条件':<24}{'ind dz':>9}{'ind 中位数':>12}{'cond dz':>10}"
          f"{'完全没变化':>12}{'放养死亡':>10}{'相对完整':>10}")
    print("-" * 84)

    base = {k: getattr(sim, k) for k in TUNABLE}
    base_world = dict(sim.WORLD_DEFAULTS)
    base_feeding = dict(scenarios.FEEDING)
    full_dz = None

    for label, overrides in CONDITIONS:
        # 复原到完整架构，再施加本条件的改动
        for k, v in base.items():
            setattr(sim, k, v)
        sim.WORLD_DEFAULTS.update(base_world)
        scenarios.FEEDING.update(base_feeding)

        overrides = dict(overrides)
        if overrides.pop("__same_user__", False):
            for k in scenarios.FEEDING:
                scenarios.FEEDING[k] = 3.0
        for k, v in overrides.items():
            apply_override(k, v)

        r = evaluate()
        if r is None:
            print(f"{label:<24}   —— 全灭")
            continue
        if full_dz is None:
            full_dz = r["ind_dz"]
            drop = "基准"
        else:
            drop = f"{(r['ind_dz'] - full_dz) / full_dz:+.0%}" if full_dz else "—"

        # 中文字符宽度：format 按字符数算，这里手工补一下
        pad = " " * max(0, 24 - sum(2 if '一' <= c <= '鿿' else 1
                                    for c in label))
        print(f"{label}{pad}{r['ind_dz']:>9.3f}{r['ind_med']:>12.2f}"
              f"{r['con_dz']:>10.3f}{r['untouched']:>11.1%}"
              f"{r['dead']:>10.1%}{drop:>10}")

    for k, v in base.items():
        setattr(sim, k, v)
    sim.WORLD_DEFAULTS.update(base_world)
    scenarios.FEEDING.update(base_feeding)

    print("\n 读法：")
    print("   ind dz        用户归因的效应量。掉得越多，说明这个机制越关键")
    print("   完全没变化     换了用户但所有载体都没动的配对比例（越低越好）")
    print("   最后一行必须全是 0 —— 那是零假设，不为 0 就说明测量管道有漏")


if __name__ == "__main__":
    main()
