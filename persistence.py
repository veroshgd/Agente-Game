"""
持久性 —— 把因去掉之后，哪个环境因素还留得住？
================================================

运行：  python persistence.py

`transplant.py` 证明了组合世界（丰富↔贫瘠）的差异在移植后保留 91%。
这个脚本把那个组合**拆成单因素**，逐个问同一个问题：

    第 0–29 天   世界 A / 世界 B      ← 造成差异
    第 30–59 天  两边都换成「基准」    ← 把因去掉
    只在后 30 天的窗口上测量

★ 主指标是【持久性】，不是【当下差异】★
一个只在"当前条件不同"时才存在的差异，是温度计不是性格。
产品要的那句「以前有一次下很大的雨…从那以后我就不太喜欢没有准备」
要求的是移植后**仍然**存在。

★ 要验的机制假设 ★
一个因素能不能留下来，取决于它**有没有写进持久结构**：

    knowledge（语义记忆）  ·  trait_identity（永久身份）  ·  flags（关键经历）

预测：书 > 天气 > 材料 > 食物速率。
书会写进 knowledge（"书里有我没见过的世界"）并生成 `learn` 目标；
食物再生速率不写进任何持久结构，它只是当下的资源水位。
如果这个预测成立，就说明**持久性来自结构，不来自强度**。
"""

import statistics
from collections import Counter

import sim
import scenarios
from behavior import ACTIONS, GLANCE
from transplant import run_phased, window_tv, SPLIT, TOTAL
from paired import pad

SEEDS = 150
COMMON = "基准"

# 单因素对 + 组合作为参照
FACTORS = [
    ("有书",     COMMON,     "书"),
    ("有音乐",   COMMON,     "音乐"),
    ("常下雨",   "天气稳定", "天气"),
    ("材料丰富", "材料稀缺", "材料"),
    ("食物丰富", "食物贫瘠", "食物速率"),
    ("丰富世界", "贫瘠世界", "组合（参照）"),
]

GOAL_TYPES = list(sim.GOAL_ACTIONS)


def goal_profile_window(agent):
    """★目标层★ 只看窗口内每天在追求什么。

    这是 018 发现的最强载体：目标 TV 的比值普遍高于作息 TV，
    而且它可以直接讲成一句话（"它这半个月都在囤粮"），
    也是 LLM 接进来时最自然的接口。
    """
    days = [g for g in agent.goal_by_day[SPLIT:TOTAL] if g]
    n = len(days) or 1
    return {g: days.count(g) / n for g in GOAL_TYPES}


def goal_tv(a, b):
    pa, pb = goal_profile_window(a), goal_profile_window(b)
    return 0.5 * sum(abs(pa[g] - pb[g]) for g in GOAL_TYPES)


_COHORT_CACHE = {}


def cohort(first, second, seeds):
    """★带缓存★ 六个因素 × 四个 cohort，基准世界会被重复算很多遍。
    后面要跑 120 天和多方向还原，这个开销会变得难受。"""
    key = (first, second, len(seeds))
    if key not in _COHORT_CACHE:
        _COHORT_CACHE[key] = [run_phased(s, first, second) for s in seeds]
    return _COHORT_CACHE[key]


def measure(cohA, cohB, seeds):
    """返回作息比值、目标比值、以及持久结构的差异"""
    live = [i for i, (a, b) in enumerate(zip(cohA, cohB))
            if a[0] is not None and b[0] is not None]
    if len(live) < 20:
        return None
    pairs = [(cohA[i], cohB[i]) for i in live]

    # 基线只用两边都活下来的种子 —— 否则筛选过的组内方差偏小，比值虚高
    base = []
    for coh in (cohA, cohB):
        al = [coh[i] for i in live]
        base += [(al[j], al[j + 1]) for j in range(0, len(al) - 1, 2)]

    hu = statistics.mean(window_tv(a[1], b[1]) for a, b in pairs)
    hb = statistics.mean(window_tv(a[1], b[1]) for a, b in base)
    gu = statistics.mean(goal_tv(a[0], b[0]) for a, b in pairs)
    gb = statistics.mean(goal_tv(a[0], b[0]) for a, b in base)

    # 持久结构：这个因素在球身上留下了什么？
    # ⚠ 第一版算的是 len(b) - len(a)，那是"B 比 A 多几条"，不是"两边不一样"。
    #    两只球各有 3 条**完全不同**的 knowledge，差值会算成 0 —— 系统性低估。
    #    改成集合的对称差（有多少条只有一边有）。
    def keys(agent):
        return (set(agent.knowledge),
                {t for t, v in agent.trait_identity.items() if v > 0},
                set(agent.flags))

    def symdiff(i):
        return statistics.mean(len(keys(a[0])[i] ^ keys(b[0])[i])
                               for a, b in pairs)

    dk, di, df = symdiff(0), symdiff(1), symdiff(2)

    return {
        "hr": hu / hb if hb else 0.0, "gr": gu / gb if gb else 0.0,
        "n": len(pairs), "dead": 1 - len(pairs) / len(cohA),
        "dk": dk, "di": di, "df": df,
        "traits": {t: statistics.mean(b[0].traits[t] - a[0].traits[t]
                                      for a, b in pairs) for t in sim.TRAITS},
    }


