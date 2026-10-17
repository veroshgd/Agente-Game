"""
规则 71 因果消融 —— 是不是同一套正反馈既造就 persistence、又消灭 plasticity？
==============================================================================

运行：  python rule71_ablation.py --seeds 300

★ 要检验的命题（规则 71）★

> v3 的正反馈（性状漂移 + 目标持续）把 agent 推向专精，
> 每条资源轴都塌成"全投入 / 全放弃"，梯度型干预因而没有中间地带可作用。
> **同一套产生持久个体差异的机制，同时消灭了未来的可塑性。**

026 只**观察到**这个相关（材料双峰、shelter 双峰、knowledge 近乎 0/1）。
本实验**直接问因果**：把正反馈强度调下去，三件事是不是**一起**变。

★ 为什么做消融而不是直接开发 v4 ★
v4 会改变模型，消融是**在 v3 内部**问"这个机制到底是不是原因"。
**科学上更硬，而且不需要重新验证整个 persistence 架构。**

--------------------------------------------------------------------------
★ 事前方向预测（跑之前写下，跑完照抄对比）★

沿 `TRAIT_DRIFT` 由 0 升到 2.4（默认 1.20），预测：

    (a) persistence  移植比值            ↑ 单调上升
    (b) specialization 资源状态双峰程度   ↑ 单调上升
    (c) plasticity   Δ=3.0 可翻转决策占比 ↓ 单调下降

**三者同向移动 = 规则 71 得到因果支持。**
若 (a) 上升而 (b)(c) 不动 → 正反馈只造就 persistence，
**规则 71 关于"代价"的那一半不成立，必须撤回。**

⚠ 这是 **mechanistic / exploratory** 分析，不是 confirmatory：
   用已烧掉的种子 `20000+`，无预注册，结论按探索性表述。
⚠ Δ=3.0 的 susceptibility 只是**机制探针**（026 封存时定的），
   **不承担 generalization 的任何结论。**
--------------------------------------------------------------------------
"""

import argparse
import multiprocessing as mp
import os
import statistics
from collections import Counter

WA, WB, COMMON = "丰富世界", "贫瘠世界", "基准"
DEV_DAYS, OBS_DAYS = 30, 30
DRIFT_GRID = (0.0, 0.3, 0.6, 1.2, 2.4)     # 1.20 = v3 默认
DELTA = 3.0                                 # 标准化决策扰动幅度（026 封存时冻结）
CHUNK = 25
BASE_K = 5


def task(job):
    world, drift, seed0, n = job
    import novel_situation as NS
    sim = NS.sim
    # ★规则 55★ 显式设定
    sim.COND_RECOVER_AT = 65.0
    sim.COND_DEADZONE_RECOVER = sim.COND_SHELTER_RECOVER = 0.0
    sim.SLEEP_SUPPRESS = sim.HUNGER_URGENCY = 0.0
    sim.SLEEP_EFF_FLOOR = 0.35
    sim.KNOWLEDGE_WEIGHT, sim.KNOWLEDGE_GOAL_WEIGHT, sim.KNOWLEDGE_FORGET = 12.0, 0.25, 0.02
    sim.TRAIT_DRIFT = drift                 # ★ 被消融的正反馈增益 ★

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
            out.append(None)
            continue
        snap = [Counter(c) for c in life.agent.action_by_hour]
        w = sim.World(s, **NS.scenarios.WORLDS[COMMON])
        life.world = w
        life.agent.world = w
        ag = life.agent

        margins = []
        alive = True
        for day in range(DEV_DAYS, DEV_DAYS + OBS_DAYS):
            for t in range(sim.TICKS_PER_DAY):
                w.tick(day, t)
                for inf in life.influences:
                    inf(w, ag, day, t, life.inf_rng)
                ag._scores = []
                ag.tick(day, t)
                sc = sorted(ag._scores, reverse=True)
                if len(sc) >= 2:
                    margins.append(sc[0] - sc[1])
                if not ag.alive:
                    alive = False
                    break
            if not alive:
                break
            ag.daily(day)
        if not alive:
            out.append(None)
            continue

        win = [Counter(c) - snap[h] for h, c in enumerate(ag.action_by_hour)]
        mat = []
        for h in win:
            tot = sum(h.values()) or 1
            mat.append(tuple(h[a] / tot for a in sim.ACTIONS))
        tot_w = sum(sum(h.values()) for h in win) or 1
        out.append({
            "mat": tuple(mat),
            "explore": sum(h["explore"] for h in win) / tot_w,
            "shelter": ag.shelter, "material": ag.inventory["material"],
            "flip": sum(1 for m in margins if m < DELTA) / max(len(margins), 1),
            "margin_med": statistics.median(margins) if margins else 0.0,
        })
    return world, drift, seed0, out


