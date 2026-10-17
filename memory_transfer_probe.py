"""
实验 029 —— memory_transfer_probe.py（★ 识别性探针，不是实验 ★）
================================================================================

跑：  python memory_transfer_probe.py

--------------------------------------------------------------------------------
★★ 这个文件不叫 experiment029.py，是故意的 ★★
--------------------------------------------------------------------------------
我们已经吃过很多次亏：**机制根本没有能力影响 outcome，却直接跑 group
comparison。** 026 的四个 probe 全部栽在这一类问题上。

所以 029 的第一个程序只问一件事：

    ┌──────────────────────────────────────────────────────────┐
    │  这条 memory → retrieval → evidence → choice 的通路，     │
    │  在其他一切完全相同的情况下，                             │
    │  到底有没有能力改变未来的 choice sequence？               │
    └──────────────────────────────────────────────────────────┘

这是 **identifiability check**，不是 hypothesis test。
和 026 当时一样：先证明"实验有能力测到它声称测的东西"。

**本文件明确不做**（今天一律不碰）：
    ⛔ Stable vs Volatile 的正式比较      ⛔ 029 final seeds
    ⛔ preregistration                    ⛔ SESOI
    ⛔ λ 的最终值（本文件**扫**λ，不选 λ）
    ⛔ 把 memory 写进 sim.py              ⛔ LLM / embedding
    ⛔ episodic + semantic + abstraction 三套机制同时上

种子：只用 development 段 `0–1499`（早已烧过）。
      **不碰 80000–81499。**

--------------------------------------------------------------------------------
① 记忆是什么（029 自己的实验层结构，不复用 autobiographical memory）
--------------------------------------------------------------------------------
现有的 `{event, day, importance, text}` 适合做自传体记忆，
**不足以做 causal transfer** —— 它存的是"发生了什么"，不是"什么关系起了作用"。

029 单独建：

    Episode:
        context               关系性情境标签（不是场景描述）
        previous_expectation  当时对手上这个策略的预期
        observation           实际观察到的回报
        prediction_error      observation − previous_expectation
        action_relation       ★ "stay" / "switch" ★
        outcome               采取该 action_relation 之后拿到的回报

    ★★ 最重要的一条：存 stay/switch，不存 A/B ★★
    存了 A/B，换一个新任务之后就没有任何可迁移性 ——
    新任务里根本没有 A 和 B。存"关系"才可能迁移。

    本文件用 `_assert_relational_only()` 把这条**变成硬约束**：
    Episode 的字段里出现任何选项身份都会直接报错。

--------------------------------------------------------------------------------
② 检索（第一版：一个 relational query，故意极简）
--------------------------------------------------------------------------------
    当前状态：  手上这个策略过去一直很好  +  最近连续 prediction error
                        ↓
    检索：      过去有没有出现过 "previously-good strategy + persistent surprise"
                        ↓
    记忆返回：  那种情况下 stay 之后回报怎样、switch 之后回报怎样
                        ↓
    evidence：  m = E[R | switch, similar past] − E[R | stay, similar past]
                        ↓
    决策：      logit(switch) = base_learning + λ·m

**与 027 的本质差异：**

    027    trait_i → β_i                                    （我们替它读一个标量）
    029    current situation → retrieval → past outcomes → evidence → choice
           （"我现在遇到了这个情况，所以我想起以前类似的情况"）

query 不成立时 `m = 0`，**记忆不进入决策** —— 检索是情境触发的，这正是重点。

--------------------------------------------------------------------------------
③ 今天的两把刀
--------------------------------------------------------------------------------
    ★ POSITIVE CONTROL ★
        同一 current state / 同一 Q / 同一 reward table / 同一 random uniforms /
        同一 body —— **只换 memory**。choice sequence 会不会变？
        做不到 → 后面 Stable / Volatile 没必要跑。

    ★ SWAP TEST ★
        Body A + Memory S   vs   Body A + Memory V
        Body B + Memory S   vs   Body B + Memory V
        必须满足：**outcome 跟着 memory 换**，
        而不是"换了 memory，结果仍然跟 body/traits 走"。

--------------------------------------------------------------------------------
④ 任务底座
--------------------------------------------------------------------------------
直接复用 027 的 `novel_task.py`：同一张奖励表、同一 α/β/τ、同一 80 trial +
第 41 trial 反转、同一 restricted switch latency。**一个数都不改**，
这样"memory 通路"与"027 的 trait 通路"是可比的。

⚠ 决策规则改写成 stay/switch 形式（λ=0 时与 027 的 value 差等价，
   但 u 的消耗口径不同 —— 本文件不声称与 027 逐 trial 相同，只声称同底座）。

⚠ 下面这些阈值是 **probe 旋钮，未经校准**，今天只用来看识别性：
   `GOOD_THRESH` / `PE_THRESH` / `SURPRISE_RUN_MIN`。
   它们**不是** 029 的设计参数，正式值要走 group-blind 校准。
"""

