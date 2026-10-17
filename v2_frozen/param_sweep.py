"""
参数随机化集合 —— 回答"这是不是一组手调参数刷出来的"
=========================================================

运行：  python param_sweep.py                    # 默认 500 组 × 300 种子
       python param_sweep.py --configs 2000     # 更密
       python param_sweep.py --seed-offset 10000 --out holdout.csv   # 留出集

不是网格扫描。从先验分布里独立抽 N 组参数，每组重跑一遍移植实验，
报**效应的分布**而不是一个点。结论长这样：

    "在 500 组随机采样的参数配置中，移植比值 > 1 的占 X%，中位数 1.Y"

审稿人问的是 "how do I know this isn't a parameter artifact"，
这句话是唯一能直接回答它的东西。

★ 三处方法学修正（相对 transplant.py）★
  1. 基线用 K=5 次【随机】配对，不是相邻配对。
     相邻种子生成的球更像 → 基线偏小 → 比值虚高 2.2%（实测）。
  2. 同时报对数比值。比值 = 均值之比，分母有噪声就系统性上偏（Jensen）。
  3. 死亡率一起落盘。参数抽到极端值会团灭，那些行必须在分析时剔掉。

断点续跑：结果逐行 flush 到 CSV，中断后重跑同一条命令会跳过已完成的组。
"""

import argparse
import csv
import math
import multiprocessing as mp
import os
import random
import statistics
import sys
import time

WA, WB, COMMON = "丰富世界", "贫瘠世界", "基准"
BASE_PAIRINGS = 5          # 基线随机配对次数（实测 K=5 已饱和）

# 先验：("logu", lo, hi) 对数均匀 · ("u", lo, hi) 均匀 · ("int", lo, hi) 整数
# 区间基本是默认值的 ×0.5 ~ ×2
PRIORS = {
    "PERSONALITY_WEIGHT":  ("logu", 15.0, 60.0),    # 默认 30.0
    "TRAIT_DRIFT":         ("logu", 0.60, 2.40),    # 默认 1.20
    "TRAIT_SATURATION":    ("u",    0.00, 0.98),    # 默认 0.90
    "LANDMARK_BONUS":      ("logu", 12.5, 50.0),    # 默认 25.0
    "HARDSHIP_MAX_BOOST":  ("logu", 11.0, 44.0),    # 默认 22.0
    "FLOOR_DECAY_PER_DAY": ("logu", 0.17, 0.70),    # 默认 0.35
    "LANDMARK_PERMANENT":  ("u",    0.10, 0.80),    # 默认 0.40
    "GOAL_BONUS":          ("logu", 16.0, 64.0),    # 默认 32.0
    "GOAL_OFF_TASK":       ("logu",  7.0, 28.0),    # 默认 14.0
    "GOAL_SWITCH_MARGIN":  ("logu", 0.125, 0.50),   # 默认 0.25
    "GOAL_MIN_DAYS":       ("int",   1,    4),      # 默认 2
    "GOAL_REFRACTORY":     ("int",   3,   12),      # 默认 6
    "GOAL_STALL_DAYS":     ("int",   2,    8),      # 默认 4
    "GOAL_SLACK_FOOD":     ("logu",  2.0,  8.0),    # 默认 4.0（规则 27）
    "GOAL_SLACK_COND":     ("u",    60.0, 100.0),   # 默认 90.0
}

PARAM_NAMES = list(PRIORS)
FIELDS = (["config_id"] + PARAM_NAMES +
          ["n_move", "n_stay", "dead_move", "dead_stay",
           "ratio_move", "logratio_move", "ratio_stay",
           "goal_ratio_move", "keep"])


def sample_config(config_id):
    """config_id 决定参数 —— 同一个 id 永远抽到同一组，续跑才可复现"""
    rng = random.Random(0xC0FFEE + config_id)
    out = {}
    for name, spec in PRIORS.items():
        kind, lo, hi = spec
        if kind == "logu":
            out[name] = math.exp(rng.uniform(math.log(lo), math.log(hi)))
        elif kind == "u":
            out[name] = rng.uniform(lo, hi)
        else:
            out[name] = rng.randint(lo, hi)
    return out


def _shuffled_baseline(windows, k, rng, tv):
    """K 次独立随机配对。每只球用 K 次，方差远低于相邻配对一次。"""
    out = []
    idx = list(range(len(windows)))
    for _ in range(k):
        rng.shuffle(idx)
        out += [tv(windows[idx[j]], windows[idx[j + 1]])
                for j in range(0, len(idx) - 1, 2)]
    return out


