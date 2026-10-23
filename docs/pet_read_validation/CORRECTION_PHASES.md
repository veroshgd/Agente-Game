# 更正记录：阅读轮的阶段安全统计（2026-10-23，第 4 轮）

本记录不覆盖任何冻结文件。`pet/validate_read.py`（sha256 `ff5d2663…`）、`read_dev_result.json`、
`base2_verification.json` 保持原样；复算由新模块 `pet/recheck_read_phases.py` 完成，结果存于
`correction_phases_recheck.json`。

## 缺陷

1. **`plastic_life()` 没有阶段标记。** 110 天（成长 20 + 共同 20 + 干预 30 + 恢复 40）被当成一个
   “growth” 阶段检查，30 天干预期的风险被整段平均掩盖；两个分支（stay / away）还共用同一个 life_id。
   更正：同样的调用、同样的顺序，只加 `phase('common' / 'intervention' / 'recovery')`，id 加分支名。
2. **去重只保留同一轨迹第一次运行的阶段标记。** 同一轨迹若在另一次运行中带有不同阶段（例如
   read_nodecision 的 keep / swap 双胞胎），其阶段检查会被丢掉。更正：每条唯一轨迹的阶段失败取所有运行的并集。

## 行为与随机状态不变

所有 plastic 生命的轨迹指纹、随机数发生器终态与冻结版本逐一相同（三组样本均为 `true`）。

## 复算（唯一轨迹中阶段检查失败的数量）

| 样本 | 组 | 冻结统计 | + 阶段标记 | + 并集去重 |
|---|---|---:|---:|---:|
| 开发 | base | 9 | **10** | **10** |
| 开发 | base2 | 10 | **11** | **11** |
| 复核 7021–7040 | base | 8 | 9 | 9 |
| 复核 7021–7040 | base2 | 8 | 9 | 9 |
| 阅读开发 | read_nodecision（对照） | 9 | **10** | **10** |
| 阅读开发 | read_value（候选） | 13 | 13 | **13** |
| 阅读开发 | read_flat | 6 | 6 | 6 |

- 新增失败都来自 **6006 · plastic · away 的干预阶段**（复核样本中为 7039 · plastic · stay）。
  6006 away：base 与 base2 干预期低于 20 的时间均为 **10.56 %**（标准 ≤ 8 %），最低 6.55；整段生命仍通过。
- 去重：read_nodecision 有 20 条轨迹带不同阶段标记，但本次没有丢失任何失败（并集与首次相同）。缺陷真实存在，本次数值未受影响。
- 所有整生命检查不变（252/252、372/372）。

## 结论是否改变

- base2：11 > 10，仍未通过自身核验，不采用（结论不变）。
- 阅读候选：H 阶段 13 > 10，仍未通过（结论不变，差距从 4 缩为 3）。
- 回归测试：`tests/test_pet_interest.py::test_plastic_6006_away_intervention_fails_once_phases_are_marked`。

复现：`py -3 -m pet.recheck_read_phases docs/pet_read_validation`（约 6 分钟）。
