"""
实验 029 —— memory_lambda_calibration.py（★ group-blind 接口容量校准 ★）
================================================================================

跑：  python memory_lambda_calibration.py

--------------------------------------------------------------------------------
校准要回答的问题（★ 和"哪个 λ 让 029 成功"完全无关 ★）
--------------------------------------------------------------------------------
    ┌──────────────────────────────────────────────────────────────────┐
    │  真实 memory 输入经过这个接口后，单次决策能不能产生一个           │
    │  【不饱和、但也不是微不足道】的影响？                             │
    └──────────────────────────────────────────────────────────────────┘

⛔ **不是**："哪个 λ 最容易让 029 成功 / 最能拉开两个 group？"

--------------------------------------------------------------------------------
★★ group-blind 是结构性的，不是靠自觉 ★★
--------------------------------------------------------------------------------
输入 = `memory_acquisition_probe.py`（ANOMALY_AT=36 冻结版）自然生成的 m，
**但在 calibration 层把 condition label 拿掉**：

```
pooled_empirical_m()  →  一个【排过序的 float 列表】，长度 2×400
                          排序会彻底摧毁 m 与 Stable/Volatile 的对应关系，
                          本文件在任何地方都【无法】恢复分组。
```

- **包含 m = 0 的 agent**（没长出可用记忆的那些）—— 见规则 91：
  先筛掉他们再校准，会系统性夸大 memory channel 的真实输入强度。
- 本文件**不含**任何按 condition 分组的代码路径。

--------------------------------------------------------------------------------
只报告这些
--------------------------------------------------------------------------------
```
✅ mean |Δp| / median |Δp| / p90 |Δp|      单次决策被推动多少
✅ decision saturation                     推完之后是不是已经没得选了
✅ active-memory exposure                  记忆还是不是 event-triggered
✅ P(翻转偏好)                             记忆把 argmax 掀过 0.5 的比例
⛔ Stable vs Volatile ΔC                   ⛔ Stable vs Volatile latency
⛔ 哪个 λ 最能拉开两个 group
```

`Δp` 的口径：**相对"没有记忆"的反事实**

```
Δp(state, m, λ) = p_switch( z_base + λ·m·s )  −  p_switch( z_base )
```

decision states 来自 **λ=0 的 memory-blind 轨迹**（probe3 的 frozen-state
pipeline），所以 state 本身不含任何记忆影响。

--------------------------------------------------------------------------------
λ 的判据（用户拍板，三条同时满足）
--------------------------------------------------------------------------------
```
① 不饱和                    推完之后 p 不应大量落到 ≤0.05 / ≥0.95
② 有实质但不过强            单次决策要能被推动，但不能变成"记忆说了算"
③ memory 保持 event-triggered  active exposure 不能吃掉整个任务
```
**本文件只给出这三条的读数与一个建议，冻结 λ 由使用者拍板。**
"""

import math
import statistics
import sys

import novel_task as NT
import memory_transfer_probe3 as P3
import memory_acquisition_probe as ACQ
from memory_transfer_probe import PROBE_SEEDS

BODY = ACQ.NeutralBody                      # 校准用中性 body
LAMBDA_GRID = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)
SAT_LO, SAT_HI = 0.05, 0.95

# ============================================================================
# ★★★ 2026-08-18 正式冻结 ★★★
#
# 这四个是 **engineering admissibility gates**，不是 scientific significance
# thresholds。它们在**没有看过任何 Stable/Volatile downstream transfer outcome**
# 之前冻结 —— 从这一刻起不再因为任何 outcome 改动。
# ----------------------------------------------------------------------------
SATURATION_MAX      = 0.05   # 推后落到 p≤.05 或 ≥.95 的比例 —— 记忆不该把超过
                             # 1/20 的 eligible decision 推成近乎确定性
MEDIAN_ABS_DP_MIN   = 0.02   # 最低能力门槛 —— 连典型决策概率都推不动 2 个百分点，
                             # 就很难说接口真正进入了决策
PREF_FLIP_MAX       = 0.25   # 记忆可以改变一部分选择，但不能在大比例 eligible
                             # state 上直接接管 argmax。最多四次里一次翻面
ACTIVE_EXPOSURE_MAX = 20     # /80 —— 把 event-triggered 钉死成"最多参与四分之一
                             # 任务"。λ=1 实测仅约 7/80，这条主要防未来架构漂移
MEMORY_LAMBDA       = 1.00   # ★ 正式冻结 ★
# ----------------------------------------------------------------------------
# ★ exposure gate 用 max，不用 mean ★
#   event-triggeredness 不应该允许"某一种 memory sign 已接近常驻，
#   却被另外两种平均掉"。λ=1 的最大 exposure 只有 6.95/80，判定不受影响。
#
# ★★ selection rule（跑 FINAL 之前写死，照抄进论文）★★
#
#   Lambda was calibrated without condition labels or downstream transfer
#   outcomes. Values were required to satisfy prespecified interface-capacity
#   constraints on saturation, median probability shift, preference reversal,
#   and retrieval exposure. Among admissible values, the log-scale midpoint of
#   the admissible range was selected.
#
#   合格带 {0.5, 1.0, 2.0} 在倍增网格上，1.0 = sqrt(0.5 × 2) 恰是 log 尺度中心。
#   ⚠ 不是"选 potency 最大的"，是"选距离上下两个失效方向最远的"。
#   → 以后没有人能问"是不是换个 λ 就能阳" —— λ 在看到 group transfer outcome
#     之前已经由接口性质冻结。
# ============================================================================


