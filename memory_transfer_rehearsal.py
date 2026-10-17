"""
实验 029 —— memory_transfer_rehearsal.py（★ OWN / DELETE / SWAP / SHUFFLE ★）
================================================================================

跑：  python memory_transfer_rehearsal.py

**第一次把 natural Stable/Volatile memory 接到 novel task 上。**
仍然**只用已烧的开发种子 0–399**。⛔ 不碰 80000–81499，⛔ 不写预注册，⛔ 不定 SESOI。

--------------------------------------------------------------------------------
冻结输入（跑本文件之前全部已冻结，本文件一个都不许改）
--------------------------------------------------------------------------------
```
acquisition   ANOMALY_AT=36  ANOMALY_LEN=8  T_PROBLEM=66（anomaly 后 22）
retrieval     stateful，RESOLVED 在 Q-update 之后判（probe3）
interface     MEMORY_LAMBDA = 1.00   ← group-blind capacity calibration 冻结
gates         saturation ≤5% / median|Δp| ≥.02 / flip ≤25% / max exposure ≤20/80
primary       ΔC = post-change cumulative errors（trial 40–79 选错次数）
secondary     restricted switch latency + exposure / ACTIVE duration
population    ★全部 400 个种子，含 m=0 的 agent★（规则 91）
```

--------------------------------------------------------------------------------
四个臂
--------------------------------------------------------------------------------
```
OWN       每个 agent 用自己发育史长出来的记忆
DELETE    记忆整个拿掉（空库，m≡0）
SWAP      两个 condition 的记忆互换
SHUFFLE   记忆条目内 action_relation 打乱 —— 保留 marginal，摧毁关系
```

### ⚠⚠ 必须先说清楚：本架构下 DELETE 与 SWAP 是**代数恒等式** ⚠⚠

本 rehearsal 里 body 是**常数**（`NeutralBody`），发育史除了记忆之外
**不携带任何东西**进入任务。于是同一个种子的两个 condition
**只差记忆**，因此：

```
DELETE   两边都是空库 → 逐 trial 相同 → ΔC ≡ 0        （恒等）
SWAP     两边记忆互换 → 就是 OWN 换了个标签 → ΔC ≡ −ΔC(OWN)   （恒等）
```

**它们不是证据，是断言** —— 用来证明"发育史除了记忆没有第二条泄漏通路"。
本文件把它们当**断言**跑（不符就报错），不当结果解释。

> ★ 规则 93（最终版）★
> When memory is the sole developmental pathway into the test task, DELETE and
> within-seed SWAP are **algebraic integrity checks rather than independent
> causal evidence**. A second developmental pathway should **not** be introduced
> merely to make these controls non-trivial; causal support should instead come
> from **interventions on memory structure** such as relational shuffling and
> cross-seed donor tests.
>
> ⛔ 不许为了让 SWAP"变得非平凡"而把 trait 通路加回来 ——
> 那会把干净的 `history → relational memory → novel adaptation`
> 重新变成 `history → memory + traits → …`，
> 又要处理 memory/trait competition、interaction、budget，即 027/028 那一整套。

所以：**confirmatory 的科学控制是 SHUFFLE**（对记忆结构本身的干预），
另加一个回答 seed 耦合的臂：

```
XSEED-DONOR   种子 s 用【另一个种子 s'=(s+200)%400】的对侧记忆
              → 回答"效应不是 development/test 共用 seed 的耦合造成的"
```

★ 命名纪律 ★ **不叫 SWAP-XS** —— 它和 SWAP 问的不是同一件事：
SWAP 问"结果跟不跟记忆身份走"（此架构下是恒等式）；
XSEED-DONOR 问"效应是不是靠发育与测试共享种子"（非平凡）。

--------------------------------------------------------------------------------
三个要检查的问题（用户拍板）
--------------------------------------------------------------------------------
```
① natural Stable/Volatile memory 能否通过冻结的 λ=1 接口产生 downstream difference
② DELETE 是否让该差异塌缩
③ SWAP 是否让结果跟 memory identity 走，SHUFFLE 是否摧毁这种效果
```
⚠ 按上面所述，②③ 的 DELETE/SWAP 部分是恒等式；
**真正在检验 ③ 的是 SHUFFLE 与 XSEED-DONOR。**

--------------------------------------------------------------------------------
仍然不做
--------------------------------------------------------------------------------
```
⛔ final seeds  ⛔ preregistration  ⛔ SESOI  ⛔ 改 λ  ⛔ 改任何 acquisition 参数
```
本文件的 CI 一律是**描述性**的：没有 SESOI 就不做功能意义判读。
"""

