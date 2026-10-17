"""
规则 48 判别检验 —— 比值真的升了，还是选择效应？
==================================================

运行：  python rule48_test.py              （默认 N=800，12 进程）
        python rule48_test.py --seeds 200 --workers 6

★ 待答的问题 ★
3g 节九档比值**全部 ≥ 现状**，据此立了规则 48（生存压力压缩行为方差）。
但那张表有个结构性缺陷：`fix_compare.ratio_and_death` 的 `live` 要求
**两个世界都活**，所以**每一档的比值算在不同的幸存子集上**。
死亡率一降，进入统计的就是另一批球 —— 跨档比较混进了选择效应。
而规则 48 想说的恰恰是"筛掉谁"会改变比值，两者完全缠在一起。

★ 三个改进 ★
① **共同种子集**：只用「所有档 × 两个世界都活」的那批种子重算全部档位。
   同一批球、同一段窗口，唯一的差别就是体质规则本身。
② **逐种子配对**：Δ_i = δ_i(某档) − δ_i(现状)，符号置换（规则 021 第 5 节的
   δ 构造）。3g 用的是比 CI 重不重叠 —— N_BOOT=400 的 CI 宽到互相覆盖一大半，
   本来就判不出显著。配对检验消掉种子间方差，功效高一个量级。
③ **对手索引固定**：δ_i 的基线 b_i 要抽 BASE_K 个同世界对手。各档抽**同一组**
   索引，否则抽样噪声会伪装成档间差异。

★ 一个反向旁证（不是本脚本测的）★
规则 34：比值估计量 N 小则虚高。现状的有效 N 最小、比值却最低 ——
偏差方向解释不了 3g 那个现象。所以规则 48 有戏，但要靠 ①②③ 才站得住。
"""

import argparse
import multiprocessing as mp
import os
import random
import statistics
import time

WA, WB, COMMON = "丰富世界", "贫瘠世界", "基准"
SPLIT, TOTAL = 30, 60          # 比值口径：60 天窗口（和 3g 一致）
BASE_K = 5
N_PERM = 10000

VARIANTS = [
    ("现状",          30.0, 0.00, 0.00),
    ("① 阈值 55",     55.0, 0.00, 0.00),
    ("① 阈值 60",     60.0, 0.00, 0.00),
    ("① 阈值 65",     65.0, 0.00, 0.00),
    ("③ 住所 +0.10",  30.0, 0.00, 0.10),
]
CHUNK = 40


def evaluate(task):
    """一个任务 = (档位, 世界, 地板全关, 起始种子, 颗数)
    返回每颗种子的【归一化窗口矩阵】（死了就是 None）—— 比回传 Counter 省得多"""
    vi, world, floor_off, seed0, n = task

    import sim
    import scenarios
    import persistence_ablation as PA
    import transplant as T
    from transplant import run_phased

    sim.KNOWLEDGE_WEIGHT, sim.KNOWLEDGE_GOAL_WEIGHT, sim.KNOWLEDGE_FORGET = 12.0, 0.25, 0.02
    _, rec_at, dz, sh = VARIANTS[vi]
    sim.COND_RECOVER_AT, sim.COND_DEADZONE_RECOVER, sim.COND_SHELTER_RECOVER = rec_at, dz, sh
    sim.SIM_DAYS, T.TOTAL = TOTAL, TOTAL

    def to_mat(w):
        """[24 × Counter] → [24 × 归一化频率]，window_tv 的等价紧凑形式"""
        out = []
        for h in w:
            tot = sum(h.values()) or 1
            out.append(tuple(h[x] / tot for x in sim.ACTIONS))
        return tuple(out)

    scenarios.make = PA.patched_make(False, floor_off)
    try:
        res = []
        for s in range(seed0, seed0 + n):
            _, w = run_phased(s, world, COMMON, split=SPLIT, total=TOTAL)
            res.append(None if w is None else to_mat(w))
    finally:
        scenarios.make = PA._orig_make
    return (vi, world, floor_off), seed0, res


def mat_tv(a, b):
    """与 transplant.window_tv 逐位等价，输入是归一化矩阵"""
    return sum(0.5 * sum(abs(x - y) for x, y in zip(ha, hb))
               for ha, hb in zip(a, b)) / len(a)


def deltas_on(idx, wa, wb, opp):
    """给定种子下标集 idx 和固定的对手抽样 opp，算逐种子 δ_i、分子、分母"""
    ds, bs = [], []
    for k, i in enumerate(idx):
        d = mat_tv(wa[i], wb[i])
        o = [mat_tv(wa[i], wa[idx[j]]) for j in opp[k][0]] + \
            [mat_tv(wb[i], wb[idx[j]]) for j in opp[k][1]]
        ds.append(d)
        bs.append(statistics.mean(o))
    return [d - b for d, b in zip(ds, bs)], statistics.mean(ds), statistics.mean(bs)


