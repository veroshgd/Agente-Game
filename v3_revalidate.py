"""
v3 机制重验 —— 同种子对照 v2，只有 COND_RECOVER_AT 变了
===========================================================

运行：  python v3_revalidate.py                （全量，约 1 小时，13 进程）
        python v3_revalidate.py --quick        （N=300/BOOT=500，约 5 分钟，先看方向）
        python v3_revalidate.py --only 021     （只跑 021§3）

★ 这不是新的 confirmatory experiment ★
------------------------------------
我们已经看过数据、改了模型，而且 65 本身就是诊断实验选出来的。
所以这一步的正确名字是 **v3 mechanistic revalidation / robustness reanalysis**，
它回答的是"修掉 survival confound 之后，依赖它的结论变成什么"，
**不能承担最终确认**。最终确认要等模型完全冻结后，用一段从未跑过的新种子做。

★ 为什么用旧种子 —— 这是优势不是问题 ★
唯一变量是 `COND_RECOVER_AT: 30 → 65`。同种子对照能干净地把
"结论变了"归因到这一个数上，而不是归因到"换了一批球"。

★ v2 臂怎么来的 ★
`v2_frozen/` 与主目录逐位对比过：**唯一的可执行差异就是 COND_RECOVER_AT**
（其余全是注释和新增的 MODEL_VERSION）。所以 v2 臂 = 在 v3 代码里设回 30.0，
和跑 `v2_frozen/` 完全等价，但省掉了两套 import 路径的麻烦。

重验哪三项（011–020 不重跑 —— 它们是 development history，任务已完成）：

  021 §3   地板消融        `−全部地板①②` 在 N=1500 上还站不站得住
  022 P1   接线后无地板 >1  预注册判据：bootstrap CI 下界 > 1.00
  022 P2   非嵌套删除      删 knowledge 会不会让持久性塌掉

外加 **hardship 触发诊断**（规则 50 的直接待办）：
`fears_hunger` 触发率 / 首次触发日 / anchor 存在率 / 存活率。
⚠ 主效应一律报**全部预定义种子**，不只报 86% 的触发者 ——
   "有没有触发"本身是模拟的产物，事后只取触发者会重新制造选择效应。
   触发者内部的结果只作 secondary descriptive analysis。
"""

import argparse
import io
import multiprocessing as mp
import os
import time
from contextlib import redirect_stdout

WA, WB, COMMON = "丰富世界", "贫瘠世界", "基准"
VERSIONS = [("v2", 30.0), ("v3", 65.0)]
K22 = (12.0, 0.25, 0.02)          # 022 打开时的 KNOWLEDGE_* 三件套
CHUNK = 250


def _setup(rec_at):
    import sim
    sim.COND_RECOVER_AT = rec_at
    sim.COND_DEADZONE_RECOVER = 0.0
    sim.COND_SHELTER_RECOVER = 0.0
    return sim


# ---------------------------------------------------------------- 021 §3
def task_021(job):
    ver, rec_at, seed0, label, cfg, n_seeds, n_perm = job
    sim = _setup(rec_at)
    import significance_main as S
    S.N_PERM = n_perm
    sim.KNOWLEDGE_WEIGHT = sim.KNOWLEDGE_GOAL_WEIGHT = sim.KNOWLEDGE_FORGET = 0.0
    buf = io.StringIO()
    with redirect_stdout(buf):
        S.run(label, cfg, n_seeds, seed0)
    return ("021", ver, f"seeds {seed0}+", label, buf.getvalue().strip(), None)


# ---------------------------------------------------------------- 022 P1
def task_p1(job):
    ver, rec_at, tag, kw, label, cfg, n_seeds, n_boot, n_perm = job
    sim = _setup(rec_at)
    import p1_test as P
    P.N_SEEDS, P.N_BOOT, P.N_PERM = n_seeds, n_boot, n_perm
    sim.KNOWLEDGE_WEIGHT, sim.KNOWLEDGE_GOAL_WEIGHT, sim.KNOWLEDGE_FORGET = kw
    buf = io.StringIO()
    with redirect_stdout(buf):
        ret = P.analyse(label, cfg)
    return ("P1", ver, tag, label, buf.getvalue().strip(), ret)


