"""
anchor 内容因果探针 —— anchor 里装的历史切片，是不是 persistence 的载体？
==========================================================================

运行：  python anchor_probe.py --verify        （只跑 A 部分，~2 分钟）
        python anchor_probe.py                （全量，13 进程）

★ 冻结声明 ★
v3 已冻结（`v3_frozen/`）。本脚本是 **experiment-level intervention**：
只改 agent 实例上的 `_hardship_anchor`，**不动 `sim.py` 的任何默认值**。

--------------------------------------------------------------------------
A. 先证伪一个错误推论：v3 并没有推迟 anchor
--------------------------------------------------------------------------
023 §7.5 曾推论"v3 把 consolidation 时刻后移 → 采到更成熟的性格"。
**这不成立**，而且从代码上本来就不可能成立：

    sim.py:965   if deficit > 0:  ...  if self._hardship_anchor is None: 写入
    deficit = (100 − condition)/100

condition 只能被 `COND_DRAIN`（饿>70）拉下 100；在 condition 仍等于 100 时，
`COND_RECOVER_AT` 抬高带来的 gain 全被 `clamp` 吃掉。
**所以在 anchor 写入之前，v2 和 v3 的轨迹逐位相同** —— anchor 日必然相同。

A 部分逐种子核对这一点（v2 vs v3，同种子，报"完全相同的比例"）。

被误当成 anchor 的那个量是 `fears_hunger`：它要 `hardship_norm ≥ 0.5`
（`HARDSHIP_STORY_AT`）才记，是**叙事路标**，不是人格固化时刻。

--------------------------------------------------------------------------
B. 新的实验问题：anchor 的【内容】是不是因果载体？
--------------------------------------------------------------------------
不用"第 N 天才开始写 anchor"那种做法 —— 那会同时改两件事
（① 快照里是什么 ② floor 从何时开始起作用），因果上不干净。

改成 **anchor-content transplant**（这就是小号的 state transplant）：

    1. 让 agent 正常跑完整个 development phase（0–29 天），
       途中保存 trait 快照：day 5 / 10 / 20 / 29
    2. 到固定干预点（第 30 天，移植那一刻）deepcopy 出完全相同的状态
    3. **只改 `_hardship_anchor`**，换成不同的历史切片
    4. 所有分支从完全相同的当前状态进入 common garden（基准世界）

唯一变量 = anchor 里装的那张历史切片。

★ 天然 negative control ★
`persistence_ablation` 的无地板档把 `trait_floor` 换成 `FrozenZero()`，
而 `_hardship_anchor` 唯一的作用路径就是 anchor → trait_floor（sim.py:970）。
**所以无地板条件下，anchor 里放什么都不该有区别。**
如果无地板也跟着变 → 存在泄漏或第二条 anchor 通路，那会是很强的阴性对照失败。

★ 预测（primary / secondary）★
  primary   完整架构下，anchor-content 干预**能产生可检出的后期行为持久性差异**
            （不预注册 Day5 < Day10 < Day20 < Day29 的单调关系 ——
             系统有反馈、hardship boost、floor 和 saturation，晚期快照
             信息更多不等于终效应单调）
  secondary Day 顺序的趋势
  negative  无地板档：Day5 ≈ Day10 ≈ Day20 ≈ Day29 ≈ No-anchor

★ 种子 ★ 用**已经看过的 development seeds（0+）**。
final confirmation 的全新种子块留着不动。
"""

import argparse
import copy
import multiprocessing as mp
import os
import random
import statistics
import time

WA, WB, COMMON = "丰富世界", "贫瘠世界", "基准"
SPLIT, TOTAL = 30, 60
SNAP_DAYS = (5, 10, 20, 29)
BRANCHES = ["自然 anchor", "Day 5", "Day 10", "Day 20", "Day 29", "无 anchor"]
BASE_K = 5
N_PERM = 10000
V3_RECOVER_AT = 65.0        # B 部分只在冻结的 v3 上做，显式钉死，不靠继承
CHUNK = 50


