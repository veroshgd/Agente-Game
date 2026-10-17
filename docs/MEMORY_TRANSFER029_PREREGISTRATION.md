# 实验 029 预注册 —— Memory-Mediated Transfer

**写死日期：2026-08-18 · 状态：★ 全部冻结 ★ → 待起飞检查 → 待执行**

一次性文件。写完之后到跑完之前，**不改这个文件、不改 architecture、
不改 acquisition 参数、不改 retrieval、不改 λ、不改 capacity gates、
不改 primary endpoint、不改 SESOI、不改判读规则、不改统计程序、不改种子块。**
跑完之后**也不改**，只在实验记录里追加结果。

> ✅ **§6.3 已拍板：CI 上界 < 0.25（B）**，并附条件性判读（§6.3.2）与
> pilot-informed 透明披露（§6.3.1）。
> **本文件至此全部冻结。** 80000–81499 在通过起飞检查之前仍然一颗不碰。

---

## 0. 研究问题

> **相同的异常经历，因为后来在不同世界里得到不同结果，是否能形成不同的
> 关系性记忆；而这份记忆，是否能在表面陌生但结构相似的未来问题里
> 减少实际错误？**

形式化：

```
Can structurally relevant past experience be retrieved and causally used
to adapt to a surface-novel problem?
```

### 与 025 / 027 / 028 的分工

| 实验 | 问题 | 结果 |
|---|---|---|
| 025 / v3 | 过去能不能**留下**？ | ✓ 明显 |
| 027 | 留下的 personality 会**自动迁移**吗？ | 极弱（0.08 trial） |
| 028 | 等预算下**加宽** personality readout 能救吗？ | 没有（G ≈ 0） |
| **029** | 过去的**经验**能否被**检索**并**因果使用**？ | ← 本实验 |

⚠ 029 换掉的是**通路的类型**，不是带宽：

```
027 / 028   历史 → 我们替它读出的一个标量 → β → 探索加成
029         历史 → 可寻址的关系性条目 → agent 自己按情境取用 → 决策
```

---

## 1. ★ 冻结对象（跑本实验前全部已冻结）★

```
architecture   memory-only。发育史【只】经记忆进入测试任务。
               body = NeutralBody（curiosity=caution=50），两个 condition 完全相同。
               ⛔ 不加 trait 通路（理由见 §8 规则 93 最终版）

acquisition    3 problems × 66 trial；ANOMALY_AT=36，ANOMALY_LEN=8，anomaly 后 22
               α=0.05  τ=0.20  Q_INIT=0.5  P_HIGH/P_LOW=0.80/0.20

retrieval      情境窗口 stateful：RETRIEVE → ACTIVE → RESOLVED
               进入：Q[cur] ≥ 0.60 且连续 surprise ≥ 3（PE < −0.30）
               退出：Q[另一个] > Q[suspect]  或  在 suspect 上连续 3 次不再意外
               ★ RESOLVED 在 Q-update【之后】判 ★（probe3 修掉的时序 bug）

interface      logit(switch) += λ · m · s     s=+1 离开 suspect / s=−1 回到 suspect
               ★ MEMORY_LAMBDA = 1.00 ★（group-blind capacity calibration 冻结）

capacity gates SATURATION_MAX=0.05  MEDIAN_ABS_DP_MIN=0.02
               PREF_FLIP_MAX=0.25   ACTIVE_EXPOSURE_MAX=20/80（★取 max 不取 mean★）

novel task     027 的 novel_task.py，一个数不改。指纹 26778f672e9e7009
               80 trial，第 41 trial 反转，P=0.80/0.20，哪个先好按种子随机
```

### λ 的 selection rule（照抄进论文）

> Lambda was calibrated without condition labels or downstream transfer
> outcomes. Values were required to satisfy prespecified interface-capacity
> constraints on saturation, median probability shift, preference reversal,
> and retrieval exposure. Among admissible values, the log-scale midpoint of
> the admissible range was selected.

