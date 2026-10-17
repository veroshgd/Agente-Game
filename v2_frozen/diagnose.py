"""棘轮到底有没有按用户类型区分开？—— 这决定下一步该怎么改"""

import statistics

import sim
import scenarios

names = list(scenarios.FEEDING)
agents = [scenarios.run(n, names[n % 3]) for n in range(999)]
alive = [a for a in agents if a.alive]

print("=" * 70)
print(" 棘轮触发率（按用户类型）—— 想看到的是三行差别很大")
print("=" * 70)
head = f"{'':<9}{'饿怕了':>10}{'怕暴雨':>10}{'爱探索':>10}{'勤劳':>9}{'体质':>9}"
print(head)
print("-" * 70)
for n in names:
    g = [a for a in alive if a.scenario == n]
    rate = lambda k: sum(1 for a in g if k in a.flags) / len(g)
    ind = statistics.mean([a.traits["industry"] for a in g])
    cond = statistics.mean([a.condition for a in g])
    print(f"{n:<9}{rate('fears_hunger'):>9.1%}{rate('fears_storm'):>10.1%}"
          f"{rate('loves_exploring'):>10.1%}{ind:>9.1f}{cond:>9.1f}")

print()
print(" 解读：")
print("  · 三行的『饿怕了』差别大 → 机制正确，只是幅度不够 → 放大棘轮效果")
print("  · 三行的『饿怕了』差别小 → 机制没生效 → 用户的食物根本没起作用")
print("  · 『怕暴雨』三行应该一样（那是不可抗力，与用户无关）—— 用作对照组")
