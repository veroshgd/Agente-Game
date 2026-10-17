"""
实验 029 —— memory_acquisition_probe.py（★ 只做上游，不接 novel task ★）
================================================================================

跑：  python memory_acquisition_probe.py

--------------------------------------------------------------------------------
唯一要回答的问题
--------------------------------------------------------------------------------
    ┌────────────────────────────────────────────────────────────────┐
    │  Stable 和 Volatile 两种经历，能不能【自然生成】我们手工        │
    │  MEM_S / MEM_V 所代表的那种不同 relational evidence？          │
    └────────────────────────────────────────────────────────────────┘

**本文件不接 novel task。** 允许看的只有上游：

```
✅ episode 数 / surprise episode 数 / stay-switch 数 / reward marginal
✅ memory evidence m 的分布 / episode completeness
✅ Stable / Volatile 的 manipulation check 与 matching diagnostics
⛔ novel-task latency        ⛔ post-change errors
⛔ Stable vs Volatile transfer effect
```

这样我们还保留调 acquisition 机制的自由，
**而不会开始围着 final outcome 调设计。**

--------------------------------------------------------------------------------
★ 关键设计：两边都经历 surprise ★
--------------------------------------------------------------------------------
❌ 错误做法：「Stable 从来没有 surprise，Volatile 有很多 surprise」。
   那太容易了 —— memory 的区别会退化成"一个有数据、一个没数据"。

✅ 正确做法：**同一种表面现象，意味着不同的东西。**

```
Stable    过去一直有效的策略 → 连续异常失败 → 但环境其实没变 → 坚持原策略最终恢复
Volatile  过去一直有效的策略 → 连续异常失败 → 环境真的 change point → switch 后恢复
```

于是两边真正学到的关系是：

```
Stable memory     persistent surprise 有时只是 noise，stay 更划算
Volatile memory   persistent surprise 往往意味着规则变了，switch 更划算
```

### ★★ 异常窗口内两个世界【逐位相同】★★

每个 problem 的时间结构：

```
trial  0 .. E-1        原策略 p_high，另一个 p_low      ← 两个条件相同
trial  E .. E+D-1      ★两个都掉到 p_low★              ← 两个条件【相同】：
                                                          光看异常本身分不出身处哪个世界
trial  E+D .. T-1      Stable   ：原策略恢复 p_high
                       Volatile ：另一个变成 p_high
```

- **reward opportunity 逐 trial 相等**（任何 trial 都恰好有一个 p_high 或都没有）
- 异常窗口里的 reward 抽样**共用同一条随机流** → 两个条件在 `trial < E+D` 上
  **逐位相同**。差异只出现在 E+D 之后 —— 也就是"这次异常到底意味着什么"。

--------------------------------------------------------------------------------
Episode 怎么长出来（复用探针的同一套 query / resolution）
--------------------------------------------------------------------------------
acquisition 期间 **没有记忆可用**（记忆正在被建立），所以选择只由 base learning
决定（Q-learning + softmax，与 027 同 α/τ）。

情境窗口的进出条件与 `memory_transfer_probe3.py` **逐字相同**：

```
进入：Q[cur] ≥ GOOD_THRESH 且连续 surprise ≥ SURPRISE_RUN_MIN   → 记下 suspect
退出：Q[另一个] > Q[suspect]  或  在 suspect 上连续不意外 ≥ SURPRISE_RUN_MIN
      （★ 用 Q update 之后的 Q 判 —— probe3 修掉的时序 bug ★）
```

窗口内**每一次决策写一条 Episode**：

```
context               "previously_good_strategy"
previous_expectation  窗口开始时 Q[suspect]（那个正在失效的策略，我们本来指望它多少）
observation           触发窗口的那串异常里的平均回报
prediction_error      observation − previous_expectation
action_relation       这次决策是 stay（还在 suspect 上）还是 switch（离开了）
outcome               这次决策拿到的回报
```

★ 依旧**只存 relation，不存 identity**（规则 85）—— 直接复用探针的 `Episode`，
它的 `__post_init__` 会把任何选项身份挡回去。

--------------------------------------------------------------------------------
四个 matching diagnostics（Stable / Volatile 必须尽量匹配）
--------------------------------------------------------------------------------
```
① 总 trial 数              ② 总 reward opportunity
③ episode 数量             ④ 具体 option identity / first-good side
```
**允许不同的只有**：`context × action × outcome` 的关系结构。
以后 SHUFFLE 控制才能进一步证明：起作用的是**关系**，而不是 marginal statistics。

--------------------------------------------------------------------------------
本阶段仍然不做
--------------------------------------------------------------------------------
```
⛔ 接 novel task    ⛔ 校准 λ    ⛔ SESOI    ⛔ preregistration    ⛔ final seeds
⛔ 看任何 transfer outcome
```
λ 要等真实 m 分布出来之后，用 **frozen-state counterfactual potency**
（probe3 已写好那套 pipeline）按**接口容量**冻结 ——
而不是按"Stable/Volatile 最后谁赢得漂亮"。
"""