合格带 {0.5, 1.0, 2.0}，`1.0 = √(0.5×2)` 是 log 尺度中心 ——
**选"距离上下两个失效方向最远的"，不是"potency 最大的"**。
代码里有断言：λ 若不再等于合格带 log 中心即报错。

⚠ **λ 在看到任何 group transfer outcome 之前冻结。**
所以"是不是换个 λ 就能阳"这个问题的答案是：**不知道，也不允许事后换。**

---

## 2. 发育史：Stable vs Volatile（★ 两边都经历 surprise ★）

⛔ **错误做法**：「Stable 从来没有 surprise，Volatile 有很多」——
那会让记忆的区别退化成"一个有数据、一个没数据"。

✅ **本设计**：**同一种表面现象，意味着不同的东西。**

```
trial  0 .. 35     原策略 p_high、另一个 p_low        ← 两条件相同
trial 36 .. 43     ★两个都掉到 p_low★                ← 两条件【逐位相同】
trial 44 .. 65     Stable  ：原策略恢复 p_high
                   Volatile：另一个变成 p_high
```

- 奖励抽样两条件**共用同一条随机流** → `trial < 44` 上**逐位相同**。
  **光看异常本身分不出身处哪个世界**，差异只在"这次异常意味着什么"。
- 每个 problem 的 first-good side 按种子 counterbalance。
- 学到的关系是：
  - **Stable**：persistent surprise 有时只是 noise，**stay 更划算**
  - **Volatile**：persistent surprise 往往意味着规则变了，**switch 更划算**

### 必须匹配（构造性，逐位相等）

```
① 总 trial 数      ② 总 reward opportunity      ③ first-good identity
④ pre-anomaly observations                       ⑤ task length structure
```

### ★ 明确【不】匹配，且不许事后补平 ★

- **realized reward**：Volatile 更低（change point 后必须重新学习）。
  补平它 ≈ 给 Volatile 额外补偿、**取消 volatility 本身的成本**。
- **memory completeness**：两侧不等（见 §9）。强行配平 =
  **修改 post-treatment mediator**。
- **episode 数**：行为产物，报告即可。

---

## 3. 记忆结构（★ 规则 85：存 relation，不存 identity ★）

```
Episode:
    context               关系性情境标签（"previously_good_strategy"）
    previous_expectation  窗口开始时 Q[suspect]
    observation           触发窗口的那串异常里的平均回报
    prediction_error      observation − previous_expectation
    action_relation       ★ "stay" / "switch" ★
    outcome               这次决策拿到的回报
```

**存了 A/B，换一个新任务之后就没有任何可迁移性** —— 新任务里根本没有 A 和 B。
已实现为**硬约束**：`Episode.__post_init__` + `_assert_relational_only()`，
字段里出现任何选项身份直接报错。

读出：

```
m = E[R | switch, similar past] − E[R | stay, similar past]
任一侧无条目 → m = 0（无证据，不是"证据为零差异"）
```

⚠ `suspect` 是决策时的**工作变量**，不是 Episode 字段。

---

## 4. ★ Primary endpoint：ΔC ★

```
C_i = Σ_{t=40..79} 1( choice_t ≠ correct_option_t )     规则变化后一共选错多少次
ΔC  = C(Volatile-history) − C(Stable-history)           同种子配对
ΔC < 0  ⇔  Volatile 型记忆更有帮助
```

`C = 40 × (1 − 反转后正确率)`，恒等式已写成断言。

### 为什么不是 switch latency（★ 规则 89 ★）

`ACTIVE` 的退出条件 ≈「Q 证明新策略更好」，
restricted switch latency ≈「新策略开始稳定占优」——**构造上重叠**。
**primary endpoint 不能与机制自身的活跃窗口重叠。**
latency 保留为 secondary mechanistic。

ΔC 的好处：窗口由任务事先固定 / 不读 ACTIVE 或 RESOLVED /
无 never-switch censoring / **所有 agent 都有** / 单位是 trial / 测的是实际
functional cost。

### ★ SESOI = 1.0 post-change error ★

即在固定的 40 个 post-change trial 里**少犯 1 次错误**，
等价于 `1/40 = 2.5%` 的 post-change accuracy。

