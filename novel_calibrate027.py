"""
实验 027 group-blind 校准 —— 冻结 β / α / τ
==========================================

运行：  python novel_calibrate027.py --seeds 300

★★ group-blind 是结构性的 ★★
worker 只回传 `novelty_style`（一个 [0,1] 的标量）与种子，
**没有发育世界标签**。`evaluate()` 拿到的是一个混好的池子，
**物理上算不出 rich/poor 差异**。`_assert_blind()` 强制检查。

> ### 铁律 ###
> 绝不能出现 "β=0.1 rich/poor 不显著，β=0.3 显著 → 用 0.3"。
> 本脚本连那个量都算不出来。

★ 效率 ★ 60 天发育与 (α, β) 无关 → 只跑一次，提取每只球的
`novelty_style`，整个网格就是纯算术，秒级完成。

★ 合格条件（跑前冻结）★
  ① 学习前段两个选项都有人选（★个体内★较少选项占比 ≥ 5%）
  ② trial 31–40 正确率 ∈ [65%, 90%]        规则学得会，但没饱和
  ③ 反转后前 10 trial 已切换者 ∈ [20%, 80%]  不能一秒全懂，也不能没人懂
  ④ trial 71–80 正确率 ∈ [65%, 90%]        reversal 是可学的

★ 选择顺序（字典序，跑前冻结）★ **β 升序 → α 升序 → τ 升序**，取第一个合格格。
  β 放第一位，因为它是**唯一让历史进来的旋钮**，
  **取最小 = 最不容易制造效应**（最保守的方向）。

种子：`20000+`（已烧段）。**不碰 `60000–61499`。**
"""

import argparse
import multiprocessing as mp
import os
import statistics
from collections import Counter

import novel_task as NT

WA, WB = "丰富世界", "贫瘠世界"
ALPHA_GRID = (0.05, 0.10, 0.20, 0.40)
BETA_GRID = (0.05, 0.10, 0.20, 0.30, 0.50)
TAU_GRID = (0.02, 0.05, 0.10, 0.20)
CHUNK = 25

C_MIN_SHARE = 0.05                 # ① ★个体内★较少选项的占比下限（不是 pooled）
C_LEARN_LO, C_LEARN_HI = 0.65, 0.90   # ② trial 31–40
C_SWITCH_LO, C_SWITCH_HI = 0.20, 0.80  # ③ 反转后 10 trial 内切换者比例
C_RELEARN_LO, C_RELEARN_HI = 0.65, 0.90  # ④ trial 71–80


def task(job):
    """跑 60 天 v3 核心，只回传【无标签】的 novelty_style + 种子"""
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
        NS.level_state(life.agent)          # 拉平身体状态后再进任务
        # ★ 只回传这两个 —— 没有世界标签 ★
        out.append({"seed": s, "ns": NT.novelty_style(life.agent)})
    return out


def _dispatch(j):
    return task(j[1])


def _assert_blind(pool):
    banned = {"world", "label", "dev", "development", "history", "rich", "poor"}
    for r in pool[:50]:
        bad = banned & set(r)
        if bad:
            raise AssertionError(f"✗ group-blind 被破坏：{sorted(bad)}")


class _Stub:
    """只带 traits 的最小 agent —— 校准阶段不需要真 agent 对象"""
    def __init__(self, ns):
        # 反解出一对 (curiosity, caution) 使 novelty_style 恰好等于 ns
        self.traits = {"curiosity": 50.0 + (ns - 0.5) * 100.0,
                       "caution": 50.0 - (ns - 0.5) * 100.0,
                       "industry": 50.0}