def main():
    seeds = list(range(SEEDS))
    print("=" * 100)
    print(f" 持久性实验   {SEEDS} 颗种子   第 0–{SPLIT-1} 天分化，"
          f"第 {SPLIT}–{TOTAL-1} 天在【基准世界】里测量")
    print("=" * 100)
    print("  「持续」= 后半生留在原世界（因还在）   "
          "「移植」= 后半生两边都换成基准（因去掉）")
    print(f"\n  {pad('因素', 14)}{pad('持续 作息', 11, True)}{pad('移植 作息', 11, True)}"
          f"{pad('保留', 8, True)}{pad('持续 目标', 11, True)}"
          f"{pad('移植 目标', 11, True)}{pad('保留', 8, True)}{pad('死亡', 8, True)}")
    print("  " + "-" * 84)

    rows = []
    for wa, wb, label in FACTORS:
        stay = measure(cohort(wa, wa, seeds), cohort(wb, wb, seeds), seeds)
        move = measure(cohort(wa, COMMON, seeds), cohort(wb, COMMON, seeds), seeds)
        if stay is None or move is None:
            print(f"  {pad(label, 14)}  —— 样本不足")
            continue
        keep_h = move["hr"] / stay["hr"] if stay["hr"] else 0
        keep_g = move["gr"] / stay["gr"] if stay["gr"] else 0
        rows.append((label, stay, move, keep_h, keep_g))
        star = "  ★" if move["hr"] >= 1.0 or move["gr"] >= 1.0 else ""
        print(f"  {pad(label, 14)}{pad(f'{stay['hr']:.2f}', 11, True)}"
              f"{pad(f'{move['hr']:.2f}', 11, True)}{pad(f'{keep_h:.0%}', 8, True)}"
              f"{pad(f'{stay['gr']:.2f}', 11, True)}{pad(f'{move['gr']:.2f}', 11, True)}"
              f"{pad(f'{keep_g:.0%}', 8, True)}"
              f"{pad(f'{move['dead']:.1%}', 8, True)}{star}")

    print("\n  ★ = 移植后比值仍 ≥ 1，也就是把因去掉之后差异还站得住")

    # --- 机制：留得住的因素，是不是写进了持久结构？ ---
    print("\n" + "=" * 100)
    print(" 机制检验：留得住的因素，有没有写进持久结构？")
    print("=" * 100)
    print(f"  {pad('因素', 14)}{pad('移植后作息', 12, True)}{pad('移植后目标', 12, True)}"
          f"{pad('语义记忆差', 12, True)}{pad('永久身份差', 12, True)}"
          f"{pad('关键经历差', 12, True)}")
    for label, stay, move, kh, kg in rows:
        print(f"  {pad(label, 14)}{pad(f'{move['hr']:.2f}', 12, True)}"
              f"{pad(f'{move['gr']:.2f}', 12, True)}"
              f"{pad(f'{move['dk']:.2f}', 12, True)}"
              f"{pad(f'{move['di']:.2f}', 12, True)}"
              f"{pad(f'{move['df']:.2f}', 12, True)}")
    print("\n  三列都是【对称差】：平均有几条只存在于其中一边（越大越不一样）")
    print("  语义记忆 = knowledge 键   永久身份 = trait_identity 非零维度   "
          "关键经历 = flags")
    print("  假设：写进这三列的因素才留得住；只改资源水位的因素留不住。")
    print("  ⚠ 但 knowledge 和 memories 目前【不进 score()】，是只写不读的，")
    print("     所以第一列大不代表行为上留得住 —— 见实验 019 规则 30。")

    # --- 还原相跑三个方向 ---
    # ⚠ 「基准」不是中立的：它的 objects 是空的，在"有没有书"这件事上
    #    它等于贫瘠世界。丰富分身移植过去会**失去书**，`learn` 整条目标通路
    #    被砍掉；贫瘠分身什么都没失去。这是不对称的适应成本，会混进结果里。
    #    所以还原相至少要跑三个方向。
    print("\n" + "=" * 100)
    print(" 还原相的方向依赖：移植到不同的世界，结论一样吗")
    print("=" * 100)
    print(f"  {pad('因素', 14)}" + "".join(pad(f"→{d}", 14, True)
                                            for d in ("基准", "丰富世界", "贫瘠世界")))
    for wa, wb, label in FACTORS:
        cells = ""
        for dest in ("基准", "丰富世界", "贫瘠世界"):
            m = measure(cohort(wa, dest, seeds), cohort(wb, dest, seeds), seeds)
            cells += pad(f"{m['hr']:.2f}" if m else "—", 14, True)
        print(f"  {pad(label, 14)}{cells}")
    print("\n  方向之间差很多 → 测到的东西里混着「移植过去要重新适应」的成本，")
    print("  不是纯粹的持久性。三个方向都 ≥1 才叫稳。")

    # --- 性格残留 ---
    print("\n" + "=" * 100)
    print(" 移植 30 天后仍然存在的性格差（后 − 前）")
    print("=" * 100)
    print(f"  {pad('因素', 14)}" + "".join(pad(t, 13, True) for t in sim.TRAITS))
    for label, stay, move, kh, kg in rows:
        print(f"  {pad(label, 14)}"
              + "".join(pad(f"{move['traits'][t]:+.1f}", 13, True)
                        for t in sim.TRAITS))


if __name__ == "__main__":
    main()
