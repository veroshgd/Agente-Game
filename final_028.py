"""
实验 028 执行器 —— 严格按 NOVEL_TASK028_PREREGISTRATION.md
============================================================

彩排（已烧种子，可随便跑）：
    python final_028.py --check
    python final_028.py --seed0 10000 --n 300
    python final_028.py --seed0 10000 --n 300 --workers 5     规则 55 自检

正式（**只允许执行一次**）：
    python final_028.py --final

★ 四条工程保护（预注册 §8）★
    ① Seed guard          --final 只接受 seed0=70000, N=1500
    ② One-shot lock       final_028_result.txt 已存在 → 拒绝
    ③ Preflight ledger    开跑前打印并落盘完整种子账本
    ④ 冻结校验            v3_frozen SHA + 任务指纹 + interface028 sha256

★ 判读顺序 ★ **validity gates 先于 task outcome** —— 即使 outcome 已算出，
  也先判 validity，避免看到结果后产生解释自由度。
"""

import argparse
import hashlib
import multiprocessing as mp
import os
import statistics as st
import sys
import time

import interface028 as IF
import novel_task as NT
import stats028 as S

HERE = os.path.dirname(os.path.abspath(__file__))
V3DIR = os.path.join(HERE, "v3_frozen")
WA, WB = "丰富世界", "贫瘠世界"
FINAL_SEED0, FINAL_N = 70000, 1500
CHUNK = 25
ARMS = ("A", "Bp", "Bm", "Cp", "Cm")
SESOI = 1.0
# ⚠ 这【不是】binding gate：028 预注册与修订 01 都没有把 <90% 定义成 G 的判据，
#   也不并入 primary_ok。五臂使用**完全相同**的 survivor intersection，
#   所以 G 仍只由 C± 的 transport gates 裁决。
#   它是 **pre-task attrition diagnostic**；A 作为 027 sampling replication
#   时须与之一并报告。
ATTRITION_REPORT_REF = 0.90

LEDGER = [
    ("0–1499", "development"),
    ("10000–11499", "021 留出集 / 028 transport rehearsal"),
    ("20000–21499", "022 预注册段 / 027 + 028 group-blind calibration"),
    ("50000–51499", "v3 persistence FINAL"),
    ("60000–61499", "027 novel-task FINAL"),
    ("70000–71499", "★028 breadth FINAL★"),
]


def acquire_burn_lock(dirpath, result_name, lock_name, payload):
    """★crash-safe burn lock★ 在生成【任何】trajectory 之前原子创建。

    仅靠 result 文件是不够的：`--final` 跑到一半崩溃时 result 尚未写出，
    但 70000 段的 trajectory 已经生成 —— 按预注册那已经算 burned。
    所以用 `open(..., "x")` 独占创建一个 STARTED 锁，**崩溃也绝不删除**。

        无 STARTED            → 从未烧过
        有 STARTED 无 result  → 启动过但未正常完成；seed 已烧，禁止重跑
        有 STARTED 有 result  → 正常完成；禁止重跑
    """
    res = os.path.join(dirpath, result_name)
    lock = os.path.join(dirpath, lock_name)
    if os.path.exists(res) or os.path.exists(lock):
        raise SystemExit(
            "✗ 028 FINAL 已开始或已完成；70000–71499 已视为 burned，拒绝再次运行。"
            f"（STARTED={os.path.exists(lock)}  result={os.path.exists(res)}）")
    with open(lock, "x", encoding="utf-8") as f:      # 独占创建，已存在则抛错
        f.write(payload)
    return lock


def _test_burn_lock():
    """不触碰 final seeds 的单元测试"""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        acquire_burn_lock(d, "r.txt", "s.lock", "x")          # 第一次成功
        try:
            acquire_burn_lock(d, "r.txt", "s.lock", "x")
        except SystemExit:
            pass
        else:
            raise AssertionError("✗ 第二次创建竟然成功")
        # crash 状态：有 STARTED、无 result → 必须拒绝
        assert os.path.exists(os.path.join(d, "s.lock"))
        assert not os.path.exists(os.path.join(d, "r.txt"))
        try:
            acquire_burn_lock(d, "r.txt", "s.lock", "x")
        except SystemExit:
            pass
        else:
            raise AssertionError("✗ crash 状态下竟然允许重跑")
    with tempfile.TemporaryDirectory() as d:              # 只有 result 也要拒绝
        open(os.path.join(d, "r.txt"), "w").close()
        try:
            acquire_burn_lock(d, "r.txt", "s.lock", "x")
        except SystemExit:
            pass
        else:
            raise AssertionError("✗ 已完成状态下竟然允许重跑")
    print("  ✓ burn lock：首次成功；重复 / crash 状态 / 已完成 三种情形均拒绝")


