"""
⚠ 已退役（RETIRED）—— 实验 026 Probe C，干预饱和 75–85%（规则 70）。保留作阴性结果证据；--test 仍是规则 72 的回归测试。
Probe C「离家失修」group-blind κ 校准
=======================================

运行：  python novel_calibrate3.py --seeds 300

机制：每执行一次 explore，shelter 发生 κ 的"无人维护损耗"（硬下限 40）；
`build` 仍按 v3 原规则修复。**ON / OFF 两支的背景世界完全同构**
（都用 `storm_chance = 0`），唯一差异就是 κ。

理论链：
    explore → shelter loss → improve_home 优先级/进度 → goal 持续/切换 → 动作

★ 所以必须看到【两层】响应 ★（A2 的教训：机制数学上生效 ≠ 行为 landscape 改变）
    goal layer 变了  AND  action trajectory 变了
若 shelter 确实掉了、但 goal 分布/切换完全不动 → **不该走到 G1**。

★ group-blind ★ 只输出 pooled 量与跨个体方差。种子 `20000+`。
**不碰 `60000–61499`。**
"""

import argparse
import multiprocessing as mp
import os
import statistics
import time
from collections import Counter

WA, WB, COMMON = "丰富世界", "贫瘠世界", "基准"
DEV_DAYS, W_CON = 30, 30
W_DEC_GRID = (5, 7, 10, 14)                    # 先按它升序
KAPPA_GRID = (0.05, 0.10, 0.20, 0.40, 0.80)    # 再按它升序
PAIR = ("see_the_world", "improve_home")
CHUNK = 25

# 合格条件（跑前冻结）
C_DSURV = 0.02        # ① |存活 ON−OFF|
C_DPHYS = 2.0         # ① |hunger / condition 的 ON−OFF|（0–100 刻度）
C_SAT = 0.20          # ② Probe-C intervention saturation rate
C_PAIR_BOTH = 0.50    # ③ 两个 goal 都经历过的比例（已冻结的 guardrail）
C_PAIR_DAYS = 0.30    # ③ 这一对占 goal-days
C_TV_ACT = 0.02       # ④ 动作分布 TV(ON, OFF)
C_TV_GOAL = 0.02      # ⑤ goal 分布 TV(ON, OFF) —— goal 层 manipulation check
C_SPREAD_REL = 0.70   # ⑥ spread_ON ≥ 这个比例 × spread_OFF（防个体方差坍缩）


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
        for kap in (0.0,) + KAPPA_GRID:
            c = NS.fork(life, False)
            NS.enter_novel(c)                       # ★只清 intention★
            w = NS.novel_world(s)                   # ★ON/OFF 背景同构★
            inf = NS.home_neglect(kap) if kap else None
            # 逐日跑，逐日记账（run_window 只给全窗口汇总，切不出 decision window）
            c.world = w
            c.agent.world = w
            day_acts, alive = [], True
            for dd in range(W_CON):
                before = Counter(c.agent.action_log)
                alive, _ = NS.run_window(c, DEV_DAYS + dd, 1,
                                         extra_inf=(inf,) if inf else ())
                day_acts.append(Counter(c.agent.action_log) - before)
                if not alive:
                    break
            ag = c.agent
            # ★规则 72 修复★ 原来只存全窗口汇总的 per_hour，导致动作侧的
            #   manipulation check 用了整个 consequence window，而 goal 侧用
            #   decision window —— 两个时间尺度的量不能互相比较。
            #   现在改存【逐日】动作计数，任何窗口都能切。
            per_day = [dict(d) for d in day_acts]
            ctr = dict(inf.counters) if inf else {}
            out.append({
                "kappa": kap, "alive": alive, "per_day": per_day,
                "goals": list(ag.goal_by_day[DEV_DAYS:DEV_DAYS + W_CON]),
                "hunger": ag.hunger, "condition": ag.condition,
                "shelter": ag.shelter, "ctr": ctr,
            })
    return out


def _dispatch(j):
    return task(j[1])


def act_share(r, w_dec):
    """★规则 72★ 必须按 decision window 切 —— 与 G1 / goal 侧同口径。"""
    acc = Counter()
    for d in r["per_day"][:w_dec]:
        acc.update(d)
    tot = sum(acc.values()) or 1
    return {a: v / tot for a, v in acc.items()}, tot


def tv(d0, d1):
    keys = set(d0) | set(d1)
    return 0.5 * sum(abs(d0.get(k, 0) - d1.get(k, 0)) for k in keys)