def sign_perm_p(vals, rng, n_perm=N_PERM):
    obs = statistics.mean(vals)
    hits = sum(1 for _ in range(n_perm)
               if abs(statistics.mean(v if rng.random() < .5 else -v for v in vals)) >= abs(obs))
    return obs, (hits + 1) / (n_perm + 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=800)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    a = ap.parse_args()
    N = a.seeds

    tasks = [(vi, w, fo, s0, min(CHUNK, N - s0))
             for vi in range(len(VARIANTS))
             for w in (WA, WB)
             for fo in (False, True)
             for s0 in range(0, N, CHUNK)]

    print(f"规则 48 判别检验  {len(VARIANTS)} 档 × 2 世界 × 2 架构 × {N} 种子 "
          f"× {TOTAL} 天   进程数 {a.workers}")
    store, t0 = {}, time.time()
    for key in [(vi, w, fo) for vi in range(len(VARIANTS))
                for w in (WA, WB) for fo in (False, True)]:
        store[key] = [None] * N
    with mp.Pool(a.workers) as pool:
        for k, (key, s0, res) in enumerate(pool.imap_unordered(evaluate, tasks), 1):
            store[key][s0:s0 + len(res)] = res
            if k % 20 == 0 or k == len(tasks):
                el = time.time() - t0
                print(f"  {k}/{len(tasks)}  已用 {el/60:.1f}min  "
                      f"剩余 ~{el/k*(len(tasks)-k)/60:.1f}min", flush=True)

    for floor_off in (False, True):
        arch = "地板全关（规则 44 的污染源）" if floor_off else "完整架构"
        print("\n" + "=" * 100)
        print(f" 规则 48 判别检验 · {arch} · N={N} · 60 天窗口")
        print("=" * 100)

        own = {vi: [i for i in range(N)
                    if store[(vi, WA, floor_off)][i] is not None
                    and store[(vi, WB, floor_off)][i] is not None]
               for vi in range(len(VARIANTS))}
        common = sorted(set.intersection(*(set(v) for v in own.values())))
        n_c = len(common)
        print(f"\n  各档自己的幸存种子数：" +
              "  ".join(f"{VARIANTS[vi][0]}={len(own[vi])}" for vi in own))
        print(f"  共同种子集（全档 × 两世界都活）：n={n_c}"
              f"（占 {n_c/N:.1%}）")
        if n_c < 50:
            print("  ⚠ 共同集太小，跳过")
            continue

        # ③ 对手索引固定：所有档共用同一组抽样
        opp = build_opp(n_c, random.Random(20260815))

        rows = []
        for vi, (label, *_) in enumerate(VARIANTS):
            wa, wb = store[(vi, WA, floor_off)], store[(vi, WB, floor_off)]
            # 「自己集」大小逐档不同，只能各抽各的（这正是 3g 口径的毛病之一）
            d_own, num_o, den_o = deltas_on(
                own[vi], wa, wb, build_opp(len(own[vi]), random.Random(999)))
            d_com, num_c, den_c = deltas_on(common, wa, wb, opp)
            rows.append((label, len(own[vi]), num_o / den_o,
                         d_com, num_c / den_c))

        base_d = rows[0][3]
        print(f"\n  {'修法':<14}{'自己集n':>8}{'比值(自己集)':>14}"
              f"{'比值(共同集)':>14}{'δ均值':>10}{'Δvs现状':>10}{'dz':>7}{'p':>9}")
        print("  " + "-" * 96)
        prng = random.Random(777)
        for label, n_own, r_own, d_com, r_com in rows:
            dm = statistics.mean(d_com)
            if label == "现状":
                print(f"  {label:<14}{n_own:>8}{r_own:>14.3f}{r_com:>14.3f}"
                      f"{dm:>10.4f}{'—':>10}{'—':>7}{'—':>9}")
                continue
            diff = [x - y for x, y in zip(d_com, base_d)]
            obs, p = sign_perm_p(diff, prng)
            sd = statistics.stdev(diff)
            dz = obs / sd if sd else 0.0
            star = "***" if p < .001 else "**" if p < .01 else "*" if p < .05 else "n.s."
            print(f"  {label:<14}{n_own:>8}{r_own:>14.3f}{r_com:>14.3f}"
                  f"{dm:>10.4f}{obs:>+10.4f}{dz:>7.2f}{p:>9.4f} {star}")

        print(f"\n  「自己集」= 3g 的口径（每档各自的幸存者，混着选择效应）")
        print(f"  「共同集」= 同一批 {n_c} 颗种子，唯一差别是体质规则本身")
        print(f"  Δvs现状 = 逐种子配对差的均值，{N_PERM} 次符号置换")
        print(f"  ★ 判读 ★ 共同集上仍显著为正 → 规则 48 成立（真效应）")
        print(f"           共同集上归零 → 3g 那个「意外」是选择效应，规则 48 撤回")


def build_opp(n, rng):
    out = []
    for k in range(n):
        pick = lambda: [(lambda j: j if j < k else j + 1)(rng.randrange(n - 1))
                        for _ in range(BASE_K)]
        out.append((pick(), pick()))
    return out


if __name__ == "__main__":
    mp.freeze_support()
    main()