def _dispatch(j):
    return task(j[1])


def mat_tv(a, b):
    return sum(0.5 * sum(abs(x - y) for x, y in zip(ha, hb))
               for ha, hb in zip(a, b)) / len(a)


def extremity(vals, lo, hi):
    """极化程度：落在两端 5% 区间的比例。★只能用于有【固定量程】的变量★"""
    span = hi - lo
    return sum(1 for v in vals
               if v <= lo + 0.05 * span or v >= hi - 0.05 * span) / len(vals)


def poles(vals, lo_th, hi_th):
    """★用固定阈值量极化★ 返回 (低极, 高极, 中间)。

    ⚠ 冒烟时发现：material 用 `extremity(v, 0, max(v))` 是**坏指标** ——
      量程 `max(v)` 逐条件变化，且 material 高度右偏（多数为 0、少数上百），
      于是"落在量程 5% 内"几乎把所有人都算成低极（实测 98%，接近天花板），
      不同 drift 之间根本不可比。改用**与条件无关的固定阈值**：
      material < 3（连一次 build 都买不起） / > 50（明显过剩）。
    """
    n = len(vals) or 1
    lo = sum(1 for v in vals if v < lo_th) / n
    hi = sum(1 for v in vals if v > hi_th) / n
    return lo, hi, 1.0 - lo - hi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=300)
    ap.add_argument("--seed0", type=int, default=20000)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    a = ap.parse_args()
    N = a.seeds

    jobs = [(task, (w, d, s0, min(CHUNK, a.seed0 + N - s0)))
            for d in DRIFT_GRID for w in (WA, WB)
            for s0 in range(a.seed0, a.seed0 + N, CHUNK)]
    print(f"规则 71 因果消融   TRAIT_DRIFT {DRIFT_GRID}（默认 1.20）"
          f"   种子 {a.seed0}–{a.seed0+N-1}   进程 {a.workers}")
    print(f"Δ = {DELTA}（机制探针，不承担 generalization 结论）\n", flush=True)

    store = {(w, d): [None] * N for d in DRIFT_GRID for w in (WA, WB)}
    with mp.Pool(a.workers) as p:
        for world, drift, s0, recs in p.imap_unordered(_dispatch, jobs):
            store[(world, drift)][s0 - a.seed0:s0 - a.seed0 + len(recs)] = recs

    import random
    print("=" * 104)
    print(" 规则 71 因果消融结果")
    print("=" * 104)
    print(f"  {'TRAIT_DRIFT':>12}{'n':>6}{'(a)移植比值':>13}{'(b)shelter极化':>15}"
          f"{'(b)material两极':>16}{'(c)可翻转决策':>14}{'margin中位':>12}"
          f"{'material中间层':>14}")
    print("  " + "-" * 100)

    rows = []
    for d in DRIFT_GRID:
        ca, cb = store[(WA, d)], store[(WB, d)]
        live = [i for i in range(N) if ca[i] and cb[i]]
        if len(live) < max(20, min(50, N // 3)):   # 小样本调试按比例放宽
            print(f"  {d:>12.2f}{len(live):>6}   ⚠ 有效 n 不足")
            continue
        wa = [ca[i]["mat"] for i in live]
        wb = [cb[i]["mat"] for i in live]
        rng = random.Random(777)
        treat = [mat_tv(wa[k], wb[k]) for k in range(len(live))]
        base = []
        for ws in (wa, wb):
            idx = list(range(len(ws)))
            for _ in range(BASE_K):
                rng.shuffle(idx)
                base += [mat_tv(ws[idx[j]], ws[idx[j + 1]])
                         for j in range(0, len(idx) - 1, 2)]
        ratio = statistics.mean(treat) / statistics.mean(base)

        allr = [ca[i] for i in live] + [cb[i] for i in live]
        ex_sh = extremity([r["shelter"] for r in allr], 0, 100)
        m_lo, m_hi, m_mid = poles([r["material"] for r in allr], 3.0, 50.0)
        ex_mt = m_lo + m_hi          # 两极合计（固定阈值，跨条件可比）
        flip = statistics.mean(r["flip"] for r in allr)
        mmed = statistics.mean(r["margin_med"] for r in allr)
        rows.append((d, ratio, ex_sh, ex_mt, flip, mmed, m_mid))
        print(f"  {d:>12.2f}{len(live):>6}{ratio:>13.3f}{ex_sh:>15.1%}"
              f"{ex_mt:>16.1%}{flip:>14.1%}{mmed:>12.2f}{m_mid:>12.1%}")

    print("\n" + "=" * 104)
    print(" 事前预测对照（预测写在脚本头部，跑前已定）")
    print("=" * 104)
    if len(rows) >= 3:
        # ★ 同时报【全网格端点】与【现实区间 0→默认1.2】★
        #   预测写的是"沿 0→2.4 单调"，所以判定以全网格为准；
        #   现实区间单独报出来，但**只能作探索性描述，不能拿来救预测**。
        r0, r1 = rows[0], rows[-1]
        rd = next((r for r in rows if r[0] == 1.2), None)
        if rd:
            print(f"  【现实区间 drift 0.0 → 1.2（v3 默认）】探索性描述，非判定依据")
            print(f"    (a) {r0[1]:.3f} → {rd[1]:.3f}   (b)shelter {r0[2]:.1%} → {rd[2]:.1%}"
                  f"   (c) {r0[4]:.1%} → {rd[4]:.1%}")
            print()
        def arrow(a_, b_):
            return "↑" if b_ > a_ else ("↓" if b_ < a_ else "→")
        print(f"  drift {r0[0]} → {r1[0]}")
        print(f"    (a) 移植比值 persistence     {r0[1]:.3f} → {r1[1]:.3f}  "
              f"{arrow(r0[1], r1[1])}   预测 ↑")
        print(f"    (b) shelter 极化             {r0[2]:.1%} → {r1[2]:.1%}  "
              f"{arrow(r0[2], r1[2])}   预测 ↑")
        print(f"    (b) material 极化            {r0[3]:.1%} → {r1[3]:.1%}  "
              f"{arrow(r0[3], r1[3])}   预测 ↑")
        print(f"    (c) 可翻转决策 plasticity    {r0[4]:.1%} → {r1[4]:.1%}  "
              f"{arrow(r0[4], r1[4])}   预测 ↓")
        ok = (r1[1] > r0[1]) and (r1[2] > r0[2] or r1[3] > r0[3]) and (r1[4] < r0[4])
        print()
        if ok:
            print("  ★ 三者同向 → 规则 71 得到因果支持：")
            print("    同一套正反馈既造就 persistence，又消灭 plasticity。")
        else:
            print("  ✗ 三者未同向 → **规则 71 关于'代价'的那一半不成立，应当撤回或改写。**")
            print("    （若 (a) 上升而 (b)(c) 不动 → 正反馈只造就 persistence。）")
    print("=" * 104)


if __name__ == "__main__":
    mp.freeze_support()
    main()
