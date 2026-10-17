"""
持久性消融 —— 移植后留下来的东西,有多少是"写死的"?
=========================================================

运行：  python persistence_ablation.py

`transplant.py` 显示移植后差异保留 90%+。但架构里有**三个**只会让差异
变得更持久的机制，全都是手写的：

    ① trait_identity   永久地板，只增不减（sim.py:463 的 max()）
    ② trait_floor      软地板，每天只退 0.35，且不低于 ①
    ③ TRAIT_SATURATION 越极端越难改变（pull 最低 0.12 = 慢 8.3 倍）

③ 是这一版新加的，用来治 60 天团灭。但它顺手也是一个**持久性机制**：
一个被推到 caution=90 的球，extremity=0.8 → pull=0.28，漂回去的速度只有
中间值的三分之一。这不是巩固，这是乘数。

审稿人会问的那句话：
    "你不是发现了不可逆性，你是把不可逆性写进去了。"

这个脚本回答它。同时补上缺失的零假设对照（两个分身走同一个世界）。
"""

import statistics

import sim
import scenarios
from transplant import run_phased, window_tv, SPLIT, TOTAL
from behavior import GLANCE

SEEDS = 150
WA, WB = "丰富世界", "贫瘠世界"
COMMON = "基准"


class FrozenZero(dict):
    """写不进去的地板：读永远是 0"""
    def __init__(self):
        super().__init__({t: 0.0 for t in sim.TRAITS})

    def __setitem__(self, k, v):
        pass


_orig_make = scenarios.make


def patched_make(kill_identity=False, kill_floor=False):
    def make(seed, name, **kw):
        life = _orig_make(seed, name, **kw)
        if kill_identity or kill_floor:
            life.agent.trait_identity = FrozenZero()
        if kill_floor:
            life.agent.trait_floor = FrozenZero()
        return life
    return make


CONDITIONS = [
    ("完整架构",              dict()),
    ("− 饱和(③)",            dict(sat=0.0)),
    ("− 永久身份(①)",         dict(ident=True)),
    ("− 全部地板(①②)",       dict(floor=True)),
    ("− 三个全关",            dict(sat=0.0, floor=True)),
]


def run_condition(cfg, first_a, first_b):
    """跑一个消融条件下的移植实验，返回保留率等指标"""
    sat_backup = sim.TRAIT_SATURATION
    if "sat" in cfg:
        sim.TRAIT_SATURATION = cfg["sat"]
    scenarios.make = patched_make(cfg.get("ident", False), cfg.get("floor", False))
    try:
        stay_a = [run_phased(s, first_a, first_a) for s in range(SEEDS)]
        stay_b = [run_phased(s, first_b, first_b) for s in range(SEEDS)]
        mov_a = [run_phased(s, first_a, COMMON) for s in range(SEEDS)]
        mov_b = [run_phased(s, first_b, COMMON) for s in range(SEEDS)]
    finally:
        sim.TRAIT_SATURATION = sat_backup
        scenarios.make = _orig_make

    def ratio(cA, cB):
        live = [i for i in range(SEEDS)
                if cA[i][0] is not None and cB[i][0] is not None]
        if len(live) < 20:
            return None
        num = statistics.mean(window_tv(cA[i][1], cB[i][1]) for i in live)
        base = []
        for coh in (cA, cB):
            al = [coh[i] for i in live]
            base += [(al[j], al[j + 1]) for j in range(0, len(al) - 1, 2)]
        den = statistics.mean(window_tv(x[1], y[1]) for x, y in base)
        traits = {t: statistics.mean(cB[i][0].traits[t] - cA[i][0].traits[t]
                                     for i in live) for t in sim.TRAITS}
        eye = sum(1 for i in live
                  if any(f(cA[i][0]) != f(cB[i][0]) for _, f in GLANCE)) / len(live)
        return {"r": num / den if den else 0, "traits": traits,
                "dead": 1 - len(live) / SEEDS, "eye": eye, "n": len(live)}

    return ratio(stay_a, stay_b), ratio(mov_a, mov_b)


def main():
    print("=" * 104)
    print(f" 持久性消融   {SEEDS} 颗种子   {WA} ↔ {WB} → {COMMON}")
    print("=" * 104)
    print(f"  {'条件':<16}{'持续比值':>10}{'移植比值':>10}{'保留':>8}"
          f"{'一眼可辨':>10}{'死亡':>8}   移植后性格差")
    print("  " + "-" * 100)

    for label, cfg in CONDITIONS:
        stay, move = run_condition(cfg, WA, WB)
        if stay is None or move is None:
            print(f"  {label:<16}  —— 样本不足（死太多）")
            continue
        keep = move["r"] / stay["r"] if stay["r"] else 0
        tr = "  ".join(f"{t[:2]} {move['traits'][t]:+5.1f}" for t in sim.TRAITS)
        print(f"  {label:<16}{stay['r']:>10.2f}{move['r']:>10.2f}{keep:>7.0%}"
              f"{move['eye']:>10.1%}{move['dead']:>8.1%}   {tr}")

    # ---- 零假设：两个分身走同一个世界 ----
    print("\n" + "=" * 104)
    print(" 零假设对照：两个分身前 30 天走【同一个】世界，后 30 天也都进基准")
    print(" （测的是\"跑两遍本来就会差多少\"。这一档不应该有信号。）")
    print("=" * 104)
    for w in (WA, WB):
        stay, move = run_condition(dict(), w, w)
        if move:
            print(f"  双方都在「{w}」   移植比值 {move['r']:.2f}   "
                  f"一眼可辨 {move['eye']:.1%}   "
                  + "  ".join(f"{t[:2]} {move['traits'][t]:+5.1f}"
                              for t in sim.TRAITS))

    print("\n  读法：")
    print("    移植比值 ≥ 1  →  把因去掉后差异仍大于两只球本来的差异")
    print("    关掉地板后仍 ≥ 1  →  持久性来自动力学，是发现")
    print("    关掉地板后塌掉    →  持久性来自那几个 max()，是假设")
    print("    零假设那两行必须接近 0，否则测量管道有泄漏")


if __name__ == "__main__":
    main()
