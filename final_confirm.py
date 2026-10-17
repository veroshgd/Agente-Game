"""
FINAL CONFIRMATION —— 严格按 FINAL_PREREGISTRATION.md 执行
============================================================

调通（开发种子，可以随便跑）：
    python final_confirm.py --check                    只核对 hash + frozen import
    python final_confirm.py --n 200                    小样本走通全流程
    python final_confirm.py --n 200 --workers 5        规则 55 自检：结果须逐位相同

正式（**只允许执行一次**）：
    python final_confirm.py --final

★ 本脚本从 `v3_frozen/` 导入模型 ★
不是从主目录。主目录的文件随时可能被后续实验改动；预注册锁的是 frozen 那份。
启动时强制核对 `v3_frozen/SHA256SUMS.txt`，对不上直接拒绝运行。

★ 五个条件（预注册第 6 节）★
    H1    完整架构        022 ON    不删      主效应
    P1    −全部地板①②     022 ON    不删      地板全关后还站不站得住
    P2②   −全部地板①②     022 ON    删 knowledge
    NC③   −全部地板①②     022 ON    删 memories        阴性对照：须与 P1 逐位相同
    R52   −全部地板①②     022 OFF   不删      规则 52 的裁决 ★唯一真正未知的一项★

★ 统计（预注册第 5 节）★
    基线    同世界跨种子 TV，随机配对重复 K=5（规则 35）
    CI      cluster bootstrap 按 agent 重采样 3000 次，2.5/97.5 分位
    p       逐种子 δ 的符号置换 10000 次，p=(hits+1)/(n_perm+1)

★ 规则 55 ★ 每个子任务开头显式设定所有全局量，绝不靠继承。
"""

import argparse
import hashlib
import multiprocessing as mp
import os
import random
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
V3DIR = os.path.join(HERE, "v3_frozen")

WA, WB, COMMON = "丰富世界", "贫瘠世界", "基准"
SPLIT, TOTAL = 30, 60
BASE_K = 5
N_BOOT = 3000
N_PERM = 10000
CHUNK = 50

FINAL_SEED0, FINAL_N = 50000, 1500        # 预注册第 3 节。只跑一次。

# 预注册修订 A（第 5.5 节）：CI 下界判据改为三值。
# 门槛 0.01 ≈ 10 × 实测蒙特卡洛 SD(0.00097)。跑前定死。
BOUNDARY = 0.01
DIAG_AT = 0.02          # |lo−1| 小于这个值就加跑边界诊断（只影响报告）
DIAG_SEEDS = [777 + 1000 * r for r in range(8)]

# (标签, 地板全关, 022 打开, 移植那刻删什么)
CONDITIONS = [
    ("H1  完整架构",        False, True,  frozenset()),
    ("P1  −全部地板①②",     True,  True,  frozenset()),
    ("P2② 删 knowledge",    True,  True,  frozenset({"semantic"})),
    ("NC③ 删 memories",     True,  True,  frozenset({"episodic"})),
    ("R52 −地板 · 022关",   True,  False, frozenset()),
]