import random
import statistics
import sys

import novel_task as NT
import memory_transfer_probe3 as P3
import memory_acquisition_probe as ACQ
from memory_transfer_probe import Episode, MemoryStore, PROBE_SEEDS
from memory_lambda_calibration import MEMORY_LAMBDA

BODY = ACQ.NeutralBody
LAM = MEMORY_LAMBDA
N_BOOT = 10000
ANALYSIS_SEED = 8181
SHUFFLE_SALT = 0x29C10
XS_OFFSET = len(PROBE_SEEDS) // 2          # XSEED-DONOR 的错位量


# ================================================================== 记忆
def build_memories():
    """每个种子 × 每个 condition 的自然记忆（含长不出记忆的 → 空库，m=0）"""
    mem = {}
    for cond in ACQ.CONDITIONS:
        for sd in PROBE_SEEDS:
            eps, _ = ACQ.acquire(sd, cond)
            mem[(cond, sd)] = MemoryStore(f"{cond}-{sd}", eps)
    return mem


def shuffled(store, sd):
    """★ SHUFFLE ★ 在 agent 自己的条目内打乱 action_relation。

    保留：episode 数、stay/switch 各自的条数、outcome 的边际分布。
    摧毁：action ↔ outcome 的**关系**。
    → 若效应来自 marginal statistics，SHUFFLE 后应当保留；
      若效应来自关系结构，SHUFFLE 后应当塌缩。
    """
    eps = store.episodes
    rel = [e.action_relation for e in eps]
    random.Random(SHUFFLE_SALT ^ sd ^ (len(eps) << 8)).shuffle(rel)
    return MemoryStore(store.name + "-shuf", [
        Episode(context=e.context,
                previous_expectation=e.previous_expectation,
                observation=e.observation,
                prediction_error=e.prediction_error,
                action_relation=r,
                outcome=e.outcome)
        for e, r in zip(eps, rel)])


EMPTY = MemoryStore("empty", [])


# ================================================================== 端点
def endpoints(rec):
    return (P3.post_change_errors(rec),          # ★ primary candidate ★
            P3.latency(rec),                     # secondary mechanistic
            sum(rec["fired"]),                   # realized exposure
            statistics.fmean(rec["active_runs"]) if rec["active_runs"] else 0.0)


def arm(mem, memory_of):
    """跑一个臂：memory_of(cond, seed) → 该 agent 在这个臂里实际用的记忆库"""
    out = {}
    for cond in ACQ.CONDITIONS:
        rows = [endpoints(P3.run_fixed(BODY, memory_of(cond, sd), sd, LAM))
                for sd in PROBE_SEEDS]
        out[cond] = rows
        assert len(rows) == len(PROBE_SEEDS)      # 规则 88/91：全人群
    return out


def paired_delta(res, idx):
    """同种子配对差 Volatile − Stable"""
    return [v[idx] - s[idx]
            for s, v in zip(res[ACQ.CONDITIONS[0]], res[ACQ.CONDITIONS[1]])]


def boot_ci(d):
    rng = random.Random(ANALYSIS_SEED)
    n = len(d)
    b = sorted(statistics.fmean([d[rng.randrange(n)] for _ in range(n)])
               for _ in range(N_BOOT))
    return b[int(0.025 * N_BOOT)], b[int(0.975 * N_BOOT)]


