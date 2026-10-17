"""
knowledge effective-support audit —— ★ group-blind ★ Probe D 的放行前提
========================================================================

运行：  python knowledge_support_audit.py --seeds 300

★ 沿用规则 70 的思想 ★
不问"变量看起来连不连续"，问 **"一个固定大小的外部 contingency 还能不能改变
决策"**。knowledge 分布是梯度的（99.7% 有 ≥1 条、87.8% 少于 4 条）——
但那只是"看起来连续"。真正要量的是**有效支撑**：

    score(action) += KNOWLEDGE_WEIGHT(12.0) × know(key) × slack     sim.py:835
    propose_goals: pri += KNOWLEDGE_GOAL_WEIGHT(0.25) × know(key)   sim.py:656

所以一个作用于 knowledge 的干预，其可动用的分数幅度上限就是 **12.0 × strength**。
它能不能改变行为，取决于**决策时刻 top1 与 top2 的分数间距（margin）**：

    margin < Δ  →  这次决策可以被 Δ 大小的干预翻转
    margin ≥ Δ  →  翻不动，干预静默失效（= 规则 70 说的饱和）

★ 放行条件（跑前冻结）★
存在某个可行的 Δ（≤ KNOWLEDGE_WEIGHT = 12.0），使得
**responsive population ∈ [20%, 80%]**
（responsive = 该 agent 至少 10% 的决策 tick 可被 Δ 翻转）。
找不到 → **Probe D 直接不做，026 封存。**

★ 排除 books ★（规则 67）书只在丰富世界 → 只统计 far_places / shelter / food。
★ group-blind ★ 只输出 pooled 量。种子 `20000+`。**不碰 `60000–61499`。**
"""

import argparse
import multiprocessing as mp
import os
import statistics
from collections import Counter

WA, WB, COMMON = "丰富世界", "贫瘠世界", "基准"
DEV_DAYS, OBS_DAYS = 30, 30
CHUNK = 25
KEYS = ("far_places", "shelter", "food")      # ★ 排除 books ★
DELTAS = (1.0, 3.0, 6.0, 12.0)                # 干预幅度候选，上限 = KNOWLEDGE_WEIGHT
RESP_MIN_FRAC = 0.10                          # 一个 agent 至少这么多决策可翻转才算 responsive
GATE_LO, GATE_HI = 0.20, 0.80                 # responsive population 的放行区间


def task(job):
    world, seed0, n = job
    import novel_situation as NS
    sim = NS.sim
    sim.COND_RECOVER_AT = 65.0
    sim.COND_DEADZONE_RECOVER = sim.COND_SHELTER_RECOVER = 0.0
    sim.SLEEP_SUPPRESS = sim.HUNGER_URGENCY = 0.0
    sim.SLEEP_EFF_FLOOR = 0.35
    sim.KNOWLEDGE_WEIGHT, sim.KNOWLEDGE_GOAL_WEIGHT, sim.KNOWLEDGE_FORGET = 12.0, 0.25, 0.02

    # ★ 只读探针：包住 score()，记录每次决策实际算出的分数 ★
    #   不额外调用 score()（那可能扰动随机流），只把真实决策的分数抄下来。
    if not hasattr(sim.Agent, "_score_patched"):
        _orig = sim.Agent.score

        def score(self, action, day):
            v = _orig(self, action, day)
            if v is not None:
                self._scores.append(v)
            return v
        sim.Agent.score = score
        sim.Agent._score_patched = True
        sim.Agent._scores = []

    out = []
    for s in range(seed0, seed0 + n):
        life = NS.scenarios.make(s, world)
        ok, _ = NS.run_window(life, 0, DEV_DAYS)
        if not ok:
            continue
        NS.level_state(life.agent)
        c = NS.fork(life, False)
        NS.enter_novel(c)
        w = NS.novel_world(s)
        c.world = w
        c.agent.world = w
        ag = c.agent

        margins, ks_trace = [], []
        for day in range(DEV_DAYS, DEV_DAYS + OBS_DAYS):
            for t in range(sim.TICKS_PER_DAY):
                w.tick(day, t)
                for inf in c.influences:
                    inf(w, ag, day, t, c.inf_rng)
                ag._scores = []
                ag.tick(day, t)
                sc = sorted(ag._scores, reverse=True)
                if len(sc) >= 2:
                    margins.append(sc[0] - sc[1])
                if not ag.alive:
                    break
            if not ag.alive:
                break
            ag.daily(day)
            ks_trace.append({k: ag.knowledge_strength.get(k, 0.0) for k in KEYS})

        out.append({
            "margins": margins,
            "ks_end": {k: ag.knowledge_strength.get(k, 0.0) for k in KEYS},
            "ks_mean": {k: statistics.mean([d[k] for d in ks_trace]) if ks_trace else 0.0
                        for k in KEYS},
            "alive": ag.alive,
        })
    return out


