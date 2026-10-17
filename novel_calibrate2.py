"""
⚠ 已退役（RETIRED）—— 实验 026 Probe A2，乘性加成落空（规则 68）。保留作阴性结果证据。
Probe A2「探路」可行性校准 —— ★ group-blind ★
================================================

运行：  python novel_calibrate2.py --seeds 300

机制（`novel_situation.discovery_gather`）：
    必须执行 `gather_material` 才拿得到材料；
    **该次采集的 yield 取决于最近 τ 个 tick 内 explore 的比例**（加成强度 α）。
    纯 explore 拿不到材料；纯 gather 只能低效拿；受益的是**时序组合**。

规则 65：不碰 hunger / condition / food supply —— 生存只作安全检查。
规则 66：建在 `explore ↔ gather_material` 这条唯一有足够个体方差的轴上。
规则 67：`material` 在两个发育世界都合法（只是 2.0 vs 0.5 速率差）→ 同等新颖。

★ manipulation check（本轮新增）★
如果打开新规则后这两个量没变，那么**代码上有新规则、行为上却没有新的
strategy landscape**，probe 太弱：

    命中率      有 explore 前置的 gather 占全部 gather 的比例
    单次收益    每次 gather_material 实际拿到多少材料

★ group-blind ★ 只输出 pooled 量与跨个体方差，不按发育世界分组。
种子 `20000+`。**不碰 `60000–61499`。**
"""

import argparse
import multiprocessing as mp
import os
import statistics
import time
from collections import Counter, deque

WA, WB, COMMON = "丰富世界", "贫瘠世界", "基准"
DEV_DAYS, W_CON = 30, 30
TAU_GRID = (6, 12, 24, 48)              # 滑动窗口长度（tick），升序
ALPHA_GRID = (0.5, 1.0, 2.0, 4.0)       # 加成强度，升序
CHUNK = 25

# 合格条件（跑前冻结）。⚠ 数值是我拟的，需拍板。
C_SURV = 0.99            # ① novel 存活率
C_SURV_DELTA = 0.02      # ① 与规则关闭时的存活率之差
C_TERCILE_MIN = 0.25     # ② 各档平均材料获取量 ≥ 最高档的这个比例（没有一无所获）
C_TERCILE_RATIO = 4.0    # ② 最高/最低 ≤ 这个（没有垄断）
C_HIT_LO, C_HIT_HI = 0.20, 0.80   # ③ 命中率 pooled 区间
C_HIT_SD = 0.10          # ④ 命中率的跨个体 SD（不是所有球走同一序列）
C_TRAJ_TV = 0.02         # ⑤ ON vs OFF 的 pooled 动作分布 TV
C_YIELD_GAIN = 0.10      # ⑥ ON 的单次收益相对 OFF 的最小提升


def _run(NS, life, tau, alpha):
    """跑 novel 窗口，逐 tick 记录动作 —— ★不含任何世界标签★"""
    sim = NS.sim
    ag = life.agent
    infl = list(life.influences)
    if alpha > 0:
        infl.append(NS.discovery_gather(tau, alpha))
    seq, yields = [], []
    alive = True
    for day in range(DEV_DAYS, DEV_DAYS + W_CON):
        for t in range(sim.TICKS_PER_DAY):
            life.world.tick(day, t)
            for inf in infl:
                inf(life.world, ag, day, t, life.inf_rng)
            before = ag.action_log["gather_material"]
            mat_before = ag.inventory["material"]
            yield_now = life.world.p["material_yield"]
            ag._last_act = None
            ag.tick(day, t)
            seq.append(ag._last_act)          # 由 act() 探针记录（见 task 里的 patch）
            if ag.action_log["gather_material"] > before:
                yields.append(ag.inventory["material"] - mat_before)
            if not ag.alive:
                alive = False
                break
        if not alive:
            break
        ag.daily(day)
    return {"seq": seq, "yields": yields, "alive": alive,
            "end_material": ag.inventory["material"]}


