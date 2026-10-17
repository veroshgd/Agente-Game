"""
实验 029 —— memory_transfer_probe2.py（★ 识别性探针 v2：stateful retrieval ★）
================================================================================

跑：  python memory_transfer_probe2.py

v1（`memory_transfer_probe.py`）**原封不动保留**，结果也不覆盖 ——
那次失败本身是方法学记录的一部分。本文件 import v1 的记忆库、身体、阈值，
**唯一改变的是检索机制**：one-shot → stateful。

--------------------------------------------------------------------------------
① (c) 判据修正：dominance criterion ★ 正式撤回 ★
--------------------------------------------------------------------------------
    ⛔ 撤回：|memory effect| > |body effect|

> Original SWAP dominance criterion failed at all tested λ, after which
> inspection showed that the criterion compared an event-triggered channel
> active on ~0.69/80 trials with an always-on trait channel. The dominance
> criterion was therefore **retired before any Stable/Volatile outcome was
> observed**.

**撤回的理由不是"它没通过"，而是它测的不是我们想知道的东西。**
它回答的是"memory 的终点效应是不是比 body 还大"，
而 SWAP 该回答的是"**body 完全固定时，只换 memory，未来行为是否随记忆内容
发生预测方向的改变**"。这是两个完全不同的 estimand。

### 新 SWAP（本文件实现）

```
M_C = L(Body C, Memory V) − L(Body C, Memory S)
M_K = L(Body K, Memory V) − L(Body K, Memory S)
M   = (M_C + M_K) / 2
```

关心：① M_C 与 M_K 方向是否一致  ② pooled M 是否在预注册方向
      ③ 是否超过功能 SESOI（**今天不定 SESOI**）
      ④ Body × Memory interaction 是否强到说明 memory 只在某一种 body 上工作

**body effect 只作 robustness diagnostic，不再是闸门。**

--------------------------------------------------------------------------------
② 规则 86 的方向修正 → 新规则 87
--------------------------------------------------------------------------------
❌ 旧说法："比较之前必须 equal exposure。"

**memory 和 personality 本来就不该有相同 exposure。**
人格是一直存在的 prior；记忆应该是**遇到相关情况时才被调用**。
为了公平强行让 memory 80/80 trial 在线，反而会毁掉本设计最重要的理论特征
—— **context-dependent retrieval**。

> ### ★ 规则 87 ★
> 对 event-triggered 机制，**不能直接拿 endpoint effect 与 always-on 机制
> 比大小**；必须把 **exposure** 与 **per-opportunity influence** 分开报告。

所以 memory effect 拆成两个量：

```
A. Exposure   E_i = #{retrieval-eligible trials}      ← 有多少次发言机会
B. Potency    Δp_t = p_switch(M_V) − p_switch(M_S)    ← 每次发言能推多远
              在**完全相同的 decision state** 上算
```

Potency 的算法：用 **λ=0 的 memory-blind 轨迹冻结 decision states**
（同 Q / 同 N / 同 current option / 同 surprise state），
再 counterfactually 只换 Memory S / Memory V。
这样才能区分"memory 很弱"与"memory 每次出手都有力、只是几乎没机会出手"。

--------------------------------------------------------------------------------
③ (a) stateful retrieval —— 不是"固定保持 N trial"
--------------------------------------------------------------------------------
固定 N 会新增一个任意参数。改成 **retrieval → active memory state → resolution**：

```
NORMAL
  ↓  连续 persistent surprise（≥ SURPRISE_RUN_MIN，且手上策略过去很好）
RETRIEVE   ← 记下此刻的 suspect strategy（"我怀疑的是这一个"）
  ↓  m 进入 working decision state，接下来每次决策继续使用
ACTIVE
  ↓  ① 新策略拿到足够证据：Q[另一个] > Q[suspect]        →"哦，看来真的变了"
  ↓  ② surprise 被解释：在 suspect 上连续 SURPRISE_RUN_MIN 次不再意外
  ↓                                                     →"刚才只是偶然"
RESOLVED → 清除 memory evidence，回到 NORMAL（以后可再次触发）
```

**两个 resolution 条件都只用已有量**（Q、pe、`PE_THRESH`、`SURPRISE_RUN_MIN`），
**没有新增任何参数**。②与入场条件对称：进场要连续 3 次意外，
出场也要连续 3 次不意外。

### ★ 关键：ACTIVE 期间 m 的作用对象是 suspect，不是"switch"这个动作 ★

v1 每个 trial 都把 `+λm` 加在"switch"上。一旦推成了一次 switch，
下一 trial 再加 `+λm` 就变成"再换回去"，语义是错的，会来回抖。

记忆的内容是"**在这种情况下，离开那个可疑策略更划算**"。所以：

```
logit(switch) += λ · m · s        s = +1 若 switch 是【离开 suspect】
                                  s = −1 若 switch 是【回到 suspect】
```

这才是"我想起来以前遇到过这种情况，因此我现在**怀疑规则变了**"——
这个怀疑会一直持续到"看来真的变了"或"刚才只是偶然"。

⚠ `suspect` 是决策时的**工作变量**，**不是** Episode 里存的东西。
记忆里依旧只有 stay/switch，没有任何选项身份（规则 85 不变）。

--------------------------------------------------------------------------------
④ 顺手锁住一个隐藏问题：potential vs realized retrieval
--------------------------------------------------------------------------------
`fired` 本身受前面 choice sequence 影响 —— 例如 cautious body 更容易连续 stay
三次，于是更容易触发检索。**触发次数本身就是 task dynamics 的产物。**

```
potential retrieval opportunity   在 memory-blind（λ=0）轨迹上定义 → 查机制 exposure
realized retrieval                正式 memory-enabled 轨迹上实际发生 → 是结果的一部分
```

⛔ **绝对不许**只分析"成功想起了记忆"的 agent —— 那是 survivor conditioning。
本文件所有汇总都用**全部 400 个种子**，不按是否触发筛选（有断言）。

--------------------------------------------------------------------------------
⑤ 本次故意不动的东西
--------------------------------------------------------------------------------
```
GOOD_THRESH=.60   PE_THRESH=.30   SURPRISE_RUN_MIN=3   任务仍只有一次 reversal
seeds 0–399       λ 仍然只扫不选
⛔ (b) 放宽 SURPRISE_RUN_MIN      ⛔ (d) 多 change-point 任务
⛔ final seeds  ⛔ preregistration  ⛔ SESOI  ⛔ Stable/Volatile outcome
```

**为什么先 (a) 不先 (b)**：v1 已证明触发时决策**没有饱和**
（base p(switch) 中位数 0.208），所以不是"想起来太晚已经没得选"。
把 `SURPRISE_RUN_MIN` 3→2 只是让记忆更早出现，
**没有解决"一出现就被清掉"** —— 那是治数量，不是治机制。

**为什么现在不做 (d)**：把一次 reversal 变成三次，exposure 自然变多，
结果变强时我们分不清是"机制修好了"还是"同一个弱 one-shot 效应重复了三遍"。
(d) 该在单 change-point 上把机制搞对之后再做，那时它是
**dose-of-opportunity robustness test**。
"""

