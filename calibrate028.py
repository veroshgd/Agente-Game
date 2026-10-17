"""
实验 028 常数冻结 —— ★ group-blind ★
=====================================

运行：  python calibrate028.py          → 写出 interface028_frozen.json

★★ 结构性 group-blind ★★
只收集 traits 三元组，**不带任何世界标签**；`_assert_blind()` 强制检查
池子里没有可用于分组的字段。本脚本**物理上算不出 rich/poor 差异**。

--------------------------------------------------------------------------
要冻结什么（五个问题一次解决）
--------------------------------------------------------------------------
① **负 beta** —— 不用"线性缩放 + 钳位"，改用 **quantile mapping**：
   把每个 readout 的排序映射到 **A 臂（027 原接口）的冻结 beta 边际分布**。
   于是 support / mean / SD / 偏度 / 尾部 / 钳位率 **全部与 A 相同**，
   负 beta 问题**不存在**，也不需要解释"主动回避未知项"。

② **C+ / C− 预算不等** —— quantile mapping 之后**自动消失**：
   两者都获得 A 的整条边际分布，**唯一剩下的差异是"哪些 agent 拿到较大的
   beta"**（排序），这正是我们要比较的东西。

③ **共线性** —— 实测 `corr(x_A, industry) = −0.8781`，raw industry 基本是
   A 的反向镜像。若直接用它，`C− = A − B ≈ 2A`，标准化后又变回很像 A，
   **测到的不是 breadth 而是两个共线变量的加减**。
   所以正式 breadth test 用 **正交残差（OLS 残差）**：

       slope = Cov(a_ord, x_B) / Var(a_ord)
       x_B⊥  = (x_B − slope · a_ord) / SD(残差)

   ⚠ **不要用** `(x_B − ρ·x_A)/√(1−ρ²)` —— 那个公式只在两者**都已标准化**
     时才正交；实测 σ(curiosity)=20.87、σ(caution)=29.55，套那个公式会
     **残留 +0.8629 的相关**（被断言抓到过，见规则 81）。

   ⚠ 正交化的基准必须是 **a_ord = curiosity − caution**，即
     **A 臂 beta 实际的排序变量**，而不是 `z(cur) − z(cau)`。
     因为 A 的 beta = clamp((cur−cau+100)/200) 是 **raw 差**的单调函数；
     而 σ_cur ≠ σ_cau，所以 z 差与 raw 差**排序并不相同**
     （Spearman 0.9999，接近但不等于 1）。
     quantile mapping 完全是**基于排序**的，所以必须对齐排序变量。
   B 的含义随之变精确：**不是"industry 能不能迁移"，而是
   "industry 中不被 exploration 轴解释的那部分历史信息能不能迁移"。**

④ **符号任意性** —— 正交化后 B⊥ 更没有天然方向，所以双符号全跑。

⑤ **A 保持 027 原样** —— A 不重新标准化，其余臂来适配它。
   A 因而是货真价实的 **sampling-level replication arm**（规则 80）。

--------------------------------------------------------------------------
⚠ 所有常数只在 calibration block（20000–21499）上估一次并冻结，
   **final 阶段只应用、绝不重估**。
"""

import hashlib
import json
import multiprocessing as mp
import os
import statistics as st

import novel_task as NT

WA, WB = "丰富世界", "贫瘠世界"
CAL_SEED0, CAL_N = 20000, 1500
CHUNK = 25
RANK_GATE = 0.05     # ★practical redundancy gate★ 看幅度，不做显著性检验
                     #  （n=2936 下极小的相关也可能"显著"）
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "interface028_frozen.json")


def task(job):
    """★ 只回传 traits 三元组，无任何世界标签 ★"""
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


def _assert_blind(pool):
    """池子必须只是 [cur, cau, ind] 的裸三元组 —— 没有任何可分组字段"""
    for r in pool[:100]:
        assert isinstance(r, list) and len(r) == 3 and all(
            isinstance(v, float) for v in r), f"✗ group-blind 被破坏：{r}"


