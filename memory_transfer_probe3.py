"""
实验 029 —— memory_transfer_probe3.py（★ resolution 时序修正版 ★）
================================================================================

跑：  python memory_transfer_probe3.py

v1（`memory_transfer_probe.py`）与 v2（`memory_transfer_probe2.py`）
**原封保留、结果不覆盖**。本文件只改一处时序，并新增 primary endpoint 候选。

--------------------------------------------------------------------------------
① ★ 修的 bug：RESOLVED 在 Q update 之前判 ★
--------------------------------------------------------------------------------
v2 的循环顺序是：

    choice → reward → 算 PE → 判 RESOLVED（用**旧的** Q）→ 更新 Q

于是：如果这一 trial 的新证据**刚好**让新策略的 Q 超过 suspect，
判定时这条证据还没写进 Q。

> **resolution test was originally evaluated before incorporating the current
> outcome into Q, allowing retrieved evidence to persist for one extra decision
> after the resolution criterion had effectively been met.**

修正后：

    choice → reward → 算 PE → **更新 Q** → 用**更新后的** Q 判 RESOLVED

`calm_run` 那条退出逻辑保持不变（它本来就用 pre-update 的 PE ——
prediction error 按定义就是对**当时的**预期而言的）；
只是 `Q[other] > Q[suspect]` 移到 Q update 之后判。

⚠ 方向性：这个 bug **会放大**效果（ACTIVE 多活一个 decision，memory 多推一次）。
修掉之后效果会缩水一点 —— 但故事不变（见文末结果）。

--------------------------------------------------------------------------------
② ★ endpoint 改组：latency 降级为 secondary mechanistic ★
--------------------------------------------------------------------------------
`ACTIVE` 的退出条件 ≈「Q 证明新策略更好」，而 restricted switch latency
≈「新策略开始稳定占优」—— **两者天然绑在一起**，构造性重叠。
latency 仍然可报（它很好地描述"memory 让切换发生得多快"），
但**不能**当 029 最强的科学 endpoint。

### ★ Primary candidate：post-change cumulative errors ★

```
C_i = Σ_{t=40}^{79} 1( choice_t ≠ correct_option_t )      规则变化后一共选错多少次
ΔC  = C(V-memory) − C(S-memory)          V-memory 有帮助时 ΔC < 0
```

与已有的 `post_correct` 恒等（`C = 40 × (1 − post_correct)`），
但**单位直接是 trial**。它的好处：

```
· trial 40–79 是任务事先固定的窗口
· 不读 retrieval 是否 ACTIVE、不读什么时候 RESOLVED
· 没有 never-switch censoring       · 所有 agent 都有这个量
· 单位是 trial，以后好定 SESOI      · 测的就是实际 functional cost
```

### Secondary mechanistic

`restricted switch latency` / `retrieval exposure` / `per-opportunity potency`
/ `ACTIVE duration` / `realized retrieval`。
**Primary 问"实际少犯多少错"，secondary 解释"为什么"。**

--------------------------------------------------------------------------------
③ 仍然不动的东西
--------------------------------------------------------------------------------
```
GOOD_THRESH=.60  PE_THRESH=.30  SURPRISE_RUN_MIN=3   单次 reversal   seeds 0–399
λ 仍然只扫不选   ⛔ (b) 放宽 SURPRISE_RUN_MIN   ⛔ (d) 多 change-point
⛔ final seeds   ⛔ preregistration   ⛔ SESOI   ⛔ Stable/Volatile outcome
```

⚠ **下一步不是校准 λ。** 手工 MEM_S/MEM_V = ±0.667 是**最大对比度**；
在知道真实 Stable/Volatile 历史到底产生 m = 0.03 还是 0.30 之前，
争论 λ 取 .25 还是 1 没有科学意义。正确顺序：

```
修 resolution bug → 锁 independent endpoint → 造真实 Stable/Volatile histories
→ 让 history 自己生成 Episode → 观察真实 memory evidence 分布 → 最后才校准 λ
```
"""

