"""
配对实验 —— 同一颗种子，不同的用户
====================================

运行：  python paired.py

为什么要有这个脚本
------------------
`significance.py` 问的是："三组球的均值差得多不多？"
但用户心里的问题不是这个，是：

    "如果当初是另一个人养，它会不一样吗？"

分组比较回答不了这个问题，因为每组里的球本来就带着不同的初始种子，
而种子造成的差异（σ≈34）远大于用户造成的差异。用户的信号淹在里面。

配对实验的做法：**同一颗种子跑两遍，只换用户。**
初始性格完全相同 → 种子这个最大的噪声源被消掉了 → 剩下的差异才是用户的。

好处有两个：
  1. 灵敏度高得多（实测：配对 11.6 倍标准误 vs 分组 7.2 倍）
  2. 它问的就是产品要回答的那个问题

★ 一个必须承认的局限
--------------------
同一颗种子只能保证**初始状态**相同。一旦两次模拟的行动开始分叉，
rng 流就错开了，之后的暴雨/采集成败也就不同了。
所以配对消掉的是"种子噪声"，没消掉"世界运气噪声"。
下面的符号置换检验就是为了把后者当作零假设来处理。

噪声地板（沿用实验 009 的教训）
------------------------------
配对数据的正确零假设检验是**符号置换**：
如果用户没有系统性影响，那么每一对的差值往哪边偏就是随机的，
把差值的正负号随机翻转不应该改变结论。翻 2000 次，看实测均值排在哪。
"""

import random
import statistics
import unicodedata
from collections import Counter

import sim
import scenarios

SEEDS         = 400     # 跑多少颗种子（每颗 × 3 种用户）
DAYS          = 30
N_PERM        = 2000    # 符号置换次数
VISIBLE_DELTA = 5.0     # 差多少分才算"这一对确实不一样"

HEADLINE = ("溺爱型", "放养型")   # 两个极端，主结论看这一对

# 载体：性格 / 状态 —— 笔记的结论是后两类才是强信号，所以一起量
CARRIERS = [
    ("性格", "caution",   lambda a: a.traits["caution"]),
    ("性格", "curiosity", lambda a: a.traits["curiosity"]),
    ("性格", "industry",  lambda a: a.traits["industry"]),
    ("状态", "condition", lambda a: a.condition),
    ("状态", "shelter",   lambda a: a.shelter),
]

FLAGS = [("fears_hunger", "饿怕了"),
         ("fears_storm",  "怕暴雨"),      # 对照组：不可抗力，应该没差别
         ("loves_exploring", "爱探索")]


# ---------- 中英混排对齐（format 的宽度是按字符数算的，中文会错位）----------

def _w(s):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in str(s))


def pad(s, n, right=False):
    s = str(s)
    fill = " " * max(0, n - _w(s))
    return fill + s if right else s + fill


# ---------- 统计 ----------

def signflip_p(diffs, n_perm, rng):
    """符号置换检验（双侧）。零假设：差值围绕 0 对称，即用户没有系统性影响。"""
    obs = abs(statistics.mean(diffs))
    n = len(diffs)
    hits = 0
    for _ in range(n_perm):
        tot = 0.0
        for d in diffs:
            tot += d if rng.getrandbits(1) else -d
        if abs(tot / n) >= obs:
            hits += 1
    return hits / n_perm


def describe(diffs, perm_rng=None):
    """一组配对差值的完整描述"""
    n = len(diffs)
    mean = statistics.mean(diffs)
    sd = statistics.pstdev(diffs)
    return {
        "n": n,
        "mean": mean,
        # ★中位数比均值重要★ 如果均值不为 0 但中位数是 0，说明效应不是
        # "所有球都变了一点"，而是"绝大多数球毫无变化，少数球剧变"。
        # 对产品来说这两件事完全不同：后者意味着多数用户什么都感觉不到。
        "median": statistics.median(diffs),
        "sd": sd,
        "se": sd / n ** 0.5 if n else 0.0,
        # dz = 配对效应量。0.2 小 / 0.5 中 / 0.8 大
        "dz": mean / sd if sd else 0.0,
        # 50% = 没有效应；越偏离 50% 说明方向越稳定
        "pos": sum(1 for d in diffs if d > 0) / n,
        "big": sum(1 for d in diffs if abs(d) >= VISIBLE_DELTA) / n,
        "p": signflip_p(diffs, N_PERM, perm_rng) if perm_rng else None,
    }


# ---------- 跑模拟 ----------

def run_all():
    sim.SIM_DAYS = DAYS
    return {(s, arch): scenarios.run(s, arch)
            for s in range(SEEDS)
            for arch in scenarios.FEEDING}


def valid_pairs(world, a_name, b_name):
    """两边都活着的配对。死掉的单独报告，不能混进均值里（幸存者偏差）"""
    both, only_a_died, only_b_died = [], 0, 0
    for s in range(SEEDS):
        a, b = world[(s, a_name)], world[(s, b_name)]
        if a.alive and b.alive:
            both.append((a, b))
        elif a.alive:
            only_b_died += 1
        else:
            only_a_died += 1
    return both, only_a_died, only_b_died


# ---------- 报告 ----------