import math
import random
import statistics
import sys

import novel_task as NT
from memory_transfer_probe import (Episode, MemoryStore, GOOD_THRESH,
                                   PE_THRESH, SURPRISE_RUN_MIN, PROBE_SEEDS)

# ---- acquisition 参数：★ 2026-08-18 冻结为 029 acquisition candidate ★ ----
#
# 只增加 anomaly【前】的学习长度，不动 GOOD_THRESH / PE_THRESH / RUN_MIN，
# 也不增加 problem 数量。纯上游 sweep（0–399，未接 novel task）：
#
#   pre-anomaly   Stable completeness   Volatile completeness   complete-only m 分离度
#      20              23.5%                  24.0%                  +0.904
#      28              49.2%                  52.0%                  +0.872
#      34              61.0%                  69.3%                  +0.902
#   ★ 36 ★            65.8%                  73.3%                  +0.894
#      40              69.5%                  76.8%                  +0.884
#
# → 增加 pre-anomaly experience **主要修 yield，几乎不改 memory contrast**，
#   是一个干净的 engineering correction。
# → 选 36 是 elbow（20→36 换来 +42pp / +49pp；36→40 只再换 3–4pp），
#   **不是**挑 separation 最大的点 —— separation 在 34/35/36/38 都差不多。
N_PROBLEMS = 3
ANOMALY_AT = 36          # ★冻结★ anomaly 前的学习长度（原 20）
ANOMALY_LEN = 8          # ★不变★
T_PROBLEM = 66           # ★冻结★ 使 anomaly 后仍为 66−36−8 = 22（与原来相同）
P_HIGH, P_LOW = NT.P_HIGH, NT.P_LOW
ALPHA, TAU, Q_INIT = NT.ALPHA, NT.TAU, NT.Q_INIT

_SALT_ACQ = 0x29A10
_SALT_U = 0x29B10

CONDITIONS = ("Stable", "Volatile")

# 唯一变化是 pre-anomaly 学习长度；anomaly 本身与 anomaly 后的再学习时间都没动
assert T_PROBLEM - ANOMALY_AT - ANOMALY_LEN == 22, "anomaly 后必须仍是 22 个 trial"
assert ANOMALY_LEN == 8


class NeutralBody:
    """acquisition 阶段用中性 body，避免把 trait 通路混进上游诊断"""
    name = "Neutral（50/50）"
    traits = {"curiosity": 50.0, "caution": 50.0, "industry": 50.0}


# ================================================================== 环境
def problem_schedule(condition, t):
    """返回 (p_option0_is_good, 两个选项的 p)。good0 之类的身份在外面 counterbalance。

    ★ trial < ANOMALY_AT+ANOMALY_LEN 时两个条件完全相同 ★
    """
    if t < ANOMALY_AT:
        return "orig"                       # 原策略好
    if t < ANOMALY_AT + ANOMALY_LEN:
        return "none"                       # ★异常窗口：两个都不好★
    return "orig" if condition == "Stable" else "flip"