import math
import os
import statistics
import sys
from dataclasses import dataclass, fields

import novel_task as NT

# ------------------------------------------------------------------ probe 旋钮
GOOD_THRESH = 0.60        # "这个策略过去一直很好"：手上策略的 Q ≥ 此值
PE_THRESH = 0.30          # 单次 prediction error 算"意外"的门槛（负向）
SURPRISE_RUN_MIN = 3      # "持续意外"：连续几次负向 PE 才触发检索

LAMBDA_GRID = (0.0, 0.25, 0.5, 1.0, 2.0, 4.0)
PROBE_SEEDS = tuple(range(0, 400))        # ★ development 段，早已烧过 ★

ALLOWED_CONTEXTS = ("previously_good_strategy",)
ALLOWED_RELATIONS = ("stay", "switch")


# ================================================================== 记忆结构
@dataclass(frozen=True)
class Episode:
    """029 的实验层记忆条目。★ 不含任何选项身份 ★"""
    context: str
    previous_expectation: float
    observation: float
    prediction_error: float
    action_relation: str      # "stay" / "switch" —— 绝不是 "A" / "B"
    outcome: float

    def __post_init__(self):
        if self.context not in ALLOWED_CONTEXTS:
            raise ValueError(f"未知 context：{self.context!r}")
        if self.action_relation not in ALLOWED_RELATIONS:
            raise ValueError(
                f"action_relation 必须是 stay/switch，拿到 {self.action_relation!r}"
                " —— 存选项身份会让记忆在新任务里失去可迁移性")


class MemoryStore:
    """极简记忆库：一个 relational query，返回 stay/switch 的回报对比。"""

    def __init__(self, name, episodes):
        self.name = name
        self.episodes = list(episodes)

    def evidence(self, context):
        """m = E[R | switch, similar past] − E[R | stay, similar past]

        任一侧没有可比条目 → m = 0（**没有证据，不是证据为 0 差异**）。
        """
        if context is None:
            return 0.0, 0, 0
        sw = [e.outcome for e in self.episodes
              if e.context == context and e.action_relation == "switch"]
        st = [e.outcome for e in self.episodes
              if e.context == context and e.action_relation == "stay"]
        if not sw or not st:
            return 0.0, len(sw), len(st)
        return statistics.fmean(sw) - statistics.fmean(st), len(sw), len(st)


def _episode(relation, outcome, *, expect=0.80, obs=0.0):
    """构造一条 'previously-good strategy + persistent surprise' 下的经历"""
    return Episode(context="previously_good_strategy",
                   previous_expectation=expect,
                   observation=obs,
                   prediction_error=obs - expect,
                   action_relation=relation,
                   outcome=outcome)


# ★ 两个手工记忆库 ★
#
# ⚠ 用户原话只写了 switch 那一侧（S：switch→bad；V：switch→good）。
#    但 m 是**差值**，只有一侧则 evidence() 按定义返回 0（无证据）。
#    所以这里各补了互补的 stay 一侧，并保持两库**完全对称**：
#    唯一差异就是"过去这种情况下，是 stay 划算还是 switch 划算"。
MEM_S = MemoryStore("Memory S（持续意外时：switch 吃亏、stay 划算）", [
    _episode("switch", 0.2), _episode("switch", 0.2), _episode("switch", 0.1),
    _episode("stay",   0.8), _episode("stay",   0.8), _episode("stay",   0.9),
])
MEM_V = MemoryStore("Memory V（持续意外时：switch 划算、stay 吃亏）", [
    _episode("switch", 0.8), _episode("switch", 0.8), _episode("switch", 0.9),
    _episode("stay",   0.2), _episode("stay",   0.2), _episode("stay",   0.1),
])
MEM_EMPTY = MemoryStore("Memory ∅（空库）", [])