def _prep(floor_off, rec_at):
    """★ 必须显式传 rec_at ★
    mp.Pool 的 worker 进程是**复用**的：A 部分的 task_verify 会把
    `sim.COND_RECOVER_AT` 设成 30.0 或 65.0 并留在那个进程里。
    如果 B 部分不显式设回来，它跑的就是上一个任务残留的版本 ——
    结果取决于任务调度顺序，同样的命令两次跑出不同的数。
    （第一版就是这么翻车的：N=100 两次结果完全对不上。）"""
    import sim
    import scenarios
    import persistence_ablation as PA
    sim.COND_RECOVER_AT = rec_at
    sim.COND_DEADZONE_RECOVER = 0.0
    sim.COND_SHELTER_RECOVER = 0.0
    sim.KNOWLEDGE_WEIGHT, sim.KNOWLEDGE_GOAL_WEIGHT, sim.KNOWLEDGE_FORGET = 12.0, 0.25, 0.02
    scenarios.make = PA.patched_make(False, floor_off)
    return sim, scenarios, PA


# ------------------------------------------------------------------ A 部分
def task_verify(job):
    """逐种子记录 anchor 首次写入日 + fears_hunger 首次出现日，v2/v3 各一遍"""
    rec_at, world, floor_off, seed0, n = job
    sim, scenarios, PA = _prep(floor_off, rec_at)
    out = []
    try:
        for s in range(seed0, seed0 + n):
            life = scenarios.make(s, world)
            ag = life.agent
            a_day = f_day = None
            for day in range(SPLIT):
                for t in range(sim.TICKS_PER_DAY):
                    life.world.tick(day, t)
                    for inf in life.influences:
                        inf(life.world, ag, day, t, life.inf_rng)
                    ag.tick(day, t)
                    if a_day is None and ag._hardship_anchor is not None:
                        a_day = day
                    if f_day is None and "fears_hunger" in ag.flags:
                        f_day = day
                    if not ag.alive:
                        break
                if not ag.alive:
                    break
                ag.daily(day)
            out.append((s, a_day, f_day))
    finally:
        scenarios.make = PA._orig_make
    return ("V", rec_at, world, floor_off, out)


# ------------------------------------------------------------------ B 部分
def task_branch(job):
    """一个种子块 × 一个世界 × 一个架构 → 每个分支的窗口矩阵"""
    world, floor_off, seed0, n = job
    sim, scenarios, PA = _prep(floor_off, V3_RECOVER_AT)   # ★显式钉死 v3★
    from collections import Counter

    def to_mat(w):
        out = []
        for h in w:
            tot = sum(h.values()) or 1
            out.append(tuple(h[x] / tot for x in sim.ACTIONS))
        return tuple(out)

    res = {b: [None] * n for b in BRANCHES}
    try:
        for k, s in enumerate(range(seed0, seed0 + n)):
            life = scenarios.make(s, world)
            ag = life.agent
            snaps, dead = {}, False

            for day in range(SPLIT):                       # ── development
                for t in range(sim.TICKS_PER_DAY):
                    life.world.tick(day, t)
                    for inf in life.influences:
                        inf(life.world, ag, day, t, life.inf_rng)
                    ag.tick(day, t)
                    if not ag.alive:
                        dead = True
                        break
                if dead:
                    break
                ag.daily(day)
                if day in SNAP_DAYS:
                    snaps[day] = dict(ag.traits)
            if dead or len(snaps) < len(SNAP_DAYS):
                continue

            snap0 = [Counter(c) for c in ag.action_by_hour]   # 第 30 天快照

            for b in BRANCHES:                              # ── 干预 + common garden
                life_b = copy.deepcopy(life)               # 完全相同的状态（含 RNG）
                ag_b = life_b.agent
                # ⚠ 陷阱：FrozenZero 是 dict 子类且 __setitem__ 是 no-op，
                #   deepcopy 重建它时正是走 __setitem__ 灌数据 → 复制出**空 dict**
                #   → 下一次读 trait_floor['industry'] 直接 KeyError。
                #   v3 已冻结，不改 persistence_ablation.py，在这里补回来。
                #   FrozenZero 不携带任何状态（读恒 0、写恒丢），重建等价。
                if floor_off:
                    ag_b.trait_floor = PA.FrozenZero()
                    ag_b.trait_identity = PA.FrozenZero()
                if b == "无 anchor":
                    ag_b._hardship_anchor = None
                elif b != "自然 anchor":
                    ag_b._hardship_anchor = dict(snaps[int(b.split()[1])])

                w = sim.World(s, **scenarios.WORLDS[COMMON])   # 各分支同一个世界
                life_b.world, ag_b.world = w, w
                ok = True
                for day in range(SPLIT, TOTAL):
                    for t in range(sim.TICKS_PER_DAY):
                        life_b.world.tick(day, t)
                        for inf in life_b.influences:
                            inf(life_b.world, ag_b, day, t, life_b.inf_rng)
                        ag_b.tick(day, t)
                        if not ag_b.alive:
                            ok = False
                            break
                    if not ok:
                        break
                    ag_b.daily(day)
                if ok:
                    res[b][k] = to_mat([Counter(c) - snap0[h]
                                        for h, c in enumerate(ag_b.action_by_hour)])
    finally:
        scenarios.make = PA._orig_make
    return ("B", world, floor_off, seed0, res)