def acq_tables(seed, condition):
    """每个 problem 一张表。奖励抽样对两个条件**共用同一条随机流**。

    → `trial < ANOMALY_AT+ANOMALY_LEN` 的部分两个条件逐位相同。
    """
    probs = []
    for pi in range(N_PROBLEMS):
        rng = random.Random(_SALT_ACQ ^ (seed * 131 + pi))
        orig_is_0 = rng.random() < 0.5        # ★ counterbalance：哪个 index 先好 ★
        rows, opp = [], 0.0
        for t in range(T_PROBLEM):
            who = problem_schedule(condition, t)
            if who == "none":
                p0 = p1 = P_LOW
            else:
                good0 = orig_is_0 if who == "orig" else (not orig_is_0)
                p0, p1 = (P_HIGH, P_LOW) if good0 else (P_LOW, P_HIGH)
            # ★共用随机流★：先抽两个 u，再按 p 判定
            u0, u1 = rng.random(), rng.random()
            rows.append((1 if u0 < p0 else 0, 1 if u1 < p1 else 0))
            opp += max(p0, p1)
        urng = random.Random(_SALT_U ^ (seed * 131 + pi))
        us = [urng.random() for _ in range(T_PROBLEM)]
        probs.append({"rows": rows, "us": us, "orig_is_0": orig_is_0,
                      "opportunity": opp})
    return probs


# ================================================================== 获取
def acquire(seed, condition, body=NeutralBody):
    """跑 N_PROBLEMS 个发育问题，产出 Episode 列表 + 上游诊断。**无记忆参与。**"""
    b = NT.BETA * NT.novelty_style(body)
    episodes, diag = [], {"trials": 0, "opportunity": 0.0, "reward": 0,
                          "windows": 0, "window_trials": 0, "orig_is_0": []}

    for prob in acq_tables(seed, condition):
        rows, us = prob["rows"], prob["us"]
        diag["opportunity"] += prob["opportunity"]
        diag["orig_is_0"].append(prob["orig_is_0"])
        Q, N = [Q_INIT, Q_INIT], [0, 0]
        cur, surprise_run = None, 0
        suspect, calm_run = None, 0
        onset_expect, onset_obs = 0.0, 0.0
        surprise_buf = []

        for t in range(T_PROBLEM):
            val = [Q[i] + b / math.sqrt(1 + N[i]) for i in (0, 1)]
            if cur is None:
                d = max(-60.0, min(60.0, (val[0] - val[1]) / TAU))
                c = 0 if us[t] < 1.0 / (1.0 + math.exp(-d)) else 1
                in_window = False
            else:
                if suspect is None and Q[cur] >= GOOD_THRESH \
                        and surprise_run >= SURPRISE_RUN_MIN:
                    suspect = cur
                    calm_run = 0
                    onset_expect = Q[cur]
                    onset_obs = statistics.fmean(surprise_buf[-surprise_run:]) \
                        if surprise_run else 0.0
                    diag["windows"] += 1
                oth = 1 - cur
                in_window = suspect is not None
                # ★ acquisition 期间没有记忆可用 —— 纯 base learning ★
                z = max(-60.0, min(60.0, (val[oth] - val[cur]) / TAU))
                c = oth if us[t] < 1.0 / (1.0 + math.exp(-z)) else cur

            r = rows[t][c]
            pe = r - Q[c]
            surprise_buf.append(r)

            if in_window:
                episodes.append(Episode(
                    context="previously_good_strategy",
                    previous_expectation=onset_expect,
                    observation=onset_obs,
                    prediction_error=onset_obs - onset_expect,
                    action_relation="stay" if c == suspect else "switch",
                    outcome=float(r)))
                diag["window_trials"] += 1

            if cur is not None and c == cur and pe < -PE_THRESH:
                surprise_run += 1
            else:
                surprise_run = 0
            if suspect is not None and c == suspect:
                calm_run = calm_run + 1 if pe >= -PE_THRESH else 0

            N[c] += 1
            Q[c] += ALPHA * (r - Q[c])           # ★先更新 Q★

            if suspect is not None:              # ★再判 resolution（probe3 时序）★
                if Q[1 - suspect] > Q[suspect] or calm_run >= SURPRISE_RUN_MIN:
                    suspect, calm_run = None, 0

            cur = c
            diag["trials"] += 1
            diag["reward"] += r

    return episodes, diag