# ---------------------------------------------------------------- 022 P2
def task_p2(job):
    ver, rec_at, label, wipe, n_seeds, n_boot = job
    sim = _setup(rec_at)
    import p2_test as P
    import p1_test as P1
    P.N_SEEDS, P1.N_BOOT = n_seeds, n_boot
    sim.KNOWLEDGE_WEIGHT, sim.KNOWLEDGE_GOAL_WEIGHT, sim.KNOWLEDGE_FORGET = K22
    buf = io.StringIO()
    with redirect_stdout(buf):
        ret = P.analyse(label, wipe)
    return ("P2", ver, "seeds 20000+", label, buf.getvalue().strip(), ret)


# ------------------------------------------------- hardship 触发诊断（规则 50）
def task_trigger(job):
    """全部种子都统计 —— 死掉的也算，不做任何事后筛选"""
    ver, rec_at, world, floor_off, seed0, n = job
    sim = _setup(rec_at)
    import scenarios
    import persistence_ablation as PA
    sim.KNOWLEDGE_WEIGHT, sim.KNOWLEDGE_GOAL_WEIGHT, sim.KNOWLEDGE_FORGET = K22

    alive = trig = anchor = 0
    first_days = []
    scenarios.make = PA.patched_make(False, floor_off)
    try:
        for s in range(seed0, seed0 + n):
            life = scenarios.make(s, world)
            ag = life.agent
            first = None
            dead = False
            for day in range(60):
                if day == 30:                       # 第 30 天移植到基准
                    w = sim.World(s, **scenarios.WORLDS[COMMON])
                    life.world, ag.world = w, w
                for t in range(sim.TICKS_PER_DAY):
                    life.world.tick(day, t)
                    for inf in life.influences:
                        inf(life.world, ag, day, t, life.inf_rng)
                    ag.tick(day, t)
                    if first is None and "fears_hunger" in ag.flags:
                        first = day
                    if not ag.alive:
                        dead = True
                        break
                if dead:
                    break
                ag.daily(day)
            alive += not dead
            if first is not None:
                trig += 1
                first_days.append(first)
            if getattr(ag, "_hardship_anchor", None) is not None:
                anchor += 1
    finally:
        scenarios.make = PA._orig_make
    return ("TRIG", ver, world, "地板全关" if floor_off else "完整架构",
            (alive, trig, anchor, first_days, n))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--only", default="all",
                    help="all / 021 / p1 / p2 / trig（可逗号分隔）")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()

    N = 300 if a.quick else 1500
    BOOT = 500 if a.quick else 3000
    PERM = 2000 if a.quick else 10000
    want = {w.strip() for w in a.only.split(",")} if a.only != "all" \
        else {"021", "p1", "p2", "trig"}

    jobs = []
    if "021" in want:
        for ver, rec in VERSIONS:
            for seed0 in (0, 10000):
                for label, cfg in [("完整架构", dict()), ("−全部地板①②", dict(floor=True))]:
                    jobs.append((task_021, (ver, rec, seed0, label, cfg, N, PERM)))
    if "p1" in want:
        for ver, rec in VERSIONS:
            for tag, kw in [("022 关闭", (0.0, 0.0, 0.0)), ("022 打开", K22)]:
                for label, cfg in [("完整架构", dict()), ("−全部地板①②", dict(floor=True))]:
                    jobs.append((task_p1, (ver, rec, tag, kw, label, cfg, N, BOOT, PERM)))
    if "p2" in want:
        for ver, rec in VERSIONS:
            for label, wipe in [("① 什么都不删（=P1）", set()),
                                ("② 只删语义 knowledge", {"semantic"}),
                                ("③ 只删情节 memories", {"episodic"}),
                                ("④ 只删 flags", {"flags"}),
                                ("⑤ 删语义+情节+flags", {"semantic", "episodic", "flags"})]:
                jobs.append((task_p2, (ver, rec, label, wipe, N, BOOT)))
    if "trig" in want:
        for ver, rec in VERSIONS:
            for world in (WA, WB):
                for fo in (False, True):
                    for s0 in range(20000, 20000 + N, CHUNK):
                        jobs.append((task_trigger,
                                     (ver, rec, world, fo, s0, min(CHUNK, 20000 + N - s0))))

    print(f"v3 机制重验   {len(jobs)} 个任务   N={N} BOOT={BOOT} PERM={PERM}   "
          f"进程数 {a.workers}")
    print("唯一变量：COND_RECOVER_AT  v2=30.0  vs  v3=65.0\n", flush=True)

    t0, out = time.time(), []
    with mp.Pool(a.workers) as pool:
        for k, r in enumerate(pool.imap_unordered(_dispatch, jobs), 1):
            out.append(r)
            el = time.time() - t0
            print(f"  [{k}/{len(jobs)}] {r[0]:<5}{r[1]:<4}{str(r[2]):<14}{r[3]:<22}"
                  f"已用 {el/60:.1f}min 剩余 ~{el/k*(len(jobs)-k)/60:.1f}min", flush=True)

    report(out, N)