import math
import random
import statistics
import sys

import novel_task as NT
import memory_transfer_probe as P1
from memory_transfer_probe import (BODY_C, BODY_K, MEM_S, MEM_V,
                                   GOOD_THRESH, PE_THRESH, SURPRISE_RUN_MIN,
                                   LAMBDA_GRID, PROBE_SEEDS, query_from_state)

N_BOOT = 10000
ANALYSIS_SEED = 8181            # 固定，分析层可复现


# ================================================================== v2 主循环
def run_stateful(body, memory, seed, lam, *, trace=False):
    """stateful retrieval：RETRIEVE → ACTIVE → RESOLVED。

    返回 choices/rewards + 每 trial 的 active 标记；trace=True 时另外返回
    每个 ACTIVE trial 的冻结 decision state（供 potency 反事实计算）。
    """
    rows, us, a_good_first = NT.reward_table(seed)
    b = NT.BETA * NT.novelty_style(body)
    Q = [NT.Q_INIT, NT.Q_INIT]
    N = [0, 0]
    cur = None
    surprise_run = 0
    suspect = None                 # None = NORMAL；否则 = ACTIVE，值为被怀疑的策略
    calm_run = 0
    choices, rewards, active, states = [], [], [], []

    for t in range(NT.TRIALS):
        val = [Q[i] + b / math.sqrt(1 + N[i]) for i in (0, 1)]

        if cur is None:
            d = max(-60.0, min(60.0, (val[0] - val[1]) / NT.TAU))
            c = 0 if us[t] < 1.0 / (1.0 + math.exp(-d)) else 1
            is_active = False
        else:
            # ---- NORMAL → RETRIEVE：入场条件与 v1 逐字相同 ----
            if suspect is None and query_from_state(Q[cur], surprise_run):
                suspect = cur          # ★ 记下"我怀疑的是这一个" ★
                calm_run = 0

            oth = 1 - cur
            is_active = suspect is not None
            if is_active:
                m, _, _ = memory.evidence("previously_good_strategy")
                s = 1.0 if cur == suspect else -1.0   # switch 是离开还是回到 suspect
            else:
                m, s = 0.0, 0.0

            z_base = (val[oth] - val[cur]) / NT.TAU
            z = max(-60.0, min(60.0, z_base + lam * m * s))
            c = oth if us[t] < 1.0 / (1.0 + math.exp(-z)) else cur
            if trace and is_active:
                states.append((z_base, s))

        r = rows[t][c]
        pe = r - Q[c]

        # 与 v1 完全相同的 surprise_run 口径（入场条件不动）
        if cur is not None and c == cur and pe < -PE_THRESH:
            surprise_run += 1
        else:
            surprise_run = 0

        # ---- ACTIVE → RESOLVED（两个条件都只用已有量，无新参数）----
        if suspect is not None:
            if c == suspect:
                calm_run = calm_run + 1 if pe >= -PE_THRESH else 0
            if Q[1 - suspect] > Q[suspect]:        # ① 新策略拿到足够证据
                suspect, calm_run = None, 0
            elif calm_run >= SURPRISE_RUN_MIN:     # ② surprise 被解释
                suspect, calm_run = None, 0

        N[c] += 1
        Q[c] += NT.ALPHA * (r - Q[c])
        cur = c
        choices.append(c)
        rewards.append(r)
        active.append(1 if is_active else 0)

    out = {"seed": seed, "a_good_first": a_good_first, "choices": choices,
           "rewards": rewards, "fired": active, "explores": [0] * NT.TRIALS}
    if trace:
        out["states"] = states
    return out


