"""
实验 027 —— Novel-Task Transfer + Reversal（v4 的唯一新模块）
================================================================

自检：  python novel_task.py

★★ v4 的定义 ★★
    v4 = v3_frozen 的核心（**逐字节不动**） + 本模块
本模块**不修改 `v3_frozen/` 的任何一行**，也不在 60 天之内接触 agent 状态。
所以「NovelTask 关闭时 v4 与 v3 逐 tick 完全相同」是**构造上成立**的，
但仍然写成回归测试（`_test_v3_equivalence`），防止日后有人不小心把它耦合进去。

--------------------------------------------------------------------------
任务：两个从未存在过的按钮 A / B
--------------------------------------------------------------------------
    30 天发育（丰富/贫瘠）→ 30 天 common garden → 拉平身体状态
    → 进入新任务：80 个 trial，每个 trial 选 A 或 B，得到 0/1 点数

**这个任务与 食物 / 房子 / 材料 / 死亡 完全无关** —— 026 的四个 probe
全部栽在"操纵资源 → 变成生存问题或饱和问题"（规则 64/68/70/71），
027 彻底绕开资源经济。

    Trial 1–40   好选项 80% / 差选项 20%
    Trial 41     ★规则突然反转★
    Trial 41–80  反过来

哪个先好**按种子随机**（一半种子 A 先好），所以不存在"某种历史天然与 A 对齐"。
**同一颗种子的双胞胎共享同一张奖励表**，连平局裁决位都共享 ——
所以不能说"rich 只是运气好"。

--------------------------------------------------------------------------
过去怎么进入新任务（★最敏感的一点★）
--------------------------------------------------------------------------
**过去不许决定 A 还是 B 好。** 那是把结论写进去。

过去只能通过一个非常一般的东西进入：**愿不愿意去试一个还不确定的选项。**

    novelty_style = (curiosity − caution + 100) / 200   ∈ [0,1]
    beta          = BETA * novelty_style
    value(x)      = Q_x + beta / sqrt(1 + N_x)          ← 不确定性奖励

所以：curious 的球更愿意试"我还不了解"的选项；
cautious 的球更倾向继续用已经有证据的选项。
**哪个选项真的奖励高，完全由外部任务决定。**

★ 学习率 α 对所有 agent 完全相同 ★ —— 绝不能设计成 "rich 学得快"。

⚠ 措辞纪律：本任务里 agent **确实在学**（Q 值按反馈更新），
   这是 v4 相对 v3 的新增能力。但它学的是**一个 2 臂赌博机的价值**，
   **不是**"理解了世界的因果结构"。文案里不许写成后者。
"""

import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
V3DIR = os.path.join(HERE, "v3_frozen")
if V3DIR not in sys.path:
    sys.path.insert(0, V3DIR)

import sim                                        # noqa: E402

assert os.path.abspath(sim.__file__).startswith(V3DIR), "核心必须来自 v3_frozen"
assert sim.MODEL_VERSION == "v3"

MODEL_VERSION = "v4"          # v4 = v3 核心 + 本模块

# ---- 任务参数（校准前的占位值；正式值由 group-blind 校准产出后写进预注册）----
TRIALS = 80
REVERSAL_AT = 40
P_HIGH, P_LOW = 0.80, 0.20
# ★★ 已由 group-blind 校准冻结（2026-08-17）★★
#   字典序 β↑ → α↑ → τ↑ 取第一个合格格；80 格中 12 格合格。
#   校准只看 pooled 指标，脚本物理上算不出 rich/poor 差异。
ALPHA = 0.05                  # 学习率 —— ★所有 agent 相同★
BETA = 0.05                   # 不确定性奖励强度 —— ★唯一让历史进来的旋钮★
TAU = 0.20                    # softmax 温度 —— ★所有 agent 相同，不是历史通道★
Q_INIT = 0.5

# ⚠ 默认值必须与冻结值一致：final runner 若忘了显式传参，
#   绝不能悄悄跑回占位参数。下面的断言 + 指纹是硬拦截。
_FROZEN = dict(ALPHA=0.05, BETA=0.05, TAU=0.20, TRIALS=80, REVERSAL_AT=40,
               P_HIGH=0.80, P_LOW=0.20, Q_INIT=0.5)

# ⚠ 为什么需要 TAU（第一版没有，校准全格不合格）：
#   纯确定性 argmax 下，只要 Q 的【排序】正确，选择就 100% 正确 ——
#   于是 31–40 trial 的正确率恒在 94–100%，与 α、β 无关，
#   永远进不了 65–90% 的合格带。这是**任务设计问题**，不是参数没调好。
#   加一个对所有 agent 相同的选择噪声（softmax），正确率才有可调区间。
#   ★ TAU 对所有 agent 相同，所以它不构成第二条历史通道。★