def _dispatch(j):
    return task(j[1])


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

    print("=" * 100)
    print(f" knowledge effective-support audit（group-blind，已排除 books）"
          f"  n={n}  存活 {sum(r['alive'] for r in pool)/n:.1%}")
    print("=" * 100)

    print("\n  【1】knowledge_strength 分布（不是条数 —— 强度才是进 score() 的东西）")
    print(f"  {'key':<14}{'持有该条的比例':>14}{'均值强度':>10}{'p10':>8}"
          f"{'p50':>8}{'p90':>8}{'p90−p10':>10}")
    print("  " + "-" * 74)
    for k in KEYS:
        v = sorted(r["ks_mean"][k] for r in pool)
        held = sum(1 for x in v if x > 0) / n
        print(f"  {k:<14}{held:>13.1%}{statistics.mean(v):>10.3f}"
              f"{v[n//10]:>8.3f}{v[n//2]:>8.3f}{v[9*n//10]:>8.3f}"
              f"{v[9*n//10]-v[n//10]:>10.3f}")

    print("\n  【2】决策间距 margin = top1 − top2（决定干预翻不翻得动）")
    allm = sorted(m for r in pool for m in r["margins"])
    q = lambda p: allm[int(p * len(allm))]
    print(f"    全部决策 tick n={len(allm)}   "
          f"p10 {q(.10):.2f}  p25 {q(.25):.2f}  中位 {q(.50):.2f}  "
          f"p75 {q(.75):.2f}  p90 {q(.90):.2f}")

    print("\n  【3】★ 有效支撑 ★ 一个 Δ 大小的干预能翻转多少决策 / 覆盖多少 agent")
    print(f"  {'Δ':>6}{'可翻转的决策占比':>16}{'responsive agent 占比':>22}{'判定':>10}")
    print("  " + "-" * 60)
    ok_any = None
    for d in DELTAS:
        flip_all = sum(1 for m in allm if m < d) / len(allm)
        per = [sum(1 for m in r["margins"] if m < d) / len(r["margins"])
               for r in pool if r["margins"]]
        resp = sum(1 for x in per if x >= RESP_MIN_FRAC) / len(per)
        good = GATE_LO <= resp <= GATE_HI
        print(f"  {d:>6.1f}{flip_all:>15.1%}{resp:>21.1%}"
              f"{'  ★合格' if good else '':>10}")
        if good and ok_any is None:
            ok_any = (d, resp)

    print("\n" + "=" * 100)
    if ok_any:
        d, resp = ok_any
        print(f" ★ 放行 ★ 存在可行的 Δ = {d}（≤ KNOWLEDGE_WEIGHT=12.0），"
              f"responsive population = {resp:.1%} ∈ [20%, 80%]")
        print(" → 允许设计**唯一一个** Probe D 设计族（closure rule 见记录）。")
    else:
        print(" ✗ 没有任何 Δ ≤ 12.0 能给出 20–80% 的 responsive population。")
        print("")
        print(" → **Probe D 不做，026 正式封存。**")
        print(" 结论不是'没想到好 probe'，而是：**当前架构的可用通路上，")
        print("   不存在能够承载 clean graded novel contingency 的有效中间态。**")
        print(" 这与规则 71（正反馈把每条轴塌成双峰/极端）高度吻合 ——")
        print(" knowledge 的【条数】看起来是梯度的，但它进入决策后的【有效支撑】不是。")
    print("=" * 100)


if __name__ == "__main__":
    mp.freeze_support()
    main()