理由：
- 与 027 / 028 采用的 **1 trial 功能单位一致**，不是现在临时创造一个 0.5 或 0.75；
- **开发 rehearsal 已经看到 ΔC = −0.927**，定 1.0 **不会**把已看到的开发结果
  事后包装成"功能成功" —— 恰恰相反，按此门槛开发结果只能算
  *statistically detectable / directionally strong，功能意义尚未建立*。

### ★ 三档判读（95% CI，双侧）★

| 情况 | 判读 |
|---|---|
| CI **包含 0** | **No evidence of memory-mediated transfer.** |
| CI 完全 **< 0**，但未完全越过 **−1** | **Detectable memory-mediated transfer, but functional significance not established.** |
| CI **整体 < −1** | **Functionally meaningful memory-mediated transfer established.** |
| CI 完全 **> 0** | 明确是**反方向 / 有害** transfer，照写 |

（开发 rehearsal 的 `[−1.202, −0.677]` 正属于第二档。）

---

## 5. Secondary mechanistic

```
restricted switch latency（截尾规则沿用 027：0–35 真实值，36 = 观察窗内未切换）
retrieval exposure（potential 在 λ=0 轨迹上定义 / realized 在正式轨迹上）
per-opportunity potency Δp
ACTIVE duration
```

⚠ **规则 88**：`potential` 与 `realized` 必须分开报，
且**绝不许**只分析"成功想起了记忆"的 agent。

---

## 6. ★ Confirmatory mechanistic control：SHUFFLE ★

### 6.1 定义

在**每个 agent 自己的条目内**打乱 `action_relation`：

```
保留：episode 数、stay/switch 各自的条数、outcome 的边际分布
摧毁：action ↔ outcome 的【关系】
```

问的是：**起作用的是关系结构，还是记忆库的 marginal statistics？**

### ★ permutation rule 与 salt 冻结（FINAL 前写死）★

```
rng = random.Random( SHUFFLE_SALT ^ seed ^ (len(episodes) << 8) )
rng.shuffle(relations)                     SHUFFLE_SALT = 0x29C10
```

⛔ **不许**在 FINAL 运行时现场生成新的 shuffle 方案。
同一 `(seed, len(episodes))` 必须永远给出同一个置换（runner 里写成确定性自检）。

### 6.2 统计量：retention ratio

```
R = |ΔC_SHUFFLE| / |ΔC_OWN|
```

**joint same-seed bootstrap**：每个 replicate 重采样**一组**种子下标，
两个臂共用该组下标，**abs 与除法逐 replicate 施加**（承 028 的教训：
先分别求均值再套非线性、或拿两条 marginal CI 的端点相除，都是错的）。

⚠ **规则 84**：`R` 恒 ≥ 0，所以"CI 排除 0"没有信息量。
判据**只看上界**与 0.25 的关系。

### 6.3 ★ 判据：CI 上界 < 0.25（选 B，已拍板）★

```
判据：  CI_97.5%( R )  <  0.25
```

⛔ **不采用**"点估计 < 0.25"。只要求点估计，会让"**至少 75% 的 transfer 被摧毁**"
这句话说得**比证据强**。既然我们真正想声称的是"relational structure 被破坏后，
大部分 transfer 消失"，那么**不确定性本身也必须支持这句话**。

### 6.3.1 ⚠ 透明披露（必须写进结果与论文）⚠

开发 rehearsal（n=400）实测：

```
R = 0.094      95% CI [0.005, 0.261]
```

按本判据，开发数据上的诚实写法是：

> **point estimate strongly supports collapse, but the rehearsal sample is
> insufficient to establish ≥75% attenuation with 95% confidence.**

**不是**"差一点所以改成 A"。

必须随结果一起写明：

> **The CI-upper interpretation in §6.3 was finalized after observing the
> development rehearsal retention estimate R = 0.094, 95% CI [0.005, 0.261],
> but before any observation from the confirmatory seed block.**

