"""
体质收支三种修法对比 —— 治得了死亡率，会不会顺手抹平世界差异？
==================================================================

运行：  python cond_compare.py

规则 47：移植后恢复通道几乎从不触发，系统 90–98% 的时间待在死区里被掏空，
第 30 天之后没有任何球有正收支。三个候选修法（`sim.py` 已参数化）：

    ① COND_RECOVER_AT      抬高恢复阈值（30 → 45/55/65），削掉死区
    ② COND_DEADZONE_RECOVER 死区里也缓慢恢复
    ③ COND_SHELTER_RECOVER  住所也贡献体质

★ 规则 45 的教训 ★ 只看死亡率会选错。**必须同时测比值。**
让球活下来但抹平世界差异的改法是失败的 —— 而这三个都有这个风险：
体质普遍变好 → 贫瘠世界的压力变小 → 两个世界可能就没那么不同了。
③ 的方向甚至不好预判（住所贡献体质 → 富世界材料优势被放大 → 也可能拉大差异）。

判据：两个死亡率 <15%，且两个比值不显著低于「现状」。
"""

import sim
from fix_compare import ratio_and_death, N_RATIO, N_DEATH

# (标签, 恢复阈值, 死区恢复, 住所恢复)
VARIANTS = [
    ("现状",                30.0, 0.00, 0.00),
    ("① 阈值 45",           45.0, 0.00, 0.00),
    ("① 阈值 55",           55.0, 0.00, 0.00),
    ("① 阈值 65",           65.0, 0.00, 0.00),
    ("② 死区 +0.03",        30.0, 0.03, 0.00),
    ("② 死区 +0.06",        30.0, 0.06, 0.00),
    ("③ 住所 +0.05",        30.0, 0.00, 0.05),
    ("③ 住所 +0.10",        30.0, 0.00, 0.10),
    ("①55 + ③0.05 合用",    55.0, 0.00, 0.05),
]


def main():
    sim.KNOWLEDGE_WEIGHT, sim.KNOWLEDGE_GOAL_WEIGHT, sim.KNOWLEDGE_FORGET = 12.0, 0.25, 0.02
    print("=" * 104)
    print(f" 体质收支三修法   022 打开   比值 N={N_RATIO}(60天)   死亡率 N={N_DEATH}(120天)")
    print("=" * 104)
    print(f"  {'修法':<18}{'死亡%完整':>11}{'死亡%无地板':>12}"
          f"{'比值 完整':>22}{'比值 无地板':>22}")
    print("  " + "-" * 100)

    for label, rec_at, dz, sh in VARIANTS:
        sim.COND_RECOVER_AT = rec_at
        sim.COND_DEADZONE_RECOVER = dz
        sim.COND_SHELTER_RECOVER = sh
        r_f, ci_f, _ = ratio_and_death(False, 60)
        r_a, ci_a, _ = ratio_and_death(True, 60)
        _, _, d_f = ratio_and_death(False, 120, N_DEATH)
        _, _, d_a = ratio_and_death(True, 120, N_DEATH)
        print(f"  {label:<18}{d_f:>10.1%}{'' if d_f < .15 else '⚠':<1}"
              f"{d_a:>11.1%}{'' if d_a < .15 else '⚠':<1}"
              f"{r_f:>10.3f} [{ci_f[0]:.3f},{ci_f[1]:.3f}]"
              f"{r_a:>10.3f} [{ci_a[0]:.3f},{ci_a[1]:.3f}]")

    print("\n  判据：两列死亡率都 <15%（无 ⚠），且两列比值都不显著低于「现状」")
    print("  ⚠ 比值塌了就是失败，哪怕死亡率降到 0")


if __name__ == "__main__":
    main()
