"""
v3 novel-probe capacity audit —— 用同一套资格标准扫所有现有通道
=================================================================

运行：  python novel_capacity_audit.py --seeds 300

★ 为什么做这个 ★
三个 probe 连续失败，每次原因不同：
  Probe A 冻土     → 生存分裂（规则 64：动食物只能压出生死差异）
  Probe B 盐碱地   → 生存分裂（同上，方向相反）
  Probe A2 探路    → 乘性加成落空（规则 68：77% 的球从不采集，乘的是 0）

**再凭感觉找第四个 probe 没有意义。** 改成：把 v3 现有的行为通道
全部用**同一套资格标准**扫一遍，看有没有任何一个通道够格。

★ 资格标准（六条，全过才算够格）★
  Q1 近乎全员可参与    参与率 ≥ 70%                （规则 68）
  Q2 个体差异足够      跨个体 p90−p10 ≥ 0.10        （规则 66）
  Q3 确实是紧约束      ≥ 20% 的个体真的被它限制住    （规则 68 的另一半）
  Q4 不决定生死        操纵它不改变存活              （规则 65）
  Q5 有回读通路        进入 score() / goal，行为才可能变（反应式通路）
  Q6 两世界同等可及    发育期两边都有该可供性         （规则 67）

Q1–Q3 实测；Q4–Q6 由代码结构判定（在 CHANNELS 里逐条注明依据）。

★ group-blind ★ 只输出 pooled 量与跨个体方差。种子 `20000+`。
**不碰 `60000–61499`。**

★ 结论怎么用 ★
- 有通道全过 → 那就是第四个 probe 该建的地方
- **一个都不过 → 026 以「v3 不具备可干净检验 generalization 的动作经济」封存**，
  并且 v4 的设计目标随之变得非常明确：不是"让模型更复杂"，
  而是补上这三轮暴露的缺口 —— **至少一个不决定生死、近乎全员可参与、
  具有多种有效策略、并允许 agent 对新 contingency 产生行为适应的经济。**
"""

import argparse
import multiprocessing as mp
import os
import statistics
from collections import Counter

WA, WB, COMMON = "丰富世界", "贫瘠世界", "基准"
DEV_DAYS, OBS_DAYS = 30, 30
CHUNK = 25

# (通道, Q4 不决定生死?, Q5 有回读通路?, Q6 两世界同等可及?, 依据)
STRUCTURAL = {
    "sleep / energy": (
        False, True, True,
        "energy 经 SLEEP_EFF_FLOOR 与 condition 相连 → 触及生死通路（Q4 存疑，需拍板）"),
    "explore / 非食物产出": (
        True, True, True,
        "flag/knowledge/性状反馈进 score()；两世界都能 explore"),
    "material / build": (
        True, True, True,
        "inventory 进目标进度；两世界都有 material_yield（2.0 vs 0.5）"),
    "goal 结构": (
        True, True, True,
        "goal 直接进 score()；两世界共用同一套 GOAL_ACTIONS"),
    "knowledge": (
        True, True, True,
        "022 已接入 score()；但书只在丰富世界 → 见下方 Q6 实测"),
    "shelter / storm": (
        False, True, True,
        "shelter 低 → condition 受损通路；storm_chance 两世界不同(0.02/0.1)"),
    "objects / 动作合法性": (
        True, True, False,
        "★Q6 不过★ read 需要 book，book 只在丰富世界 → 不是对两组同等新颖"),
}


def task(job):
    world, seed0, n = job
    import novel_situation as NS
    sim = NS.sim
    sim.COND_RECOVER_AT = 65.0
    sim.COND_DEADZONE_RECOVER = sim.COND_SHELTER_RECOVER = 0.0
    sim.SLEEP_SUPPRESS = sim.HUNGER_URGENCY = 0.0
    sim.SLEEP_EFF_FLOOR = 0.35
    sim.KNOWLEDGE_WEIGHT, sim.KNOWLEDGE_GOAL_WEIGHT, sim.KNOWLEDGE_FORGET = 12.0, 0.25, 0.02

    out = []
    for s in range(seed0, seed0 + n):
        life = NS.scenarios.make(s, world)
        ok, _ = NS.run_window(life, 0, DEV_DAYS)
        if not ok:
            continue
        NS.level_state(life.agent)
        c = NS.fork(life, False)
        w = sim.World(s, **NS.scenarios.WORLDS[COMMON])
        lo_energy = [0]

        alive, win = NS.run_window(c, DEV_DAYS, OBS_DAYS, world=w)
        ag = c.agent
        acc = Counter()
        for h in win:
            acc.update(h)
        tot = sum(acc.values()) or 1
        goals = [g for g in ag.goal_by_day[DEV_DAYS:] if g]
        gc = Counter(goals)
        out.append({
            "sleep": acc["sleep"] / tot,
            "explore": acc["explore"] / tot,
            "gather_material": acc["gather_material"] / tot,
            "build": acc["build"] / tot,
            "read": acc["read"] / tot,
            "energy_end": ag.energy,
            "material_end": ag.inventory["material"],
            "shelter_end": ag.shelter,
            "n_flags": len(ag.flags),
            "has_explore_flag": int("loves_exploring" in ag.flags),
            "n_knowledge": len(ag.knowledge),
            "n_goal_kinds": len(gc),
            "top_goal_share": (max(gc.values()) / len(goals)) if goals else 0.0,
            "alive": alive,
        })
    return out