即：029 相对 FINAL 仍然是 **prospective**，但**这条机制判据明确是
pilot-informed**，不许假装是 rehearsal 之前就有的。

（功效尺度检查：把同一份 400 种子的 joint per-seed 经验分布放大到 N=1500，
预期 ratio CI 约缩到 `[0.014, 0.182]` 量级。**这不是对 FINAL 的预测保证**，
只说明 B 在 N=1500 下不是一个荒谬地严、注定失败的 gate。）

### 6.3.2 ★★ 条件性判读（分母不可辨识时不许判 SHUFFLE）★★

若 FINAL 的 `ΔC_OWN ≈ 0`，则 `R` 的分母接近 0，比值不稳定甚至爆炸。
**这时不能说 "SHUFFLE control failed"** —— 根本没有一个 OWN transfer
可以拿来问"保留了多少"。

> **The SHUFFLE retention criterion is interpreted only if the OWN primary
> effect shows evidence of transfer (its 95% CI excludes 0 in the preregistered
> direction). If OWN does not establish transfer, the retention ratio is
> reported descriptively but no relational-mediation claim is evaluated.**

```
OWN CI 含 0（或方向相反）
    → primary 不成立
    → R 仅作描述性报告
    → ⛔ 不判 "relation retained / destroyed"

OWN CI 完全 < 0
    → 才进入 SHUFFLE mechanism gate
    → CI_97.5%(R) < 0.25 才支持 "≥75% attenuation"
```

**这一条在看到 FINAL 之前写死。**

## 7. Seed-coupling control：XSEED-DONOR

种子 s 使用**另一个种子**的**同条件**记忆。

问的是：**效应是不是靠"发育与测试共享同一个种子"的耦合造成的？**

### ★ donor mapping 冻结（FINAL 前写死，不许临场决定）★

```
donor_index(i) = (i + N // 2) % N          deterministic half-block rotation
FINAL：N = 1500  →  donor_index(i) = (i + 750) % 1500
rehearsal：N = 400 →  (i + 200) % 400      （同一条规则）
```

必须满足（runner 里写成断言）：

```
① 无 self-donor：∀i, donor_index(i) ≠ i
② 一一映射（bijection）
③ Stable 与 Volatile 使用【同一个】 donor permutation
④ ⛔ 不许根据任何 memory / outcome 选择 donor
```

预期：基本保留（开发 rehearsal：保留 OWN 的 **96.0%**）。

⚠ 命名纪律：**不叫 SWAP-XS**。它与 SWAP 问的不是同一件事。

---

## 8. ★ Integrity assertions：DELETE 与 within-seed SWAP ★

```
DELETE   两个 condition 都用空库 → 逐 trial 相同 → ΔC ≡ 0
SWAP     两个 condition 的记忆互换 → ΔC ≡ −ΔC(OWN)
```

在 memory-only 架构下这两条**在构造上必然成立**。
它们作为**断言**运行（不符即整批作废），**不作为科学证据报告**。

> ### ★ 规则 93（最终版）★
> When memory is the sole developmental pathway into the test task, DELETE and
> within-seed SWAP are **algebraic integrity checks rather than independent
> causal evidence**. A second developmental pathway should **not** be introduced
> merely to make these controls non-trivial; causal support should instead come
> from **interventions on memory structure** such as relational shuffling and
> cross-seed donor tests.

⛔ **不许**为了让 SWAP"变得非平凡"而把 trait 通路加回来。那会把干净的
`history → relational memory → novel adaptation` 重新变成
`history → memory + traits → …`，又要处理 memory/trait competition、
interaction、budget —— 即 027/028 那一整套。
**029 的目标不是证明"memory 比人格更重要"。**

---

## 9. ★ Extensive margin 的口径（冻结）★

```
primary extensive margin  =  P( relational memory COMPLETE )
                             complete := 至少 1 条 stay 且至少 1 条 switch
```

开发块实测：**Stable 65.75% / Volatile 73.25%**

另报（**可以报，但不许叫 extensive / availability**）：

```
non-zero evidence rate     Stable 64.25% / Volatile 73.25%
```