def mat_tv(a, b):
    return sum(0.5 * sum(abs(x - y) for x, y in zip(ha, hb))
               for ha, hb in zip(a, b)) / len(a)


def build_opp(n, rng):
    out = []
    for k in range(n):
        pick = lambda: [(lambda j: j if j < k else j + 1)(rng.randrange(n - 1))
                        for _ in range(BASE_K)]
        out.append((pick(), pick()))
    return out


def deltas_on(idx, wa, wb, opp):
    ds, bs = [], []
    for k, i in enumerate(idx):
        ds.append(mat_tv(wa[i], wb[i]))
        bs.append(statistics.mean(
            [mat_tv(wa[i], wa[idx[j]]) for j in opp[k][0]] +
            [mat_tv(wb[i], wb[idx[j]]) for j in opp[k][1]]))
    return [d - b for d, b in zip(ds, bs)], statistics.mean(ds), statistics.mean(bs)


def sign_perm_p(vals, rng, n_perm=N_PERM):
    obs = statistics.mean(vals)
    hits = sum(1 for _ in range(n_perm)
               if abs(statistics.mean(v if rng.random() < .5 else -v
                                      for v in vals)) >= abs(obs))
    return obs, (hits + 1) / (n_perm + 1)


def _dispatch(job):
    fn, args = job
    return fn(args)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=600)
    ap.add_argument("--verify", action="store_true", help="只跑 A 部分")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    N = a.seeds

    jobs = []
    for rec in (30.0, 65.0):                       # A：v2 / v3
        for world in (WA, WB):
            for fo in (False, True):
                for s0 in range(0, N, CHUNK):
                    jobs.append((task_verify, (rec, world, fo, s0, min(CHUNK, N - s0))))
    if not a.verify:
        for world in (WA, WB):                     # B：只在 v3（已冻结）上做
            for fo in (False, True):
                for s0 in range(0, N, CHUNK):
                    jobs.append((task_branch, (world, fo, s0, min(CHUNK, N - s0))))

    print(f"anchor 探针   {len(jobs)} 任务   N={N}（development seeds 0+）   "
          f"进程数 {a.workers}")
    print("★ v3 已冻结：本脚本只改 agent 实例的 _hardship_anchor，不动 sim.py 默认值\n",
          flush=True)

    t0, out = time.time(), []
    with mp.Pool(a.workers) as pool:
        for k, r in enumerate(pool.imap_unordered(_dispatch, jobs), 1):
            out.append(r)
            if k % 10 == 0 or k == len(jobs):
                el = time.time() - t0
                print(f"  {k}/{len(jobs)}  已用 {el/60:.1f}min  "
                      f"剩余 ~{el/k*(len(jobs)-k)/60:.1f}min", flush=True)

    report_verify([r for r in out if r[0] == "V"], N)
    if not a.verify:
        report_branch([r for r in out if r[0] == "B"], N)