import math
import random
import statistics
import sys

import novel_task as NT
import memory_transfer_probe as P1
import memory_transfer_probe2 as P2
from memory_transfer_probe import (BODY_C, BODY_K, MEM_S, MEM_V,
                                   GOOD_THRESH, PE_THRESH, SURPRISE_RUN_MIN,
                                   LAMBDA_GRID, PROBE_SEEDS, query_from_state)

N_BOOT = P2.N_BOOT
ANALYSIS_SEED = P2.ANALYSIS_SEED


# ================================================================== v3 主循环
def run_fixed(body, memory, seed, lam, *, trace=False):
    """与 v2 逐字相同，**只有 RESOLVED 的判定时点从 Q-update 之前挪到之后**。"""
    rows, us, a_good_first = NT.reward_table(seed)
    b = NT.BETA * NT.novelty_style(body)
    Q = [NT.Q_INIT, NT.Q_INIT]
    N = [0, 0]
    cur = None
    surprise_run = 0
    suspect = None
    calm_run = 0
    choices, rewards, active, states, runs = [], [], [], [], []
    cur_run = 0

    for t in range(NT.TRIALS):
        val = [Q[i] + b / math.sqrt(1 + N[i]) for i in (0, 1)]

        if cur is None:
            d = max(-60.0, min(60.0, (val[0] - val[1]) / NT.TAU))
            c = 0 if us[t] < 1.0 / (1.0 + math.exp(-d)) else 1
            is_active = False
        else:
            if suspect is None and query_from_state(Q[cur], surprise_run):
                suspect = cur
                calm_run = 0
            oth = 1 - cur
            is_active = suspect is not None
            if is_active:
                m, _, _ = memory.evidence("previously_good_strategy")
                s = 1.0 if cur == suspect else -1.0
            else:
                m, s = 0.0, 0.0
            z_base = (val[oth] - val[cur]) / NT.TAU
            z = max(-60.0, min(60.0, z_base + lam * m * s))
            c = oth if us[t] < 1.0 / (1.0 + math.exp(-z)) else cur
            if trace and is_active:
                states.append((z_base, s))

        r = rows[t][c]
        pe = r - Q[c]

        if cur is not None and c == cur and pe < -PE_THRESH:
            surprise_run += 1
        else:
            surprise_run = 0

        # calm_run 用 pre-update 的 PE（prediction error 按定义对当时的预期而言）
        if suspect is not None and c == suspect:
            calm_run = calm_run + 1 if pe >= -PE_THRESH else 0

        N[c] += 1
        Q[c] += NT.ALPHA * (r - Q[c])          # ★★ 先更新 Q ★★

        # ★★ 再判 RESOLVED —— 用更新后的 Q ★★
        if suspect is not None:
            if Q[1 - suspect] > Q[suspect] or calm_run >= SURPRISE_RUN_MIN:
                suspect, calm_run = None, 0

        cur = c
        choices.append(c)
        rewards.append(r)
        active.append(1 if is_active else 0)
        if is_active:
            cur_run += 1
        elif cur_run:
            runs.append(cur_run)
            cur_run = 0
    if cur_run:
        runs.append(cur_run)

    out = {"seed": seed, "a_good_first": a_good_first, "choices": choices,
           "rewards": rewards, "fired": active, "explores": [0] * NT.TRIALS,
           "active_runs": runs}
    if trace:
        out["states"] = states
    return out


RUNNERS = {"v1 one-shot": P1.run,
           "v2 pre-fix": P2.run_stateful,
           "v3 fixed": run_fixed}


# ================================================================== endpoints
def post_change_errors(rec):
    """★ Primary candidate ★ 反转后 40 个 trial 一共选错多少次（单位：trial）"""
    ch = rec["choices"]
    return sum(1 for t in range(NT.REVERSAL_AT, NT.TRIALS)
               if ch[t] != NT.correct_option(rec["a_good_first"], t))