def main():
    rng = random.Random(0)
    print("=" * 78)
    print(f" 配对实验   同一颗种子，不同的用户   "
          f"{SEEDS} 颗种子 × {DAYS} 天   符号置换 {N_PERM} 次")
    print("=" * 78)

    world = run_all()

    # --- 存活率：死亡本身就是一种用户效应，先单独看 ---
    print("\n【存活率】")
    for arch in scenarios.FEEDING:
        alive = sum(1 for s in range(SEEDS) if world[(s, arch)].alive)
        print(f"  {pad(arch, 10)}{alive / SEEDS:6.1%}")

    # --- 主结论：两个极端的配对 ---
    a_name, b_name = HEADLINE
    pairs, a_died, b_died = valid_pairs(world, a_name, b_name)
    print(f"\n【{a_name} → {b_name}】{len(pairs)} 对有效"
          f"（{a_name}单方死亡 {a_died}，{b_name}单方死亡 {b_died}）")
    print(f"  {pad('载体', 20)}{pad('差值均值', 11, True)}{pad('中位数', 10, True)}"
          f"{pad('dz', 7, True)}{pad('变大的比例', 12, True)}"
          f"{pad('|d|≥5', 8, True)}{pad('p', 8, True)}")
    print("  " + "-" * 74)

    headline_dz = None
    for kind, label, get in CARRIERS:
        st = describe([get(b) - get(a) for a, b in pairs], rng)
        if label == "industry":
            headline_dz = st["dz"]
        note = ""
        if st["p"] >= 0.05:
            note = "   ← 噪声"
        elif abs(st["median"]) < 0.5 <= abs(st["mean"]):
            note = "   ← 中位数为 0：多数球毫无变化"
        print(f"  {pad(kind + ' ' + label, 20)}{pad(f'{st['mean']:+.2f}', 11, True)}"
              f"{pad(f'{st['median']:+.2f}', 10, True)}{pad(f'{st['dz']:+.2f}', 7, True)}"
              f"{pad(f'{st['pos']:.1%}', 12, True)}{pad(f'{st['big']:.1%}', 8, True)}"
              f"{pad(f'{st['p']:.3f}', 8, True)}{note}")

    print("\n  读法：")
    print("    中位数      ★最该看的一列★ 中位数≈0 而均值不为 0")
    print("                = 归因是全有或全无，不是渐变 → 多数用户感觉不到")
    print("    dz          配对效应量。0.2 小 / 0.5 中 / 0.8 大")
    print("    变大的比例  50% = 没有效应。偏离越远，方向越稳定")
    print("    |d|≥5       这一对确实能看出不一样的比例")

    # --- 事件载体：差异体现在"发生过什么"上 ---
    print(f"\n【不可逆事件】{a_name} → {b_name}   只有一边触发的配对（不一致对）")
    print(f"  {pad('事件', 12)}{pad('只有' + b_name, 14, True)}"
          f"{pad('只有' + a_name, 14, True)}{pad('净差', 9, True)}")
    for key, label in FLAGS:
        only_b = sum(1 for a, b in pairs if key in b.flags and key not in a.flags)
        only_a = sum(1 for a, b in pairs if key in a.flags and key not in b.flags)
        net = (only_b - only_a) / len(pairs)
        print(f"  {pad(label, 12)}{pad(only_b, 14, True)}{pad(only_a, 14, True)}"
              f"{pad(f'{net:+.1%}', 9, True)}")
    print(f"  （「怕暴雨」是对照组：不可抗力，两列应该差不多——它是测量管道的自检）")

    # --- 剂量反应：真信号应该是单调的 ---
    print("\n【剂量反应】投喂越少 → 效应越大？真信号应该单调递增")
    order = ["溺爱型", "平衡型", "放养型"]
    print(f"  {pad('对比', 20)}" + "".join(pad(l, 13, True) for _, l, _ in CARRIERS))
    for i in range(len(order)):
        for j in range(i + 1, len(order)):
            pr, _, _ = valid_pairs(world, order[i], order[j])
            row = "".join(
                pad(f"{statistics.mean([g(b) - g(a) for a, b in pr]):+.2f}", 13, True)
                for _, _, g in CARRIERS)
            print(f"  {pad(order[i] + '→' + order[j], 20)}{row}")

    # --- 产品判据 ---
    same = sum(1 for a, b in pairs if a.dominant_style() == b.dominant_style())
    flip = 1 - same / len(pairs)
    print("\n" + "=" * 78)
    print(" 产品判据：换个用户，这只球会变成另一个样子吗")
    print("=" * 78)
    print(f"  性格标签改变的比例        {flip:6.1%}      目标 > 50%")
    print("    （判据顺序的 bug 已在实验 015 修掉；但标签仍然读的是性格数值，"
          "而行为层指标显示性格与行为可以脱节 —— 主结论请看 behavior.py）")
    changed = Counter(f"{a.dominant_style()} → {b.dominant_style()}"
                      for a, b in pairs if a.dominant_style() != b.dominant_style())
    for k, v in changed.most_common(5):
        print(f"      {pad(k, 26)}{v:4d}")

    # 换了用户，但每一个载体都几乎没动的配对 —— 这才是最直接的产品判据
    untouched = sum(
        1 for a, b in pairs
        if all(abs(get(b) - get(a)) < VISIBLE_DELTA for _, _, get in CARRIERS)
        and a.flags == b.flags)
    print(f"\n  换了用户但【所有载体都没变】的配对   {untouched / len(pairs):6.1%}"
          f"      目标 < 20%")
    print("    这些用户不管怎么养，养出来的都是同一只球。")

    print(f"\n  ★ 四个要跟踪的数（改配置后对比这四行）")
    print(f"      industry 效应量 dz     {headline_dz:+.3f}   目标 > 0.8")
    print(f"      完全没变化的配对        {untouched / len(pairs):6.1%}   目标 < 20%")
    print(f"      性格标签改变率          {flip:6.1%}   目标 > 50%")
    dead = 1 - sum(1 for s in range(SEEDS) if world[(s, '放养型')].alive) / SEEDS
    print(f"      放养型死亡率            {dead:6.1%}   目标 < 10%")


if __name__ == "__main__":
    main()