# ================================================================== 输入
def pooled_empirical_m():
    """★ group-blind ★ 返回**排过序的** m 列表；label 在本函数内即被丢弃。

    - 两个 condition 的 agent 全部汇入同一个池子
    - **包含 m = 0 的 agent**（规则 91：不许按"是否长出记忆"筛选）
    - 排序后，m 与 condition 的对应关系在本模块内**无法恢复**
    """
    pool = []
    for cond in ACQ.CONDITIONS:             # ← label 只在这一行出现，随即丢弃
        for sd in PROBE_SEEDS:
            eps, _ = ACQ.acquire(sd, cond)
            m, _, _ = ACQ.evidence_of(eps)
            pool.append(float(m))
    pool.sort()                             # ★ 摧毁分组信息 ★
    assert len(pool) == len(PROBE_SEEDS) * len(ACQ.CONDITIONS)
    assert all(isinstance(x, float) for x in pool)
    return pool


class ConstantMemory:
    """把一个给定的 m 直接当作 evidence 读出 —— 只用于 exposure 测量"""

    def __init__(self, m):
        self._m = float(m)
        self.name = f"m={self._m:+.4f}"

    def evidence(self, context):
        return (self._m, 1, 1) if context else (0.0, 0, 0)


def frozen_states(body):
    """λ=0 memory-blind 轨迹上的 eligible decision states（probe3 pipeline）"""
    st = []
    for sd in PROBE_SEEDS:
        st += P3.run_fixed(body, ConstantMemory(0.0), sd, 0.0, trace=True)["states"]
    return st


def _sig(z):
    return 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, z))))


def _q(xs, f):
    return xs[min(len(xs) - 1, int(f * len(xs)))]


# ================================================================== 报告
def capacity_report(states, pool):
    print("\n" + "=" * 78)
    print("★ 接口容量 —— 单次决策被真实 memory 推动多少（相对无记忆反事实）★")
    print("=" * 78)
    base = [_sig(z) for z, _ in states]
    base_sat = sum(1 for p in base if p <= SAT_LO or p >= SAT_HI) / len(base)
    print(f"  eligible decision states = {len(states)}"
          f"   （每种子 {len(states) / len(PROBE_SEEDS):.2f} 个）")
    print(f"  无记忆时 base p(switch)：中位数 {statistics.median(base):.3f}"
          f"   本身已饱和的比例 {base_sat:.1%}")
    print(f"  pooled empirical m（含 m=0）：n={len(pool)}"
          f"  mean {statistics.fmean(pool):+.4f}"
          f"  |m| 中位数 {statistics.median([abs(x) for x in pool]):.4f}"
          f"  m=0 占 {sum(1 for x in pool if x == 0.0) / len(pool):.1%}")
    print(f"\n{'λ':>6}{'mean|Δp|':>11}{'median|Δp|':>13}{'p90|Δp|':>10}"
          f"{'推后饱和':>11}{'P(翻转偏好)':>14}")
    print("-" * 78)
    out = {}
    for lam in LAMBDA_GRID:
        d, sat, flip, n = [], 0, 0, 0
        for z, s in states:
            p0 = _sig(z)
            for m in pool:
                p1 = _sig(z + lam * m * s)
                d.append(abs(p1 - p0))
                sat += p1 <= SAT_LO or p1 >= SAT_HI
                flip += (p0 - 0.5) * (p1 - 0.5) < 0
                n += 1
        d.sort()
        out[lam] = dict(mean=statistics.fmean(d), med=statistics.median(d),
                        p90=_q(d, .90), sat=sat / n, flip=flip / n)
        print(f"{lam:>6.2f}{out[lam]['mean']:>11.4f}{out[lam]['med']:>13.4f}"
              f"{out[lam]['p90']:>10.4f}{out[lam]['sat']:>10.1%}"
              f"{out[lam]['flip']:>13.1%}")
    return out