def evaluate(pool, w_dec, kap, base):
    rs = [r for r in pool if r["kappa"] == kap]
    if not rs:
        return False, {}
    n = len(rs)

    # 动作层
    da = Counter()
    for r in rs:
        for d in r["per_day"][:w_dec]:      # ★规则 72★ 与 goal 侧同窗口
            da.update(d)
    db = Counter()
    for r in base:
        for d in r["per_day"][:w_dec]:
            db.update(d)
    na, nb = sum(da.values()) or 1, sum(db.values()) or 1
    tv_act = tv({k: v / na for k, v in da.items()}, {k: v / nb for k, v in db.items()})

    # goal 层（decision window 内）
    ga, gb = Counter(), Counter()
    for r in rs:
        ga.update(g for g in r["goals"][:w_dec] if g)
    for r in base:
        gb.update(g for g in r["goals"][:w_dec] if g)
    nga, ngb = sum(ga.values()) or 1, sum(gb.values()) or 1
    tv_goal = tv({k: v / nga for k, v in ga.items()},
                 {k: v / ngb for k, v in gb.items()})

    both = sum(1 for r in rs
               if all(g in r["goals"][:w_dec] for g in PAIR)) / n
    pair_days = sum(ga[g] for g in PAIR) / nga

    # 个体方差（explore 占比）
    def spread(xs):
        v = sorted(xs)
        return v[int(.90 * len(v))] - v[int(.10 * len(v))]
    ex_on = [act_share(r, w_dec)[0].get("explore", 0.0) for r in rs]
    ex_off = [act_share(r, w_dec)[0].get("explore", 0.0) for r in base]
    sp_on, sp_off = spread(ex_on), spread(ex_off)

    # 饱和：★不是"贴边时间比例"，是"explore 发生时已无法再施加损耗的比例"★
    tot_ex = sum(r["ctr"].get("explore", 0) for r in rs)
    sat = sum(r["ctr"].get("saturated", 0) for r in rs) / max(tot_ex, 1)
    clip = sum(r["ctr"].get("clipped", 0) for r in rs) / max(tot_ex, 1)

    surv = sum(r["alive"] for r in rs) / n
    surv0 = sum(r["alive"] for r in base) / len(base)
    m = {
        "n": n, "surv": surv, "dsurv": abs(surv - surv0),
        "dhunger": abs(statistics.mean(r["hunger"] for r in rs)
                       - statistics.mean(r["hunger"] for r in base)),
        "dcond": abs(statistics.mean(r["condition"] for r in rs)
                     - statistics.mean(r["condition"] for r in base)),
        "sat": sat, "clip": clip, "tv_act": tv_act, "tv_goal": tv_goal,
        "both": both, "pair_days": pair_days,
        "sp_on": sp_on, "sp_off": sp_off,
        "sp_rel": (sp_on / sp_off) if sp_off else 0.0,
        "shelter": statistics.mean(r["shelter"] for r in rs),
    }
    m["checks"] = {
        "①生理≈OFF": m["dsurv"] <= C_DSURV and m["dhunger"] <= C_DPHYS
                     and m["dcond"] <= C_DPHYS,
        "②未饱和<20%": sat < C_SAT,
        "③两goal仍活跃": both >= C_PAIR_BOTH and pair_days >= C_PAIR_DAYS,
        "④动作landscape变": tv_act >= C_TV_ACT,
        "⑤goal层也变": tv_goal >= C_TV_GOAL,
        "⑥方差未坍缩": m["sp_rel"] >= C_SPREAD_REL,
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
    print(f"★ group-blind ★ Probe C「离家失修」κ 校准   种子 {a.seed0}–"
          f"{a.seed0+a.seeds-1}   进程 {a.workers}")
    print(f"κ {KAPPA_GRID}   W_dec {W_DEC_GRID}   字典序：先 W_dec 最短，再 κ 最小\n",
          flush=True)

    pool, t0 = [], time.time()
    with mp.Pool(a.workers) as p:
        for k, recs in enumerate(p.imap_unordered(_dispatch, jobs), 1):
            pool.extend(recs)
            if k % 6 == 0 or k == len(jobs):
                el = time.time() - t0
                print(f"  {k}/{len(jobs)}  已用 {el/60:.1f}min  "
                      f"剩余 ~{el/k*(len(jobs)-k)/60:.1f}min", flush=True)
    if not pool:
        raise SystemExit("✗ 池子为空 —— 故障")
    base = [r for r in pool if r["kappa"] == 0.0]

    print("\n" + "=" * 112)
    print(" 饱和曲线（★ 定义 = explore 发生时因 shelter ≤ 40 已无法施加损耗的比例 ★）")
    print(" 注意：这【不是】'shelter 贴在 40 的时间比例' —— 自然衰减 0.35/tick 会")
    print("       把 shelter 带到 40 以下，此后 Probe C 静默失效，贴边比例会严重低估。")
    print("=" * 112)
    print(f"  {'κ':>6}{'饱和率':>10}{'被截断率':>10}{'末 shelter 均值':>16}")
    for kap in KAPPA_GRID:
        _, m = evaluate(pool, W_DEC_GRID[0], kap, base)
        print(f"  {kap:>6.2f}{m['sat']:>10.1%}{m['clip']:>10.1%}{m['shelter']:>16.1f}")

    print("\n" + "=" * 112)
    print(" 逐格结果")
    print("=" * 112)
    print(f"  {'W_dec':>6}{'κ':>6}{'n':>6}{'存活':>7}{'Δ生理':>8}{'饱和':>8}"
          f"{'两goal':>8}{'对占比':>8}{'动作TV':>8}{'goalTV':>8}"
          f"{'方差ON/OFF':>11}")
    print("  " + "-" * 108)
    winner = None
    for w_dec in W_DEC_GRID:
        for kap in KAPPA_GRID:
            ok, m = evaluate(pool, w_dec, kap, base)
            print(f"  {w_dec:>6}{kap:>6.2f}{m['n']:>6}{m['surv']:>7.1%}"
                  f"{max(m['dhunger'], m['dcond']):>8.2f}{m['sat']:>8.1%}"
                  f"{m['both']:>8.1%}{m['pair_days']:>8.1%}{m['tv_act']:>8.3f}"
                  f"{m['tv_goal']:>8.3f}{m['sp_rel']:>11.2f}"
                  + ("   ★合格" if ok else ""))
            if ok and winner is None:
                winner = (w_dec, kap, m)

    print("\n" + "=" * 112)
    if winner is None:
        fail = Counter()
        for w_dec in W_DEC_GRID:
            for kap in KAPPA_GRID:
                _, m = evaluate(pool, w_dec, kap, base)
                for k2, v in m["checks"].items():
                    if not v:
                        fail[k2] += 1
        print(" ✗ 没有 (W_dec, κ) 满足全部条件 → Probe C 退役，不放宽标准。")
        print("\n 失败频次（诊断用，不作放宽依据）：")
        for k2, v in fail.most_common():
            print(f"   {k2:<20} {v}/{len(W_DEC_GRID)*len(KAPPA_GRID)} 格")
        print("\n 判读：")
        print("   goal 变了但动作 TV 不变 → 目标冲突存在但没传到策略层")
        print("   动作 TV 大但饱和/方差/生理失败 → 操纵太强，压出强迫行为")
    else:
        w_dec, kap, m = winner
        print(f" ★ Probe C 合格 ★  W_dec = {w_dec} 天   κ = {kap}")
        print(f"   存活 {m['surv']:.1%}（Δ{m['dsurv']:.1%}）  饱和 {m['sat']:.1%}  "
              f"动作TV {m['tv_act']:.3f}  goalTV {m['tv_goal']:.3f}  "
              f"方差比 {m['sp_rel']:.2f}")
        print("   → 这是前四轮以来第一个同时满足【新因果结构存在 + agent 确实响应")
        print("     + 不靠死亡 + 不抹平个体差异】的 novel environment。")
        print("   下一步：M0 = familiar actions + goals → 20000+ 可判定性彩排")
        print("           → NOVEL_PREREGISTRATION → 最后才碰 60000–61499。")
    print("=" * 112)


def _regression_rule72():
    """★规则 72 的回归测试★ 证明动作侧真的按 decision window 切了。

    修复前：`act_share(r, w_dec)` 收下 w_dec 却不用，`tv_act` 汇总整个
    consequence window —— 于是 goal 侧用 decision window、动作侧用全窗口，
    两个时间尺度的量被拿来互相比较（规则 62 的窗口分离被破坏）。
    """
    # 构造一条 30 天记录：前 5 天全是 explore，后 25 天全是 build
    r = {"per_day": [Counter({"explore": 24}) for _ in range(5)]
                    + [Counter({"build": 24}) for _ in range(25)],
         "goals": ["see_the_world"] * 5 + ["improve_home"] * 25,
         "ctr": {}, "alive": True, "hunger": 0, "condition": 0, "shelter": 0,
         "kappa": 1.0}
    d5, _ = act_share(r, 5)
    d30, _ = act_share(r, 30)
    assert abs(d5.get("explore", 0) - 1.0) < 1e-9,         f"✗ w_dec=5 没有只取前 5 天：{d5}"
    assert d30.get("explore", 0) < 0.2, f"✗ w_dec=30 应被 build 主导：{d30}"
    assert d5 != d30, "✗ act_share 对 w_dec 不敏感 —— 规则 72 的 bug 还在"

    # tv_act 也必须随窗口变化
    base = [{**r, "kappa": 0.0,
             "per_day": [Counter({"build": 24}) for _ in range(30)]}]
    pool = [r] + base
    _, m5 = evaluate(pool, 5, 1.0, base)
    _, m30 = evaluate(pool, 30, 1.0, base)
    assert m5["tv_act"] > m30["tv_act"] + 0.1,         f"✗ tv_act 不随窗口变化：w5={m5['tv_act']:.3f} w30={m30['tv_act']:.3f}"
    print("✓ 规则 72 回归测试通过：动作侧与 goal 侧现在同用 decision window")
    print(f"    w_dec=5  explore 占比 {d5.get('explore',0):.3f}  tv_act {m5['tv_act']:.3f}")
    print(f"    w_dec=30 explore 占比 {d30.get('explore',0):.3f}  tv_act {m30['tv_act']:.3f}")


if __name__ == "__main__":
    mp.freeze_support()
    import sys
    if "--test" in sys.argv:
        _regression_rule72()
    else:
        main()