def latency(rec):
    """secondary mechanistic（与 ACTIVE 窗口构造性重叠）"""
    return NT.switch_latency_restricted(rec)


ENDPOINTS = {"ΔC post-change errors ★primary候选★": post_change_errors,
             "Δlatency（secondary）": latency}


# ================================================================== 自检
def _test_prior_versions_unchanged():
    chg = sum(1 for sd in PROBE_SEEDS
              if P1.run(BODY_C, MEM_S, sd, 1.0)["choices"]
              != P1.run(BODY_C, MEM_V, sd, 1.0)["choices"])
    assert chg == 71, f"v1 变了：{chg} ≠ 71"
    m2 = P2.new_swap(P2.run_stateful, 1.0, quiet=True)
    assert abs(m2["M"] - (-3.989)) < 5e-4, f"v2 pre-fix 变了：{m2['M']}"
    print(f"  ✓ v1（71/400）与 v2 pre-fix（pooled M {m2['M']:+.3f}）"
          f"逐位不变 —— 旧结果没被覆盖")


def _test_only_timing_changed():
    """λ=0 时两版必须完全一致：RESOLVED 时点不影响 memory-blind 轨迹"""
    d = sum(1 for sd in PROBE_SEEDS
            if P2.run_stateful(BODY_C, MEM_V, sd, 0.0)["choices"]
            != run_fixed(BODY_C, MEM_V, sd, 0.0)["choices"])
    assert d == 0, f"✗ λ=0 时两版轨迹就不同（{d} 个种子）—— 改动不止时序"
    for runner in (run_fixed,):
        dd = sum(1 for sd in PROBE_SEEDS
                 if runner(BODY_C, MEM_S, sd, 0.0)["choices"]
                 != runner(BODY_C, MEM_V, sd, 0.0)["choices"])
        assert dd == 0, "✗ λ=0 时记忆仍影响决策"
    print("  ✓ λ=0 时 v2/v3 逐 trial 相同 → 改的确实只是 RESOLVED 时点")
    print("  ✓ memory-blind（λ=0）：v3 两个记忆库 400/400 种子完全相同")


def _test_endpoint_identity():
    """C = 40 × (1 − post_correct) 必须恒等"""
    for sd in PROBE_SEEDS[:50]:
        r = run_fixed(BODY_C, MEM_V, sd, 1.0)
        assert abs(post_change_errors(r)
                   - 40 * (1 - NT.correct_rate(r, 40, 80))) < 1e-9
    print("  ✓ post-change errors ≡ 40 × (1 − 反转后正确率)")


# ================================================================== 分析
def swap(runner, lam, endpoint):
    L = {}
    for body in (BODY_C, BODY_K):
        for mem in (MEM_S, MEM_V):
            L[(body.name, mem.name)] = [endpoint(runner(body, mem, sd, lam))
                                        for sd in PROBE_SEEDS]
            assert len(L[(body.name, mem.name)]) == len(PROBE_SEEDS)

    def per_seed(body):
        return [v - s for v, s in zip(L[(body.name, MEM_V.name)],
                                      L[(body.name, MEM_S.name)])]

    mc, mk = per_seed(BODY_C), per_seed(BODY_K)
    M_C, M_K = statistics.fmean(mc), statistics.fmean(mk)
    rng = random.Random(ANALYSIS_SEED)
    n = len(PROBE_SEEDS)
    boot = []
    for _ in range(N_BOOT):
        idx = [rng.randrange(n) for _ in range(n)]
        boot.append((statistics.fmean([mc[i] for i in idx])
                     + statistics.fmean([mk[i] for i in idx])) / 2.0)
    boot.sort()
    return dict(M_C=M_C, M_K=M_K, M=(M_C + M_K) / 2.0,
                ci=(boot[int(0.025 * N_BOOT)], boot[int(0.975 * N_BOOT)]),
                inter=M_C - M_K,
                same_sign=(M_C < 0) == (M_K < 0) and M_C != 0 and M_K != 0)


