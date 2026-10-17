"""
环境实验 —— 同一颗种子，两个世界
==================================

运行：  python environment.py

这是笔记 ⑥ 要的那个实验，也是产品哲学的直接检验：

    用户不是控制 NPC，而是像上帝一样改变它所处的世界；
    生命根据环境自己成长。

所以不再比较「溺爱型 vs 放养型」，改成：

    同一颗 seed、同一个初始 personality、同一个 Agent、同样的投喂频率，
    唯一改变的是**世界**。

30 天以后问一句：它们有没有变成不同的生命？

★ 噪声地板（规则 9）
--------------------
跟 behavior.py 一样，比值才是结论：

    环境造成的差异  = 同种子，不同世界
    基线            = 同世界，不同种子   ← 两只球本来就有的差异

**环境比值必须超过 1**，否则"换个世界它就长成另一个样"这句话不成立。
顺便把老的投喂轴也列进来，直接比较两条通路谁更有力。
"""

import statistics
import sys

import sim
import scenarios
from behavior import GLANCE, hourly_tv, profile, tv
from paired import pad

SEEDS = 250
DAYS = 30

# 要比较的世界对。前两个是笔记里的 Experiment A / B
PAIRS = [
    ("丰富世界", "贫瘠世界"),
    ("有书",     "基准"),
    ("有音乐",   "基准"),
    ("食物丰富", "食物贫瘠"),
    ("材料丰富", "材料稀缺"),
    ("常下雨",   "天气稳定"),
]

# 老的对照轴：用户投喂频率。放在同一张表里才知道哪条通路更有力
FEED_PAIR = ("溺爱型", "放养型")

GOAL_TYPES = list(sim.GOAL_ACTIONS)


def goal_profile(agent):
    """一生中每种目标各占多少天 —— goal 层带来的新载体"""
    days = [g for g in agent.goal_by_day if g]
    n = len(days) or 1
    return {g: days.count(g) / n for g in GOAL_TYPES}


def goal_tv(a, b):
    pa, pb = goal_profile(a), goal_profile(b)
    return 0.5 * sum(abs(pa[g] - pb[g]) for g in GOAL_TYPES)


def cohort(name):
    return [scenarios.run(s, name, days=DAYS) for s in range(SEEDS)]


def compare(name_a, name_b, cache):
    for n in (name_a, name_b):
        if n not in cache:
            cache[n] = cohort(n)
    A, B = cache[name_a], cache[name_b]

    live = [i for i in range(SEEDS) if A[i].alive and B[i].alive]
    pairs = [(A[i], B[i]) for i in live]
    if not pairs:
        return None

    # 基线：同一个世界里，两只不同种子的球差多少
    # ★只用两边都活下来的那些种子★
    # 旧版是在各自 cohort 内部挑存活者配对。问题：贫瘠世界的存活者是被
    # 筛选过的一批（弱的都死了）→ 组内方差偏小 → 基线偏小 → 比值虚高。
    # 处理组用的是"两边都活"的交集，基线也必须用同一批种子，否则两边
    # 的选择压力不一样，比的就不是同一件事。
    base = []
    for coh in (A, B):
        al = [coh[i] for i in live]
        base += [(al[i], al[i + 1]) for i in range(0, len(al) - 1, 2)]

    def mean(fn, ps):
        return statistics.mean(fn(x, y) for x, y in ps)

    hu, hb = mean(hourly_tv, pairs), mean(hourly_tv, base)
    gu, gb = mean(goal_tv, pairs), mean(goal_tv, base)
    eye = sum(1 for a, b in pairs
              if any(t(a) != t(b) for _, t in GLANCE)) / len(pairs)
    dead = 1 - len(live) / SEEDS
    dtr = {t: statistics.mean(b.traits[t] - a.traits[t] for a, b in pairs)
           for t in sim.TRAITS}
    return {"hu": hu, "hb": hb, "hr": hu / hb if hb else 0,
            "gu": gu, "gb": gb, "gr": gu / gb if gb else 0,
            "eye": eye, "dead": dead, "traits": dtr, "n": len(pairs)}


