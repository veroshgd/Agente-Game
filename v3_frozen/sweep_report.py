"""
读 param_sweep.py 的结果，出论文能直接引的那几句话。

运行：  python sweep_report.py [sweep_results.csv]
"""

import csv
import statistics
import sys

DEAD_MAX = 0.40      # 死亡率超过这个的配置剔掉（团灭时比值没有意义）
PARAMS = ["PERSONALITY_WEIGHT", "TRAIT_DRIFT", "TRAIT_SATURATION",
          "LANDMARK_BONUS", "HARDSHIP_MAX_BOOST", "FLOOR_DECAY_PER_DAY",
          "LANDMARK_PERMANENT", "GOAL_BONUS", "GOAL_OFF_TASK",
          "GOAL_SWITCH_MARGIN", "GOAL_MIN_DAYS", "GOAL_REFRACTORY",
          "GOAL_STALL_DAYS", "GOAL_SLACK_FOOD", "GOAL_SLACK_COND"]


def spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = rank(xs), rank(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else 0.0


def pct(vals, p):
    s = sorted(vals)
    return s[min(len(s) - 1, int(p * len(s)))]


def main(path="sweep_results.csv"):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("空文件")
        return

    kept = [r for r in rows if float(r["dead_move"]) <= DEAD_MAX]
    rm = [float(r["ratio_move"]) for r in kept]
    gm = [float(r["goal_ratio_move"]) for r in kept]
    lr = [float(r["logratio_move"]) for r in kept]

    print("=" * 78)
    print(f" 参数随机化集合   共 {len(rows)} 组，剔除团灭后 {len(kept)} 组"
          f"（死亡率 > {DEAD_MAX:.0%}）")
    print("=" * 78)

    for label, vals, thresh in [("移植比值（作息）", rm, 1.0),
                                ("移植比值（目标）", gm, 1.0),
                                ("对数比值（作息）", lr, 0.0)]:
        above = sum(1 for v in vals if v > thresh) / len(vals)
        print(f"\n  {label}")
        print(f"    中位数 {statistics.median(vals):.3f}   "
              f"IQR [{pct(vals, .25):.3f}, {pct(vals, .75):.3f}]   "
              f"90%区间 [{pct(vals, .05):.3f}, {pct(vals, .95):.3f}]")
        print(f"    > {thresh:g} 的比例：{above:.1%}   ← 论文里报这个数")

    print("\n" + "=" * 78)
    print(" 参数敏感度（Spearman，|ρ| 大 = 结论依赖这个旋钮）")
    print("=" * 78)
    corr = sorted(((abs(spearman([float(r[p]) for r in kept], rm)), p,
                    spearman([float(r[p]) for r in kept], rm))
                   for p in PARAMS), reverse=True)
    for mag, name, rho in corr:
        bar = "#" * int(mag * 40)
        print(f"  {name:<22}{rho:+.3f}  {bar}")

    print("\n  读法：|ρ| < 0.2 = 结论对这个参数不敏感（好）")
    print("        |ρ| > 0.4 = 效应主要由这个旋钮决定，必须在论文里讨论")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sweep_results.csv")