# ================================================================== 身体
class Body:
    """027 那条通路的载体：只有 curiosity / caution 进 β。"""

    def __init__(self, name, curiosity, caution):
        self.name = name
        self.traits = {"curiosity": float(curiosity),
                       "caution": float(caution),
                       "industry": 50.0}


# 取两个极端 —— 给 body 通路它可能有的最大量程
BODY_C = Body("Body C（curious 90/10）", 90.0, 10.0)     # novelty_style = 0.90
BODY_K = Body("Body K（cautious 10/90）", 10.0, 90.0)    # novelty_style = 0.05


# ================================================================== 检索触发
def query_from_state(q_cur, surprise_run):
    """current situation → 关系性 query（成立返回 context，不成立返回 None）"""
    if q_cur >= GOOD_THRESH and surprise_run >= SURPRISE_RUN_MIN:
        return "previously_good_strategy"
    return None


# ================================================================== 任务
def run(body, memory, seed, lam):
    """跑 027 的 80-trial 反转任务，决策规则写成 stay/switch 形式。

    logit(switch) = (val_switch − val_stay)/τ  +  λ · m
                     └── base_learning ──┘      └ memory evidence ┘
    """
    rows, us, a_good_first = NT.reward_table(seed)
    b = NT.BETA * NT.novelty_style(body)
    Q = [NT.Q_INIT, NT.Q_INIT]
    N = [0, 0]
    cur = None
    surprise_run = 0
    choices, rewards, fired, m_trace = [], [], [], []

    for t in range(NT.TRIALS):
        val = [Q[i] + b / math.sqrt(1 + N[i]) for i in (0, 1)]

        if cur is None:
            # 第一个 trial 没有"手上的策略"，也就无所谓 stay/switch。
            # 此时 Q、N 两侧相同 → p = 0.5，由共享的 u 决定，两个选项对称。
            d = max(-60.0, min(60.0, (val[0] - val[1]) / NT.TAU))
            c = 0 if us[t] < 1.0 / (1.0 + math.exp(-d)) else 1
            ctx, m = None, 0.0
        else:
            oth = 1 - cur
            ctx = query_from_state(Q[cur], surprise_run)
            m, _, _ = memory.evidence(ctx)
            z = (val[oth] - val[cur]) / NT.TAU + lam * m
            z = max(-60.0, min(60.0, z))
            c = oth if us[t] < 1.0 / (1.0 + math.exp(-z)) else cur

        r = rows[t][c]
        pe = r - Q[c]

        # 只有"继续用同一个策略却持续失望"才累积；换过就清零
        if cur is not None and c == cur and pe < -PE_THRESH:
            surprise_run += 1
        else:
            surprise_run = 0

        N[c] += 1
        Q[c] += NT.ALPHA * (r - Q[c])
        cur = c
        choices.append(c)
        rewards.append(r)
        fired.append(1 if ctx is not None else 0)
        m_trace.append(m)

    return {"seed": seed, "a_good_first": a_good_first, "choices": choices,
            "rewards": rewards, "fired": fired, "m": m_trace, "beta": b,
            "explores": [0] * NT.TRIALS}


def latency(rec):
    return NT.switch_latency_restricted(rec)


def post_correct(rec):
    return NT.correct_rate(rec, NT.REVERSAL_AT, NT.TRIALS)


# ================================================================== 自检
def _assert_relational_only():
    """★硬约束★ Episode 里不许出现任何选项身份"""
    names = {f.name for f in fields(Episode)}
    banned = {"option", "arm", "choice", "a", "b", "stimulus", "label"}
    assert not (names & banned), f"Episode 出现选项身份字段：{names & banned}"
    for mem in (MEM_S, MEM_V):
        for e in mem.episodes:
            assert e.action_relation in ALLOWED_RELATIONS
            assert e.context in ALLOWED_CONTEXTS
            for f in fields(Episode):
                v = getattr(e, f.name)
                assert not (isinstance(v, str) and v in ("A", "B", "0", "1")), \
                    f"字段 {f.name} 存了选项身份 {v!r}"
    # 记忆读出的 evidence 与"手上是哪个物理选项"无关（结构上不可能相关）
    assert MEM_S.evidence("previously_good_strategy")[0] < 0
    assert MEM_V.evidence("previously_good_strategy")[0] > 0
    assert MEM_EMPTY.evidence("previously_good_strategy")[0] == 0.0
    assert MEM_S.evidence(None)[0] == 0.0
    ms = MEM_S.evidence("previously_good_strategy")[0]
    mv = MEM_V.evidence("previously_good_strategy")[0]
    print(f"  ✓ 关系性约束：Episode 只存 stay/switch，不存 A/B")
    print(f"      m(Memory S) = {ms:+.4f}     m(Memory V) = {mv:+.4f}"
          f"     m(空库) = 0（无证据）")
    return ms, mv


