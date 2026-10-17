"""
行为层指标 —— 用户造成的差异，看得见吗
========================================

运行：  python behavior.py

为什么需要这个脚本
------------------
消融实验（014）暴露了一个盲区：把 `PERSONALITY_WEIGHT` 设成 0，
性格数值就**完全不影响行为**了——可是 industry dz 只掉了 4%。

    → 说明我们所有的指标量的都是"一个数字的差异"，
      没有一个在量"行为的差异"。

而用户看到的是行为。[[设计要点与风险]] §5.5 说得很清楚：
"两只球谨慎度 78 vs 45，如果外在行为看起来一样，用户感知不到。"

这个脚本就是补上那一层。

三个指标
--------
1. **动作分布的总变差距离 TV** —— 两只球把时间花在不同事情上的比例。
   TV ∈ [0,1]，可以直接读成"作息有百分之多少不一样"。

2. **作息差异** —— 一天 24 个时辰里，有几个时辰的主导动作不同。
   这是 §5.5 点名要的"每天作息"，也是最好的 demo 素材。

3. **一眼可辨特征** —— 有家 / 看着瘦 / 有存粮 / 常出门。
   这才是用户真正能"看见"的东西。

★ 噪声地板（规则 9：新指标必须先测噪声地板）
-------------------------------------------
TV 恒为正，所以不能用符号置换。这里的正确对照是：

    TV_user  = 同一颗种子，不同用户        ← 用户造成的行为差异
    TV_base  = 同一种用户，不同种子        ← 两只球本来就有的差异

**TV_user 必须明显高过 TV_base**，否则"我的球跟别人不一样"
和"球本来就各不相同"就无法区分——那用户还是不会觉得是自己养的。

用两组独立样本的置换检验比较两者。
"""

import random
import statistics

import sim
import scenarios
from paired import pad

SEEDS = 300
DAYS = 30
N_PERM = 2000
A_NAME, B_NAME = "溺爱型", "放养型"

ACTIONS = list(sim.ACTION_TRAIT_MATCH)
GLYPH = {"eat": "食", "sleep": "睡", "gather_food": "采",
         "gather_material": "拾", "build": "建", "explore": "探", "read": "读"}

# 一眼可辨的特征 —— 用户真正能看见的东西
GLANCE = [
    ("有像样的家", lambda a: a.shelter >= 50),
    ("看着还健康", lambda a: a.condition >= 90),
    ("有存粮",     lambda a: a.inventory["food"] >= 3),
    ("常出门",     lambda a: profile(a)["explore"] >= 0.20),
]


GOAL_TYPES = list(sim.GOAL_ACTIONS)


def profile(agent):
    """动作分布（归一化）"""
    tot = sum(agent.action_log.values()) or 1
    return {a: agent.action_log[a] / tot for a in ACTIONS}


def goal_profile(agent):
    """★主载体★ 一生中每种目标各占多少天。

    为什么是主载体（实验 019）：
      · 比作息强 —— 投喂轴上作息比值 0.72，目标比值 1.79
      · 可归因 —— goal 带着 `created_from`，能追到是哪段经历生成的
      · 可讲成一句话 —— "它这半个月都在囤粮"，作息分布讲不出这种话
      · 是 LLM 接进来时最自然的接口（context_packet 就是围着它组的）
    """
    days = [g for g in agent.goal_by_day if g]
    n = len(days) or 1
    return {g: days.count(g) / n for g in GOAL_TYPES}


def goal_tv(a, b):
    pa, pb = goal_profile(a), goal_profile(b)
    return 0.5 * sum(abs(pa[g] - pb[g]) for g in GOAL_TYPES)


def tv(p, q):
    """总变差距离。0 = 作息完全一样，1 = 完全不重叠"""
    return 0.5 * sum(abs(p[a] - q[a]) for a in ACTIONS)


def rhythm(agent):
    """一天 24 个时辰各自的主导动作。★只用于打印 demo，不要用来当指标★"""
    return [c.most_common(1)[0][0] if c else None for c in agent.action_by_hour]


def rhythm_diff(a, b):
    """主导动作不同的时辰数。
    ⚠ 这个指标不可靠，保留只为对照。见 mode_margin() 的说明。"""
    ra, rb = rhythm(a), rhythm(b)
    return sum(1 for x, y in zip(ra, rb) if x != y)


def mode_margin(agent):
    """每个时辰里，头号动作领先第二名多少（占比之差）。

    ★为什么要有这个函数★
    实验 016 之后 rhythm_diff 从 5.05 暴涨到 10.58，看起来像行为差异变大了。
    其实是这个 margin 从 0.40 塌到 0.16 —— 球开始在几个动作之间来回穿插，
    头号动作只领先第二名 16 个百分点，于是极小的扰动就能把"主导动作"翻面。
    **rhythm_diff 涨的是模态的脆弱性，不是行为的差异。**
    证据：基线同步从 7.73 涨到 13.88，比值几乎没动。
    """
    ms = []
    for c in agent.action_by_hour:
        tot = sum(c.values()) or 1
        t2 = c.most_common(2)
        ms.append(1.0 if len(t2) < 2 else (t2[0][1] - t2[1][1]) / tot)
    return statistics.mean(ms)