def task(job):
    world, seed0, n = job
    import novel_situation as NS
    sim = NS.sim
    sim.COND_RECOVER_AT = 65.0
    sim.COND_DEADZONE_RECOVER = sim.COND_SHELTER_RECOVER = 0.0
    sim.SLEEP_SUPPRESS = sim.HUNGER_URGENCY = 0.0
    sim.SLEEP_EFF_FLOOR = 0.35
    sim.KNOWLEDGE_WEIGHT, sim.KNOWLEDGE_GOAL_WEIGHT, sim.KNOWLEDGE_FORGET = 12.0, 0.25, 0.02

    # 给 Agent 挂一个"本 tick 动作"探针（只读记录，不改 v3 文件）
    if not hasattr(sim.Agent, "_probe_patched"):
        _orig_act = sim.Agent.act

        def act(self, action, day, hour=0):
            self._last_act = action
            return _orig_act(self, action, day, hour)
        sim.Agent.act = act
        sim.Agent._probe_patched = True
        sim.Agent._last_act = None

    grid = [(0, 0.0)] + [(t, al) for t in TAU_GRID for al in ALPHA_GRID]
    out = []
    for s in range(seed0, seed0 + n):
        life = NS.scenarios.make(s, world)
        ok, _ = NS.run_window(life, 0, DEV_DAYS)
        if not ok:
            continue
        NS.level_state(life.agent)
        for tau, al in grid:
            c = NS.fork(life, False)
            w = sim.World(s, **NS.scenarios.WORLDS[COMMON])
            c.world = w
            c.agent.world = w
            r = _run(NS, c, tau or 1, al)
            r["param"] = (tau, al)
            out.append(r)
    return out


def _dispatch(j):
    return task(j[1])


def hit_rate(seq, tau):
    """有 explore 前置的 gather_material 占全部 gather 的比例"""
    hist = deque(maxlen=tau)
    hit = tot = 0
    for a in seq:
        if a == "gather_material":
            tot += 1
            hit += 1 if sum(hist) > 0 else 0
        hist.append(1 if a == "explore" else 0)
    return (hit / tot if tot else None), tot


def dist_of(rs):
    acc = Counter()
    for r in rs:
        acc.update(r["seq"])
    tot = sum(acc.values()) or 1
    return {a: acc[a] / tot for a in acc}