def _test_determinism():
    for sd in (7, 42, 301):
        a = run(BODY_C, MEM_V, sd, 1.0)
        b = run(BODY_C, MEM_V, sd, 1.0)
        assert a["choices"] == b["choices"] and a["rewards"] == b["rewards"]
    print("  ✓ 确定性：同 body + 同 memory + 同种子 → 逐 trial 相同")


def _test_memory_blind():
    """★ λ=0 = memory-blind ★ 两个记忆库必须逐 trial 完全相同"""
    diff = 0
    for sd in PROBE_SEEDS:
        if run(BODY_C, MEM_S, sd, 0.0)["choices"] != \
           run(BODY_C, MEM_V, sd, 0.0)["choices"]:
            diff += 1
    assert diff == 0, f"✗ λ=0 时记忆仍影响决策（{diff} 个种子）—— 存在第二条通路"
    print(f"  ✓ memory-blind（λ=0）：{len(PROBE_SEEDS)} 个种子逐 trial 完全相同")


def _retrieval_diagnostics():
    """检索到底有没有触发、什么时候触发 —— 不触发的话后面全是空转"""
    ever, first, rate = 0, [], []
    for sd in PROBE_SEEDS:
        r = run(BODY_C, MEM_V, sd, 1.0)
        f = r["fired"]
        rate.append(sum(f) / NT.TRIALS)
        if any(f):
            ever += 1
            first.append(f.index(1))
    pre = statistics.fmean(
        [sum(run(BODY_C, MEM_V, sd, 1.0)["fired"][:NT.REVERSAL_AT])
         for sd in PROBE_SEEDS])
    n_fire = statistics.fmean(
        [sum(run(BODY_C, MEM_V, sd, 1.0)["fired"]) for sd in PROBE_SEEDS])
    print(f"  ✓ 检索触发：{ever}/{len(PROBE_SEEDS)} 个种子至少触发一次"
          f"（{ever / len(PROBE_SEEDS):.1%}）")
    print(f"      平均每个种子触发 {n_fire:.2f} 个 trial（共 {NT.TRIALS} 个）"
          f"   首次触发 trial 中位数 {statistics.median(first):.0f}"
          f"   反转前平均触发 {pre:.2f} 次")
    return ever, n_fire


def _base_pressure_diagnostic():
    """★ 关键诊断 ★ 检索触发的那一刻，base_learning 自己已经多想 switch 了？

    如果触发时 base 的 p(switch) 已经接近 1，那么 λ·m 无论多大都改不了什么 ——
    **不是记忆没用，是记忆来得太晚**。这决定下一步该修哪里。
    """
    ps = []
    for sd in PROBE_SEEDS:
        rows, us, _ = NT.reward_table(sd)
        b = NT.BETA * NT.novelty_style(BODY_C)
        Q = [NT.Q_INIT, NT.Q_INIT]
        N = [0, 0]
        cur, run_ = None, 0
        for t in range(NT.TRIALS):
            val = [Q[i] + b / math.sqrt(1 + N[i]) for i in (0, 1)]
            if cur is None:
                d = max(-60.0, min(60.0, (val[0] - val[1]) / NT.TAU))
                c = 0 if us[t] < 1.0 / (1.0 + math.exp(-d)) else 1
            else:
                oth = 1 - cur
                z = max(-60.0, min(60.0, (val[oth] - val[cur]) / NT.TAU))
                p = 1.0 / (1.0 + math.exp(-z))
                if query_from_state(Q[cur], run_) is not None:
                    ps.append(p)                 # ★ 只在触发时刻记录 ★
                c = oth if us[t] < p else cur
            r = rows[t][c]
            pe = r - Q[c]
            run_ = run_ + 1 if (cur is not None and c == cur
                                and pe < -PE_THRESH) else 0
            N[c] += 1
            Q[c] += NT.ALPHA * (r - Q[c])
            cur = c
    if not ps:
        print("  ⚠ 检索从未触发 —— 后面的一切都是空转")
        return None
    ps.sort()
    q = lambda f: ps[min(len(ps) - 1, int(f * len(ps)))]      # noqa: E731
    print(f"  ⚑ 触发时刻 base_learning 自己的 p(switch)："
          f"中位数 {statistics.median(ps):.3f}"
          f"   四分位 [{q(.25):.3f}, {q(.75):.3f}]"
          f"   ≥0.9 的比例 {sum(1 for x in ps if x >= 0.9) / len(ps):.1%}")
    return statistics.median(ps)


