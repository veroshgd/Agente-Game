"""
⚠ 已退役（RETIRED）—— 实验 026 Probe A/B，group-blind 校准全格不合格（规则 64）。保留作阴性结果证据。
NOVEL-SITUATION 难度校准 —— ★ group-blind ★
==============================================

运行：  python novel_calibrate.py --probe A --seeds 300
        python novel_calibrate.py --probe B --seeds 300
        python novel_calibrate.py --probe A --seeds 60 --workers 5   （规则 55 自检）

★★ group-blind 是【结构性】的，不是纪律性的 ★★
worker 返回的每条记录里**根本没有发育世界这个字段**（见 `_record()`）。
聚合函数 `evaluate()` 只收到一个混好的池子，**物理上拿不到标签**，
不是"拿得到但我们约定不看"。`_assert_blind()` 会强制检查这一点。

> ### 铁律（设计 §6）###
> 选 `W_dec` / `S` / `λ` 时**不许看哪个值让 rich/poor 差异最大** —— 那是在调
> effect size。本脚本连算都算不出那个量。

★ 找不到合格参数怎么办 ★
**判这个 probe 的设计不干净，不产出参数。**
**绝不降低 95% / 80% / 10pp 这些标准去救它。**
026 测的是 strategy transfer，不是重新研究 survival selection。

种子：`20000+`（已烧掉的 022 段）。**不碰 `60000–61499`。**
"""

import argparse
import multiprocessing as mp
import os
import time
from collections import Counter

WA, WB, COMMON = "丰富世界", "贫瘠世界", "基准"
DEV_DAYS = 30           # 发育期
W_CON = 30              # consequence window（novel 世界里总共跑多少天）
W_DEC_GRID = (5, 7, 10, 14)             # decision window 候选（升序）
S_GRID = (55.0, 60.0, 65.0, 70.0, 75.0, 80.0)      # Probe A 门槛（升序，须 > 拉平 shelter=50）
LAM_GRID = (0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0)    # Probe B 耦合强度（升序）
M_MARGIN = 0.05         # 策略归类的边距
CHUNK = 25

# 合格条件（设计 §6，跑前冻结）
C_STRAT_LO, C_STRAT_HI = 0.20, 0.80     # ① 两条主策略各自占比
C_SURV_DEC = 0.95                       # ② decision window 内 pooled 存活率
C_SURV_CON = 0.80                       # ③ consequence window 总体存活率
C_EARLY_MAX = 0.50                      # ④ 5 天内达标者上限（Probe A）
C_GATE_LO, C_GATE_HI = 0.20, 0.80       # ⑤ 窗口结束前达标比例（Probe A）
C_STRAT_SURV = 0.80                     # ⑥ 每条策略各自的存活率
C_STRAT_SURV_GAP = 0.10                 # ⑥ 两条策略存活率之差上限
C_MIN_ACTIONS = 120                     # ⑦ 每只球的总动作数
C_BITE_MIN = 0.02                       # ⑧ Probe B 专用：耦合相对 λ=0 的最小行为改变
#     ⚠ ⑧ 是我为 Probe B 补的（④⑤ 是门控专用，Probe B 没有门）。**需拍板。**


# ---------------------------------------------------------------- worker
def _setup():
    """★规则 55★ 每个任务显式设定所有全局量，不靠继承"""
    import novel_situation as NS
    sim = NS.sim
    sim.COND_RECOVER_AT = 65.0
    sim.COND_DEADZONE_RECOVER = 0.0
    sim.COND_SHELTER_RECOVER = 0.0
    sim.SLEEP_SUPPRESS = sim.HUNGER_URGENCY = 0.0
    sim.SLEEP_EFF_FLOOR = 0.35
    sim.KNOWLEDGE_WEIGHT, sim.KNOWLEDGE_GOAL_WEIGHT, sim.KNOWLEDGE_FORGET = 12.0, 0.25, 0.02
    return NS


