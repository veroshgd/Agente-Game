"""
死亡率拆分 —— 把 cond_compare 的「配对死亡率」拆回单个世界
==============================================================

运行：  python death_split.py            （默认 N=300，12 进程，约 5 分钟）
        python death_split.py --seeds 100 --workers 6

★ 为什么要拆 ★
`fix_compare.ratio_and_death` 里 `live` 要求**丰富、贫瘠两支都活**，
所以它报的是**配对**死亡率 ≈ 1−(1−p丰)(1−p贫)，一个数糊住了两个世界。

`cliff_probe.py`（N=60，只跑贫瘠）对上了「现状」那一格：
    单只贫瘠球 23.3% → 1−(1−0.233)² = 41.2%   vs   cond_compare 实测 40.7% ✓
但 ①阈值55 对不上：
    单只贫瘠球 11.7% → 应 ≈22%                vs   cond_compare 实测 43.3% ✗

两种可能，必须分清楚，否则 v3 选哪个阈值就是蒙的：
  (a) 丰富世界那一支在 55 档反常地死得多 —— 那 ①55 真的不能用；
  (b) cliff_probe 的 N=60 噪声（SE≈±5pp）—— 那 ①55 其实没问题。

这里两个世界都跑、N 拉到 300、逐档报单世界死亡率，并**顺手用单世界数字
重算配对死亡率**，跟 cond_compare 的实测值对账。对不上就说明"两支独立"
这个假设本身错了（同种子的两支共享初始性格，本来就相关）。
"""

import argparse
import multiprocessing as mp
import os
import time

WA, WB, COMMON = "丰富世界", "贫瘠世界", "基准"
SPLIT, TOTAL = 30, 120

# (标签, 恢复阈值, 死区恢复, 住所恢复)
VARIANTS = [
    ("现状",          30.0, 0.00, 0.00),
    ("① 阈值 55",     55.0, 0.00, 0.00),
    ("① 阈值 60",     60.0, 0.00, 0.00),
    ("① 阈值 65",     65.0, 0.00, 0.00),
    ("③ 住所 +0.10",  30.0, 0.00, 0.10),
]
CHUNK = 25          # 每个任务跑多少颗种子，摊薄进程启动开销


def evaluate(task):
    """一个任务 = (档位, 世界, 地板全关, 起始种子, 颗数) → 死了几只"""
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

    scenarios.make = PA.patched_make(False, floor_off)
    try:
        dead = sum(run_phased(s, world, COMMON, split=SPLIT, total=TOTAL)[0] is None
                   for s in range(seed0, seed0 + n))
    finally:
        scenarios.make = PA._orig_make
    return (vi, world, floor_off), dead, n


# cond_compare 3g 节的实测配对死亡率，用来对账
COND_COMPARE = {          # 标签: (完整, 无地板)
    "现状":         (0.187, 0.407),
    "① 阈值 55":    (0.137, 0.433),
    "① 阈值 65":    (0.050, 0.073),
    "③ 住所 +0.10": (0.067, 0.340),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=300)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    a = ap.parse_args()

    tasks = [(vi, w, fo, s0, min(CHUNK, a.seeds - s0))
             for vi in range(len(VARIANTS))
             for w in (WA, WB)
             for fo in (False, True)
             for s0 in range(0, a.seeds, CHUNK)]

    print(f"死亡率拆分  {len(VARIANTS)} 档 × 2 世界 × 2 架构 × {a.seeds} 种子 "
          f"× {TOTAL} 天   进程数 {a.workers}")
    acc, t0 = {}, time.time()
    with mp.Pool(a.workers) as pool:
        for k, (key, dead, n) in enumerate(pool.imap_unordered(evaluate, tasks), 1):
            d, t = acc.get(key, (0, 0))
            acc[key] = (d + dead, t + n)
            if k % 20 == 0 or k == len(tasks):
                el = time.time() - t0
                print(f"  {k}/{len(tasks)}  已用 {el/60:.1f}min  "
                      f"剩余 ~{el/k*(len(tasks)-k)/60:.1f}min", flush=True)

    for floor_off in (False, True):
        arch = "地板全关" if floor_off else "完整架构"
        print("\n" + "=" * 92)
        print(f" 单世界死亡率 · {arch} · N={a.seeds} · 120 天 · 第 30 天移植到基准")
        print("=" * 92)
        print(f"  {'修法':<14}{'丰富世界':>10}{'贫瘠世界':>10}"
              f"{'独立推算配对':>14}{'cond_compare':>14}{'差':>8}")
        print("  " + "-" * 88)
        for vi, (label, *_) in enumerate(VARIANTS):
            da, na = acc[(vi, WA, floor_off)]
            db, nb = acc[(vi, WB, floor_off)]
            pa, pb = da / na, db / nb
            pred = 1 - (1 - pa) * (1 - pb)
            obs = COND_COMPARE.get(label, (None, None))[1 if floor_off else 0]
            o = f"{obs:>13.1%}" if obs is not None else f"{'—':>14}"
            df = f"{pred-obs:>+7.1%}" if obs is not None else f"{'—':>8}"
            print(f"  {label:<14}{pa:>9.1%}{pb:>9.1%}{pred:>13.1%}{o}{df}")
        print(f"\n  「独立推算配对」= 1−(1−p丰)(1−p贫)，假设两支独立。")
        print(f"  与 cond_compare 的差就是**同种子两支的相关性**（共享初始性格）：")
        print(f"  推算 > 实测 → 两支同生共死（正相关）；推算 < 实测 → 反常，要查。")
        se = (0.25 / a.seeds) ** 0.5
        print(f"  单世界死亡率的最大标准误 ≈ ±{se:.1%}（N={a.seeds}）")


if __name__ == "__main__":
    mp.freeze_support()
    main()