# ================================================================== 正控制
def positive_control():
    """★ 只换 memory，其他一切相同 —— choice sequence 会不会变？★"""
    print("\n" + "=" * 78)
    print("★ POSITIVE CONTROL ★  同 body / 同 Q / 同奖励表 / 同 u —— 只换 memory")
    print("=" * 78)
    print(f"{'λ':>6}  {'轨迹改变的种子':>14}  {'首个分歧 trial':>14}"
          f"  {'Δlatency (V−S)':>16}  {'Δ反转后正确率':>14}")
    print("-" * 78)
    out = []
    for lam in LAMBDA_GRID:
        changed, firstdiv, dlat, dpc = 0, [], [], []
        for sd in PROBE_SEEDS:
            s = run(BODY_C, MEM_S, sd, lam)
            v = run(BODY_C, MEM_V, sd, lam)
            if s["choices"] != v["choices"]:
                changed += 1
                firstdiv.append(next(i for i in range(NT.TRIALS)
                                     if s["choices"][i] != v["choices"][i]))
            dlat.append(latency(v) - latency(s))
            dpc.append(post_correct(v) - post_correct(s))
        frac = changed / len(PROBE_SEEDS)
        med = statistics.median(firstdiv) if firstdiv else float("nan")
        print(f"{lam:>6.2f}  {changed:>6}/{len(PROBE_SEEDS)} = {frac:>5.1%}"
              f"  {med:>14.0f}  {statistics.fmean(dlat):>+16.3f}"
              f"  {statistics.fmean(dpc):>+14.4f}")
        out.append((lam, frac, statistics.fmean(dlat), statistics.fmean(dpc)))
    return out