def _record(NS, life, param, gate_S):
    """跑 novel 世界的 consequence window，逐日记录 —— ★不含任何世界标签★"""
    sim = NS.sim
    ag = life.agent
    per_day = []            # 每天：(动作 Counter, 是否已达标, 是否活着)
    reached = False
    alive = True
    for day in range(DEV_DAYS, DEV_DAYS + W_CON):
        before = Counter(ag.action_log)
        for t in range(sim.TICKS_PER_DAY):
            life.world.tick(day, t)
            for inf in life.influences:
                inf(life.world, ag, day, t, life.inf_rng)
            ag.tick(day, t)
            if gate_S is not None and ag.shelter >= gate_S:
                reached = True
            if not ag.alive:
                alive = False
                break
        per_day.append((Counter(ag.action_log) - before, reached, alive))
        if not alive:
            break
        ag.daily(day)
    return {
        "param": param,
        "per_day": per_day,
        "alive_con": alive,
        "reached_any": reached,
        "reached_by5": any(r for _, r, _ in per_day[:5]),
        "end_food": ag.inventory["food"], "end_shelter": ag.shelter,
        "end_condition": ag.condition,
    }
    # ★ 注意：这里没有 world / label / 发育世界 字段 —— group-blind 的结构保证


def task(job):
    probe, world, seed0, n = job
    NS = _setup()
    sim = NS.sim
    out = []
    grid = (0.0,) + S_GRID if probe == "A" else (0.0,) + LAM_GRID  # 都多跑一个"规则关闭"基线
    for s in range(seed0, seed0 + n):
        life = NS.scenarios.make(s, world)
        ok, _ = NS.run_window(life, 0, DEV_DAYS)
        if not ok:
            continue                       # 发育期就死的球不进入 novel 阶段
        NS.level_state(life.agent)
        for p in grid:
            c = NS.fork(life, False)
            if probe == "A":
                w = NS.GatedWorld(s, gate_S=p, **NS.scenarios.WORLDS[COMMON])
                c.world = w
                c.agent.world = w
                w.agent = c.agent
                out.append(_record(NS, c, p, p))
            else:
                w = sim.World(s, **NS.scenarios.WORLDS[COMMON])
                c.world = w
                c.agent.world = w
                if p > 0:
                    c.influences = list(c.influences) + [NS.salt_flat(p)]
                out.append(_record(NS, c, p, None))
    return probe, seed0, out


# ---------------------------------------------------------------- 聚合
def _assert_blind(pool):
    """结构性保证：池子里不许出现任何可用于分组的标签"""
    banned = {"world", "label", "dev", "development", "history", "rich", "poor",
              "seed", "origin"}
    for r in pool[:50]:
        bad = banned & set(r)
        if bad:
            raise AssertionError(f"✗ group-blind 被破坏：记录里出现 {sorted(bad)}")


def _profile(per_day, w_dec):
    """decision window 内的动作占比 + 是否活满该窗口"""
    days = per_day[:w_dec]
    alive = len(days) == w_dec and days[-1][2]
    acc = Counter()
    for c, _, _ in days:
        acc.update(c)
    tot = sum(acc.values())
    return acc, tot, alive


def classify(acc, tot, actions):
    if tot == 0:
        return "混合"
    b = (acc["gather_material"] + acc["build"]) / tot
    e = acc["explore"] / tot
    if b - e >= M_MARGIN:
        return "盖房派"
    if e - b >= M_MARGIN:
        return "探索派"
    return "混合"