_SALT_REWARD = 0x27A50        # 固定盐，保证奖励表只由种子决定
_SALT_TIE = 0x27B10


def config_fingerprint():
    """任务配置指纹 —— 每次正式运行都要打印/落盘，跑错版本一眼看得出"""
    import hashlib
    payload = "|".join(f"{k}={v!r}" for k, v in sorted(dict(
        TRIALS=TRIALS, REVERSAL_AT=REVERSAL_AT, P_HIGH=P_HIGH, P_LOW=P_LOW,
        ALPHA=ALPHA, BETA=BETA, TAU=TAU, Q_INIT=Q_INIT,
        SALT_R=_SALT_REWARD, SALT_T=_SALT_TIE).items()))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def assert_frozen():
    """★硬拦截★ 参数必须与校准冻结值逐位一致"""
    cur = dict(ALPHA=ALPHA, BETA=BETA, TAU=TAU, TRIALS=TRIALS,
               REVERSAL_AT=REVERSAL_AT, P_HIGH=P_HIGH, P_LOW=P_LOW,
               Q_INIT=Q_INIT)
    bad = {k: (v, cur[k]) for k, v in _FROZEN.items() if cur[k] != v}
    if bad:
        raise AssertionError(f"✗ 任务参数偏离冻结值：{bad}")
    return config_fingerprint()


# ------------------------------------------------------------------ 奖励表
def reward_table(seed):
    """★双胞胎共享★ 只由种子决定：奖励序列 + 平局裁决位 + 哪个选项先好。

    平局位也**预先生成**（每 trial 一位），而不是临时抽 ——
    否则两个分身在不同 trial 上遇到平局时会消耗不同的随机数，
    平局裁决本身就变成了一条分歧来源。
    """
    rng = random.Random(_SALT_REWARD ^ seed)
    a_good_first = rng.random() < 0.5
    rows = []
    for t in range(TRIALS):
        flipped = t >= REVERSAL_AT
        a_is_good = a_good_first != flipped          # XOR
        pa = P_HIGH if a_is_good else P_LOW
        pb = P_LOW if a_is_good else P_HIGH
        rows.append((1 if rng.random() < pa else 0,
                     1 if rng.random() < pb else 0))
    # 每 trial 一个共享的均匀抽样，用于 softmax 决策。
    # ★双胞胎共享★ → 不能说"某一支只是掷骰子运气好"。
    # 它同时替代了原来的平局裁决位：val 相等时 p0 = 0.5，由同一个 u 决定。
    trng = random.Random(_SALT_TIE ^ seed)
    us = [trng.random() for _ in range(TRIALS)]
    return rows, us, a_good_first


def correct_option(a_good_first, t):
    """第 t 个 trial 的"正确"选项（0=A, 1=B）"""
    return (0 if a_good_first else 1) if t < REVERSAL_AT \
        else (1 if a_good_first else 0)


# ------------------------------------------------------------------ 选择规则
def novelty_style(agent):
    """[0,1]。**只用 curiosity 与 caution，不读任何资源/生存/历史标签。**"""
    ns = (agent.traits["curiosity"] - agent.traits["caution"] + 100.0) / 200.0
    return min(1.0, max(0.0, ns))


def run_task(agent, seed, *, beta=BETA, alpha=ALPHA, tau=TAU,
             history_blind=False):
    """跑完 80 个 trial。返回逐 trial 记录。**不触碰 agent 的任何既有状态。**

    `history_blind=True` → beta 固定为中值，学习照常
      （控制三：若历史仍造成系统差异，说明还有没发现的通路）
    """
    rows, us, a_good_first = reward_table(seed)
    b = beta * (0.5 if history_blind else novelty_style(agent))
    Q = [Q_INIT, Q_INIT]
    N = [0, 0]
    choices, rewards, explores = [], [], []

    for t in range(TRIALS):
        val = [Q[i] + b / math.sqrt(1 + N[i]) for i in (0, 1)]
        d = (val[0] - val[1]) / tau
        d = max(-60.0, min(60.0, d))          # 防 exp 溢出
        p0 = 1.0 / (1.0 + math.exp(-d))
        c = 0 if us[t] < p0 else 1            # ★共享抽样★
        # "探索" = 选了当前 Q 值较低的那个（不是贪婪选择）
        explores.append(1 if (Q[c] < Q[1 - c]) else 0)
        r = rows[t][c]
        N[c] += 1
        Q[c] += alpha * (r - Q[c])
        choices.append(c)
        rewards.append(r)

    return {
        "seed": seed, "a_good_first": a_good_first,
        "choices": choices, "rewards": rewards, "explores": explores,
        "beta": b, "tau": tau, "Q_end": list(Q), "N_end": list(N),
    }