# ---------------------------------------------------------------- 冻结校验
def verify_frozen(verbose=True):
    sums = os.path.join(V3DIR, "SHA256SUMS.txt")
    if not os.path.exists(sums):
        raise SystemExit(f"✗ 找不到 {sums}")
    bad, n = [], 0
    for line in open(sums, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        want, name = line.split(maxsplit=1)
        p = os.path.join(V3DIR, name)
        if not os.path.exists(p):
            bad.append(f"{name}: 文件不存在")
            continue
        got = hashlib.sha256(open(p, "rb").read()).hexdigest()
        n += 1
        if got != want:
            bad.append(f"{name}: {got[:16]} ≠ {want[:16]}")
    if bad:
        print("✗ v3_frozen 校验失败：")
        for b in bad:
            print("   ", b)
        raise SystemExit("拒绝运行。预注册第 0 节：对不上就不要跑。")
    if verbose:
        print(f"✓ v3_frozen 校验通过（{n} 个文件）")
    return n


def load_frozen():
    """从 v3_frozen 导入模型，并断言拿到的确实是冻结的那一份"""
    if V3DIR not in sys.path:
        sys.path.insert(0, V3DIR)
    import sim, scenarios
    import persistence_ablation as PA
    for m in (sim, scenarios, PA):
        assert os.path.abspath(m.__file__).startswith(V3DIR), \
            f"✗ {m.__name__} 来自 {m.__file__}，不是 v3_frozen"
    assert sim.MODEL_VERSION == "v3", f"✗ MODEL_VERSION={sim.MODEL_VERSION}"
    return sim, scenarios, PA


# ---------------------------------------------------------------- 模拟
def wipe(agent, what):
    """★非嵌套★ 每一档只删一样。与 p2_test.wipe_at_transplant 同语义。
    trait_floor / trait_identity 永不在此处删 —— 那是 floor 消融的事。"""
    if "semantic" in what:
        agent.knowledge = {}
        agent.knowledge_strength = {}
    if "episodic" in what:
        agent.memories = []
    if "flags" in what:
        agent.flags = set()


def task_sim(job):
    """一个条件 × 一个世界 × 一个种子块 → 每颗种子的归一化窗口矩阵（死了给 None）"""
    ci, world, seed0, n = job
    from collections import Counter

    sim, scenarios, PA = load_frozen()
    label, floor_off, k22, what = CONDITIONS[ci]

    # ★规则 55★ 显式设定，不靠继承
    sim.COND_RECOVER_AT = 65.0
    sim.COND_DEADZONE_RECOVER = 0.0
    sim.COND_SHELTER_RECOVER = 0.0
    sim.SLEEP_SUPPRESS = sim.HUNGER_URGENCY = 0.0
    sim.SLEEP_EFF_FLOOR = 0.35
    (sim.KNOWLEDGE_WEIGHT, sim.KNOWLEDGE_GOAL_WEIGHT, sim.KNOWLEDGE_FORGET) = \
        (12.0, 0.25, 0.02) if k22 else (0.0, 0.0, 0.0)

    def to_mat(w):
        out = []
        for h in w:
            tot = sum(h.values()) or 1
            out.append(tuple(h[x] / tot for x in sim.ACTIONS))
        return tuple(out)

    scenarios.make = PA.patched_make(False, floor_off)
    res = []
    try:
        for s in range(seed0, seed0 + n):
            life = scenarios.make(s, world)
            ag = life.agent

            def phase(d0, d1):
                for day in range(d0, d1):
                    for t in range(sim.TICKS_PER_DAY):
                        life.world.tick(day, t)
                        for inf in life.influences:
                            inf(life.world, ag, day, t, life.inf_rng)
                        ag.tick(day, t)
                        if not ag.alive:
                            return False
                    ag.daily(day)
                return True

            if not phase(0, SPLIT):
                res.append(None)
                continue
            snap = [Counter(c) for c in ag.action_by_hour]
            w = sim.World(s, **scenarios.WORLDS[COMMON])
            life.world, ag.world = w, w
            wipe(ag, what)                       # ★就在移植这一刻★
            if not phase(SPLIT, TOTAL):
                res.append(None)
                continue
            res.append(to_mat([Counter(c) - snap[h]
                               for h, c in enumerate(ag.action_by_hour)]))
    finally:
        scenarios.make = PA._orig_make
    return ci, world, seed0, res


# ---------------------------------------------------------------- 统计
def mat_tv(a, b):
    """与 transplant.window_tv 等价（输入已按小时归一化）"""
    return sum(0.5 * sum(abs(x - y) for x, y in zip(ha, hb))
               for ha, hb in zip(a, b)) / len(a)


def shuffled_base(ws, k, rng):
    """规则 35：随机配对重复 K 次（与 p1_test.shuffled_base 同语义）"""
    out, idx = [], list(range(len(ws)))
    for _ in range(k):
        rng.shuffle(idx)
        out += [mat_tv(ws[idx[j]], ws[idx[j + 1]])
                for j in range(0, len(idx) - 1, 2)]
    return out


def task_stats(job):
    """一个条件的全部统计。放子进程里跑 —— bootstrap 是大头。"""
    ci, wa, wb, dead_a, dead_b, n_seeds = job
    label = CONDITIONS[ci][0]
    n = len(wa)
    # 预注册第 4 节：有效 n < 1000（= N=1500 的 2/3，死亡率 > 33%）判为【无效】。
    # 小样本调试运行按同一个比例走，否则每次调试都会被判无效。
    floor_n = 1000 if n_seeds >= FINAL_N else max(30, (2 * n_seeds) // 3)
    if n < floor_n:
        return ci, dict(label=label, n=n, invalid=True,
                        dead_a=dead_a, dead_b=dead_b, n_seeds=n_seeds)

    rng = random.Random(777)
    treat = [mat_tv(wa[k], wb[k]) for k in range(n)]
    base = shuffled_base(wa, BASE_K, rng) + shuffled_base(wb, BASE_K, rng)
    ratio = statistics.mean(treat) / statistics.mean(base)

    boots = []                                   # cluster bootstrap，按 agent
    for _ in range(N_BOOT):
        pick = [rng.randrange(n) for _ in range(n)]
        t = [treat[i] for i in pick]
        b = (shuffled_base([wa[i] for i in pick], BASE_K, rng) +
             shuffled_base([wb[i] for i in pick], BASE_K, rng))
        boots.append(statistics.mean(t) / statistics.mean(b))
    boots.sort()
    lo, hi = boots[int(.025 * N_BOOT)], boots[int(.975 * N_BOOT)]

    drng = random.Random(12345)                  # 逐种子 δ
    deltas = []
    for k in range(n):
        opp = []
        for _ in range(BASE_K):
            j = drng.randrange(n - 1); j = j if j < k else j + 1
            opp.append(mat_tv(wa[k], wa[j]))
            j = drng.randrange(n - 1); j = j if j < k else j + 1
            opp.append(mat_tv(wb[k], wb[j]))
        deltas.append(treat[k] - statistics.mean(opp))

    prng = random.Random(999)
    obs = statistics.mean(deltas)
    hits = sum(1 for _ in range(N_PERM)
               if abs(statistics.mean(d if prng.random() < .5 else -d
                                      for d in deltas)) >= abs(obs))
    p = (hits + 1) / (N_PERM + 1)
    sd = statistics.stdev(deltas)
    return ci, dict(label=label, n=n, invalid=False, ratio=ratio, lo=lo, hi=hi,
                    delta=obs, dz=obs / sd if sd else 0.0, p=p,
                    dead_a=dead_a, dead_b=dead_b, n_seeds=n_seeds,
                    fingerprint=round(statistics.mean(treat), 12))


def task_boundary(job):
    """边界诊断（预注册修订 A）：换分析种子重跑 bootstrap，只报告，不参与判读。"""
    ci, wa, wb, seed = job
    n = len(wa)
    rng = random.Random(seed)
    treat = [mat_tv(wa[k], wb[k]) for k in range(n)]
    boots = []
    for _ in range(N_BOOT):
        pick = [rng.randrange(n) for _ in range(n)]
        b = (shuffled_base([wa[i] for i in pick], BASE_K, rng) +
             shuffled_base([wb[i] for i in pick], BASE_K, rng))
        boots.append(statistics.mean(treat[i] for i in pick) / statistics.mean(b))
    boots.sort()
    return ci, seed, boots[int(.025 * N_BOOT)]


def _dispatch(job):
    fn, args = job
    return fn(args)


# ---------------------------------------------------------------- 判据
def verdicts(R, out):
    def ci_ok(k):
        """预注册修订 A：三值判读。返回 '过' / '不过' / '边界' / '无效'"""
        r = R.get(k)
        if not r or r["invalid"]:
            return "无效"
        d = r["lo"] - 1.0
        if d >= BOUNDARY:
            return "过"
        if d <= -BOUNDARY:
            return "不过"
        return "边界"

    def mark(k):
        v = ci_ok(k)
        return {"过": "✓ 过", "不过": "✗ 不过",
                "边界": "◐ 落在检出边界，本判据无法裁决",
                "无效": "—— 无效 ——"}[v]

    P = out.append
    bad = [R[k]["label"] for k in sorted(R) if R[k]["invalid"]]
    if bad:
        P("")
        P("=" * 100)
        P(f" ⚠ 以下条件有效 n 不足，判为【无效】而非「不显著」：{', '.join(bad)}")
        P(" 判据无法裁决，下面只输出仍然有效的部分。")
        P("=" * 100)

    def fmt(k):
        r = R.get(k)
        if not r or r["invalid"]:
            return "—— 无效 ——"
        return f"{r['ratio']:.3f} [{r['lo']:.5f}, {r['hi']:.5f}]"
    P("")
    P("=" * 100)
    P(" 预注册判据（FINAL_PREREGISTRATION.md 第 6 节）")
    P("=" * 100)

    P(f"\n  H1  主效应：完整架构 CI 下界 > 1.00")
    P(f"      → {mark(0)}   {fmt(0)}")

    P(f"\n  P1  地板全关后仍 > 1")
    P(f"      → {mark(1)}   {fmt(1)}")
    P(f"      过 = 存在不依赖地板棘轮的持久性通路")

    ok12 = not (R[1]["invalid"] or R[2]["invalid"])
    drop = R[1]["ratio"] - R[2]["ratio"] if ok12 else float("nan")
    overlap = (not (R[2]["hi"] < R[1]["lo"] or R[1]["hi"] < R[2]["lo"])) if ok12 else True
    p2 = ok12 and drop >= 0.05 and not overlap
    P(f"\n  P2  只删 knowledge：落差 ≥ 0.05 且 CI 不重叠")
    P(f"      → {'✓ 过' if p2 else '✗ 不过'}"
      f"   {fmt(1)} → {fmt(2)}"
      f"   落差 {drop:+.3f}   CI {'重叠' if overlap else '不重叠'}")
    P(f"      不过 = 不能声称 knowledge 通路，主线为「离散记忆结构不是长期载体」")

    P(f"\n  R52 ★唯一真正未知★  022 关闭 + 地板全关，CI 下界 > 1.00")
    P(f"      → {mark(4)}   {fmt(4)}")
    P(f"      过   = 无地板残余效应真实存在，规则 33 的撤回要再议")
    P(f"      不过 = 规则 33 撤回定案：trait_identity 是【必要机制】，不是放大器")
    P(f"      边界 = 真值压在检出限上，本次不裁决（预注册修订 A）")

    same = R[1].get("fingerprint") == R[3].get("fingerprint")
    P(f"\n  阴性对照  只删 memories 须与 P1 逐位相同")
    P(f"      → {'✓ 通过' if same else '✗ 失败 —— 整批结果作废重查'}"
      f"   {R[1].get('fingerprint')} vs {R[3].get('fingerprint')}")

    P("\n" + "-" * 100)
    P("  事前预测对照（预注册第 7 节）")
    g = lambda k: ("—" if not R.get(k) or R[k]["invalid"] else f"{R[k]['ratio']:.3f}")
    P(f"    H1  预测 过, 1.12–1.16      实测 {ci_ok(0)}, {g(0)}")
    P(f"    P1  预测 过, 1.07–1.10      实测 {ci_ok(1)}, {g(1)}")
    P(f"    P2  预测 不过, 落差≈0.03    实测 {'过' if p2 else '不过'}, 落差 {drop:+.3f}")
    P(f"    R52 预测 不过, 1.03–1.06    实测 {ci_ok(4)}, {g(4)}")
    P(f"    情节记忆 预测 逐位相同       实测 {'逐位相同' if same else '不同'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", action="store_true",
                    help=f"用预注册的 final 种子块 {FINAL_SEED0}–"
                         f"{FINAL_SEED0+FINAL_N-1}（只允许一次）")
    ap.add_argument("--seed0", type=int, default=0)
    ap.add_argument("--n", type=int, default=1500)
    ap.add_argument("--check", action="store_true", help="只做冻结校验")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    a = ap.parse_args()

    verify_frozen()
    sim, _, _ = load_frozen()
    print(f"✓ 模型来自 {os.path.dirname(sim.__file__)}")
    print(f"✓ MODEL_VERSION={sim.MODEL_VERSION}  COND_RECOVER_AT={sim.COND_RECOVER_AT}")
    if a.check:
        return

    seed0, N = (FINAL_SEED0, FINAL_N) if a.final else (a.seed0, a.n)
    if a.final:
        print("\n" + "!" * 78)
        print(f"!! FINAL CONFIRMATION  seeds {seed0}–{seed0+N-1}  ——  这一段只允许跑一次")
        print(f"!! 跑完不论结果如何都不再改模型（预注册第 3 节）")
        print("!" * 78)
    else:
        print(f"\n[调试运行] seeds {seed0}–{seed0+N-1}，N={N}"
              f"   —— 不是 final，可以随便重跑")

    # ⚠ 曾经写成 min(CHUNK, N - s0)：seed0=0 时恰好对，seed0=50000 时是负数
    #   → 每个任务跑 0 颗种子 → 全部 n=0。彩排用 seed0=0，正好躲过。见规则 57。
    jobs = [(task_sim, (ci, w, s0, min(CHUNK, seed0 + N - s0)))
            for ci in range(len(CONDITIONS))
            for w in (WA, WB)
            for s0 in range(seed0, seed0 + N, CHUNK)]
    print(f"\n模拟 {len(jobs)} 个任务，进程数 {a.workers}", flush=True)

    store = {(ci, w): [None] * N for ci in range(len(CONDITIONS)) for w in (WA, WB)}
    t0 = time.time()
    with mp.Pool(a.workers) as pool:
        for k, (ci, w, s0, res) in enumerate(pool.imap_unordered(_dispatch, jobs), 1):
            store[(ci, w)][s0 - seed0:s0 - seed0 + len(res)] = res
            if k % 30 == 0 or k == len(jobs):
                el = time.time() - t0
                print(f"  {k}/{len(jobs)}  已用 {el/60:.1f}min  "
                      f"剩余 ~{el/k*(len(jobs)-k)/60:.1f}min", flush=True)

    # ★起飞后自检★ 覆盖率必须是 100%：任何一格没被任务写到，就说明分块算错了，
    #   而不是"球都死了"。这两种情况的处理完全不同，绝不能混。
    planned = sum(j[1][3] for j in jobs)
    want = len(CONDITIONS) * 2 * N
    if planned != want:
        raise SystemExit(f"✗ 分块覆盖不全：计划模拟 {planned} 次，应为 {want}。"
                         f"（检查 CHUNK/seed0 的算术）本次不产生结果。")

    sjobs, live_w = [], {}
    for ci in range(len(CONDITIONS)):
        ca, cb = store[(ci, WA)], store[(ci, WB)]
        live = [i for i in range(N) if ca[i] is not None and cb[i] is not None]
        if len(live) == 0:
            raise SystemExit(f"✗ {CONDITIONS[ci][0]} 有效 n = 0。"
                             f"n=0 是**故障**不是死亡率，本次不产生结果。")
        live_w[ci] = ([ca[i] for i in live], [cb[i] for i in live])
        sjobs.append((task_stats, (ci, [ca[i] for i in live], [cb[i] for i in live],
                                   1 - sum(x is not None for x in ca) / N,
                                   1 - sum(x is not None for x in cb) / N, N)))
    print(f"\n统计 {len(sjobs)} 个条件（bootstrap {N_BOOT} + 置换 {N_PERM}）…", flush=True)
    R = {}
    with mp.Pool(min(a.workers, len(sjobs))) as pool:
        for ci, r in pool.imap_unordered(_dispatch, sjobs):
            R[ci] = r
            print(f"  完成 {r['label']}", flush=True)

    # ── 边界诊断（预注册修订 A）：只影响报告，永不参与判读 ──
    need = [ci for ci in R if not R[ci]["invalid"]
            and abs(R[ci]["lo"] - 1.0) < DIAG_AT]
    diag = {}
    if need:
        print(f"\n边界诊断：{len(need)} 个条件的 |CI下界−1| < {DIAG_AT}，"
              f"换 {len(DIAG_SEEDS)} 个分析种子重跑…", flush=True)
        bjobs = [(task_boundary, (ci, live_w[ci][0], live_w[ci][1], sd))
                 for ci in need for sd in DIAG_SEEDS]
        with mp.Pool(min(a.workers, len(bjobs))) as pool:
            for ci, sd, lo in pool.imap_unordered(_dispatch, bjobs):
                diag.setdefault(ci, []).append(lo)

    out = []
    out.append("\n" + "=" * 100)
    tag = "FINAL CONFIRMATION" if a.final else "调试运行（非 final）"
    out.append(f" {tag}   seeds {seed0}–{seed0+N-1}   N={N}   模型 v3（frozen）")
    out.append("=" * 100)
    out.append(f"  {'条件':<20}{'n':>6}{'死亡丰':>8}{'死亡贫':>8}{'比值':>8}"
               f"  {'95% CI':<18}{'δ均值':>9}{'dz':>7}{'p':>10}")
    out.append("  " + "-" * 96)
    for ci in range(len(CONDITIONS)):
        r = R[ci]
        if r["invalid"]:
            out.append(f"  {r['label']:<20}{r['n']:>6}  ⚠ 有效 n < 1000 → 判为【无效】"
                       f"，不是「不显著」（预注册第 4 节）")
            continue
        out.append(f"  {r['label']:<20}{r['n']:>6}{r['dead_a']:>8.1%}{r['dead_b']:>8.1%}"
                   f"{r['ratio']:>8.3f}  [{r['lo']:.3f}, {r['hi']:.3f}]"
                   f"{r['delta']:>+9.4f}{r['dz']:>7.2f}{r['p']:>10.4f}")
    if diag:
        out.append("")
        out.append("=" * 100)
        out.append(" 边界诊断（预注册修订 A · 只影响报告，不参与判读）")
        out.append("=" * 100)
        out.append(f"  {'条件':<20}{'下界范围':>26}{'MC SD':>10}{'过/总':>8}")
        out.append("  " + "-" * 66)
        for ci in sorted(diag):
            v = diag[ci]
            sd = statistics.stdev(v) if len(v) > 1 else 0.0
            npass = sum(1 for x in v if x > 1.0)
            out.append(f"  {R[ci]['label']:<20}"
                       f"[{min(v):.5f}, {max(v):.5f}]".rjust(26) +
                       f"{sd:>10.5f}{f'{npass}/{len(v)}':>8}")
        out.append("  「过/总」若既不是 0/8 也不是 8/8 → 该判据被分析种子左右，")
        out.append("   这正是预注册修订 A 要求判「◐ 检出边界」的情形。")
    verdicts(R, out)
    out.append("\n  ⚠ 射程（预注册第 0.5 节）：本次确认的是 **persistence architecture**，")
    out.append("     不是 generalized individuality。后者属于 novel-situation generalization。")
    text = "\n".join(out)
    print(text)

    fn = os.path.join(HERE, "final_confirm_result.txt" if a.final
                      else "final_confirm_debug.txt")
    with open(fn, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(f"\n已写入 {fn}")


if __name__ == "__main__":
    mp.freeze_support()
    main()