差别来自 **6 个 Stable agent（1.5%）两侧都有条目、但两侧均值恰好相等 → m = 0**。

> ⚠ 它们**不是"没有形成记忆"**。它们形成了**完整的**关系性记忆，
> 只不过这份经验告诉它"**过去 switch 和 stay 没有区别**" ——
> 这是**有意义的零证据**。把 `m ≠ 0` 叫成 memory availability，
> 会把"形成了一份中性经验"错误归类成"没有记忆"。

### ★ 规则 91（不变）★

> Memory availability is itself a developmental outcome. Do not condition
> transfer or calibration on successful memory formation. Report the extensive
> margin (P[m usable]) and intensive margin (m | usable) separately, but all
> primary analyses use the full predefined population.

**所有 primary transfer 分析使用全部预定义 agent，含 incomplete 与 m = 0。**

---

## 10. 统计程序

```
配对        逐种子 d_i = C_Volatile,i − C_Stable,i（same-seed 双胞胎）
Primary     mean(d_i)
CI          按种子 cluster bootstrap 10,000 次，95%
R           joint same-seed bootstrap 10,000 次，逐 replicate 施加 abs 与除法
分析种子    8181（固定，落盘）
```

⚠ 双胞胎共享 novel task 的奖励表与 softmax 抽样 `u_t` ——
这是 **common random numbers / counterfactual pairing 的方差缩减设计**，
**不是**假装现实中两个 agent 会共享随机数。必须在 Methods 说明。

### 提前套用规则 56（可判定性）

`CI 是否越过 −1` 又是一条 bright line。**彩排阶段**（已烧种子）要换 8 个分析
随机种子重跑；若判读会被分析随机种子左右，**在跑 FINAL 之前**把边界宽度
取 ≥10 × 实测 MC SD 写成三值判读。**绝不事后改。**

---

## 11. ★ Validity gates（判读顺序：先于 outcome）★

按顺序执行，**全部通过之后才允许计算 ΔC**：

### G1 acquisition manipulation check（构造性）

```
trial < 44 两条件逐位相同                              必须成立
总 trial 数 / 总 reward opportunity / first-good side  必须逐位相等
```

### G2 interface capacity transport（★ group-blind ★）

在 **FINAL 块**上重算 empirical m 分布（**pooled、含 m=0、排序，label 丢弃**），
用 λ=0 的 frozen decision states 重算四个 capacity 读数：

```
P(推后饱和) ≤ 0.05     median|Δp| ≥ 0.02
P(翻转偏好) ≤ 0.25     max(realized exposure @ m10/m50/m90) ≤ 20/80
```

⚠ 这一步**不会**泄露分组：label 在输入处即被丢弃。

**失败时的固定措辞：**

> Interface capacity calibrated on the development block did not transport to
> the confirmatory population; the memory channel is not cleanly interpretable
> under the preregistered capacity constraints.

⛔ gate 失败**不许重估 λ**。

### G3 integrity assertions

```
DELETE ΔC ≡ 0（逐种子）        SWAP ΔC ≡ −ΔC(OWN)（逐种子）
```

任一失败 → **整批作废**（说明发育史存在记忆以外的泄漏通路）。

---

## 12. ★ 种子账本与 FINAL 块 ★

```
0–1499          development（029 的全部探针、校准、rehearsal 都在 0–399）
10000–11499     021 留出集 / 028 transport rehearsal
20000–21499     022 预注册段 / 027 + 028 group-blind calibration
50000–51499     v3 / 025 persistence FINAL
60000–61499     027 novel-task FINAL
70000–71499     028 breadth FINAL
80000–81499     ★ 029 FINAL ★
```

### 029 FINAL CONFIRMATORY BLOCK

```
seed0 = 80000     N = 1500     seeds = 80000–81499
```

- **仅用于 Experiment 029 FINAL**
- **禁止**用于 calibration / transport / rehearsal / parameter selection
- **一旦任何 agent trajectory 被正式生成，该 block 视为 burned**

已核实：整个仓库与实验记录中 `80000` 只出现在
"untouched / 不碰 / 预留"这类说明里，**没有任何 simulation 路径使用过这一段**。