def evaluate3(pool, alpha, beta, tau):
    recs = [NT.run_task(_Stub(r["ns"]), r["seed"], alpha=alpha, beta=beta,
                        tau=tau) for r in pool]
    n = len(recs)

    # ★修正★ 判据① 必须按【个体内】算。按 pooled 算是假象：
    #   一半种子 A 好、一半 B 好，混起来永远接近 50/50，
    #   于是这条判据既不可能通过也不可能失败（实测恒为 48.7%）。
    per = [min(r["choices"][:NT.REVERSAL_AT].count(0),
               r["choices"][:NT.REVERSAL_AT].count(1)) / NT.REVERSAL_AT
           for r in recs]
    min_share = statistics.mean(per)

    learn = statistics.mean(NT.correct_rate(r, 30, 40) for r in recs)
    relearn = statistics.mean(NT.correct_rate(r, 70, 80) for r in recs)
    lat = [NT.switch_latency(r) for r in recs]
    switched10 = sum(1 for x in lat if x is not None and x <= 10) / n
    never = sum(1 for x in lat if x is None) / n

    m = {"n": n, "min_share": min_share, "learn": learn, "relearn": relearn,
         "switched10": switched10, "never": never,
         "explore_early": statistics.mean(NT.explore_rate(r, 0, 10) for r in recs),
         "lat_med": statistics.median([x for x in lat if x is not None] or [0])}
    m["checks"] = {
        "①两选项都有人选": min_share >= C_MIN_SHARE,
        "②31-40正确率65-90%": C_LEARN_LO <= learn <= C_LEARN_HI,
        "③反转后10trial切换20-80%": C_SWITCH_LO <= switched10 <= C_SWITCH_HI,
        "④71-80正确率65-90%": C_RELEARN_LO <= relearn <= C_RELEARN_HI,
    }
    return all(m["checks"].values()), m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=300)
    ap.add_argument("--seed0", type=int, default=20000)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    a = ap.parse_args()

    jobs = [(task, (w, s0, min(CHUNK, a.seed0 + a.seeds - s0)))
            for w in (WA, WB) for s0 in range(a.seed0, a.seed0 + a.seeds, CHUNK)]
    print(f"★ group-blind ★ 027 校准   种子 {a.seed0}–{a.seed0+a.seeds-1}"
          f"   进程 {a.workers}")
    print(f"α {ALPHA_GRID}   β {BETA_GRID}   字典序：β 升序 → α 升序 → τ 升序\n",
          flush=True)

    pool = []
    with mp.Pool(a.workers) as p:
        for recs in p.imap_unordered(_dispatch, jobs):
            pool.extend(recs)
    if not pool:
        raise SystemExit("✗ 池子为空 —— 故障")
    _assert_blind(pool)
    ns = sorted(r["ns"] for r in pool)
    print(f"混合池 {len(pool)} 只球（已通过 group-blind 检查）")
    print(f"novelty_style 分布：p10 {ns[len(ns)//10]:.3f}  中位 {ns[len(ns)//2]:.3f}"
          f"  p90 {ns[9*len(ns)//10]:.3f}\n")

    print("=" * 110)
    print(f"  {'β':>6}{'α':>6}{'τ':>6}{'个体内少选占比':>15}{'31-40正确':>11}"
          f"{'反转10内切换':>13}{'71-80正确':>11}{'从不切换':>10}{'切换中位':>10}")
    print("  " + "-" * 106)
    winner, rows = None, []
    for be in BETA_GRID:                     # ★β 第一位：历史通道最弱优先★
        for al in ALPHA_GRID:
            for ta in TAU_GRID:
                ok, m = evaluate3(pool, al, be, ta)
                rows.append((be, al, ta, ok, m))
                if ok or m["checks"]["②31-40正确率65-90%"]:
                    print(f"  {be:>6.2f}{al:>6.2f}{ta:>6.2f}{m['min_share']:>15.1%}"
                          f"{m['learn']:>11.1%}{m['switched10']:>13.1%}"
                          f"{m['relearn']:>11.1%}{m['never']:>10.1%}"
                          f"{m['lat_med']:>10.0f}" + ("   ★合格" if ok else ""))
                if ok and winner is None:
                    winner = (be, al, ta, m)
    print(f"  （只列出【②已通过】的格；共扫 {len(rows)} 格）")

    print(chr(10) + "=" * 110)
    if winner is None:
        fail = Counter()
        for be, al, ta, ok, m in rows:
            for k, v in m["checks"].items():
                if not v:
                    fail[k] += 1
        print(" ✗ 没有 (β, α, τ) 满足全部条件 → 任务参数化不合格，不产出参数。")
        print("   ⚠ 不放宽标准。若要改，只能改任务【设计】本身，且要重新校准。")
        print(chr(10) + " 失败频次：")
        for k, v in fail.most_common():
            print(f"   {k:<26} {v}/{len(rows)} 格")
    else:
        be, al, ta, m = winner
        print(f" ★ 冻结 ★  β = {be}   α = {al}   τ = {ta}")
        print(f"   个体内少选占比 {m['min_share']:.1%} · 31–40 正确率 {m['learn']:.1%}")
        print(f"   反转后 10 trial 内切换 {m['switched10']:.1%} · "
              f"71–80 正确率 {m['relearn']:.1%}")
        print(f"   切换延迟中位 {m['lat_med']:.0f} trial · 从不切换 {m['never']:.1%}")
        print(" → 写进 NOVEL_TASK_PREREGISTRATION.md 后不再更改。")
    print("=" * 110)


if __name__ == "__main__":
    mp.freeze_support()
    main()