# ================================================================== SWAP
def swap_test(lam):
    """★ SWAP TEST ★ outcome 必须跟着 memory 换，而不是跟着 body 走"""
    print("\n" + "=" * 78)
    print(f"★ SWAP TEST ★  Body × Memory 2×2      λ = {lam}")
    print("=" * 78)
    cell, seqs = {}, {}
    for body in (BODY_C, BODY_K):
        for mem in (MEM_S, MEM_V):
            recs = [run(body, mem, sd, lam) for sd in PROBE_SEEDS]
            cell[(body.name, mem.name)] = (
                statistics.fmean([latency(r) for r in recs]),
                statistics.fmean([post_correct(r) for r in recs]))
            seqs[(body.name, mem.name)] = [r["choices"] for r in recs]

    print(f"{'':<26}{'Memory S':>22}{'Memory V':>22}")
    print(f"{'':<26}{'latency  正确率':>22}{'latency  正确率':>22}")
    print("-" * 78)
    for body in (BODY_C, BODY_K):
        row = f"{body.name:<26}"
        for mem in (MEM_S, MEM_V):
            L, P = cell[(body.name, mem.name)]
            row += f"{L:>13.3f}{P:>9.4f}"
        print(row)

    # 换 memory（body 固定）vs 换 body（memory 固定）
    mem_eff = [cell[(b.name, MEM_V.name)][0] - cell[(b.name, MEM_S.name)][0]
               for b in (BODY_C, BODY_K)]
    body_eff = [cell[(BODY_K.name, m.name)][0] - cell[(BODY_C.name, m.name)][0]
                for m in (MEM_S, MEM_V)]

    def frac_changed(k1, k2):
        return sum(1 for a, b in zip(seqs[k1], seqs[k2]) if a != b) / len(PROBE_SEEDS)

    mem_chg = [frac_changed((b.name, MEM_S.name), (b.name, MEM_V.name))
               for b in (BODY_C, BODY_K)]
    body_chg = [frac_changed((BODY_C.name, m.name), (BODY_K.name, m.name))
                for m in (MEM_S, MEM_V)]

    print("-" * 78)
    print(f"  换 memory（body 固定）  Δlatency = "
          f"{mem_eff[0]:+.3f} / {mem_eff[1]:+.3f}"
          f"   轨迹改变 {mem_chg[0]:.1%} / {mem_chg[1]:.1%}")
    print(f"  换 body（memory 固定）  Δlatency = "
          f"{body_eff[0]:+.3f} / {body_eff[1]:+.3f}"
          f"   轨迹改变 {body_chg[0]:.1%} / {body_chg[1]:.1%}")

    mm = statistics.fmean([abs(x) for x in mem_eff])
    bb = statistics.fmean([abs(x) for x in body_eff])
    ratio = mm / bb if bb > 0 else float("inf")
    print(f"\n  |memory 效应| = {mm:.3f} trial      "
          f"|body 效应| = {bb:.3f} trial      比值 = {ratio:.2f}×")
    # 判读：效应是否跟着 memory 走，且方向在两个 body 上一致
    same_sign = (mem_eff[0] < 0) == (mem_eff[1] < 0) and mem_eff[0] != 0
    verdict = mm > bb and same_sign
    print(f"  memory 效应方向在两个 body 上一致：{'是' if same_sign else '否'}")
    print(f"  ★ SWAP 判读：{'outcome 跟着 memory 换' if verdict else '⚠ 未通过'}")
    return mm, bb, ratio, verdict


# ================================================================== main
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    fp = NT.assert_frozen()
    print("=" * 78)
    print("029 memory transfer —— ★识别性探针，不是实验★")
    print("=" * 78)
    print(f"任务底座：027 novel_task  指纹 {fp}  "
          f"TRIALS={NT.TRIALS} REVERSAL_AT={NT.REVERSAL_AT} "
          f"α={NT.ALPHA} β={NT.BETA} τ={NT.TAU}")
    print(f"种子：development 段 {PROBE_SEEDS[0]}–{PROBE_SEEDS[-1]}"
          f"（n={len(PROBE_SEEDS)}）★ 不碰 80000–81499 ★")
    print(f"probe 旋钮（未校准）：GOOD_THRESH={GOOD_THRESH} "
          f"PE_THRESH={PE_THRESH} SURPRISE_RUN_MIN={SURPRISE_RUN_MIN}")
    print("\n[ 工程自检 ]")
    _assert_relational_only()
    _test_determinism()
    _test_memory_blind()
    _retrieval_diagnostics()
    _base_pressure_diagnostic()

    pc = positive_control()
    print("\n" + "=" * 78)
    print("★ SWAP TEST 沿 λ 扫（今天不选 λ，只看它能不能在某个 λ 上通过）★")
    print("=" * 78)
    sw = [(lam,) + swap_test(lam) for lam in LAMBDA_GRID if lam > 0]

    print("\n" + "=" * 78)
    print("★ 今天只回答一个问题：这条通路有没有可识别性 ★")
    print("=" * 78)
    ok = any(f > 0 for lam, f, _, _ in pc if lam > 0)
    passed = [lam for lam, _, _, _, v in sw if v]
    print(f"  positive control 通过（λ>0 时只换 memory 就能改变轨迹）："
          f"{'是' if ok else '否'}")
    print(f"  SWAP 通过的 λ：{passed if passed else '★ 无 ★（全部 λ 都没通过）'}")
    print("\n  λ      |memory 效应|   |body 效应|      比值   SWAP")
    for lam, mm, bb, ratio, v in sw:
        print(f"  {lam:<5.2f}  {mm:>12.3f}  {bb:>11.3f}  {ratio:>8.2f}×"
              f"   {'通过' if v else '未通过'}")
    print("\n⚠ 通过 ≠ 可以跑 Stable/Volatile。"
          "λ 还没定、阈值还没校准、预注册还没写。")