RUNNERS = {"v1 one-shot": P1.run, "v2 stateful": run_stateful}


def latency(rec):
    return NT.switch_latency_restricted(rec)


def post_correct(rec):
    return NT.correct_rate(rec, NT.REVERSAL_AT, NT.TRIALS)


# ================================================================== 自检
def _test_memory_blind(runner):
    d = sum(1 for sd in PROBE_SEEDS
            if runner(BODY_C, MEM_S, sd, 0.0)["choices"]
            != runner(BODY_C, MEM_V, sd, 0.0)["choices"])
    assert d == 0, f"✗ λ=0 时记忆仍影响决策（{d} 个种子）"
    return True


def _test_v1_unchanged():
    """★ v1 必须仍然逐位复现原来的失败 —— 不许被覆盖 ★"""
    chg = sum(1 for sd in PROBE_SEEDS
              if P1.run(BODY_C, MEM_S, sd, 1.0)["choices"]
              != P1.run(BODY_C, MEM_V, sd, 1.0)["choices"])
    dl = statistics.fmean([latency(P1.run(BODY_C, MEM_V, sd, 1.0))
                           - latency(P1.run(BODY_C, MEM_S, sd, 1.0))
                           for sd in PROBE_SEEDS])
    assert chg == 71, f"v1 轨迹改变数变了：{chg} ≠ 71（记录里的值）"
    assert abs(dl - (-0.125)) < 1e-9, f"v1 Δlatency 变了：{dl}"
    print(f"  ✓ v1 仍逐位复现原结果（λ=1：71/400 改变，Δlatency {dl:+.3f}）"
          f" —— 失败记录没有被覆盖")