def evaluate(pool, w_dec, param, actions, probe, base_dist=None):
    """★ 只吃混好的池子，收不到任何标签 ★ 返回 (是否合格, 指标字典)"""
    rs = [r for r in pool if r["param"] == param]
    if not rs:
        return False, {"note": "无样本"}

    n = len(rs)
    surv_dec = strat = 0
    cls, acc_all = [], Counter()
    for r in rs:
        acc, tot, alive = _profile(r["per_day"], w_dec)
        surv_dec += alive
        acc_all.update(acc)
        cls.append(classify(acc, tot, actions) if alive else None)

    live_cls = [c for c in cls if c is not None]
    nb = sum(1 for c in live_cls if c == "盖房派")
    ne = sum(1 for c in live_cls if c == "探索派")
    denom = len(live_cls) or 1
    p_b, p_e = nb / denom, ne / denom

    surv_con = sum(r["alive_con"] for r in rs) / n
    sb = [r["alive_con"] for r, c in zip(rs, cls) if c == "盖房派"]
    se = [r["alive_con"] for r, c in zip(rs, cls) if c == "探索派"]
    sv_b = sum(sb) / len(sb) if sb else 0.0
    sv_e = sum(se) / len(se) if se else 0.0

    tot_all = sum(acc_all.values()) or 1
    dist = {a: acc_all[a] / tot_all for a in sorted(acc_all)}

    m = {
        "n": n, "surv_dec": surv_dec / n, "surv_con": surv_con,
        "p_build": p_b, "p_explore": p_e,
        "sv_build": sv_b, "sv_explore": sv_e, "sv_gap": abs(sv_b - sv_e),
        "reach5": sum(r["reached_by5"] for r in rs) / n,
        "reach_end": sum(r["reached_any"] for r in rs) / n,
        "actions": actions,
    }
    if base_dist is not None:
        keys = set(dist) | set(base_dist)
        m["bite"] = 0.5 * sum(abs(dist.get(k, 0) - base_dist.get(k, 0)) for k in keys)

    checks = {
        "①两策略20-80%": C_STRAT_LO <= p_b <= C_STRAT_HI and C_STRAT_LO <= p_e <= C_STRAT_HI,
        "②决策窗存活≥95%": m["surv_dec"] >= C_SURV_DEC,
        "③后果窗存活≥80%": surv_con >= C_SURV_CON,
        "⑥策略存活≥80%/差≤10pp": sv_b >= C_STRAT_SURV and sv_e >= C_STRAT_SURV
                                  and m["sv_gap"] <= C_STRAT_SURV_GAP,
        "⑦动作数≥120": actions >= C_MIN_ACTIONS,
    }
    if probe == "A":
        checks["④5天内达标≤50%"] = m["reach5"] <= C_EARLY_MAX
        checks["⑤窗末达标20-80%"] = C_GATE_LO <= m["reach_end"] <= C_GATE_HI
    else:
        checks["⑧耦合咬得住"] = m.get("bite", 0.0) >= C_BITE_MIN
    m["checks"] = checks
    return all(checks.values()), m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", choices=["A", "B"], required=True)
    ap.add_argument("--seeds", type=int, default=300)
    ap.add_argument("--seed0", type=int, default=20000)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    a = ap.parse_args()

    grid = S_GRID if a.probe == "A" else LAM_GRID
    name = "S（冻土门槛）" if a.probe == "A" else "λ（盐碱地耦合）"
    jobs = [(task, (a.probe, w, s0, min(CHUNK, a.seed0 + a.seeds - s0)))
            for w in (WA, WB)
            for s0 in range(a.seed0, a.seed0 + a.seeds, CHUNK)]
    planned = sum(j[1][3] for j in jobs)
    assert planned == 2 * a.seeds, f"✗ 分块覆盖不全 {planned} ≠ {2*a.seeds}"

    print(f"★ group-blind 校准 ★  Probe {a.probe}   {name}")
    print(f"种子 {a.seed0}–{a.seed0+a.seeds-1}（已烧段）  两世界混合  进程 {a.workers}")
    print(f"发育 {DEV_DAYS} 天 → 拉平 → novel {W_CON} 天；"
          f"W_dec 候选 {W_DEC_GRID}\n", flush=True)

    pool, t0 = [], time.time()
    with mp.Pool(a.workers) as pool_:
        for k, (_, _, recs) in enumerate(pool_.imap_unordered(_dispatch, jobs), 1):
            pool.extend(recs)
            if k % 6 == 0 or k == len(jobs):
                el = time.time() - t0
                print(f"  {k}/{len(jobs)}  已用 {el/60:.1f}min  "
                      f"剩余 ~{el/k*(len(jobs)-k)/60:.1f}min", flush=True)
    if not pool:
        raise SystemExit("✗ 池子为空 —— 这是故障，不是结果")
    _assert_blind(pool)
    print(f"\n混合池 {len(pool)} 条记录，已通过 group-blind 结构检查\n")

    base = {}
    if a.probe == "B":                       # λ=0 基线（只用于 ⑧）
        rs = [r for r in pool if r["param"] == 0.0]
        acc = Counter()
        for r in rs:
            for c, _, _ in r["per_day"]:
                acc.update(c)
        tot = sum(acc.values()) or 1
        base = {k: v / tot for k, v in acc.items()}

    print("=" * 108)
    print(f" 逐格结果（字典序：先 W_dec 升序，再 {name} 升序）")
    print("=" * 108)
    hdr = (f"  {'W_dec':>6}{name[:1]:>7}{'n':>6}{'决策窗存活':>10}{'后果窗存活':>10}"
           f"{'盖房派':>8}{'探索派':>8}{'盖房存活':>9}{'探索存活':>9}{'差':>7}")
    hdr += f"{'5天达标':>9}{'窗末达标':>9}" if a.probe == "A" else f"{'耦合改变':>10}"
    print(hdr)
    print("  " + "-" * 110)

    print("  ── 基线：novel 规则关闭（阴性对照，应复现 persistence 阶段数字）──")
    for w_dec in W_DEC_GRID:
        _, m = evaluate(pool, w_dec, 0.0, w_dec * 24, a.probe, base or None)
        print(f"  {w_dec:>6}{0.0:>7.2f}{m['n']:>6}{m['surv_dec']:>10.1%}"
              f"{m['surv_con']:>10.1%}{m['p_build']:>8.1%}{m['p_explore']:>8.1%}"
              f"{m['sv_build']:>9.1%}{m['sv_explore']:>9.1%}{m['sv_gap']:>7.1%}")
    print("  ── 候选格 ──")

    winner = None
    for w_dec in W_DEC_GRID:
        actions = w_dec * 24
        for p in grid:
            ok, m = evaluate(pool, w_dec, p, actions, a.probe, base or None)
            row = (f"  {w_dec:>6}{p:>7.2f}{m['n']:>6}{m['surv_dec']:>10.1%}"
                   f"{m['surv_con']:>10.1%}{m['p_build']:>8.1%}{m['p_explore']:>8.1%}"
                   f"{m['sv_build']:>9.1%}{m['sv_explore']:>9.1%}{m['sv_gap']:>7.1%}")
            row += (f"{m['reach5']:>9.1%}{m['reach_end']:>9.1%}" if a.probe == "A"
                    else f"{m.get('bite',0):>10.3f}")
            print(row + ("   ★合格" if ok else ""))
            if ok and winner is None:
                winner = (w_dec, p, m)      # 字典序第一个 = 唯一解

    print("\n" + "=" * 108)
    if winner is None:
        print(f" ✗ Probe {a.probe}：没有任何 (W_dec, {name[:1]}) 组合满足全部条件。")
        print(" 按设计 §6：**判该 probe 设计不干净，不产出参数。**")
        print(" ⚠ 绝不降低 95% / 80% / 10pp 等标准去救它 ——")
        print("   026 测的是 strategy transfer，不是重新研究 survival selection。")
        print("\n 各条件的失败频次（供诊断，不作为放宽依据）：")
        fail = Counter()
        for w_dec in W_DEC_GRID:
            for p in grid:
                _, m = evaluate(pool, w_dec, p, w_dec * 24, a.probe, base or None)
                for k, v in m.get("checks", {}).items():
                    if not v:
                        fail[k] += 1
        for k, v in fail.most_common():
            print(f"   {k:<26} 失败 {v}/{len(W_DEC_GRID)*len(grid)} 格")
    else:
        w_dec, p, m = winner
        print(f" ★ 冻结参数（字典序第一个合格格）★")
        print(f"   W_dec = {w_dec} 天   {name[:1]} = {p}")
        print(f"   决策窗存活 {m['surv_dec']:.1%} · 后果窗存活 {m['surv_con']:.1%} · "
              f"盖房派 {m['p_build']:.1%} / 探索派 {m['p_explore']:.1%}")
        print(" 写进 NOVEL_PREREGISTRATION.md 后不再更改。")
    print("=" * 108)


def _dispatch(job):
    fn, args = job
    return fn(args)


if __name__ == "__main__":
    mp.freeze_support()
    main()