# ------------------------------------------------------------------ 指标
def switch_latency(rec, window=5, need=4):
    """★H2 primary★ 反转后过多少 trial 才稳定选中新的正确选项。

    定义：反转后第一个 trial t，使得 [t, t+window) 内 ≥ need 次选中新正确项。
    永远达不到 → 返回 None（不能当成 0，也不能剔掉，见 §判读）。
    """
    good = correct_option(rec["a_good_first"], REVERSAL_AT)
    ch = rec["choices"]
    for t in range(REVERSAL_AT, TRIALS - window + 1):
        if sum(1 for x in ch[t:t + window] if x == good) >= need:
            return t - REVERSAL_AT
    return None


# 可检测到的最大 latency：t 取到 TRIALS-window，故 latency ≤ 35
MAX_DETECTABLE_LATENCY = TRIALS - REVERSAL_AT - 5      # = 35
NEVER_SWITCHED = MAX_DETECTABLE_LATENCY + 1            # = 36


def switch_latency_restricted(rec):
    """★H2 primary endpoint★ 截尾切换延迟：0–35 为真实延迟，**36 = 观察窗内未切换**。

    ⚠ 36 **不是**"它在第 36 个 trial 切换了"，而是"整个观察期都没切换"。

    为什么必须现在写死（而不是 final 之后再决定）：
      · 删掉 never-switcher → 制造 selection（若某一支 never-switch 更多，
        效应会被悄悄抹掉）
      · 当成 0 → 把"从不切换"错当成"立刻切换"，方向完全反
      · 事后改用 survival model → 那是看到结果之后选统计方法
    截尾是最简单、不删数据、也不引入复杂模型的做法。
    校准实测 never-switch 只有 2.0%，所以它不会主导结果 —— 但仍然提前写死。
    """
    x = switch_latency(rec)
    return NEVER_SWITCHED if x is None else x


def correct_rate(rec, lo, hi):
    ch = rec["choices"]
    return sum(1 for t in range(lo, hi)
               if ch[t] == correct_option(rec["a_good_first"], t)) / (hi - lo)


def explore_rate(rec, lo, hi):
    return sum(rec["explores"][lo:hi]) / (hi - lo)


# ------------------------------------------------------------------ 自检
def _dev_snapshot(seed, world, days=60):
    """跑 v3 核心 days 天（30 天发育 + 30 天 common garden），返回 life"""
    import novel_situation as NS
    life = NS.scenarios.make(seed, world)
    ok, _ = NS.run_window(life, 0, 30)
    if not ok:
        return None
    w = sim.World(seed, **NS.scenarios.WORLDS["基准"])
    ok, _ = NS.run_window(life, 30, 30, world=w)
    return life if ok else None


def _test_v3_equivalence():
    """★控制一★ NovelTask 关闭时，前 60 天必须与 v3 逐位一致"""
    import novel_situation as NS
    for sd in (20000, 20001, 20002):
        a = _dev_snapshot(sd, "贫瘠世界")
        b = _dev_snapshot(sd, "贫瘠世界")
        if a is None:
            continue
        assert NS.full_hash(a) == NS.full_hash(b), f"v3 核心自身不确定（seed {sd}）"
        # 跑任务【之后】再取 hash：任务不得回写 agent 的任何既有状态
        before = NS.full_hash(a)
        run_task(a.agent, sd)
        assert NS.full_hash(a) == before, \
            "✗ NovelTask 回写了 agent 的既有状态 —— v3 等价性被破坏"
    print("  ✓ 控制一：任务不触碰 v3 状态，前 60 天逐位一致")


def _test_identical_agent():
    """★控制二★ 同一 snapshot clone 两份 + 同一奖励表 → 必须逐 trial 相同"""
    import copy
    import novel_situation as NS
    life = _dev_snapshot(20003, "丰富世界")
    assert life is not None
    x, y = copy.deepcopy(life), copy.deepcopy(life)
    for c in (x, y):
        c.agent.trait_floor = dict(c.agent.trait_floor)
    ra, rb = run_task(x.agent, 20003), run_task(y.agent, 20003)
    assert ra["choices"] == rb["choices"], "✗ 相同 agent + 相同奖励表却分叉"
    assert ra["rewards"] == rb["rewards"]
    print("  ✓ 控制二：相同 agent + 相同奖励表 → 逐 trial 相同")