def preflight():
    bad = 0
    for line in open(os.path.join(V3DIR, "SHA256SUMS.txt"), encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        want, name = line.split(maxsplit=1)
        got = hashlib.sha256(
            open(os.path.join(V3DIR, name), "rb").read()).hexdigest()
        bad += 0 if got.startswith(want) else 1
    if bad:
        raise SystemExit(f"✗ v3_frozen 校验失败（{bad} 个文件）")
    fp = NT.assert_frozen()
    print("✓ v3_frozen 校验通过")
    print(f"✓ 任务参数冻结  α={NT.ALPHA} β={NT.BETA} τ={NT.TAU}  指纹 {fp}")
    print(f"✓ 接口冻结  sha256 {IF.F['sha256'][:16]}…  n_cal={IF.F['n_cal']}"
          f"  rank 冗余 {IF.F['rho_spearman_A_Bperp']:+.4f}")
    print("\n  ── 种子账本（预注册 §7）──")
    for seg, use in LEDGER:
        print(f"    {seg:<16}{use}")
    return fp


def task_sim(job):
    world, seed0, n = job
    import novel_situation as NS
    sim = NS.sim
    sim.COND_RECOVER_AT = 65.0                     # ★规则 55★
    sim.COND_DEADZONE_RECOVER = sim.COND_SHELTER_RECOVER = 0.0
    sim.SLEEP_SUPPRESS = sim.HUNGER_URGENCY = 0.0
    sim.SLEEP_EFF_FLOOR = 0.35
    sim.KNOWLEDGE_WEIGHT, sim.KNOWLEDGE_GOAL_WEIGHT, sim.KNOWLEDGE_FORGET = 12.0, 0.25, 0.02
    out = []
    for s in range(seed0, seed0 + n):
        life = NS.scenarios.make(s, world)
        ok, _ = NS.run_window(life, 0, 30)
        if ok:
            w = sim.World(s, **NS.scenarios.WORLDS["基准"])
            ok, _ = NS.run_window(life, 30, 30, world=w)
        if not ok:
            out.append({"seed": s, "alive": False})
            continue
        NS.level_state(life.agent)
        out.append({"seed": s, "alive": True, "traits": dict(life.agent.traits)})
    return world, seed0, out


def _dispatch(j):
    return j[0](j[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--seed0", type=int, default=10000)
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--test-lock", action="store_true")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    a = ap.parse_args()

    if a.test_lock:
        _test_burn_lock()
        return
    preflight()
    if a.check:
        return

    out_path = os.path.join(HERE, "final_028_result.txt")

    if a.final:
        seed0, N = FINAL_SEED0, FINAL_N
        # ★① seed guard★
        if (a.seed0 not in (10000, FINAL_SEED0)) or \
                (a.n not in (300, FINAL_N)):
            raise SystemExit("✗ --final 时不得同时指定非默认 seed0/n")
        print("\n" + "!" * 76)
        print(f"!! 028 FINAL  seeds {seed0}–{seed0+N-1}  ——  只允许跑一次")
        print("!! 看到结果后不允许再改任何关键设计（预注册 §9）")
        print("!" * 76)
    else:
        seed0, N = a.seed0, a.n
        if seed0 == FINAL_SEED0:
            raise SystemExit("✗ 非 --final 模式不得触碰 70000 段")
        print(f"\n[彩排] seeds {seed0}–{seed0+N-1}  N={N}"
              f"  —— 只验代码路径 / n / gates / joint bootstrap / 确定性")
        print("[彩排] ⛔ 不根据 breadth effect 改任何东西\n")

    # ★② crash-safe burn lock —— 必须在生成任何 trajectory【之前】★
    if a.final:
        nl = chr(10)
        payload = nl.join([
            "028 FINAL STARTED",
            f"seeds={FINAL_SEED0}-{FINAL_SEED0+FINAL_N-1}",
            f"interface_sha={IF.F['sha256']}",
            f"task_fp={NT.config_fingerprint()}",
            "ledger=" + " | ".join(f"{s2}:{u}" for s2, u in LEDGER),
        ]) + nl
        lock = acquire_burn_lock(
            HERE, "final_028_result.txt", "final_028_STARTED.lock", payload)
        print(nl + f"✓ burn lock 已创建（seed ledger + fingerprints 已固化）："
              f"{os.path.basename(lock)}")

    jobs = [(task_sim, (w, s0, min(CHUNK, seed0 + N - s0)))
            for w in (WA, WB) for s0 in range(seed0, seed0 + N, CHUNK)]
    assert sum(j[1][2] for j in jobs) == 2 * N, "✗ 分块覆盖不全"
    store = {WA: [None] * N, WB: [None] * N}
    t0 = time.time()
    with mp.Pool(a.workers) as pool:
        for k, (w, s0, recs) in enumerate(pool.imap_unordered(_dispatch, jobs), 1):
            store[w][s0 - seed0:s0 - seed0 + len(recs)] = recs
            if k % 20 == 0 or k == len(jobs):
                print(f"  {k}/{len(jobs)}  已用 {(time.time()-t0)/60:.1f}min",
                      flush=True)

    dead_a = sum(1 for r in store[WA] if not r["alive"]) / N
    dead_b = sum(1 for r in store[WB] if not r["alive"]) / N
    pairs = [i for i in range(N)
             if store[WA][i]["alive"] and store[WB][i]["alive"]]
    keep = len(pairs) / N
    print("\n" + "=" * 100)
    print(f" pre-task attrition diagnostic（★非 binding gate★）：")
    print(f"   rich {dead_a:.2%} · poor {dead_b:.2%} · "
          f"有效双胞胎 {len(pairs)}/{N} = {keep:.2%}"
          f"   参考量级 {ATTRITION_REPORT_REF:.0%}"
          f"{'' if keep >= ATTRITION_REPORT_REF else '  ⚠ 低于以往量级，须在报告中说明'}")
    print(f"   五臂共用同一 survivor intersection；G 仅由 C± transport gates 裁决")

    # ---- 逐臂：beta / 任务 / 配对差 ----
    allt = [store[w][i]["traits"] for i in pairs for w in (WA, WB)]
    d, betas = {}, {}
    for arm in ARMS:
        betas[arm] = [IF.beta_for(arm, t) for t in allt]
        dv = []
        for i in pairs:
            ra = IF.run_arm(arm, store[WA][i]["traits"], seed0 + i)
            rb = IF.run_arm(arm, store[WB][i]["traits"], seed0 + i)
            dv.append(NT.switch_latency_restricted(ra)
                      - NT.switch_latency_restricted(rb))
        d[arm] = dv

    # ---- ★ gates 先判、先打印 ★ ----
    muA, sdA = st.mean(betas["A"]), st.stdev(betas["A"])
    diag = {}
    for arm, key in (("Bp", "B"), ("Bm", "B"), ("Cp", "Cp"), ("Cm", "Cm")):
        ref = IF.F["x_sorted"][key]
        raws = [IF.raw_readout(t)[key] for t in allt]
        oos = (sum(1 for x in raws if x < ref[0])
               + sum(1 for x in raws if x > ref[-1])) / len(raws)
        bmin, bmax = IF._BETA_A[0], IF._BETA_A[-1]
        bnd = sum(1 for v in betas[arm] if v == bmin or v == bmax) / len(betas[arm])
        diag[arm] = {"oos": oos, "boundary": bnd,
                     "mu": st.mean(betas[arm]), "sd": st.stdev(betas[arm])}
    gates, primary_ok, secondary_ok = S.check_gates(diag, muA, sdA)

    print("\n" + "=" * 100)
    print(" ★ VALIDITY GATES（先于 outcome 判读，预注册 §4）★")
    print("=" * 100)
    print(f"  contemporaneous A: μ={muA:.6f}  SD={sdA:.6f}")
    print(f"  {'臂':<5}{'越界':>9}{'边界质量':>10}{'|Δμ|/SD_A':>12}"
          f"{'|ΔSD|/SD_A':>12}{'support':>9}{'budget':>8}")
    print("  " + "-" * 88)
    for arm in ("Bp", "Bm", "Cp", "Cm"):
        g, dg = gates[arm], diag[arm]
        print(f"  {arm:<5}{dg['oos']:>9.2%}{dg['boundary']:>10.2%}"
              f"{g['dmu']:>12.1%}{g['dsd']:>12.1%}"
              f"{'✓' if g['support'] else '✗':>9}{'✓' if g['budget'] else '✗':>8}")
    print(f"\n  primary  (C±)  {'✓ valid' if primary_ok else '✗ INVALID'}"
          f"      secondary (B±)  {'✓ valid' if secondary_ok else '✗ INVALID'}")
    if N < FINAL_N:
        # ★修订 01 §A★ validity gates 以 N=1500 的 confirmatory run 为准
        se = (2.0 / (2 * len(pairs))) ** 0.5
        print(f"  ⚠ NON-BINDING：N={N} < {FINAL_N}，本次 gate 结果【不构成】对"
              f" frozen transform 的判定")
        print(f"    （|Δμ|/SD_A 的抽样 SE ≈ {se:.1%}，10% 门槛仅约 "
              f"{0.10/se:.1f} 个 SE）—— 仅验代码路径与量级")
    if not primary_ok:
        print(f"  ⚠ {S.CLOSURE_TEXT}")

    # ---- joint same-seed bootstrap ----
    boot = S.joint_bootstrap(d)
    G = S.point_G(d)
    glo, ghi = S.ci(boot["G"])
    rb = min(abs(st.mean(d["Bp"])), abs(st.mean(d["Bm"])))
    rlo, rhi = S.ci(boot["RB"])

    print("\n" + "=" * 100)
    tag = "FINAL" if a.final else "彩排（非 final）"
    print(f" 028 {tag}   seeds {seed0}–{seed0+N-1}   n={len(pairs)}")
    print("=" * 100)
    print(f"  {'臂':<5}{'E（配对差均值）':>16}{'95% CI':>28}")
    print("  " + "-" * 52)
    for arm in ARMS:
        e = st.mean(d[arm])
        lo, hi = S.ci(boot["E"][arm])
        print(f"  {arm:<5}{e:>+16.4f}   [{lo:>+8.4f}, {hi:>+8.4f}]")

    print(f"\n  ★PRIMARY G = min(|E_C+|,|E_C−|) − |E_A|★")
    if not primary_ok:
        print(f"    ✗ INVALID —— gates 未通过，既不许声称 breadth gain，"
              f"也不许声称 no-gain")
    else:
        if glo <= 0 <= ghi:
            v = "✗ 没有证据表明 broader readout 比 A 更强（CI 包含 0）"
        elif glo > SESOI:
            v = "★ functionally meaningful breadth gain established ★"
        elif glo > 0:
            v = "◐ 检测到 breadth gain，但增益低于功能门槛（CI 与 [0,1] 重叠）"
        else:
            v = "◐ CI 完全 < 0：broader readout 反而更弱（见 §6 稀释判读）"
        print(f"    {v}")
    print(f"    G = {G:+.4f} trial   95% CI [{glo:+.4f}, {ghi:+.4f}]"
          f"   SESOI = {SESOI} trial")

    print(f"\n  secondary R_B = min(|E_B+|,|E_B−|)"
          f"{'' if secondary_ok else '  ✗ INVALID'}")
    print(f"    R_B = {rb:.4f}   95% CI [{rlo:+.4f}, {rhi:+.4f}]"
          f"   （B+ {st.mean(d['Bp']):+.4f} · B− {st.mean(d['Bm']):+.4f}）")

    print(f"\n  C± 各自对 ±{SESOI} 等价区间：")
    for arm in ("Cp", "Cm"):
        lo, hi = S.ci(boot["E"][arm])
        s2 = ("整体越过 ±1" if lo > SESOI or hi < -SESOI
              else ("与 ±1 重叠" if lo > 0 or hi < 0 else "含 0"))
        print(f"    {arm}  E={st.mean(d[arm]):+.4f}  [{lo:+.4f}, {hi:+.4f}]  {s2}")

    ea = st.mean(d["A"])
    alo, ahi = S.ci(boot["E"]["A"])
    print(f"\n  ★A 臂 = 027 的 sampling-level replication（与 G 分开判）★")
    print(f"    E_A = {ea:+.4f}  [{alo:+.4f}, {ahi:+.4f}]"
          f"   027 原值 −0.0798 [−0.1632, −0.0035]")
    print(f"    {'✓ 复制出同向可检出效应' if (alo>0 or ahi<0) and ea*(-0.0798)>0 else '⚠ 未复制 027 的窄接口效应 —— 论文须如实写明'}")

    txt = os.path.join(HERE, "final_028_result.txt" if a.final
                       else "final_028_rehearsal.txt")
    with open(txt, "w", encoding="utf-8") as f:
        f.write(f"028 {tag}  seeds {seed0}-{seed0+N-1}  n={len(pairs)}\n")
        f.write(f"interface_sha={IF.F['sha256']}  task_fp={NT.config_fingerprint()}\n")
        f.write(f"attrition rich={dead_a:.4f} poor={dead_b:.4f} keep={keep:.4f}\n")
        f.write(f"gates primary={primary_ok} secondary={secondary_ok}\n")
        for arm in ("Bp", "Bm", "Cp", "Cm"):
            g, dg = gates[arm], diag[arm]
            f.write(f"gate\t{arm}\t{dg['oos']:.5f}\t{dg['boundary']:.5f}"
                    f"\t{g['dmu']:.5f}\t{g['dsd']:.5f}\n")
        for arm in ARMS:
            lo, hi = S.ci(boot["E"][arm])
            f.write(f"E\t{arm}\t{st.mean(d[arm]):+.6f}\t{lo:+.6f}\t{hi:+.6f}\n")
        f.write(f"G\t{G:+.6f}\t{glo:+.6f}\t{ghi:+.6f}\n")
        f.write(f"RB\t{rb:.6f}\t{rlo:+.6f}\t{rhi:+.6f}\n")
        f.write("ledger " + " | ".join(f"{s}:{u}" for s, u in LEDGER) + "\n")
    print(f"\n已写入 {txt}")


if __name__ == "__main__":
    mp.freeze_support()
    sys.stdout.reconfigure(encoding="utf-8")
    main()