def bugfix_impact():
    print("\n" + "=" * 78)
    print("① BUG 修正的影响（pre-fix v2  →  fixed v3）")
    print("=" * 78)
    print(f"{'λ':>6}{'pooled M pre-fix':>20}{'pooled M fixed':>18}"
          f"{'Δ':>10}{'方向一致':>10}")
    print("-" * 78)
    for lam in LAMBDA_GRID:
        if lam == 0:
            continue
        a = swap(P2.run_stateful, lam, latency)
        b = swap(run_fixed, lam, latency)
        print(f"{lam:>6.2f}{a['M']:>+20.3f}{b['M']:>+18.3f}"
              f"{b['M'] - a['M']:>+10.3f}"
              f"{'是' if b['same_sign'] else '否':>10}")
    # exposure & downstream
    for lam in (1.0,):
        for nm, rn in (("pre-fix v2", P2.run_stateful), ("fixed v3", run_fixed)):
            exp = statistics.fmean([sum(rn(BODY_C, MEM_V, sd, lam)["fired"])
                                    for sd in PROBE_SEEDS])
            pot = statistics.fmean([sum(rn(BODY_C, MEM_V, sd, 0.0)["fired"])
                                    for sd in PROBE_SEEDS])
            dpc = statistics.fmean(
                [NT.correct_rate(rn(BODY_C, MEM_V, sd, lam), 40, 80)
                 - NT.correct_rate(rn(BODY_C, MEM_S, sd, lam), 40, 80)
                 for sd in PROBE_SEEDS])
            print(f"  {nm:<12} λ=1  potential exposure {pot:>5.2f}"
                  f"   realized {exp:>5.2f}   Δ反转后正确率 {dpc:+.4f}")


def endpoint_report():
    print("\n" + "=" * 78)
    print("② ENDPOINT —— ΔC（primary 候选）与 Δlatency（secondary）")
    print("=" * 78)
    for ep_name, ep in ENDPOINTS.items():
        print(f"\n{ep_name}")
        print(f"{'机制':<14}{'λ':>6}{'M_C':>9}{'M_K':>9}{'pooled':>10}"
              f"{'95% CI（描述性）':>24}{'方向一致':>10}{'interaction':>13}")
        print("-" * 78)
        for name, runner in RUNNERS.items():
            for lam in LAMBDA_GRID:
                if lam == 0:
                    continue
                r = swap(runner, lam, ep)
                print(f"{name:<14}{lam:>6.2f}{r['M_C']:>+9.3f}{r['M_K']:>+9.3f}"
                      f"{r['M']:>+10.3f}"
                      f"   [{r['ci'][0]:+.3f}, {r['ci'][1]:+.3f}]"
                      f"{'是' if r['same_sign'] else '否':>10}"
                      f"{r['inter']:>+13.3f}")


