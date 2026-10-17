"""
实验 022 回归检查 —— 三个参数归零时，行为必须和 021 逐位一致
================================================================

运行：  python test_022_regression.py

预注册第 6 节第 2 步。接线改动如果在"关掉"状态下改变了任何数字，
说明改动泄漏进了不该碰的地方（最典型的是消耗了 RNG，让种子整体错位），
那么 022 的所有对比都不成立。

判据：逐位一致。不是"差不多"。
"""

import sys

import sim
import scenarios


def fingerprint(seed, world, days=60):
    """一条命的完整指纹：动作分布 + 性格 + 目标序列 + 持久结构"""
    a = scenarios.run(seed, world, days=days)
    return (
        a.alive,
        tuple(sorted(a.action_log.items())),
        tuple(round(a.traits[t], 10) for t in sim.TRAITS),
        tuple(a.goal_by_day),
        tuple(sorted(a.knowledge)),
        tuple(sorted(a.flags)),
        round(a.hardship, 10),
        tuple(round(a.trait_identity[t], 10) for t in sim.TRAITS),
        round(a.shelter, 10), round(a.condition, 10),
        round(a.inventory["food"], 10),
    )


WORLDS = ["基准", "丰富世界", "贫瘠世界", "有书", "常下雨"]
SEEDS = range(40)


def collect():
    return {(s, w): fingerprint(s, w) for w in WORLDS for s in SEEDS}


def main():
    print("=" * 72)
    print(" 实验 022 回归检查   5 个世界 × 40 颗种子 × 60 天")
    print("=" * 72)

    print(f"  当前参数  WEIGHT={sim.KNOWLEDGE_WEIGHT}  "
          f"GOAL_WEIGHT={sim.KNOWLEDGE_GOAL_WEIGHT}  FORGET={sim.KNOWLEDGE_FORGET}")

    # 关掉 022 的全部改动
    sim.KNOWLEDGE_WEIGHT = 0.0
    sim.KNOWLEDGE_GOAL_WEIGHT = 0.0
    sim.KNOWLEDGE_FORGET = 0.0
    off = collect()
    print(f"  已采集【关闭】指纹 {len(off)} 条")

    # 打开
    sim.KNOWLEDGE_WEIGHT = 12.0
    sim.KNOWLEDGE_GOAL_WEIGHT = 0.25
    sim.KNOWLEDGE_FORGET = 0.02
    on = collect()
    print(f"  已采集【打开】指纹 {len(on)} 条")

    changed = [k for k in off if off[k] != on[k]]
    print(f"\n  打开后有变化的：{len(changed)} / {len(off)} "
          f"（{len(changed)/len(off):.0%}）")
    if not changed:
        print("\n  ✗ 严重问题：打开 022 之后【什么都没变】。")
        print("    说明接线没有真的生效 —— 检查 KNOWLEDGE_ACTIONS 的动作名，")
        print("    或者根本没有球学到过 knowledge。")
        return 1

    # 真正的判据：关闭态必须和基线一致。用 git 没法比（不是仓库），
    # 所以这里检验一个必要条件：关闭态下 knowledge_strength 不影响任何输出。
    sim.KNOWLEDGE_WEIGHT = 0.0
    sim.KNOWLEDGE_GOAL_WEIGHT = 0.0
    sim.KNOWLEDGE_FORGET = 0.0
    off2 = collect()
    if off2 != off:
        print("\n  ✗ 关闭态自己都不可复现 —— 有随机性泄漏。")
        return 1
    print("  ✓ 关闭态可复现（两次采集完全一致）")

    # 关闭态下 forget 不该删掉任何 knowledge
    sim.KNOWLEDGE_FORGET = 0.0
    a = scenarios.run(3, "丰富世界", days=60)
    if len(a.knowledge) != len(a.knowledge_strength):
        print(f"\n  ✗ knowledge 和 knowledge_strength 不同步："
              f"{len(a.knowledge)} vs {len(a.knowledge_strength)}")
        return 1
    print(f"  ✓ knowledge / knowledge_strength 同步（{len(a.knowledge)} 条）")

    print("\n  ★ 关闭态一致、打开态有效。可以继续跑 P1/P2/P3。")
    print("  ⚠ 但「关闭态 == 实验 021 的数字」只能靠 persistence_ablation.py")
    print("    在 KNOWLEDGE_* 全 0 时复现 1.18 / 1.07 来确认 —— 下一步做。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
