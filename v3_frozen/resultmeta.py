"""
原始结果的版本标记 —— 所有 CSV 都必须带上
==============================================

v2 → v3 只差一个数（`COND_RECOVER_AT` 30 → 65），**从文件内容上完全看不出来**。
半年以后翻到一个 csv，没有版本列就只能靠文件日期猜。

所以约定：**任何写盘的原始结果，前四列固定是**

    model_version   模型版本（v2 / v3 / …）
    experiment      哪个实验（021-3 / 022-P1 / …）
    condition       哪一档（完整架构 / −全部地板①② / …）
    seed            种子（或种子块的起点）

用法：

    from resultmeta import META_FIELDS, meta
    FIELDS = META_FIELDS + ["ratio", "p", ...]
    w.writerow({**meta("021-3", "完整架构", seed), "ratio": r, ...})

⚠ `meta()` 读的是**调用时**的 `sim.MODEL_VERSION` 和 `sim.COND_RECOVER_AT`，
   所以在子进程里改了 sim 全局量也能被如实记下来 —— 这正是要点：
   不是记"我以为跑的是哪版"，是记"实际跑的是哪版"。
"""

META_FIELDS = ["model_version", "experiment", "condition", "seed",
               "cond_recover_at"]


def meta(experiment, condition, seed):
    import sim
    return {
        "model_version": getattr(sim, "MODEL_VERSION", "v2"),
        "experiment": experiment,
        "condition": condition,
        "seed": seed,
        # 冗余但值得：v2/v3 的唯一区别就是它，出问题时不用去翻代码
        "cond_recover_at": sim.COND_RECOVER_AT,
    }