def exposure_report(pool):
    """③ memory 是否仍是 event-triggered —— 用 pooled 分布的三个代表 m 测"""
    print("\n" + "=" * 78)
    print("★ active-memory exposure —— 记忆有没有从 event-triggered 变成常驻 ★")
    print("=" * 78)
    reps = [_q(pool, .10), statistics.median(pool), _q(pool, .90)]
    pot = statistics.fmean(
        [sum(P3.run_fixed(BODY, ConstantMemory(0.0), sd, 0.0)["fired"])
         for sd in PROBE_SEEDS])
    print(f"  potential exposure（λ=0 定义）= {pot:.2f} / {NT.TRIALS} trial")
    print(f"\n{'λ':>6}" + "".join(f"{'realized @ m=' + f'{m:+.3f}':>22}" for m in reps))
    print("-" * 78)
    out = {}
    for lam in LAMBDA_GRID:
        row, vals = f"{lam:>6.2f}", []
        for m in reps:
            e = statistics.fmean(
                [sum(P3.run_fixed(BODY, ConstantMemory(m), sd, lam)["fired"])
                 for sd in PROBE_SEEDS])
            vals.append(e)
            row += f"{e:>22.2f}"
        out[lam] = vals
        print(row)
    print(f"\n  ⚠ 判据③：exposure 应保持在 {NT.TRIALS} 个 trial 的一小部分。"
          "涨上去就说明记忆变成常驻 prior 了。")
    return out


def recommend(cap, exp):
    print("\n" + "=" * 78)
    print("★ 三条判据的读数（冻结 λ 由使用者拍板，本文件不替你定）★")
    print("=" * 78)
    print(f"{'λ':>6}{'①不饱和':>12}{'②有实质不过强':>18}{'③event-triggered':>20}")
    print("-" * 78)
    for lam in LAMBDA_GRID:
        c = cap[lam]
        e = max(exp[lam])          # ★ max，不是 mean ★
        ok1 = c["sat"] <= SATURATION_MAX
        ok2 = c["med"] >= MEDIAN_ABS_DP_MIN and c["flip"] <= PREF_FLIP_MAX
        ok3 = e <= ACTIVE_EXPOSURE_MAX
        col1 = ("✓ " if ok1 else "✗ ") + "{:.1%}".format(c["sat"])
        col2 = ("✓ " if ok2 else "✗ ") + "med {:.3f} flip {:.1%}".format(
            c["med"], c["flip"])
        col3 = ("✓ " if ok3 else "✗ ") + "{:.2f}/{}".format(e, NT.TRIALS)
        print(f"{lam:>6.2f}{col1:>12}{col2:>26}{col3:>20}")
    print("\n  ★ 已冻结的 admissibility gates（2026-08-18）★")
    print("    —— engineering gates，不是 significance thresholds；")
    print("       在看到任何 Stable/Volatile transfer outcome 之前冻结。")
    print(f"    ① P(推后饱和) ≤ {SATURATION_MAX:.0%}")
    print(f"    ② median|Δp| ≥ {MEDIAN_ABS_DP_MIN} 且 P(翻转偏好) ≤ {PREF_FLIP_MAX:.0%}")
    print(f"    ③ ★max★(realized exposure @ m10/m50/m90) ≤ "
          f"{ACTIVE_EXPOSURE_MAX} / {NT.TRIALS}")

    band = [l for l in LAMBDA_GRID
            if cap[l]["sat"] <= SATURATION_MAX
            and cap[l]["med"] >= MEDIAN_ABS_DP_MIN
            and cap[l]["flip"] <= PREF_FLIP_MAX
            and max(exp[l]) <= ACTIVE_EXPOSURE_MAX]
    mid = math.sqrt(band[0] * band[-1])
    print(f"\n  合格带 = {band}")
    print(f"  ★ MEMORY_LAMBDA = {MEMORY_LAMBDA:.2f} 已冻结 ★"
          f"   合格带 log 尺度中心 = sqrt({band[0]}×{band[-1]}) = {mid:.2f}")
    assert abs(mid - MEMORY_LAMBDA) < 1e-9, \
        "✗ 冻结的 λ 不再是合格带的 log 中心 —— 接口性质漂移了，必须停下来查"
    print("\n  selection rule（照抄进论文）：")
    print("    Lambda was calibrated without condition labels or downstream")
    print("    transfer outcomes. Values were required to satisfy prespecified")
    print("    interface-capacity constraints on saturation, median probability")
    print("    shift, preference reversal, and retrieval exposure. Among")
    print("    admissible values, the log-scale midpoint of the admissible")
    print("    range was selected.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("=" * 78)
    print("029 λ CAPACITY CALIBRATION —— ★group-blind，不看任何 transfer outcome★")
    print("=" * 78)
    print(f"acquisition：ANOMALY_AT={ACQ.ANOMALY_AT} ANOMALY_LEN={ACQ.ANOMALY_LEN}"
          f" T_PROBLEM={ACQ.T_PROBLEM}（anomaly 后仍 22）")
    print(f"任务底座 027 指纹 {NT.assert_frozen()}   种子 "
          f"{PROBE_SEEDS[0]}–{PROBE_SEEDS[-1]}   ★80000–81499 未碰★")
    print("输入 = pooled empirical m（label 已丢弃、含 m=0、已排序）")

    pool = pooled_empirical_m()
    states = frozen_states(BODY)
    cap = capacity_report(states, pool)
    exp = exposure_report(pool)
    recommend(cap, exp)

    print("\n" + "=" * 78)
    print("⛔ 本文件没有计算、也无法计算：Stable vs Volatile ΔC / latency /")
    print("   哪个 λ 最能拉开两个 group —— condition label 在输入处即被丢弃。")
    print("=" * 78)