def main():
    workers = max(1, (os.cpu_count() or 2) - 2)
    jobs = [(task, (w, s0, min(CHUNK, CAL_SEED0 + CAL_N - s0)))
            for w in (WA, WB)
            for s0 in range(CAL_SEED0, CAL_SEED0 + CAL_N, CHUNK)]
    pool = []
    with mp.Pool(workers) as p:
        for recs in p.imap_unordered(_dispatch, jobs):
            pool.extend(recs)
    _assert_blind(pool)
    n = len(pool)
    print(f"★ group-blind ★ calibration pool n={n}"
          f"（seeds {CAL_SEED0}–{CAL_SEED0+CAL_N-1}，两世界混合，无标签）")

    cur = [p[0] for p in pool]
    cau = [p[1] for p in pool]
    ind = [p[2] for p in pool]
    mc, sc = st.mean(cur), st.stdev(cur)
    ma, sa = st.mean(cau), st.stdev(cau)
    mi, si = st.mean(ind), st.stdev(ind)

    z = lambda v, m, s: (v - m) / s
    # ★正交化基准 = A 臂 beta 的【实际排序变量】★（见 docstring 的说明）
    a_ord = [p[0] - p[1] for p in pool]
    m_ao, s_ao = st.mean(a_ord), st.stdev(a_ord)
    xA = [(v - m_ao) / s_ao for v in a_ord]          # 标准化后的 A 轴
    xB = [z(p[2], mi, si) for p in pool]
    rho = st.covariance(xA, xB) / (st.stdev(xA) * st.stdev(xB))
    print(f"  corr(A轴, industry_raw) = {rho:+.4f}"
          f"   ← raw industry 与 exploration 轴高度共线")

    # ★正交残差★ 用 OLS 残差，不用 (x_B − ρ·x_A)/√(1−ρ²) ——
    # 后者只在 x_A、x_B **都已标准化**时才正交，而这里
    # x_A = z(cur) − z(cau) 的 SD 是 1.93（不是 1），套那个公式会残留 +0.86 的相关。
    # （这个错误被下面的 assert 抓到过，保留说明以免重犯。）
    slope = st.covariance(xA, xB) / st.variance(xA)
    xBo_raw = [b - slope * a for a, b in zip(xA, xB)]
    s_res = st.stdev(xBo_raw)
    xBo = [v / s_res for v in xBo_raw]                     # 缩放到单位方差
    rho2 = st.covariance(xA, xBo) / (st.stdev(xA) * st.stdev(xBo))
    print(f"  corr(A轴, B⊥)          = {rho2:+.6f}   ← Pearson 正交化后")
    assert abs(rho2) < 1e-9, "✗ Pearson 正交化失败"

    # ★★ rank-space redundancy gate ★★
    # quantile mapping 完全基于排序，所以 Pearson 正交【不够】——
    # 必须检查真正决定 coupling assignment 的 rank space。
    def _rank(v):
        o = sorted(range(len(v)), key=lambda i: v[i])
        r = [0] * len(v)
        for k, i in enumerate(o):
            r[i] = k
        return r

    def _spearman(u, v):
        ru, rv = _rank(u), _rank(v)
        return st.covariance(ru, rv) / (st.stdev(ru) * st.stdev(rv))

    rho_s = _spearman(a_ord, xBo)      # a_ord 决定 beta_A 的排序
    print(f"  Spearman(beta_A 排序, B⊥ 排序) = {rho_s:+.4f}"
          f"   门槛 |ρs| < {RANK_GATE}")
    assert abs(rho_s) < RANK_GATE, (
        f"✗ rank-space 冗余 {rho_s:+.4f} 超过门槛 —— quantile mapping 后两条"
        f"接口仍共享大量排序信息，应改用 rank-space / normal-score 残差化")

    xCp = [a + b for a, b in zip(xA, xBo)]
    xCm = [a - b for a, b in zip(xA, xBo)]

    # A 臂 = 027 原接口，一动不动
    ns = [min(1.0, max(0.0, (p[0] - p[1] + 100.0) / 200.0)) for p in pool]
    betaA = sorted(NT.BETA * v for v in ns)
    print(f"  A 臂（027 原接口）: μ={st.mean(betaA):.6f}  SD={st.stdev(betaA):.6f}"
          f"  范围 [{betaA[0]:.6f}, {betaA[-1]:.6f}]")

    frozen = {
        "n_cal": n, "cal_seed0": CAL_SEED0, "cal_n": CAL_N,
        "mu": {"curiosity": mc, "caution": ma, "industry": mi},
        "sd": {"curiosity": sc, "caution": sa, "industry": si},
        "rho_A_Braw": rho, "rho_spearman_A_Bperp": rho_s,
        "resid_slope": slope, "resid_sd": s_res,
        "a_ord_mu": m_ao, "a_ord_sd": s_ao,
        "betaA_sorted": betaA,
        "x_sorted": {"B": sorted(xBo), "Cp": sorted(xCp), "Cm": sorted(xCm)},
        "task_fingerprint": NT.config_fingerprint(),
    }
    payload = json.dumps(frozen, sort_keys=True, separators=(",", ":"))
    frozen["sha256"] = hashlib.sha256(payload.encode()).hexdigest()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(frozen, f, ensure_ascii=False)

    print(f"\n  quantile mapping 之后，五个臂的 beta 边际分布【完全相同】")
    print(f"  （support / mean / SD / 偏度 / 尾部 / 钳位率 全部等于 A）")
    print(f"  唯一差异 = 哪些 agent 拿到较大的 beta（排序）")
    print(f"\n已冻结 → {OUT}")
    print(f"  sha256 {frozen['sha256'][:32]}…")
    print(f"  任务指纹 {frozen['task_fingerprint']}")
    print("\n⚠ final 阶段只应用这些常数，绝不重估。")


if __name__ == "__main__":
    mp.freeze_support()
    main()