def _test_no_survivor_conditioning(cells):
    for k, v in cells.items():
        assert len(v) == len(PROBE_SEEDS), \
            f"✗ {k} 只汇总了 {len(v)}/{len(PROBE_SEEDS)} 个种子 —— survivor conditioning"
    print(f"  ✓ 所有汇总都用全部 {len(PROBE_SEEDS)} 个种子，"
          f"不按是否触发检索筛选")


# ================================================================== ① ② exposure
def exposure_report():
    """potential（λ=0 轨迹上定义）vs realized（memory-enabled 轨迹上实际发生）"""
    print("\n" + "=" * 78)
    print("① ② EXPOSURE —— potential（λ=0 定义）vs realized（λ>0 实际）")
    print("=" * 78)
    print(f"{'机制':<14}{'body':<10}{'eligible 种子':>14}"
          f"{'potential trial':>16}{'realized trial (λ=1)':>22}")
    print("-" * 78)
    out = {}
    for name, runner in RUNNERS.items():
        for body in (BODY_C, BODY_K):
            pot = [sum(runner(body, MEM_V, sd, 0.0)["fired"]) for sd in PROBE_SEEDS]
            rea = [sum(runner(body, MEM_V, sd, 1.0)["fired"]) for sd in PROBE_SEEDS]
            elig = sum(1 for x in pot if x > 0) / len(PROBE_SEEDS)
            print(f"{name:<14}{body.name[:8]:<10}{elig:>13.1%}"
                  f"{statistics.fmean(pot):>16.2f}{statistics.fmean(rea):>22.2f}")
            out[(name, body.name)] = (elig, statistics.fmean(pot),
                                      statistics.fmean(rea))
    print("\n⚠ potential 用 memory-blind 轨迹定义 —— 它是【机制 exposure】；")
    print("  realized 受 choice sequence 反馈影响 —— 它是【结果的一部分】。")
    return out


# ================================================================== ③ potency
def potency_report():
    """在 λ=0 冻结的 decision state 上，只换 Memory S/V → Δp_switch"""
    print("\n" + "=" * 78)
    print("③ POTENCY —— 同一 decision state 下只换记忆，p(switch) 差多少")
    print("=" * 78)
    mS = MEM_S.evidence("previously_good_strategy")[0]
    mV = MEM_V.evidence("previously_good_strategy")[0]

    for name, runner in RUNNERS.items():
        states = []
        for sd in PROBE_SEEDS:
            r = runner(BODY_C, MEM_V, sd, 0.0, trace=True) if name.startswith("v2") \
                else None
            if r is None:      # v1 没有 trace 接口 → 用等价的被动重放
                states += _v1_passive_states(BODY_C, sd)
            else:
                states += r["states"]
        if not states:
            print(f"{name:<14}  ⚠ 无 eligible 机会")
            continue
        sig = lambda z: 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, z))))  # noqa: E731
        base = [sig(z) for z, _ in states]
        sat = sum(1 for p in base if p >= 0.9 or p <= 0.1) / len(base)
        print(f"\n{name}   eligible opportunities = {len(states)}"
              f"   （每种子 {len(states) / len(PROBE_SEEDS):.2f} 个）")
        print(f"  base p(switch)：中位数 {statistics.median(base):.3f}"
              f"   饱和比例（≤0.1 或 ≥0.9）{sat:.1%}")
        print(f"  {'λ':>6}  {'mean|Δp|':>10}  {'median|Δp|':>12}  {'p90|Δp|':>10}")
        for lam in LAMBDA_GRID:
            if lam == 0:
                continue
            d = sorted(abs(sig(z + lam * mV * s) - sig(z + lam * mS * s))
                       for z, s in states)
            p90 = d[min(len(d) - 1, int(0.90 * len(d)))]
            print(f"  {lam:>6.2f}  {statistics.fmean(d):>10.4f}"
                  f"  {statistics.median(d):>12.4f}  {p90:>10.4f}")