def _dispatch(j):
    return task(j[1])


def spread(vals):
    v = sorted(vals)
    return v[int(.90 * len(v))] - v[int(.10 * len(v))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=300)
    ap.add_argument("--seed0", type=int, default=20000)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    a = ap.parse_args()

    jobs = [(task, (w, s0, min(CHUNK, a.seed0 + a.seeds - s0)))
            for w in (WA, WB) for s0 in range(a.seed0, a.seed0 + a.seeds, CHUNK)]
    pool = []
    with mp.Pool(a.workers) as p:
        for recs in p.imap_unordered(_dispatch, jobs):
            pool.extend(recs)
    if not pool:
        raise SystemExit("✗ 池子为空 —— 故障")
    n = len(pool)

    def frac(f):
        return sum(1 for r in pool if f(r)) / n

    # ── 各通道的 Q1 参与率 / Q2 个体方差 / Q3 紧约束 ──
    meas = {
        "sleep / energy": (
            frac(lambda r: r["sleep"] > 0),
            spread([r["sleep"] for r in pool]),
            frac(lambda r: r["energy_end"] < 30),          # 被精力限制住
            "energy<30 的比例"),
        "explore / 非食物产出": (
            frac(lambda r: r["explore"] > 0),
            spread([r["explore"] for r in pool]),
            1 - frac(lambda r: r["has_explore_flag"]),     # 信息产出未饱和的比例
            "未拿到 loves_exploring 的比例"),
        "material / build": (
            frac(lambda r: r["gather_material"] > 0),
            spread([r["gather_material"] for r in pool]),
            frac(lambda r: r["material_end"] < 3),         # 买不起一次 build
            "材料<3 的比例"),
        "goal 结构": (
            frac(lambda r: r["n_goal_kinds"] >= 2),
            spread([r["top_goal_share"] for r in pool]),
            frac(lambda r: r["top_goal_share"] < 0.9),     # 没被单一目标垄断
            "主目标占比<0.9 的比例"),
        "knowledge": (
            frac(lambda r: r["n_knowledge"] > 0),
            spread([r["n_knowledge"] / 6.0 for r in pool]),
            frac(lambda r: r["n_knowledge"] < 4),
            "knowledge 条数<4 的比例"),
        "shelter / storm": (
            1.0,
            spread([r["shelter_end"] / 100.0 for r in pool]),
            frac(lambda r: r["shelter_end"] < 50),
            "shelter<50 的比例"),
        "objects / 动作合法性": (
            frac(lambda r: r["read"] > 0),
            spread([r["read"] for r in pool]),
            0.0,
            "基准世界无书 → 恒 0"),
    }

    print("=" * 112)
    print(f" v3 novel-probe capacity audit（group-blind）  common garden {OBS_DAYS} 天"
          f"  n={n}  存活 {frac(lambda r: r['alive']):.1%}")
    print("=" * 112)
    print(f"  {'通道':<22}{'Q1参与率':>9}{'Q2方差':>9}{'Q3紧约束':>10}"
          f"{'Q4非生死':>10}{'Q5回读':>8}{'Q6同等':>8}{'资格':>8}")
    print("  " + "-" * 108)

    passed = []
    for ch, (q1, q2, q3, q3name) in meas.items():
        q4, q5, q6, why = STRUCTURAL[ch]
        ok1, ok2, ok3 = q1 >= 0.70, q2 >= 0.10, q3 >= 0.20
        ok = all([ok1, ok2, ok3, q4, q5, q6])
        mark = lambda b: "✓" if b else "✗"
        print(f"  {ch:<22}{q1:>8.1%}{mark(ok1)}{q2:>8.3f}{mark(ok2)}"
              f"{q3:>9.1%}{mark(ok3)}{mark(q4):>9}{mark(q5):>8}{mark(q6):>8}"
              f"{'★够格' if ok else '不够格':>9}")
        if ok:
            passed.append(ch)

    print("\n  Q3 的具体口径：")
    for ch, (_, _, _, q3name) in meas.items():
        print(f"    {ch:<22} {q3name}")
    print("\n  Q4/Q5/Q6 的结构性依据：")
    for ch, (_, _, _, why) in STRUCTURAL.items():
        print(f"    {ch:<22} {why}")

    print("\n" + "=" * 112)
    if passed:
        print(f" ★ 够格的通道：{passed}")
        print(" → 第四个 probe 应当建在这里；继续 group-blind feasibility calibration。")
    else:
        print(" ✗ **没有任何通道通过全部六条资格标准。**")
        print("")
        print(" → 026 以此封存：**v3 不具备可干净检验 generalization 的动作经济。**")
        print("")
        print(" 这不是'又选错了战场'，而是三轮 group-blind feasibility testing")
        print(" 得出的结构性结论。v4 的设计目标随之变得非常明确 ——")
        print(" **不是让模型更复杂，而是补上 v3 被这三轮实验暴露的缺口：**")
        print("   至少一个【不决定生死】【近乎全员可参与】【具有多种有效策略】")
        print("   【并允许 agent 对新 contingency 产生行为适应】的经济。")
        print("")
        print(" ★ 方法论上的关键区别 ★")
        print("   升级 v4 不是为了'把论文结果调出来'，")
        print("   而是因为 group-blind feasibility testing 已经明确证明：")
        print("   frozen v3 缺少测量这个问题所需的自由度。")
    print("=" * 112)


if __name__ == "__main__":
    mp.freeze_support()
    main()