### 工程保护（runner 必须实现，沿用 028 那套）

1. **Seed guard** —— `--final` 只接受 `seed0=80000, N=1500`，其他值直接拒绝
2. **One-shot lock** —— `final_029_STARTED.lock` 一旦创建，
   **哪怕后续崩溃，该 seed block 永久 burned**；`final_029_result.txt`
   已存在则拒绝再次运行
3. **Preflight ledger print** —— 开始前打印并落盘完整种子账本
4. 任务指纹 `26778f672e9e7009` + 冻结常量校验，任一不符即拒绝运行
5. 落盘 `MEMORY_LAMBDA`、四个 gate 值、分析种子、各模块 sha256

---

## 13. ★★ Closure rule ★★

> **一旦看到 80000–81499 的 Stable/Volatile 结果，不允许再改：**
> architecture（memory-only / NeutralBody）、acquisition 参数、retrieval 规则、
> λ、capacity gates、primary endpoint、SESOI、三档判读、SHUFFLE 判据、
> XSEED-DONOR 定义、extensive margin 口径、统计程序、种子块。
>
> **Primary 失败就是失败。**

失败后可做 exploratory analysis，但**只能标为 exploratory**。

---

## 14. 事前预测（跑前写下，跑完照抄对比）

| 项 | 预测 |
|---|---|
| ΔC 方向 | 预测 **< 0**（Volatile 型记忆更有帮助）—— 这是**有方向的**预测，与 027/028 的双侧不同 |
| ΔC 是否越过 SESOI = 1.0 | **未知** —— 这是本实验唯一真正未知的一项。开发块 −0.927 就在门槛下方 |
| G1 / G3 | 必过（构造性 + 已在开发块通过） |
| G2 capacity transport | 预计通过（开发块四项均有余量） |
| SHUFFLE R | 点估计预计 ≈ 0.1；CI 上界能否 < 0.25 **不预设**（功效尺度检查提示 N=1500 下约 `[0.014, 0.182]`，但那不是保证） |
| ΔC_OWN ≈ 0 的情形 | 则按 §6.3.2 **不判** SHUFFLE，只描述性报告 R |
| XSEED-DONOR | 预计保留 OWN 的 ≥ 80% |
| memory completeness | 预计 Stable ≈ 66%、Volatile ≈ 73% |

---

## 15. 措辞纪律

- ⛔ **不许写** *analogical reasoning* / agent "理解了结构 / 理解了因果"
- ⛔ **不许写** *generalized individuality*
- ⛔ **不许**把 DELETE / within-seed SWAP 写成因果证据（规则 93）
- ⛔ **不许**把 `m ≠ 0` 叫 memory availability（§9）
- ⛔ **不许**只报 complete-only 的分离度（规则 91）
- ✅ 可写：**retrieval-conditioned adaptation to a surface-novel task**
- ✅ 可写：**memory-mediated transfer**（若 primary 达标）
- ✅ 必须在 Methods 说明 common random numbers 的方差缩减设计
- ✅ 必须说明 λ 是 group-blind capacity calibration 冻结的，并附 selection rule 原文

---

## 附：029 与 027/028 的关系（写进 Discussion）

027 + 028 已经确立：

> **Persistent individuality ≠ automatically functional generalization.**

029 **不推翻**它，而是把问题换掉：不再问"过去塑造出的性格会不会神奇地帮助
任何新问题"，而是严格测试一条具体机制 ——

> 相同的异常经历，因为后来在不同世界里得到不同结果，是否能形成不同的
> **关系性记忆**；而这份记忆，是否能在**表面陌生但结构相似**的未来问题里
> **减少实际错误**。

若 029 也 ≈ 0：核心命题**加强**为"即使给它一条真正的 episodic 检索通道、
且该通道的接口容量已被独立校准为充分，持久个体差异仍然几乎不携带
可复制的功能迁移"。**两个方向都有信息量** —— 这一段在跑数之前写死，
防止事后为了拿阳性而回头改设计。