def evidence_of(episodes):
    """把长出来的 episodes 装进 MemoryStore，读出 m（与探针同一个读出口径）"""
    mem = MemoryStore("acquired", episodes)
    m, n_sw, n_st = mem.evidence("previously_good_strategy")
    return m, n_sw, n_st


# ================================================================== 诊断
def _q(xs, f):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(f * len(xs)))]


def run_all():
    out = {}
    for cond in CONDITIONS:
        rec = []
        for sd in PROBE_SEEDS:
            eps, diag = acquire(sd, cond)
            m, n_sw, n_st = evidence_of(eps)
            rec.append({"m": m, "n": len(eps), "n_sw": n_sw, "n_st": n_st,
                        "complete": n_sw > 0 and n_st > 0, **diag})
        out[cond] = rec
    return out


def matching_report(res):
    print("\n" + "=" * 78)
    print("★ MATCHING DIAGNOSTICS —— 四项必须匹配 ★")
    print("=" * 78)
    print(f"{'':<26}{'Stable':>16}{'Volatile':>16}{'一致':>8}")
    print("-" * 78)
    rows = [
        ("① 总 trial 数", lambda r: statistics.fmean([x["trials"] for x in r])),
        ("② 总 reward opportunity", lambda r: statistics.fmean([x["opportunity"] for x in r])),
        ("③ episode 数", lambda r: statistics.fmean([x["n"] for x in r])),
        ("④ first-good = index0 比例",
         lambda r: statistics.fmean([sum(x["orig_is_0"]) / N_PROBLEMS for x in r])),
        ("   实际拿到的总 reward", lambda r: statistics.fmean([x["reward"] for x in r])),
        ("   情境窗口数", lambda r: statistics.fmean([x["windows"] for x in r])),
    ]
    ok = True
    for label, fn in rows:
        a, b = fn(res["Stable"]), fn(res["Volatile"])
        same = abs(a - b) < 1e-9
        if label.startswith(("①", "②", "④")) and not same:
            ok = False
        print(f"{label:<26}{a:>16.4f}{b:>16.4f}{'✓' if same else '≠':>8}")
    print(f"\n  ★ 构造性匹配（①②④）{'全部逐位相等' if ok else '⚠ 有不相等项'} ★")
    print("  ③ episode 数是**行为产物**，不要求逐位相等 —— 但差太多就说明"
          "两边形成记忆的机会不对等，要报告。")


def manipulation_report(res):
    print("\n" + "=" * 78)
    print("★ MANIPULATION CHECK —— 同一种表面现象，意味着不同的东西 ★")
    print("=" * 78)
    # 环境层：异常窗口内两个条件是否逐位相同
    same_prefix = True
    for sd in PROBE_SEEDS[:100]:
        a, b = acq_tables(sd, "Stable"), acq_tables(sd, "Volatile")
        for pa, pb in zip(a, b):
            k = ANOMALY_AT + ANOMALY_LEN
            if pa["rows"][:k] != pb["rows"][:k] or pa["us"] != pb["us"]:
                same_prefix = False
    print(f"  异常窗口结束前（trial < {ANOMALY_AT + ANOMALY_LEN}）两个条件逐位相同："
          f"{'是 ✓' if same_prefix else '否 ✗'}")
    print(f"  → 光看异常本身**分不出**身处哪个世界；差异只在'这次异常意味着什么'。")
    # 环境层：窗口后谁好
    a = acq_tables(0, "Stable")[0]
    print(f"  异常窗口后：Stable = 原策略恢复 / Volatile = 另一个变好"
          f"（构造，见 problem_schedule）")
    # 行为层：窗口里 stay/switch 的比例
    print(f"\n{'':<12}{'窗口内 trial':>14}{'stay 条目':>12}{'switch 条目':>13}"
          f"{'switch 占比':>13}{'两侧齐全':>11}")
    print("-" * 78)
    for cond in CONDITIONS:
        r = res[cond]
        st = statistics.fmean([x["n_st"] for x in r])
        sw = statistics.fmean([x["n_sw"] for x in r])
        print(f"{cond:<12}{statistics.fmean([x['window_trials'] for x in r]):>14.2f}"
              f"{st:>12.2f}{sw:>13.2f}{sw / (st + sw) if st + sw else 0:>13.1%}"
              f"{statistics.fmean([x['complete'] for x in r]):>11.1%}")