def hour_profile(agent):
    """每个时辰各自的动作分布"""
    out = []
    for c in agent.action_by_hour:
        tot = sum(c.values()) or 1
        out.append({a: c[a] / tot for a in ACTIONS})
    return out


def hourly_tv(a, b):
    """★作息差异的正确度量★ 逐时辰比较分布，再平均。

    比 TV 聚合版严格更敏感（聚合只会缩小距离，凸性），
    又没有"主导动作"那种翻面的脆弱性。
    """
    pa, pb = hour_profile(a), hour_profile(b)
    return sum(0.5 * sum(abs(pa[h][x] - pb[h][x]) for x in ACTIONS)
               for h in range(len(pa))) / len(pa)


def perm_diff_p(g1, g2, n_perm, rng):
    """两组独立样本：均值差有多少可能是随机分组造成的"""
    obs = abs(statistics.mean(g1) - statistics.mean(g2))
    pool = list(g1) + list(g2)
    n1 = len(g1)
    hits = 0
    for _ in range(n_perm):
        rng.shuffle(pool)
        if abs(statistics.mean(pool[:n1]) - statistics.mean(pool[n1:])) >= obs:
            hits += 1
    return hits / n_perm


def main():
    rng = random.Random(0)
    sim.SIM_DAYS = DAYS
    print("=" * 78)
    print(f" 行为层指标   {SEEDS} 颗种子 × {DAYS} 天   配对：{A_NAME} → {B_NAME}")
    print("=" * 78)

    world = {(s, arch): scenarios.run(s, arch)
             for s in range(SEEDS) for arch in scenarios.FEEDING}

    # 用户造成的行为差异：同种子，不同用户
    pairs = [(world[(s, A_NAME)], world[(s, B_NAME)]) for s in range(SEEDS)
             if world[(s, A_NAME)].alive and world[(s, B_NAME)].alive]
    tv_user = [tv(profile(a), profile(b)) for a, b in pairs]

    # 基线：同一种用户，不同种子。两个都算——溺爱型可能天然更同质
    base = {}
    for arch in (A_NAME, B_NAME):
        alive = [world[(s, arch)] for s in range(SEEDS) if world[(s, arch)].alive]
        base[arch] = [tv(profile(alive[i]), profile(alive[i + 1]))
                      for i in range(0, len(alive) - 1, 2)]

    print(f"\n【1. 动作分布的总变差距离】{len(pairs)} 对")
    print(f"  {pad('比较', 30)}{pad('TV 均值', 10, True)}"
          f"{pad('中位数', 10, True)}{pad('n', 7, True)}")
    print("  " + "-" * 55)
    print(f"  {pad('用户造成（同种子，换用户）', 30)}"
          f"{pad(f'{statistics.mean(tv_user):.3f}', 10, True)}"
          f"{pad(f'{statistics.median(tv_user):.3f}', 10, True)}"
          f"{pad(len(tv_user), 7, True)}")
    for arch, vals in base.items():
        print(f"  {pad(f'基线（同为{arch}，换种子）', 30)}"
              f"{pad(f'{statistics.mean(vals):.3f}', 10, True)}"
              f"{pad(f'{statistics.median(vals):.3f}', 10, True)}"
              f"{pad(len(vals), 7, True)}")

    pooled_base = base[A_NAME] + base[B_NAME]
    ratio = statistics.mean(tv_user) / statistics.mean(pooled_base) \
        if statistics.mean(pooled_base) else float("inf")
    p = perm_diff_p(tv_user, pooled_base, N_PERM, rng)
    print(f"\n  用户 / 基线 = {ratio:.2f}×      置换检验 p = {p:.3f}")
    if ratio < 1.2:
        print("  ✗ 用户造成的行为差异，并不比两只球本来就有的差异更大")
        print("    → 用户感知不到这是自己养出来的")
    elif p < 0.05:
        print("  ✓ 用户造成的行为差异显著大于基线")

    # 哪些行为在变
    print("\n【动作层面：时间从哪里流到哪里】（放养型 − 溺爱型）")
    for act in ACTIONS:
        d = [profile(b)[act] - profile(a)[act] for a, b in pairs]
        m = statistics.mean(d)
        bar = ("+" if m >= 0 else "-") * min(30, int(abs(m) * 300))
        print(f"  {pad(act, 18)}{pad(f'{m:+.1%}', 9, True)}  {bar}")

    # 2. 作息 —— 逐时辰比分布，不比"主导动作"
    print("\n【2. 作息差异】逐时辰的动作分布，再平均")
    base_pairs = []
    for arch in (A_NAME, B_NAME):
        al = [world[(s, arch)] for s in range(SEEDS) if world[(s, arch)].alive]
        base_pairs += [(al[i], al[i + 1]) for i in range(0, len(al) - 1, 2)]
    hu = [hourly_tv(a, b) for a, b in pairs]
    hb = [hourly_tv(a, b) for a, b in base_pairs]
    print(f"  用户造成 TV(逐时辰)   {statistics.mean(hu):.3f}")
    print(f"  基线                  {statistics.mean(hb):.3f}"
          f"      比值 {statistics.mean(hu) / statistics.mean(hb):.2f}×")
    margin = statistics.mean(mode_margin(world[(s, A_NAME)]) for s in range(SEEDS))
    print(f"\n  （对照）主导动作不同的时辰   用户 "
          f"{statistics.mean(rhythm_diff(a, b) for a, b in pairs):5.2f}/24   "
          f"基线 {statistics.mean(rhythm_diff(a, b) for a, b in base_pairs):5.2f}/24")
    print(f"  ⚠ 上面这行不要单独看：主导动作的领先优势只有 {margin:.2f}，"
          f"模态很容易翻面")
    print(f"    实验 016 里它从 5.05 涨到 10.58，但基线同步从 7.73 涨到 13.88 "
          f"—— 涨的是脆弱性，不是差异")

    # ★主载体★ 目标层
    print("\n【★ 主载体：目标层】一生中各种目标占的天数")
    gu = [goal_tv(a, b) for a, b in pairs]
    gb = [goal_tv(a, b) for a, b in base_pairs]
    gr = statistics.mean(gu) / statistics.mean(gb) if statistics.mean(gb) else 0
    print(f"  用户造成 {statistics.mean(gu):.3f}   基线 {statistics.mean(gb):.3f}"
          f"   比值 {gr:.2f}×")
    if gr >= 1.0:
        print("  ✓ 目标层上，用户造成的差异【超过】了球本来就有的差异")
    print(f"  {pad('目标', 18)}{pad(f'{A_NAME}占比', 12, True)}"
          f"{pad(f'{B_NAME}占比', 12, True)}{pad('差', 9, True)}")
    for g in GOAL_TYPES:
        pa = statistics.mean(goal_profile(a)[g] for a, _ in pairs)
        pb = statistics.mean(goal_profile(b)[g] for _, b in pairs)
        print(f"  {pad(sim.GOAL_LABEL[g], 18)}{pad(f'{pa:.1%}', 12, True)}"
              f"{pad(f'{pb:.1%}', 12, True)}{pad(f'{pb - pa:+.1%}', 9, True)}")

    # 3. 一眼可辨
    print("\n【3. 一眼可辨的特征】只有一边成立的配对")
    print(f"  {pad('特征', 16)}{pad(f'只有{B_NAME}', 14, True)}"
          f"{pad(f'只有{A_NAME}', 14, True)}{pad('不一致率', 12, True)}")
    for label, test in GLANCE:
        only_b = sum(1 for a, b in pairs if test(b) and not test(a))
        only_a = sum(1 for a, b in pairs if test(a) and not test(b))
        print(f"  {pad(label, 16)}{pad(only_b, 14, True)}{pad(only_a, 14, True)}"
              f"{pad(f'{(only_a + only_b) / len(pairs):.1%}', 12, True)}")
    any_diff = sum(1 for a, b in pairs
                   if any(t(a) != t(b) for _, t in GLANCE)) / len(pairs)
    print(f"\n  ★ 至少一个特征不同的配对：{any_diff:.1%}      目标 > 60%")
    print("    这是用户不看任何数字、只是瞄一眼就能察觉差别的比例。")

    # demo 素材：挑一对差异最大的，把作息打出来
    print("\n" + "=" * 78)
    print(" demo 素材：同一颗种子，两个用户，一天的作息")
    print("=" * 78)
    idx = max(range(len(pairs)), key=lambda i: tv_user[i])
    a, b = pairs[idx]
    print(f"  时辰       " + "".join(f"{h:>2}" for h in range(24)))
    for agent, name in ((a, A_NAME), (b, B_NAME)):
        line = "".join(GLYPH.get(x, "·") for x in rhythm(agent))
        print(f"  {pad(name, 10)} {line}")
    print(f"\n  {pad(A_NAME, 10)} {a.dominant_style()}   "
          f"住所 {a.shelter:.0f}  体质 {a.condition:.0f}  "
          f"勤劳 {a.traits['industry']:.0f}")
    print(f"  {pad(B_NAME, 10)} {b.dominant_style()}   "
          f"住所 {b.shelter:.0f}  体质 {b.condition:.0f}  "
          f"勤劳 {b.traits['industry']:.0f}")
    for agent, name in ((a, A_NAME), (b, B_NAME)):
        if agent.landmarks:
            print(f"  {name} 记得：" +
                  "；".join(f"第 {d + 1} 天{t}" for d, t in agent.landmarks))
    print("\n  图例：" + "  ".join(f"{v}={k}" for k, v in GLYPH.items()))


if __name__ == "__main__":
    main()
