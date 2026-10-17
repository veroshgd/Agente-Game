"""
删除测试 —— 差异到底存在哪一层？
===================================

运行：  python deletion.py

移植实验证明了差异不依赖环境。但它没说差异**存在哪里**。
这个脚本在移植的那一刻按阶梯删掉各层，看差异什么时候塌。

    ① 完整
    ② − 情节记忆              memories = []
    ③ − 情节 + 语义           再清 knowledge
    ④ 只剩 traits             再清 flags / goal / goal_history / hardship

★ 为什么必须有第 ③ 档 ★
`knowledge` 是从情节记忆派生出来的（`mark()` 里顺手 `learn()`）。
只删情节会把语义留下，那还是**外部脚手架**在托着，
测出来的"记忆无关"是假的。

★ 为什么第 ④ 档才是真正的诊断 ★
只留性格数值、把一切经历性的结构全部抹掉。如果差异到这里还在，
那它就真的沉淀进了人格向量本身，而不是靠记忆在每天重新生成。

    塌在 ②     → 差异靠具体事件在维持
    塌在 ③     → 靠语义知识维持
    塌在 ④     → 靠 flags / goal / hardship 这些经历性开关维持
    ④ 还不塌   → 已经写进性格向量，是真正的"长成了这样"
"""

import statistics

import sim
import scenarios
from behavior import GLANCE
from transplant import window_tv
from paired import pad

SEEDS = 200
SPLIT = 30
CHECKS = (30, 60, 90)
WA, WB = "丰富世界", "贫瘠世界"
COMMON = "基准"

LADDER = [
    ("① 完整",            set()),
    ("② −情节记忆",       {"episodic"}),
    ("③ −情节+语义",      {"episodic", "semantic"}),
    ("④ 只剩 traits",     {"episodic", "semantic", "experiential"}),
]


def wipe(agent, what):
    if "episodic" in what:
        agent.memories = []
    if "semantic" in what:
        agent.knowledge = {}
        # ★022★ 强度字典必须一起清 —— `know()` 读的是它，不是 knowledge。
        # 只清 knowledge 的话行为效应仍在，删除测试会测出假的 no-op。
        agent.knowledge_strength = {}
    if "experiential" in what:
        # 经历性的开关：它们都直接进 score()，不删就不算"只剩 traits"
        agent.flags = set()
        agent.hardship = 0.0
        agent._hardship_anchor = None
        agent.goal = None
        agent.goal_history = []
        agent.goal_satiation = {}
    # 注意：trait_floor / trait_identity 保留 —— 它们是性格结构的一部分，
    # 不是记忆。要单独消融它们请用 persistence_ablation.py


def run_tracked(seed, first, what):
    life = scenarios.make(seed, first)
    agent = life.agent
    snaps, base_hour = {}, None
    for day in range(max(CHECKS)):
        if day == SPLIT:
            w = sim.World(seed, **scenarios.WORLDS[COMMON])
            life.world = w
            agent.world = w
            wipe(agent, what)
            base_hour = [c.copy() for c in agent.action_by_hour]
        for t in range(sim.TICKS_PER_DAY):
            life.world.tick(day, t)
            for inf in life.influences:
                inf(life.world, agent, day, t, life.inf_rng)
            agent.tick(day, t)
            if not agent.alive:
                return snaps
        agent.daily(day)
        if day + 1 in CHECKS:
            win = None
            if base_hour is not None:
                win = [c - base_hour[h] for h, c in enumerate(agent.action_by_hour)]
            snaps[day + 1] = {"agent": agent, "win": win,
                              **{t: agent.traits[t] for t in sim.TRAITS}}
    return snaps


def measure(what):
    A = [run_tracked(s, WA, what) for s in range(SEEDS)]
    B = [run_tracked(s, WB, what) for s in range(SEEDS)]
    out = {}
    for d in CHECKS:
        live = [i for i in range(SEEDS) if d in A[i] and d in B[i]]
        if len(live) < 20:
            continue
        row = {"n": len(live), "loss": 1 - len(live) / SEEDS,
               **{t: statistics.mean(B[i][d][t] - A[i][d][t] for i in live)
                  for t in sim.TRAITS}}
        if d > SPLIT:
            num = statistics.mean(window_tv(A[i][d]["win"], B[i][d]["win"])
                                  for i in live)
            base = []
            for coh in (A, B):
                al = [coh[i][d]["win"] for i in live]
                base += [(al[j], al[j + 1]) for j in range(0, len(al) - 1, 2)]
            den = statistics.mean(window_tv(x, y) for x, y in base)
            row["r"] = num / den if den else 0.0
            row["eye"] = sum(
                1 for i in live
                if any(f(A[i][d]["agent"]) != f(B[i][d]["agent"])
                       for _, f in GLANCE)) / len(live)
        out[d] = row
    return out


def main():
    print("=" * 100)
    print(f" 删除测试   {SEEDS} 颗种子   {WA} ↔ {WB}，第 {SPLIT} 天都进【{COMMON}】"
          f"并按阶梯删除")
    print("=" * 100)
    print(f"  {pad('条件', 16)}{pad('移植点 caut', 13, True)}"
          f"{pad('+30 caut', 11, True)}{pad('+60 caut', 11, True)}"
          f"{pad('+30 比值', 11, True)}{pad('+60 比值', 11, True)}"
          f"{pad('+60 一眼', 11, True)}{pad('+60 损失', 11, True)}")
    print("  " + "-" * 96)

    rows = []
    for label, what in LADDER:
        m = measure(what)
        if 60 not in m:
            print(f"  {pad(label, 16)}  —— 样本不足")
            continue
        rows.append((label, m))
        print(f"  {pad(label, 16)}{pad(f'{m[30]["caution"]:+.1f}', 13, True)}"
              f"{pad(f'{m[60]["caution"]:+.1f}', 11, True)}"
              f"{pad(f'{m[90]["caution"]:+.1f}' if 90 in m else '—', 11, True)}"
              f"{pad(f'{m[60]["r"]:.2f}', 11, True)}"
              f"{pad(f'{m[90]["r"]:.2f}' if 90 in m else '—', 11, True)}"
              f"{pad(f'{m[60]["eye"]:.1%}', 11, True)}"
              f"{pad(f'{m[60]["loss"]:.1%}', 11, True)}")

    print("\n" + "=" * 100)
    print(" 判定")
    print("=" * 100)
    if rows:
        full = rows[0][1]
        for label, m in rows[1:]:
            keep_r = m[60]["r"] / full[60]["r"] if full[60]["r"] else 0
            keep_c = (m[60]["caution"] / full[60]["caution"]
                      if full[60]["caution"] else 0)
            print(f"  {pad(label, 16)}  行为比值保留 {keep_r:>5.0%}   "
                  f"caution 保留 {keep_c:>5.0%}")
        last = rows[-1][1]
        print()
        if last[60]["r"] >= 1.0:
            print("  ★ 全删记忆之后，行为比值仍 ≥ 1 —— 差异已经沉淀进性格向量本身")
        elif last[60]["r"] >= 0.7 * full[60]["r"]:
            print("  ~ 全删记忆后大部分还在，但已不足以自己越过基线")
        else:
            print("  ✗ 全删记忆后塌掉 —— 差异是靠记忆每天重新生成的")
    print("\n  ⚠ 损失 >15% 的行有幸存者污染。trait_floor / trait_identity 未删，")
    print("     它们属于性格结构；要单独消融请跑 persistence_ablation.py")


if __name__ == "__main__":
    main()