# ================================================================== main
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("=" * 78)
    print("029 REHEARSAL —— natural memory × novel task（★开发种子，非 FINAL★）")
    print("=" * 78)
    print(f"acquisition ANOMALY_AT={ACQ.ANOMALY_AT} LEN={ACQ.ANOMALY_LEN} "
          f"T={ACQ.T_PROBLEM}   interface ★λ={LAM:.2f} 已冻结★")
    print(f"任务底座 027 指纹 {NT.assert_frozen()}   种子 "
          f"{PROBE_SEEDS[0]}–{PROBE_SEEDS[-1]}  n={len(PROBE_SEEDS)}"
          f"   ★80000–81499 未碰★")
    print("primary = ΔC post-change errors（trial 40–79）  "
          "secondary = latency / exposure")

    mem = build_memories()
    # ★ 口径冻结 ★ primary extensive margin = P(relational memory COMPLETE)
    #   complete := 至少 1 条 stay 且至少 1 条 switch
    #   ⚠ **不是** "m ≠ 0"：两侧都有条目、但两侧均值恰好相等的 agent
    #     形成了**完整的**关系性记忆，只不过这份经验说"switch 与 stay 没区别"——
    #     那是**有意义的零证据**，不是"没有记忆"。
    comp, nz = {}, {}
    for c in ACQ.CONDITIONS:
        ev = [mem[(c, sd)].evidence("previously_good_strategy")
              for sd in PROBE_SEEDS]
        comp[c] = statistics.fmean([1.0 if (a > 0 and b > 0) else 0.0
                                    for _, a, b in ev])
        nz[c] = statistics.fmean([1.0 if m != 0 else 0.0 for m, _, _ in ev])
    print("\n★ memory completeness（primary extensive margin）★  "
          + "   ".join(f"{c} {comp[c]:.2%}" for c in ACQ.CONDITIONS))
    print("  non-zero evidence rate（可报告，但不叫 extensive / availability）  "
          + "   ".join(f"{c} {nz[c]:.2%}" for c in ACQ.CONDITIONS))
    print("  ★ 所有 primary transfer 分析仍使用全部预定义 agent，"
          "含 incomplete 与 m=0 ★")

    ARMS = {
        "OWN": lambda c, sd: mem[(c, sd)],
        "DELETE": lambda c, sd: EMPTY,
        "SWAP": lambda c, sd: mem[(ACQ.CONDITIONS[1 - ACQ.CONDITIONS.index(c)], sd)],
        "SHUFFLE": lambda c, sd: shuffled(mem[(c, sd)], sd),
        "XSEED-DONOR": lambda c, sd: mem[(c, PROBE_SEEDS[
            (PROBE_SEEDS.index(sd) + XS_OFFSET) % len(PROBE_SEEDS)])],
    }

    res = {name: arm(mem, fn) for name, fn in ARMS.items()}

    print("\n" + "=" * 78)
    print("★ PRIMARY：ΔC = C(Volatile) − C(Stable)，同种子配对，全人群 ★")
    print("=" * 78)
    print(f"{'臂':<10}{'C Stable':>11}{'C Volatile':>12}{'ΔC':>10}"
          f"{'95% CI（描述性）':>24}{'相对 OWN':>11}")
    print("-" * 78)
    dc = {}
    for name in ARMS:
        d = paired_delta(res[name], 0)
        dc[name] = statistics.fmean(d)
        cs = statistics.fmean([x[0] for x in res[name][ACQ.CONDITIONS[0]]])
        cv = statistics.fmean([x[0] for x in res[name][ACQ.CONDITIONS[1]]])
        lo, hi = boot_ci(d)
        rel = dc[name] / dc["OWN"] if dc["OWN"] else float("nan")
        print(f"{name:<10}{cs:>11.3f}{cv:>12.3f}{dc[name]:>+10.3f}"
              f"   [{lo:+.3f}, {hi:+.3f}]{rel:>11.2f}")

    print("\n" + "=" * 78)
    print("★ 恒等式断言（不是结果）★")
    print("=" * 78)
    d_del = paired_delta(res["DELETE"], 0)
    assert all(x == 0 for x in d_del), "✗ DELETE 不为 0 → 发育史存在记忆以外的泄漏通路"
    print("  ✓ DELETE：400/400 种子逐 trial 相同，ΔC ≡ 0")
    print("     → 发育史除了记忆没有第二条通路进入任务（这是断言，不是发现）")
    d_own, d_swap = paired_delta(res["OWN"], 0), paired_delta(res["SWAP"], 0)
    assert all(a == -b for a, b in zip(d_own, d_swap)), "✗ SWAP ≠ −OWN"
    print("  ✓ SWAP：逐种子恰好等于 −OWN（body 为常数时这是代数恒等式）")
    print("     → outcome 完全跟着 memory identity 走，但**这是构造，不是证据**")

    print("\n" + "=" * 78)
    print("★ 真正的控制：SHUFFLE（摧毁关系、保留 marginal）与 XSEED-DONOR ★")
    print("=" * 78)
    print(f"  OWN      ΔC = {dc['OWN']:+.3f}")
    print(f"  SHUFFLE  ΔC = {dc['SHUFFLE']:+.3f}"
          f"   保留了 OWN 的 {dc['SHUFFLE'] / dc['OWN']:.1%}"
          if dc["OWN"] else "")
    print(f"  XSEED    ΔC = {dc['XSEED-DONOR']:+.3f}"
          f"   保留了 OWN 的 {dc['XSEED-DONOR'] / dc['OWN']:.1%}")
    # ---- SHUFFLE 的 preregistered mechanistic control：retention ratio ----
    d_own, d_shf = paired_delta(res["OWN"], 0), paired_delta(res["SHUFFLE"], 0)
    rng = random.Random(ANALYSIS_SEED)
    n = len(PROBE_SEEDS)
    ratios = []
    for _ in range(N_BOOT):
        idx = [rng.randrange(n) for _ in range(n)]        # ★同一组种子下标★
        a = abs(statistics.fmean([d_own[i] for i in idx]))
        b = abs(statistics.fmean([d_shf[i] for i in idx]))
        ratios.append(b / a if a > 0 else float("inf"))   # ★逐 replicate 施加★
    ratios.sort()
    r_lo, r_hi = ratios[int(0.025 * N_BOOT)], ratios[int(0.975 * N_BOOT)]
    r_pt = abs(dc["SHUFFLE"]) / abs(dc["OWN"])
    print(f"\n  ★ retention ratio |ΔC_shuffle| / |ΔC_own| = {r_pt:.3f}"
          f"   95% CI [{r_lo:.3f}, {r_hi:.3f}]")
    print("     joint same-seed bootstrap，abs 与除法**逐 replicate** 施加（承 028 教训）")
    print(f"     预注册判据：CI 上界 < 0.25 → "
          f"{'满足' if r_hi < 0.25 else '不满足'}"
          f"（摧毁 relation 后 ≥75% 的 transfer 消失）")
    print("     ⚠ ratio 恒 ≥ 0，'CI 排除 0' 无信息（规则 84）——只看**上界** vs 0.25。")
    print("\n  预期：SHUFFLE 应塌缩（效应来自关系，不是 marginal statistics）；")
    print("        XSEED-DONOR 应基本保留（效应由记忆内容携带，不靠发育-测试共享种子）。")

    print("\n" + "=" * 78)
    print("★ SECONDARY mechanistic ★")
    print("=" * 78)
    print(f"{'臂':<10}{'Δlatency':>11}{'exposure S':>13}{'exposure V':>13}"
          f"{'ACTIVE 段长 S':>15}{'ACTIVE 段长 V':>15}")
    print("-" * 78)
    for name in ARMS:
        dl = statistics.fmean(paired_delta(res[name], 1))
        es = statistics.fmean([x[2] for x in res[name][ACQ.CONDITIONS[0]]])
        ev = statistics.fmean([x[2] for x in res[name][ACQ.CONDITIONS[1]]])
        rs = statistics.fmean([x[3] for x in res[name][ACQ.CONDITIONS[0]]])
        rv = statistics.fmean([x[3] for x in res[name][ACQ.CONDITIONS[1]]])
        print(f"{name:<10}{dl:>+11.3f}{es:>13.2f}{ev:>13.2f}"
              f"{rs:>15.2f}{rv:>15.2f}")

    print("\n" + "=" * 78)
    print("⚠ CI 全部是描述性的（seed cluster bootstrap，n_boot=10000，"
          f"分析种子 {ANALYSIS_SEED}）。")
    print("⚠ 没有 SESOI → 不做功能意义判读。⛔ 不许据此改 λ 或任何 acquisition 参数。")
    print("⚠ 这是**开发种子上的 rehearsal**，不是 029 的确认性结果。")
    print("=" * 78)