def _v1_passive_states(body, seed):
    """v1 的被动重放：λ=0 轨迹上标出 v1 会触发的 trial 及其 base logit"""
    rows, us, _ = NT.reward_table(seed)
    b = NT.BETA * NT.novelty_style(body)
    Q, N = [NT.Q_INIT, NT.Q_INIT], [0, 0]
    cur, run_, st = None, 0, []
    for t in range(NT.TRIALS):
        val = [Q[i] + b / math.sqrt(1 + N[i]) for i in (0, 1)]
        if cur is None:
            d = max(-60.0, min(60.0, (val[0] - val[1]) / NT.TAU))
            c = 0 if us[t] < 1.0 / (1.0 + math.exp(-d)) else 1
        else:
            oth = 1 - cur
            z = (val[oth] - val[cur]) / NT.TAU
            if query_from_state(Q[cur], run_):
                st.append((z, 1.0))          # v1 永远加在"switch"上
            c = oth if us[t] < 1.0 / (1.0 + math.exp(-max(-60., min(60., z)))) else cur
        r = rows[t][c]
        pe = r - Q[c]
        run_ = run_ + 1 if (cur is not None and c == cur and pe < -PE_THRESH) else 0
        N[c] += 1
        Q[c] += NT.ALPHA * (r - Q[c])
        cur = c
    return st


# ================================================================== ④ ⑤ SWAP
def new_swap(runner, lam, quiet=False):
    """★ 新 SWAP ★ M_C / M_K / pooled M / interaction。**不再有 dominance 闸**"""
    L = {}
    for body in (BODY_C, BODY_K):
        for mem in (MEM_S, MEM_V):
            L[(body.name, mem.name)] = [latency(runner(body, mem, sd, lam))
                                        for sd in PROBE_SEEDS]
    _test_no_survivor_conditioning(L) if not quiet else None

    def per_seed(body):
        return [v - s for v, s in zip(L[(body.name, MEM_V.name)],
                                      L[(body.name, MEM_S.name)])]

    mc, mk = per_seed(BODY_C), per_seed(BODY_K)
    M_C, M_K = statistics.fmean(mc), statistics.fmean(mk)
    M = (M_C + M_K) / 2.0
    inter = M_C - M_K

    rng = random.Random(ANALYSIS_SEED)
    n = len(PROBE_SEEDS)
    boot = []
    for _ in range(N_BOOT):
        idx = [rng.randrange(n) for _ in range(n)]      # ★同一组种子下标★
        boot.append((statistics.fmean([mc[i] for i in idx])
                     + statistics.fmean([mk[i] for i in idx])) / 2.0)
    boot.sort()
    lo, hi = boot[int(0.025 * N_BOOT)], boot[int(0.975 * N_BOOT)]

    # body effect —— 仅作 robustness diagnostic，★不再是闸门★
    beff = statistics.fmean([
        statistics.fmean(L[(BODY_K.name, m.name)])
        - statistics.fmean(L[(BODY_C.name, m.name)]) for m in (MEM_S, MEM_V)])
    return dict(M_C=M_C, M_K=M_K, M=M, ci=(lo, hi), inter=inter,
                same_sign=(M_C < 0) == (M_K < 0) and M_C != 0 and M_K != 0,
                body_diag=beff)