def report_verify(rows, N):
    print("\n" + "=" * 96)
    print(" A · anchor 写入日 vs fears_hunger 日 —— v2/v3 逐种子核对")
    print("=" * 96)
    acc = {}
    for _, rec, world, fo, lst in rows:
        acc.setdefault((world, fo, rec), {}).update({s: (ad, fd) for s, ad, fd in lst})

    print(f"  {'世界':<10}{'架构':<10}{'anchor日 v2':>13}{'anchor日 v3':>13}"
          f"{'逐种子相同':>12}{'fears日 v2':>12}{'fears日 v3':>12}")
    print("  " + "-" * 92)
    for world in (WA, WB):
        for fo in (False, True):
            d2, d3 = acc[(world, fo, 30.0)], acc[(world, fo, 65.0)]
            common = sorted(set(d2) & set(d3))
            a2 = [d2[s][0] for s in common if d2[s][0] is not None]
            a3 = [d3[s][0] for s in common if d3[s][0] is not None]
            same = sum(1 for s in common if d2[s][0] == d3[s][0])
            f2 = [d2[s][1] for s in common if d2[s][1] is not None]
            f3 = [d3[s][1] for s in common if d3[s][1] is not None]
            m = lambda v: statistics.median(v) if v else float("nan")
            print(f"  {world:<10}{'地板全关' if fo else '完整架构':<10}"
                  f"{m(a2):>13.1f}{m(a3):>13.1f}{f'{same}/{len(common)}':>12}"
                  f"{m(f2):>12.1f}{m(f3):>12.1f}")
    print("\n  ★ 判读 ★ anchor 日逐种子 100% 相同 → v3 没有推迟 consolidation；")
    print("           fears_hunger 日后移 → 后移的是【叙事阈值】，不是人格固化时刻。")


def report_branch(rows, N):
    store = {}
    for _, world, fo, s0, res in rows:
        for b, lst in res.items():
            store.setdefault((b, world, fo), [None] * N)[s0:s0 + len(lst)] = lst

    for fo in (False, True):
        arch = "−全部地板①②（★阴性对照★）" if fo else "完整架构"
        print("\n" + "=" * 100)
        print(f" B · anchor 内容干预 · {arch} · N={N} · development seeds 0+")
        print("=" * 100)

        own = {b: {i for i in range(N)
                   if store[(b, WA, fo)][i] is not None
                   and store[(b, WB, fo)][i] is not None} for b in BRANCHES}
        common = sorted(set.intersection(*own.values()))
        n_c = len(common)
        print(f"\n  共同种子集（全分支 × 两世界都活）：n={n_c}（占 {n_c/N:.1%}）")
        if n_c < 50:
            print("  ⚠ 样本不足")
            continue

        opp = build_opp(n_c, random.Random(20260815))
        res = {}
        for b in BRANCHES:
            d, num, den = deltas_on(common, store[(b, WA, fo)], store[(b, WB, fo)], opp)
            res[b] = (d, num / den)

        base = res["自然 anchor"][0]
        print(f"\n  {'分支':<14}{'比值':>9}{'δ均值':>10}{'Δ vs 自然':>12}{'dz':>7}{'p':>10}")
        print("  " + "-" * 64)
        prng = random.Random(777)
        for b in BRANCHES:
            d, r = res[b]
            dm = statistics.mean(d)
            if b == "自然 anchor":
                print(f"  {b:<14}{r:>9.3f}{dm:>10.4f}{'—':>12}{'—':>7}{'—':>10}")
                continue
            diff = [x - y for x, y in zip(d, base)]
            obs, p = sign_perm_p(diff, prng)
            sd = statistics.stdev(diff)
            star = "***" if p < .001 else "**" if p < .01 else "*" if p < .05 else "n.s."
            print(f"  {b:<14}{r:>9.3f}{dm:>10.4f}{obs:>+12.4f}"
                  f"{obs/sd if sd else 0:>7.2f}{p:>10.4f} {star}")

        if fo:
            print("\n  ★ 阴性对照判读 ★ 全部 n.s. = 通过（anchor 只走 trait_floor 一条路）")
            print("  任何一档显著 → 存在泄漏或第二条 anchor 通路，要查。")
        else:
            print("\n  ★ primary ★ 只要有干预档显著 ≠ 自然，就说明 anchor 内容是因果载体之一")
            print("  ★ secondary ★ Day 顺序的趋势（不预注册单调性）")


if __name__ == "__main__":
    mp.freeze_support()
    main()
