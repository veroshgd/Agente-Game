# v2 / pre-condition-fix —— 冻结快照

冻结日期：2026-08-15
冻结点：`COND_RECOVER_AT = 30.0`（体质恢复阈值修正**之前**）

> Experiments 011–022 were conducted under model v2 and are retained as
> development history rather than overwritten by subsequent model correction.
>
> 实验 011–022 是在模型 v2 下完成的，作为开发历史保留，
> 不被后续的模型修正覆盖。

## 这里面是什么

`ai-sandbox/` 在 2026-08-15 改成 v3 之前的**完整**源码 + 原始结果：

- 全部 `.py`（含实验 022 的诊断脚本 `mortality_diagnose` / `fix_compare` /
  `cond_compare`，以及定出 v3 的三个脚本 `cliff_probe` / `death_split` /
  `rule48_test`）
- `sweep_results.csv`（021 第 4 节，500 组 × 300 种子）
- `holdout.csv`（021 留出集，seeds 10000–10299）
- `SHA256SUMS.txt`（前 16 位，用来验证快照没被动过）

## v2 → v3 到底改了什么

**只有一行**：`sim.py` 的 `COND_RECOVER_AT`，`30.0 → 65.0`。
其余全部参数、全部机制逐位不变。

理由不是"扫参数发现 65 死亡率最低"，而是有完整机制解释（见
`模拟实验记录.md` 3h 节，规则 49）：

```
抬高恢复阈值 → 体质改善 → survival urgency 减弱 → 富养 agent 减少觅食
             → 饥饿反升 → 进入【怠惰谷】（55–60 档死亡率不降反升）
             → 到 65，体质余量足以跨过这段负反馈区 → 死亡率重新下降
```

## 怎么用

复现任何 011–022 的历史数字：

```powershell
cd C:\Users\yinan\Desktop\ai-sandbox\v2_frozen
python <脚本名>.py
```

快照是自包含的（所有 import 都在本目录内），不会读到上层的 v3 `sim.py`。

⚠ 不要在这个目录里改任何东西。要改就改上层的 v3。