def evaluate(pool, tau, alpha, base_rs):
    rs = [r for r in pool if r["param"] == (tau, alpha)]
    if not rs:
        return False, {}
    n = len(rs)
    surv = sum(r["alive"] for r in rs) / n
    surv0 = sum(r["alive"] for r in base_rs) / len(base_rs)

    hits = [h for h, t in (hit_rate(r["seq"], tau) for r in rs) if h is not None]
    hit_mu = statistics.mean(hits) if hits else 0.0
    hit_sd = statistics.stdev(hits) if len(hits) > 1 else 0.0

    y = [v for r in rs for v in r["yields"]]
    y0 = [v for r in base_rs for v in r["yields"]]
    ymu = statistics.mean(y) if y else 0.0
    ymu0 = statistics.mean(y0) if y0 else 0.0

    # 按 explore 占比分三档，看材料获取量有没有被某一极端垄断
    ex = []
    for r in rs:
        tot = len(r["seq"]) or 1
        ex.append((r["seq"].count("explore") / tot, r["end_material"]))
    ex.sort()
    k = max(1, len(ex) // 3)
    terc = [statistics.mean(m for _, m in ex[i * k:(i + 1) * k] or [(0, 0)])
            for i in range(3)]
    tmax, tmin = max(terc), min(terc)

    d, d0 = dist_of(rs), dist_of(base_rs)
    keys = set(d) | set(d0)
    tv = 0.5 * sum(abs(d.get(x, 0) - d0.get(x, 0)) for x in keys)

    m = {"n": n, "surv": surv, "dsurv": abs(surv - surv0), "hit": hit_mu,
         "hit_sd": hit_sd, "yield": ymu, "yield0": ymu0,
         "ygain": (ymu / ymu0 - 1) if ymu0 else 0.0,
         "terc": terc, "tv": tv}
    m["checks"] = {
        "①存活≥99%且≈OFF": surv >= C_SURV and m["dsurv"] <= C_SURV_DELTA,
        "②无路线垄断": tmax > 0 and tmin >= C_TERCILE_MIN * tmax
                       and tmax / max(tmin, 1e-9) <= C_TERCILE_RATIO,
        "③命中率20-80%": C_HIT_LO <= hit_mu <= C_HIT_HI,
        "④命中率跨个体SD≥.10": hit_sd >= C_HIT_SD,
        "⑤轨迹确实改变": tv >= C_TRAJ_TV,
        "⑥单次收益提升≥10%": m["ygain"] >= C_YIELD_GAIN,
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
    print(f"★ group-blind ★ Probe A2「探路」可行性校准   种子 {a.seed0}–"
          f"{a.seed0+a.seeds-1}   进程 {a.workers}")
    print(f"τ 候选 {TAU_GRID}   α 候选 {ALPHA_GRID}\n", flush=True)

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
    base_rs = [r for r in pool if r["param"] == (0, 0.0)]

    print("\n" + "=" * 100)
    print(f" 逐格结果（字典序：先 τ 升序，再 α 升序）  基线 OFF：存活 "
          f"{sum(r['alive'] for r in base_rs)/len(base_rs):.1%}  "
          f"单次收益 {statistics.mean(v for r in base_rs for v in r['yields']):.3f}")
    print("=" * 100)
    print(f"  {'τ':>4}{'α':>6}{'n':>6}{'存活':>8}{'命中率':>9}{'命中SD':>9}"
          f"{'单次收益':>10}{'收益提升':>10}{'轨迹TV':>9}{'三档材料(低/中/高探索)':>26}")
    print("  " + "-" * 96)

    winner = None
    for tau in TAU_GRID:
        for al in ALPHA_GRID:
            ok, m = evaluate(pool, tau, al, base_rs)
            print(f"  {tau:>4}{al:>6.1f}{m['n']:>6}{m['surv']:>8.1%}{m['hit']:>9.1%}"
                  f"{m['hit_sd']:>9.3f}{m['yield']:>10.3f}{m['ygain']:>+10.1%}"
                  f"{m['tv']:>9.3f}"
                  f"{m['terc'][0]:>9.1f}{m['terc'][1]:>8.1f}{m['terc'][2]:>8.1f}"
                  + ("   ★合格" if ok else ""))
            if ok and winner is None:
                winner = (tau, al, m)

    print("\n" + "=" * 100)
    if winner is None:
        print(" ✗ 没有 (τ, α) 组合满足全部条件 → 判 Probe A2 设计不干净，不产出参数。")
        print(" ⚠ 不降低任何标准去救它。")
        fail = Counter()
        for tau in TAU_GRID:
            for al in ALPHA_GRID:
                _, m = evaluate(pool, tau, al, base_rs)
                for k2, v in m["checks"].items():
                    if not v:
                        fail[k2] += 1
        print("\n 失败频次：")
        for k2, v in fail.most_common():
            print(f"   {k2:<24} {v}/{len(TAU_GRID)*len(ALPHA_GRID)} 格")
    else:
        tau, al, m = winner
        print(f" ★ 可行 ★  τ = {tau} tick   α = {al}")
        print(f"   存活 {m['surv']:.1%}  命中率 {m['hit']:.1%}（SD {m['hit_sd']:.3f}）"
              f"  单次收益 {m['yield']:.3f}（{m['ygain']:+.1%}）  轨迹 TV {m['tv']:.3f}")
        print(" 下一步：写 NOVEL_PREREGISTRATION.md，之后才碰 60000–61499。")
    print("=" * 100)


if __name__ == "__main__":
    mp.freeze_support()
    main()
