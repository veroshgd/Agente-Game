"""
spread 这个指标到底有没有意义？—— 置换检验

问题：spread 取的是"三种用户类型 × 三个性格维度里的最大均值差"。
      取最大值本身就会放大噪声。性格的标准差约 34，每组 n 只球时
      均值的标准误 ≈ 34/√n；在 9 个组合里取最大，纯随机也能刷出可观的数字。

做法：把用户类型标签随机打乱 N 次，重算 spread，得到"零假设分布"。
      如果真实 spread 落在这个分布里面，那它就是噪声。
"""

import random
import statistics

import sim
import scenarios


def spread_of(alive, labels):
    """给定一组标签，算 spread"""
    names = list(scenarios.FEEDING)
    best = 0.0
    for t in sim.TRAITS:
        means = []
        for n in names:
            vals = [a.traits[t] for a, lb in zip(alive, labels) if lb == n]
            if vals:
                means.append(statistics.mean(vals))
        if len(means) >= 2:
            best = max(best, max(means) - min(means))
    return best


def main(pop=999, days=30, n_perm=400):
    names = list(scenarios.FEEDING)
    agents = [scenarios.run(n, names[n % len(names)]) for n in range(pop)]
    alive = [a for a in agents if a.alive]

    real_labels = [a.scenario for a in alive]
    observed = spread_of(alive, real_labels)

    # 零假设：打乱标签
    null = []
    shuffled = list(real_labels)
    rng = random.Random(0)
    for _ in range(n_perm):
        rng.shuffle(shuffled)
        null.append(spread_of(alive, shuffled))

    null.sort()
    p95 = null[int(0.95 * len(null))]
    p99 = null[int(0.99 * len(null))]
    p_value = sum(1 for v in null if v >= observed) / len(null)

    print("=" * 66)
    print(f" spread 显著性检验   存活 {len(alive)} 只，置换 {n_perm} 次")
    print("=" * 66)
    print(f"  实测 spread            : {observed:6.2f}")
    print(f"  零假设中位数（纯噪声）  : {statistics.median(null):6.2f}")
    print(f"  零假设 95 分位          : {p95:6.2f}   ← 要超过这条线才算有信号")
    print(f"  零假设 99 分位          : {p99:6.2f}")
    print(f"  p 值                   : {p_value:6.3f}")
    print()
    if p_value < 0.05:
        print("  ✓ 用户类型确实解释了性格差异（信号真实）")
    else:
        print("  ✗ 实测值落在噪声范围内 —— 这个 spread 是取最大值刷出来的假象。")
        print("    结论：目前用户行为对性格【没有可测量的影响】。")

    # 顺便给一个不受"取最大值"污染的指标
    print()
    print("  各维度单独看（不取最大值）：")
    for t in sim.TRAITS:
        by = {}
        for n in names:
            vals = [a.traits[t] for a in alive if a.scenario == n]
            by[n] = (statistics.mean(vals), statistics.pstdev(vals), len(vals))
        rng_span = max(m for m, _, _ in by.values()) - min(m for m, _, _ in by.values())
        # 组间差 / 合并标准误
        se = max((s / (c ** 0.5)) for _, s, c in by.values())
        print(f"    {t:<10} 组间最大差 {rng_span:5.2f}   "
              f"单组标准误 {se:4.2f}   差/标准误 = {rng_span / se:4.1f}")


if __name__ == "__main__":
    main()