def evaluate(args):
    """跑一组参数。子进程里执行 —— sim 的全局量改了也只影响本进程。"""
    config_id, n_seeds, seed_offset = args
    import sim
    import scenarios
    from transplant import run_phased, window_tv, SPLIT, TOTAL

    cfg = sample_config(config_id)
    for name, value in cfg.items():
        setattr(sim, name, value)

    goal_types = list(sim.GOAL_ACTIONS)

    def goal_tv(a, b):
        def prof(ag):
            days = [g for g in ag.goal_by_day[SPLIT:TOTAL] if g]
            n = len(days) or 1
            return {g: days.count(g) / n for g in goal_types}
        pa, pb = prof(a), prof(b)
        return 0.5 * sum(abs(pa[g] - pb[g]) for g in goal_types)

    seeds = range(seed_offset, seed_offset + n_seeds)

    def condition(dest_a, dest_b):
        ca = [run_phased(s, WA, dest_a) for s in seeds]
        cb = [run_phased(s, WB, dest_b) for s in seeds]
        live = [i for i in range(n_seeds) if ca[i][0] is not None and cb[i][0] is not None]
        # 门槛跟着样本量走。★注意★ 这个门槛本身是个选择效应：
        # 被剔掉的是"参数抽得太狠、球活不下来"的配置，不是随机剔的。
        # 所以 dead_* 一定要落盘，报结果时说明剔掉了多少、为什么。
        if len(live) < max(30, int(0.2 * n_seeds)):
            return None
        rng = random.Random(config_id)
        treat = [window_tv(ca[i][1], cb[i][1]) for i in live]
        base = (_shuffled_baseline([ca[i][1] for i in live], BASE_PAIRINGS, rng, window_tv) +
                _shuffled_baseline([cb[i][1] for i in live], BASE_PAIRINGS, rng, window_tv))
        gt = [goal_tv(ca[i][0], cb[i][0]) for i in live]
        gb = (_shuffled_baseline([ca[i][0] for i in live], BASE_PAIRINGS, rng, goal_tv) +
              _shuffled_baseline([cb[i][0] for i in live], BASE_PAIRINGS, rng, goal_tv))
        mt, mb = statistics.mean(treat), statistics.mean(base)
        mgt, mgb = statistics.mean(gt), statistics.mean(gb)
        # 对数比值：逐对配 log 差，绕开 E[X/Y] 的上偏
        logr = (statistics.mean(math.log(v) for v in treat if v > 0) -
                statistics.mean(math.log(v) for v in base if v > 0))
        return {"n": len(live), "dead": 1 - len(live) / n_seeds,
                "r": mt / mb if mb else 0.0, "logr": logr,
                "gr": mgt / mgb if mgb else 0.0}

    # ★ 两组独立记录 ★「持续」组在贫瘠世界 60 天死亡率高，经常达不到门槛。
    #   早期版本 stay 一失败就整行丢掉，把完全有效的 move 数据一起扔了 ——
    #   而 move 才是头条，且它是在【基准世界】测的，死亡率低得多。
    move = condition(COMMON, COMMON)
    if move is None:
        return None
    stay = condition(WA, WB)

    row = {"config_id": config_id}
    row.update({k: round(v, 6) if isinstance(v, float) else v for k, v in cfg.items()})
    row.update({
        "n_move": move["n"], "dead_move": round(move["dead"], 4),
        "ratio_move": round(move["r"], 5), "logratio_move": round(move["logr"], 5),
        "goal_ratio_move": round(move["gr"], 5),
        "n_stay": stay["n"] if stay else "",
        "dead_stay": round(stay["dead"], 4) if stay else "",
        "ratio_stay": round(stay["r"], 5) if stay else "",
        "keep": round(move["r"] / stay["r"], 5) if stay and stay["r"] else "",
    })
    return row


def done_ids(path):
    if not os.path.exists(path):
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        return {int(r["config_id"]) for r in csv.DictReader(f) if r.get("config_id")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", type=int, default=500)
    ap.add_argument("--seeds", type=int, default=300)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--seed-offset", type=int, default=0,
                    help="留出集用：换一段没碰过的种子，例如 10000")
    ap.add_argument("--out", default="sweep_results.csv")
    a = ap.parse_args()

    already = done_ids(a.out)
    todo = [(i, a.seeds, a.seed_offset) for i in range(a.configs) if i not in already]

    print(f"参数扫描  {a.configs} 组 × {a.seeds} 种子  "
          f"seed range [{a.seed_offset}, {a.seed_offset + a.seeds})")
    print(f"已完成 {len(already)}，待跑 {len(todo)}，进程数 {a.workers}")
    if not todo:
        print("全部已完成。")
        return

    new_file = not os.path.exists(a.out)
    t0 = time.time()
    with open(a.out, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        with mp.Pool(a.workers) as pool:
            n_ok = 0
            for k, row in enumerate(pool.imap_unordered(evaluate, todo), 1):
                if row is not None:
                    w.writerow(row)
                    f.flush()
                    n_ok += 1
                if k % 10 == 0 or k == len(todo):
                    el = time.time() - t0
                    eta = el / k * (len(todo) - k)
                    print(f"  {k}/{len(todo)}  有效 {n_ok}  "
                          f"已用 {el/60:.1f}min  剩余 ~{eta/60:.1f}min", flush=True)

    print(f"\n完成，写入 {a.out}。用 python sweep_report.py 看结果。")


if __name__ == "__main__":
    mp.freeze_support()
    main()