def mechanism_report():
    print("\n" + "=" * 78)
    print("③ SECONDARY MECHANISTIC —— exposure / ACTIVE duration / potency")
    print("=" * 78)
    print(f"{'机制':<14}{'body':<8}{'eligible':>10}{'potential':>11}"
          f"{'realized(λ=1)':>15}{'ACTIVE 段长':>12}")
    print("-" * 78)
    for name, runner in RUNNERS.items():
        for body in (BODY_C, BODY_K):
            pot = [sum(runner(body, MEM_V, sd, 0.0)["fired"]) for sd in PROBE_SEEDS]
            rea = [sum(runner(body, MEM_V, sd, 1.0)["fired"]) for sd in PROBE_SEEDS]
            elig = sum(1 for x in pot if x > 0) / len(PROBE_SEEDS)
            if name == "v3 fixed":
                runs = [x for sd in PROBE_SEEDS
                        for x in runner(body, MEM_V, sd, 1.0)["active_runs"]]
                dur = f"{statistics.fmean(runs):.2f}" if runs else "—"
            else:
                dur = "—"
            print(f"{name:<14}{body.name[:6]:<8}{elig:>9.1%}"
                  f"{statistics.fmean(pot):>11.2f}{statistics.fmean(rea):>15.2f}"
                  f"{dur:>12}")

    mS = MEM_S.evidence("previously_good_strategy")[0]
    mV = MEM_V.evidence("previously_good_strategy")[0]
    states = []
    for sd in PROBE_SEEDS:
        states += run_fixed(BODY_C, MEM_V, sd, 0.0, trace=True)["states"]
    sig = lambda z: 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, z))))  # noqa: E731
    base = [sig(z) for z, _ in states]
    sat = sum(1 for p in base if p >= 0.9 or p <= 0.1) / len(base)
    print(f"\nv3 potency（λ=0 冻结 decision state）"
          f"  机会数 {len(states)}   base p 中位数 {statistics.median(base):.3f}"
          f"   饱和 {sat:.1%}")
    print(f"  {'λ':>6}{'mean|Δp|':>11}{'median|Δp|':>13}{'p90|Δp|':>11}")
    for lam in LAMBDA_GRID:
        if lam == 0:
            continue
        d = sorted(abs(sig(z + lam * mV * s) - sig(z + lam * mS * s))
                   for z, s in states)
        print(f"  {lam:>6.2f}{statistics.fmean(d):>11.4f}"
              f"{statistics.median(d):>13.4f}"
              f"{d[min(len(d) - 1, int(0.9 * len(d)))]:>11.4f}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    fp = NT.assert_frozen()
    print("=" * 78)
    print("029 probe v3 —— resolution 时序修正 + endpoint 改组（★仍是探针★）")
    print("=" * 78)
    print(f"任务底座 027 指纹 {fp}（未改）  种子 {PROBE_SEEDS[0]}–{PROBE_SEEDS[-1]}"
          f"  n={len(PROBE_SEEDS)}  ★80000–81499 未碰★")
    print(f"阈值未动：GOOD_THRESH={GOOD_THRESH} PE_THRESH={PE_THRESH} "
          f"SURPRISE_RUN_MIN={SURPRISE_RUN_MIN}   单次 reversal   λ 只扫不选")
    print("唯一改动：RESOLVED 判定从 Q-update 之前 → Q-update 之后")

    print("\n[ 工程自检 ]")
    _test_prior_versions_unchanged()
    _test_only_timing_changed()
    _test_endpoint_identity()

    bugfix_impact()
    endpoint_report()
    mechanism_report()

    print("\n" + "=" * 78)
    print("★ 判读 ★")
    print("=" * 78)
    c = swap(run_fixed, 1.0, post_change_errors)
    l_ = swap(run_fixed, 1.0, latency)
    print(f"  λ=1  ΔC（primary 候选）= {c['M']:+.3f} trial"
          f"   CI [{c['ci'][0]:+.3f}, {c['ci'][1]:+.3f}]"
          f"   方向一致 {'是' if c['same_sign'] else '否'}")
    print(f"  λ=1  Δlatency（secondary）= {l_['M']:+.3f} trial"
          f"   方向一致 {'是' if l_['same_sign'] else '否'}")
    print("\n  Directional SWAP check（修正后）：看 M_C / M_K 是否同号")
    print("  ⛔ dominance criterion 早已 RETIRED，不计算")
    print("\n⚠ 手工 MEM_S/MEM_V = ±0.667 是**最大对比度** —— 以上是上界，不是预期效应量。")
    print("⚠ 下一步不是校准 λ，是造真实 Stable/Volatile histories"
          "（memory_acquisition_probe.py）。")