def yield_diagnostic():
    """★ 为什么只有 1/4 的 agent 长出记忆 —— 卡在入场条件的哪一半？★

    入场要同时满足：(i) Q[手上的策略] ≥ GOOD_THRESH   (ii) 连续 surprise ≥ 3。
    这里在 acquisition 轨迹上分别统计两半各自的达成率。
    """
    print("\n" + "=" * 78)
    print("★ YIELD 诊断 —— 入场条件的两半各自卡在哪 ★")
    print("=" * 78)
    print(f"{'':<12}{'异常起点 Q≥0.6':>16}{'达成过 stay-run≥3':>20}"
          f"{'两者同时':>12}{'最长 stay-run':>15}")
    print("-" * 78)
    for cond in CONDITIONS:
        okq = okr = okb = 0
        best = []
        for sd in PROBE_SEEDS:
            b = NT.BETA * NT.novelty_style(NeutralBody)
            for prob in acq_tables(sd, cond):
                rows, us = prob["rows"], prob["us"]
                Q, N = [Q_INIT, Q_INIT], [0, 0]
                cur, run_ = None, 0
                q_at_onset, maxrun, both = 0.0, 0, False
                for t in range(T_PROBLEM):
                    val = [Q[i] + b / math.sqrt(1 + N[i]) for i in (0, 1)]
                    if cur is None:
                        d = max(-60.0, min(60.0, (val[0] - val[1]) / TAU))
                        c = 0 if us[t] < 1.0 / (1.0 + math.exp(-d)) else 1
                    else:
                        oth = 1 - cur
                        z = max(-60.0, min(60.0, (val[oth] - val[cur]) / TAU))
                        c = oth if us[t] < 1.0 / (1.0 + math.exp(-z)) else cur
                    if t == ANOMALY_AT:
                        q_at_onset = Q[c]
                    r = rows[t][c]
                    pe = r - Q[c]
                    if cur is not None and c == cur and pe < -PE_THRESH:
                        run_ += 1
                        maxrun = max(maxrun, run_)
                        if run_ >= SURPRISE_RUN_MIN and Q[c] >= GOOD_THRESH:
                            both = True
                    else:
                        run_ = 0
                    N[c] += 1
                    Q[c] += ALPHA * (r - Q[c])
                    cur = c
                okq += q_at_onset >= GOOD_THRESH
                okr += maxrun >= SURPRISE_RUN_MIN
                okb += both
                best.append(maxrun)
        n = len(PROBE_SEEDS) * N_PROBLEMS
        print(f"{cond:<12}{okq / n:>15.1%}{okr / n:>20.1%}{okb / n:>12.1%}"
              f"{statistics.fmean(best):>15.2f}")
    print("\n  ⚠ 这两半哪一半更卡，决定下一步该动 acquisition 的哪个部件"
          "（今天不动）。")