def _dispatch(job):
    fn, args = job
    return fn(args)


def report(out, N):
    for tag, title, hdr in [
            ("021", "021 §3 · 地板消融（022 关闭）",
             f"  {'条件':<16}{'n':>6}{'分子TV':>9}{'基线TV':>9}{'比值':>8}"
             f"{'δ均值':>10}{'dz':>7}{'δ>0':>8}{'p':>10}"),
            ("P1", "022 P1 · 接线后无地板档还能不能 > 1", None),
            ("P2", "022 P2 · 非嵌套删除", None)]:
        rows = [r for r in out if r[0] == tag]
        if not rows:
            continue
        print("\n" + "=" * 108)
        print(f" {title}   ★ v2 vs v3 同种子对照 ★")
        print("=" * 108)
        groups = sorted({(r[2], r[3]) for r in rows})
        for grp, label in groups:
            print(f"\n  ── {grp} · {label} ──")
            for ver, _ in VERSIONS:
                line = next((r[4] for r in rows
                             if r[1] == ver and r[2] == grp and r[3] == label), None)
                if line:
                    print(f"    {ver}  {line.strip()}")

    trig = [r for r in out if r[0] == "TRIG"]
    if trig:
        print("\n" + "=" * 108)
        print(" hardship 触发诊断（规则 50）★ 全部预定义种子，不做事后筛选 ★")
        print("=" * 108)
        print(f"  {'版本':<5}{'世界':<10}{'架构':<10}{'存活%':>8}"
              f"{'触发率%':>10}{'anchor%':>10}{'首次触发日 中位':>16}")
        print("  " + "-" * 74)
        agg = {}
        for _, ver, world, arch, (al, tr, an, fd, n) in trig:
            a_, t_, an_, f_, n_ = agg.get((ver, world, arch), (0, 0, 0, [], 0))
            agg[(ver, world, arch)] = (a_ + al, t_ + tr, an_ + an, f_ + fd, n_ + n)
        for key in sorted(agg):
            al, tr, an, fd, n = agg[key]
            fd_sorted = sorted(fd)
            med = fd_sorted[len(fd_sorted) // 2] if fd_sorted else float("nan")
            print(f"  {key[0]:<5}{key[1]:<10}{key[2]:<10}{al/n:>7.1%}"
                  f"{tr/n:>9.1%}{an/n:>9.1%}{med:>15.0f}")
        print("\n  ⚠ 触发率 v2→v3 的落差要写进 021§3 重跑的报告里 —— 消融的分母变了。")
        print("  ⚠ 主因果检验用全部种子；触发者子集只能作 secondary descriptive。")


if __name__ == "__main__":
    mp.freeze_support()
    main()