def main():
    print("=" * 88)
    print(f" 环境实验   同一颗种子，不同的世界   {SEEDS} 颗种子 × {DAYS} 天")
    print("=" * 88)
    print("  同一个 Agent、同样的初始性格、同样的投喂频率，只有世界不同。\n")

    print(f"  {pad('对比', 22)}{pad('作息 TV', 10, True)}{pad('基线', 8, True)}"
          f"{pad('比值', 8, True)}{pad('目标 TV', 10, True)}{pad('基线', 8, True)}"
          f"{pad('比值', 8, True)}{pad('一眼可辨', 11, True)}{pad('死亡', 8, True)}")
    print("  " + "-" * 84)

    cache = {}
    rows = []
    for a, b in PAIRS + [FEED_PAIR]:
        r = compare(a, b, cache)
        if r is None:
            print(f"  {pad(a + '↔' + b, 22)}  —— 全灭")
            continue
        rows.append(((a, b), r))
        tag = "  ← 老轴（投喂）" if (a, b) == FEED_PAIR else ""
        mark = "" if r["hr"] <= 1.0 else "  ★"
        print(f"  {pad(a + '↔' + b, 22)}{pad(f'{r['hu']:.3f}', 10, True)}"
              f"{pad(f'{r['hb']:.3f}', 8, True)}{pad(f'{r['hr']:.2f}', 8, True)}"
              f"{pad(f'{r['gu']:.3f}', 10, True)}{pad(f'{r['gb']:.3f}', 8, True)}"
              f"{pad(f'{r['gr']:.2f}', 8, True)}"
              f"{pad(f'{r['eye']:.1%}', 11, True)}{pad(f'{r['dead']:.1%}', 8, True)}"
              f"{mark}{tag}")

    print("\n  读法：")
    print("    作息 TV   逐时辰的动作分布差异。比值 > 1 才说明环境比种子更有力")
    print("    目标 TV   一生中各种目标占的天数差异 —— goal 层带来的新载体")
    print("    ★         比值 > 1 的行")

    # --- 性格层面：哪个环境把它推向哪里 ---
    print("\n" + "=" * 88)
    print(" 性格差（后者 − 前者）")
    print("=" * 88)
    print(f"  {pad('对比', 22)}" + "".join(pad(t, 13, True) for t in sim.TRAITS))
    for (a, b), r in rows:
        print(f"  {pad(a + '↔' + b, 22)}"
              + "".join(pad(f"{r['traits'][t]:+.1f}", 13, True) for t in sim.TRAITS))

    # --- demo 素材：一对差异最大的 ---
    print("\n" + "=" * 88)
    print(" demo 素材：同一颗种子，两个世界，各自过成了什么样")
    print("=" * 88)
    best = max(rows, key=lambda r: r[1]["hr"])
    (na, nb), _ = best
    A, B = cache[na], cache[nb]
    cand = [(hourly_tv(a, b), a, b) for a, b in zip(A, B) if a.alive and b.alive]
    _, a, b = max(cand, key=lambda x: x[0])
    for agent, name in ((a, na), (b, nb)):
        gp = goal_profile(agent)
        top = sorted(gp.items(), key=lambda x: -x[1])[:2]
        print(f"\n▸ 世界：{name}")
        print(f"    性格   谨慎 {agent.traits['caution']:.0f} | "
              f"好奇 {agent.traits['curiosity']:.0f} | "
              f"勤劳 {agent.traits['industry']:.0f}   ({agent.dominant_style()})")
        print(f"    状态   住所 {agent.shelter:.0f}  体质 {agent.condition:.0f}  "
              f"存粮 {agent.inventory['food']:.0f}")
        print(f"    一生在追求  " +
              "、".join(f"{sim.GOAL_LABEL[g]}({p:.0%})" for g, p in top if p))
        print(f"    完成过 {sum(1 for g in agent.goal_history if g['outcome'] == 'done')} 件事，"
              f"半途放弃 {sum(1 for g in agent.goal_history if g['outcome'] == 'stalled')} 件")
        if agent.knowledge:
            print("    它学到的：" + "；".join(agent.knowledge.values()))
        big = [m for m in agent.memories if m["importance"] >= 0.7][:3]
        for m in big:
            print(f"      · 第 {m['day'] + 1} 天，{m['text']}")


if __name__ == "__main__":
    main()