def _test_shared_reward_table():
    """双胞胎共享奖励表与平局位 —— 不能说"某一支只是运气好\""""
    ra, ua, ga = reward_table(20004)
    rb, ub, gb = reward_table(20004)
    assert ra == rb and ua == ub and ga == gb, "奖励表不是只由种子决定"
    # 一半种子 A 先好
    good = [reward_table(s)[2] for s in range(20000, 20400)]
    frac = sum(good) / len(good)
    assert 0.40 < frac < 0.60, f"A 先好的比例偏了：{frac:.1%}"
    print(f"  ✓ 奖励表只由种子决定；A 先好的种子占 {frac:.1%}")


def _test_history_only_via_novelty():
    """★关键★ 历史只能经 curiosity/caution 进来。改别的状态不得影响任务。"""
    import copy
    life = _dev_snapshot(20005, "贫瘠世界")
    assert life is not None
    base = run_task(copy.deepcopy(life).agent, 20005)
    for field, val in (("hunger", 90.0), ("condition", 20.0),
                       ("shelter", 5.0), ("energy", 10.0)):
        c = copy.deepcopy(life)
        setattr(c.agent, field, val)
        c.agent.inventory = {"food": 99, "material": 99}
        r = run_task(c.agent, 20005)
        assert r["choices"] == base["choices"], \
            f"✗ 任务读了 {field} —— 违反'与资源/生存无关'"
    # 改 curiosity 必须有影响（否则 beta 通路是死的）
    c = copy.deepcopy(life)
    c.agent.traits["curiosity"] = 100.0
    c.agent.traits["caution"] = 0.0
    r = run_task(c.agent, 20005)
    assert r["beta"] != base["beta"], "✗ curiosity/caution 没进 beta"
    print("  ✓ 任务只读 curiosity/caution，不读任何资源/生存变量")


def _test_history_blind():
    """★控制三★ history_blind 时 beta 与历史无关"""
    import copy
    life = _dev_snapshot(20006, "丰富世界")
    assert life is not None
    a = copy.deepcopy(life)
    a.agent.traits["curiosity"], a.agent.traits["caution"] = 95.0, 5.0
    b = copy.deepcopy(life)
    b.agent.traits["curiosity"], b.agent.traits["caution"] = 5.0, 95.0
    ra = run_task(a.agent, 20006, history_blind=True)
    rb = run_task(b.agent, 20006, history_blind=True)
    assert ra["beta"] == rb["beta"] and ra["choices"] == rb["choices"], \
        "✗ history_blind 下仍受历史影响 —— 存在第二条通路"
    print("  ✓ 控制三：history-blind 时两种极端性格轨迹完全相同")


def _test_frozen_config():
    """★控制四★ 默认参数必须等于冻结值；指纹稳定"""
    fp = assert_frozen()
    assert ALPHA == 0.05 and BETA == 0.05 and TAU == 0.20
    assert fp == config_fingerprint()
    # 默认调用与显式传冻结值必须逐 trial 相同
    class S:
        traits = {"curiosity": 60.0, "caution": 40.0, "industry": 50.0}
    a = run_task(S(), 20100)
    b = run_task(S(), 20100, alpha=ALPHA, beta=BETA, tau=TAU)
    assert a["choices"] == b["choices"], "默认调用与显式传参不一致"
    print(f"  ✓ 控制四：参数已冻结 α={ALPHA} β={BETA} τ={TAU}  指纹 {fp}")


def _test_metrics():
    """指标本身的行为要正确"""
    rec = {"a_good_first": True, "choices": [0] * REVERSAL_AT + [1] * 40,
           "rewards": [0] * TRIALS, "explores": [0] * TRIALS}
    assert switch_latency(rec) == 0, "反转后立刻全选新正确项应为 0"
    assert switch_latency_restricted(rec) == 0
    rec2 = dict(rec, choices=[0] * TRIALS)
    assert switch_latency(rec2) is None, "从不切换应返回 None，不是 0"
    assert switch_latency_restricted(rec2) == NEVER_SWITCHED == 36,         "从不切换必须截尾为 36，不能是 None 也不能是 0"
    print(f"  ✓ switch_latency：立刻切换=0，从不切换截尾为 {NEVER_SWITCHED}"
          f"（不删、不当 0）")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"027 NovelTask 自检   核心来自 {os.path.dirname(sim.__file__)}"
          f"   {sim.MODEL_VERSION} → {MODEL_VERSION}")
    _test_v3_equivalence()
    _test_identical_agent()
    _test_shared_reward_table()
    _test_history_only_via_novelty()
    _test_history_blind()
    _test_frozen_config()
    _test_metrics()
    print("\n全部通过。可以进入 group-blind 校准。")