def evidence_report(res):
    print("\n" + "=" * 78)
    print("★ MEMORY EVIDENCE m 的分布（= 真实经历长出来的 relational evidence）★")
    print("=" * 78)
    print("  手工对照：MEM_S 的 m = −0.667，MEM_V 的 m = +0.667（最大对比度）")
    print(f"\n{'':<12}{'n(可定义 m)':>13}{'mean m':>10}{'SD':>9}{'p10':>9}"
          f"{'中位数':>9}{'p90':>9}{'m>0 比例':>11}")
    print("-" * 78)
    ms = {}
    for cond in CONDITIONS:
        v = [x["m"] for x in res[cond] if x["complete"]]
        ms[cond] = v
        if not v:
            print(f"{cond:<12}{'0':>13}   ⚠ 没有任何 agent 长出可定义的 m")
            continue
        print(f"{cond:<12}{len(v):>13}{statistics.fmean(v):>10.4f}"
              f"{statistics.pstdev(v):>9.4f}{_q(v, .10):>9.4f}"
              f"{statistics.median(v):>9.4f}{_q(v, .90):>9.4f}"
              f"{sum(1 for x in v if x > 0) / len(v):>11.1%}")

    # ============================================================ 规则 91
    print("\n" + "-" * 78)
    print("★ 必须分开报的两个 margin —— memory availability 本身就是发育结果 ★")
    print("-" * 78)
    print(f"{'':<12}{'extensive: P[m 可用]':>22}{'intensive: mean(m|可用)':>26}"
          f"{'全体 mean m':>14}{'全体 median':>13}")
    print("-" * 78)
    full = {}
    for cond in CONDITIONS:
        allm = [x["m"] for x in res[cond]]         # ★缺任一侧 → m=0，仍然计入★
        full[cond] = allm
        ext = statistics.fmean([x["complete"] for x in res[cond]])
        inten = statistics.fmean(ms[cond]) if ms[cond] else float("nan")
        print(f"{cond:<12}{ext:>21.1%}{inten:>26.4f}"
              f"{statistics.fmean(allm):>14.4f}{statistics.median(allm):>13.4f}")

    d_pop = statistics.fmean(full["Volatile"]) - statistics.fmean(full["Stable"])
    d_cmp = (statistics.fmean(ms["Volatile"]) - statistics.fmean(ms["Stable"])) \
        if ms["Stable"] and ms["Volatile"] else float("nan")
    print(f"\n  population-level 分离度（全部 agent，含 m=0）= {d_pop:+.4f}   ★这是真值★")
    print(f"  complete-only 分离度（只看长出记忆的）      = {d_cmp:+.4f}   ⚠ 夸大")
    print(f"  手工版分离度 = +1.3333  →  真实 population 达到 {abs(d_pop) / 1.3333:.1%}"
          f"，complete-only 会显得有 {abs(d_cmp) / 1.3333:.1%}")
    print("""
  ⛔ 校准 λ 必须用**全部 agent 的真实 m，包括 m=0 的那些**。
     先筛掉"没有成功形成可用 memory"的 agent、再用剩下最有信息的一批做 calibration，
     会**系统性夸大 memory channel 的真实输入强度** ——
     结构上与 survivor conditioning 是同一个错误（规则 88 / 91）。

  ⚠ Stable 与 Volatile 的 yield 不相等（见上）**不需要修**：
     Volatile 本来就更容易同时积累 stay 与 switch 两类经验，
     这属于 history → memory availability → future behavior 的一部分。
     强行把 completeness 配平 = 修改 post-treatment mediator。""")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("=" * 78)
    print("029 memory ACQUISITION probe —— ★只做上游，不接 novel task★")
    print("=" * 78)
    print(f"发育：{N_PROBLEMS} 个 problem × {T_PROBLEM} trial"
          f"（异常在 {ANOMALY_AT}–{ANOMALY_AT + ANOMALY_LEN - 1}）"
          f"   种子 {PROBE_SEEDS[0]}–{PROBE_SEEDS[-1]}  n={len(PROBE_SEEDS)}")
    print(f"读出口径与探针一致：GOOD_THRESH={GOOD_THRESH} PE_THRESH={PE_THRESH} "
          f"SURPRISE_RUN_MIN={SURPRISE_RUN_MIN}")
    print("★ 80000–81499 未碰 ★   ⛔ 本文件不计算任何 transfer outcome ⛔")

    res = run_all()
    matching_report(res)
    manipulation_report(res)
    yield_diagnostic()
    evidence_report(res)

    print("\n" + "=" * 78)
    print("⛔ 本阶段禁止查看：novel-task latency / post-change errors /")
    print("   Stable vs Volatile transfer effect —— 代码里也没有算。")
    print("=" * 78)