def swap_report():
    print("\n" + "=" * 78)
    print("④ NEW SWAP —— M = (M_C + M_K)/2   ⛔ dominance 判据已撤回 ⛔")
    print("=" * 78)
    print(f"{'机制':<14}{'λ':>6}{'M_C':>9}{'M_K':>9}{'pooled M':>11}"
          f"{'95% CI（描述性）':>24}{'方向一致':>10}{'interaction':>13}")
    print("-" * 78)
    res = {}
    for name, runner in RUNNERS.items():
        for lam in LAMBDA_GRID:
            if lam == 0:
                continue
            r = new_swap(runner, lam, quiet=True)
            res[(name, lam)] = r
            print(f"{name:<14}{lam:>6.2f}{r['M_C']:>+9.3f}{r['M_K']:>+9.3f}"
                  f"{r['M']:>+11.3f}"
                  f"   [{r['ci'][0]:+.3f}, {r['ci'][1]:+.3f}]"
                  f"{'是' if r['same_sign'] else '否':>10}"
                  f"{r['inter']:>+13.3f}")
    print("\n⚠ CI 是**描述性**的（seed cluster bootstrap，n_boot=10000，"
          f"分析种子 {ANALYSIS_SEED}）。")
    print("  今天**不定 SESOI**，所以不做功能意义判读。")
    return res


def downstream_report():
    """⑤ latency / correct-rate 只作为 downstream consequence"""
    print("\n" + "=" * 78)
    print("⑤ DOWNSTREAM —— 轨迹改变 + latency / 反转后正确率")
    print("=" * 78)
    print(f"{'机制':<14}{'λ':>6}{'轨迹改变':>12}{'Δlatency(V−S)':>16}"
          f"{'Δ反转后正确率':>16}")
    print("-" * 78)
    for name, runner in RUNNERS.items():
        for lam in LAMBDA_GRID:
            chg = dl = dp = 0.0
            n = len(PROBE_SEEDS)
            ch = 0
            for sd in PROBE_SEEDS:
                s = runner(BODY_C, MEM_S, sd, lam)
                v = runner(BODY_C, MEM_V, sd, lam)
                ch += (s["choices"] != v["choices"])
                dl += latency(v) - latency(s)
                dp += post_correct(v) - post_correct(s)
            print(f"{name:<14}{lam:>6.2f}{ch / n:>11.1%}"
                  f"{dl / n:>+16.3f}{dp / n:>+16.4f}")


# ================================================================== main
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    fp = NT.assert_frozen()
    print("=" * 78)
    print("029 memory transfer probe v2 —— stateful retrieval（★仍是探针，不是实验★）")
    print("=" * 78)
    print(f"任务底座：027 novel_task 指纹 {fp}（未改）  "
          f"种子 {PROBE_SEEDS[0]}–{PROBE_SEEDS[-1]}  n={len(PROBE_SEEDS)}")
    print(f"阈值未动：GOOD_THRESH={GOOD_THRESH} PE_THRESH={PE_THRESH} "
          f"SURPRISE_RUN_MIN={SURPRISE_RUN_MIN}   单次 reversal   ★80000–81499 未碰★")
    print("唯一改变：one-shot retrieval → stateful retrieval（RETRIEVE→ACTIVE→RESOLVED）")

    print("\n[ 工程自检 ]")
    _test_v1_unchanged()
    for nm, rn in RUNNERS.items():
        _test_memory_blind(rn)
    print(f"  ✓ memory-blind（λ=0）：两套机制各 {len(PROBE_SEEDS)}/{len(PROBE_SEEDS)}"
          f" 种子逐 trial 相同")
    _ = new_swap(run_stateful, 1.0)          # 触发 survivor-conditioning 断言

    exposure_report()
    potency_report()
    sw = swap_report()
    downstream_report()

    print("\n" + "=" * 78)
    print("★ 判读 ★")
    print("=" * 78)
    v1 = sw[("v1 one-shot", 1.0)]
    v2 = sw[("v2 stateful", 1.0)]
    print(f"  λ=1  v1 one-shot  pooled M = {v1['M']:+.3f}"
          f"  方向一致 {'是' if v1['same_sign'] else '否'}")
    print(f"  λ=1  v2 stateful  pooled M = {v2['M']:+.3f}"
          f"  方向一致 {'是' if v2['same_sign'] else '否'}")
    print("\n  Directional SWAP check —— 看上表 M_C / M_K 是否同号")
    print("  Dominance criterion（|memory|>|body|）—— ★ RETIRED，不再计算判读 ★")
    print("\n⚠ 这仍然不是 029 scientific success：")
    print("   记忆是手工造的、λ 没冻结、Stable/Volatile 根本还没跑。")
