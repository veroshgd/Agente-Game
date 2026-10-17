"""
028 frozen-transform transport 彩排 —— ★纯 group-blind 工程检查★
==================================================================

运行：  python transport028.py            （seeds 10000–11499）

★★ 严格边界（本脚本【不做】以下任何一件事）★★
    ✗ 读取 rich/poor label          ✗ 计算 A/B/C 的 task effect
    ✗ 跑 H1 / H2 / G / RB           ✗ 重新拟合 OLS
    ✗ 重新计算 empirical CDF        ✗ 按这批 agent 重新 rank-normalize

**只把 `interface028_frozen.json` 当作固定函数，应用到一个独立 population。**

--------------------------------------------------------------------------
★ 口径：out-of-support 必须查【输入端】，不是 beta 输出 ★
--------------------------------------------------------------------------
mapped beta 已经被 frozen empirical mapping 限死在 A 的 support 内，
**它本身根本不会告诉你发生了多少 extrapolation**。
所以要查的是 **raw readout 相对 frozen calibration 分位数组的越界比例**。

再加 **boundary mass**：有多少 mapped beta 精确等于 frozen 的
`beta_min` / `beta_max`。即使 raw 越界很少，若大量新观测堆到边界，
quantile mapping 仍会造成明显的 **distribution compression**。

--------------------------------------------------------------------------
★ 本脚本不定 validity rule ★
--------------------------------------------------------------------------
先看 frozen transform 自然 transport 到独立 population 时的实际 drift，
**然后**（在看到任何 028 outcome 之前）冻结两个 gate：

    support gate            控制 frozen domain 外的比例 / boundary pile-up
    budget-transport gate   控制 |μ_j − μ_A| 与 |SD_j − SD_A|

两者不能混成一个数：一个臂可能 support 几乎全覆盖，但因新 population 的
rank density 改变，映射后 SD 仍然漂；反之亦然。

⚠ final 上若 gate 失败，**不许重估 mapping**，只能判：
  *frozen coupling normalization did not transport adequately to the
  confirmatory population; breadth contrast is not cleanly interpretable
  under the preregistered equal-budget assumption.*
"""

import multiprocessing as mp
import os
import statistics as st
import sys

import interface028 as IF
import novel_task as NT

WA, WB = "丰富世界", "贫瘠世界"
SEED0, N = 10000, 1500          # 021 留出集：已烧，且【未参与 028 calibration】
CHUNK = 25


def task(job):
    """★只回传 traits 三元组，无任何世界标签★"""
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
        ok, _ = NS.run_window(life, 0, 30)
        if not ok:
            continue
        w = sim.World(s, **NS.scenarios.WORLDS["基准"])
        ok, _ = NS.run_window(life, 30, 30, world=w)
        if not ok:
            continue
        NS.level_state(life.agent)
        t = life.agent.traits
        out.append([t["curiosity"], t["caution"], t["industry"]])
    return out


def _dispatch(j):
    return task(j[1])


def main():
    workers = max(1, (os.cpu_count() or 2) - 2)
    jobs = [(task, (w, s0, min(CHUNK, SEED0 + N - s0)))
            for w in (WA, WB) for s0 in range(SEED0, SEED0 + N, CHUNK)]
    pool = []
    with mp.Pool(workers) as p:
        for recs in p.imap_unordered(_dispatch, jobs):
            pool.extend(recs)
    for r in pool[:100]:
        assert isinstance(r, list) and len(r) == 3, "✗ group-blind 被破坏"
    n = len(pool)

    print("=" * 104)
    print(f" 028 frozen-transform transport 彩排（★group-blind★）")
    print(f" transport population: seeds {SEED0}–{SEED0+N-1}"
          f"（已烧、未参与 028 calibration）  n={n}")
    print(f" frozen: sha256 {IF.F['sha256'][:16]}…  n_cal={IF.F['n_cal']}"
          f"  任务指纹 {IF.F['task_fingerprint']}")
    print("=" * 104)

    traits = [{"curiosity": p[0], "caution": p[1], "industry": p[2]}
              for p in pool]
    bmin, bmax = IF._BETA_A[0], IF._BETA_A[-1]

    # A 臂：真实 transport population 的 reference
    bA = [IF.beta_for("A", t) for t in traits]
    muA, sdA = st.mean(bA), st.stdev(bA)
    print(f"\n  【A 臂 reference】（027 原接口，不经 028 映射）")
    print(f"    mean {muA:.6f}   SD {sdA:.6f}   min {min(bA):.6f}   max {max(bA):.6f}")
    print(f"    对照 calibration 上的 A：mean {st.mean(IF._BETA_A):.6f}"
          f"   SD {st.stdev(IF._BETA_A):.6f}")

    print(f"\n  【各臂 transport 诊断】frozen support = "
          f"[{bmin:.6f}, {bmax:.6f}]")
    print(f"  {'臂':<5}{'raw<min':>9}{'raw>max':>9}{'越界合计':>10}"
          f"{'边界质量':>10}{'mean':>10}{'SD':>10}{'Δmean':>10}{'ΔSD':>10}")
    print("  " + "-" * 92)

    rows = []
    for arm, key, rev in (("Bp", "B", False), ("Bm", "B", True),
                          ("Cp", "Cp", False), ("Cm", "Cm", False)):
        ref = IF.F["x_sorted"][key]
        raws = [IF.raw_readout(t)[key if key != "B" else "B"] for t in traits]
        below = sum(1 for x in raws if x < ref[0]) / n
        above = sum(1 for x in raws if x > ref[-1]) / n
        b = [IF.beta_for(arm, t) for t in traits]
        bound = sum(1 for v in b if v == bmin or v == bmax) / n
        mu, sd = st.mean(b), st.stdev(b)
        rows.append((arm, below, above, below + above, bound, mu, sd,
                     mu - muA, sd - sdA))
        print(f"  {arm:<5}{below:>9.2%}{above:>9.2%}{below+above:>10.2%}"
              f"{bound:>10.2%}{mu:>10.6f}{sd:>10.6f}"
              f"{mu-muA:>+10.6f}{sd-sdA:>+10.6f}")

    print(f"\n  注：Bp / Bm 共享同一个 raw 输入（x_B⊥），所以越界比例相同；")
    print(f"      差别在映射方向，因而 boundary mass 与分布位置不同。")

    print("\n" + "=" * 104)
    print(" 供冻结 gate 参考的实测量（★本脚本不定阈值★）")
    print("=" * 104)
    print(f"  最大越界合计      {max(r[3] for r in rows):.2%}")
    print(f"  最大边界质量      {max(r[4] for r in rows):.2%}")
    print(f"  最大 |Δmean|      {max(abs(r[7]) for r in rows):.6f}"
          f"   （相对 A 的 SD = {max(abs(r[7]) for r in rows)/sdA:.1%}）")
    print(f"  最大 |ΔSD|        {max(abs(r[8]) for r in rows):.6f}"
          f"   （相对 A 的 SD = {max(abs(r[8]) for r in rows)/sdA:.1%}）")
    print("\n  → 据此在【看到任何 028 outcome 之前】冻结：")
    print("     ① support gate           越界比例 / boundary pile-up 上限")
    print("     ② budget-transport gate  |μ_j − μ_A| 与 |SD_j − SD_A| 上限")


if __name__ == "__main__":
    mp.freeze_support()
    sys.stdout.reconfigure(encoding="utf-8")
    main()
