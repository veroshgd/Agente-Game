"""
实验 027 执行器 —— 严格按 NOVEL_TASK_PREREGISTRATION.md
=========================================================

彩排（已烧种子，可随便跑）：
    python final_027.py --check                      只做冻结校验
    python final_027.py --seed0 20000 --n 300        全流程彩排
    python final_027.py --seed0 20000 --n 300 --workers 5   规则 55 自检

正式（**只允许执行一次**）：
    python final_027.py --final

★ v4 = v3_frozen 核心（逐字节不动）+ novel_task.py ★
启动时校验 `v3_frozen/SHA256SUMS.txt` 与任务配置指纹，任一不符即拒绝运行。

★ 四个臂 ★
    main            beta_i = β × novelty_style_i        主分析
    hist_blind      beta_i = β × 0.5（对所有人相同）      控制三
    trait_level     任务入口把 curiosity/caution 拉平     控制四
    （控制一/二在 `novel_task.py` 自检里，pytest 也跑）

⚠ **控制三/四 = pathway-isolation / leakage controls（修订 01 已降格）**：
  任务的输入面**只有** `novelty_style = f(curiosity, caution)`，
  所以"固定 beta"与"拉平 curiosity/caution"都会让双胞胎在任务中完全相同。
  两者因此是**两个实现层的泄漏检测器**（一个查 NovelTask 内部，
  一个查 agent state 侧），**不能**算两个独立的 negative control，
  更**不能**用来"发现另一条历史载体" —— 任务没给别的载体留输入口。
"""

import argparse
import hashlib
import os
import random
import statistics
import multiprocessing as mp
import sys
import time

import novel_task as NT

HERE = os.path.dirname(os.path.abspath(__file__))
V3DIR = os.path.join(HERE, "v3_frozen")
WA, WB = "丰富世界", "贫瘠世界"
FINAL_SEED0, FINAL_N = 60000, 1500
CHUNK = 25
N_BOOT, N_PERM = 10000, 10000
BOOT_SEED, PERM_SEED = 20260817, 777
DIAG_SEEDS = [BOOT_SEED + 1000 * r for r in range(8)]   # 可判定性彩排
ATTRITION_GATE = 0.90
SESOI = 1.0          # 修订 01：±1 trial 的 practical-equivalence region
ARMS = ("main", "hist_blind", "trait_level")


def preflight(verbose=True):
    sums = os.path.join(V3DIR, "SHA256SUMS.txt")
    bad = 0
    for line in open(sums, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        want, name = line.split(maxsplit=1)
        got = hashlib.sha256(open(os.path.join(V3DIR, name), "rb").read()).hexdigest()
        bad += 0 if got.startswith(want) else 1
    if bad:
        raise SystemExit(f"✗ v3_frozen 校验失败（{bad} 个文件）—— 拒绝运行")
    fp = NT.assert_frozen()
    if verbose:
        print(f"✓ v3_frozen 校验通过")
        print(f"✓ 任务参数已冻结  α={NT.ALPHA} β={NT.BETA} τ={NT.TAU}"
              f"  指纹 {fp}")
        print(f"✓ 模型 {NT.sim.MODEL_VERSION} → {NT.MODEL_VERSION}"
              f"  COND_RECOVER_AT={NT.sim.COND_RECOVER_AT}")
    return fp


def task_sim(job):
    """跑 60 天 v3 核心 → 拉平 → 回传任务所需的最小状态"""
    world, seed0, n = job
    import novel_situation as NS
    sim = NS.sim
    sim.COND_RECOVER_AT = 65.0                      # ★规则 55★ 显式设定
    sim.COND_DEADZONE_RECOVER = sim.COND_SHELTER_RECOVER = 0.0
    sim.SLEEP_SUPPRESS = sim.HUNGER_URGENCY = 0.0
    sim.SLEEP_EFF_FLOOR = 0.35
    sim.KNOWLEDGE_WEIGHT, sim.KNOWLEDGE_GOAL_WEIGHT, sim.KNOWLEDGE_FORGET = 12.0, 0.25, 0.02

    out = []
    for s in range(seed0, seed0 + n):
        life = NS.scenarios.make(s, world)
        ok, _ = NS.run_window(life, 0, 30)
        if ok:
            w = sim.World(s, **NS.scenarios.WORLDS["基准"])
            ok, _ = NS.run_window(life, 30, 30, world=w)
        if not ok:
            out.append({"seed": s, "alive": False})
            continue
        NS.level_state(life.agent)
        t = life.agent.traits
        out.append({"seed": s, "alive": True,
                    "cur": t["curiosity"], "cau": t["caution"]})
    return world, seed0, out


def _dispatch(j):
    return j[0](j[1])


class _Agent:
    def __init__(self, cur, cau):
        self.traits = {"curiosity": cur, "caution": cau, "industry": 50.0}


def endpoints(rec):
    """primary = restricted switch latency；secondary = trial 1–10 探索率"""
    return NT.switch_latency_restricted(rec), NT.explore_rate(rec, 0, 10)


def run_arm(arm, ra, rb, seed):
    """返回 (rich 的 (L, E), poor 的 (L, E))"""
    if arm == "trait_level":
        m_cur = (ra["cur"] + rb["cur"]) / 2.0
        m_cau = (ra["cau"] + rb["cau"]) / 2.0
        agents = (_Agent(m_cur, m_cau), _Agent(m_cur, m_cau))
    else:
        agents = (_Agent(ra["cur"], ra["cau"]), _Agent(rb["cur"], rb["cau"]))
    blind = (arm == "hist_blind")
    x = NT.run_task(agents[0], seed, history_blind=blind)
    y = NT.run_task(agents[1], seed, history_blind=blind)
    return endpoints(x), endpoints(y)


def boot_ci(d, seed, n_boot=N_BOOT):
    rng = random.Random(seed)
    n = len(d)
    vals = sorted(statistics.mean(d[rng.randrange(n)] for _ in range(n))
                  for _ in range(n_boot))
    return vals[int(.025 * n_boot)], vals[int(.975 * n_boot)]


def perm_p(d, seed, n_perm=N_PERM):
    rng = random.Random(seed)
    obs = statistics.mean(d)
    hits = sum(1 for _ in range(n_perm)
               if abs(statistics.mean(x if rng.random() < .5 else -x
                                      for x in d)) >= abs(obs))
    return obs, (hits + 1) / (n_perm + 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--seed0", type=int, default=20000)
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    a = ap.parse_args()

    fp = preflight()
    if a.check:
        return

    # ★★ closure rule 的机器强制执行 ★★
    # 预注册 §8 写了"只允许执行一次"，但光靠打印约束不住 ——
    # 再跑一次就会覆盖同一个结果文件。这里做成硬拦截。
    final_out = os.path.join(HERE, "final_027_result.txt")
    if a.final and os.path.exists(final_out):
        raise SystemExit(
            "✗ final_027_result.txt 已存在：027 FINAL 已执行过，拒绝再次运行。"
            "（预注册 §8：seeds 60000–61499 只允许烧一次。）")

    seed0, N = (FINAL_SEED0, FINAL_N) if a.final else (a.seed0, a.n)
    if a.final:
        print("\n" + "!" * 76)
        print(f"!! 027 FINAL  seeds {seed0}–{seed0+N-1}  ——  这一段只允许跑一次")
        print("!! 看到结果后不允许再改任何关键设计（预注册 §8）")
        print("!" * 76)
    else:
        print(f"\n[彩排] seeds {seed0}–{seed0+N-1}  N={N} —— 不是 final，可随便重跑")
        print("[彩排] 只检查代码路径 / n / 指标 / 控制 / 确定性 / 统计程序")
        print("[彩排] ⛔ 不根据 rich/poor effect 改任何东西\n")

    jobs = [(task_sim, (w, s0, min(CHUNK, seed0 + N - s0)))
            for w in (WA, WB) for s0 in range(seed0, seed0 + N, CHUNK)]
    planned = sum(j[1][2] for j in jobs)
    assert planned == 2 * N, f"✗ 分块覆盖不全 {planned} ≠ {2*N}"

    store = {WA: [None] * N, WB: [None] * N}
    t0 = time.time()
    with mp.Pool(a.workers) as pool:
        for k, (w, s0, recs) in enumerate(pool.imap_unordered(_dispatch, jobs), 1):
            store[w][s0 - seed0:s0 - seed0 + len(recs)] = recs
            if k % 20 == 0 or k == len(jobs):
                el = time.time() - t0
                print(f"  {k}/{len(jobs)}  已用 {el/60:.1f}min", flush=True)

    # ---- 有效性闸（预注册 §6）----
    dead_a = sum(1 for r in store[WA] if not r["alive"]) / N
    dead_b = sum(1 for r in store[WB] if not r["alive"]) / N
    pairs = [i for i in range(N) if store[WA][i]["alive"] and store[WB][i]["alive"]]
    keep = len(pairs) / N
    print("\n" + "=" * 96)
    print(f" 有效性闸：rich pre-task mortality {dead_a:.2%} · "
          f"poor {dead_b:.2%} · 有效双胞胎 {len(pairs)}/{N} = {keep:.2%}")
    if keep < ATTRITION_GATE:
        print(f" ✗ 有效双胞胎 < {ATTRITION_GATE:.0%} → **validity compromised，"
              f"不做强结论**（预注册 §6）")
    else:
        print(f" ✓ 通过（门槛 {ATTRITION_GATE:.0%}）")
    if not pairs:
        raise SystemExit("✗ 无有效配对 —— 这是故障不是结果")

    # ---- 三个臂 ----
    res = {}
    for arm in ARMS:
        dL, dE = [], []
        for i in pairs:
            (la, ea), (lb, eb) = run_arm(arm, store[WA][i], store[WB][i],
                                         seed0 + i)
            dL.append(la - lb)
            dE.append(ea - eb)
        res[arm] = {"dL": dL, "dE": dE}

    print("\n" + "=" * 96)
    tag = "FINAL" if a.final else "彩排（非 final）"
    print(f" 027 {tag}   seeds {seed0}–{seed0+N-1}   n={len(pairs)}   指纹 {fp}")
    print("=" * 96)
    print(f"  {'臂':<12}{'指标':<28}{'配对差均值':>12}{'95% CI':>26}{'p':>10}")
    print("  " + "-" * 92)
    verdict = {}
    for arm in ARMS:
        for key, name in (("dL", "H2 restricted switch latency"),
                          ("dE", "H1 trial 1–10 exploration")):
            d = res[arm][key]
            lo, hi = boot_ci(d, BOOT_SEED)
            obs, p = perm_p(d, PERM_SEED)
            sig = (lo > 0) or (hi < 0)
            verdict[(arm, key)] = (obs, lo, hi, p, sig)
            print(f"  {arm:<12}{name:<28}{obs:>+12.4f}"
                  f"   [{lo:>+8.4f}, {hi:>+8.4f}]{p:>10.4f}"
                  + ("  *" if sig else ""))

    # ---- 可判定性彩排（规则 56）----
    print("\n  可判定性诊断：换 8 个分析种子重跑 main 臂的 CI")
    for key, name in (("dL", "H2"), ("dE", "H1")):
        los = [boot_ci(res["main"][key], sd)[0] for sd in DIAG_SEEDS]
        his = [boot_ci(res["main"][key], sd)[1] for sd in DIAG_SEEDS]
        npass = sum(1 for lo, hi in zip(los, his) if lo > 0 or hi < 0)
        sd_lo = statistics.stdev(los)
        print(f"    {name}  下界范围 [{min(los):+.4f}, {max(los):+.4f}]"
              f"  MC SD {sd_lo:.4f}  判显著 {npass}/8"
              + ("   ⚠ 被分析种子左右" if 0 < npass < 8 else ""))

    print("\n" + "=" * 96)
    print(" 判读（预注册 §2/§3）")
    print("=" * 96)
    o, lo, hi, p, sig = verdict[("main", "dL")]
    # ★修订 01★ 三值判读：CI 含 0 / 排除 0 但与 ±1 重叠 / 整体越过 ±1
    if not sig:
        h2 = "✗ H2 不获支持（95% CI 包含 0）"
    elif lo > SESOI or hi < -SESOI:
        h2 = "★ functionally meaningful reversal-transfer established ★"
    else:
        h2 = "◐ 统计上存在 history effect，但【功能意义未建立】（CI 与 ±1 重叠）"
    print(f"  ★PRIMARY H2★  {h2}")
    print(f"     Δ={o:+.4f} trial  95% CI [{lo:+.4f}, {hi:+.4f}]  p={p:.4f}"
          f"   SESOI = ±{SESOI} trial")
    print(f"     正 = rich 切换更慢；负 = poor 切换更慢。**双侧，不预设方向。**")
    print(f"     ⚠ 不采用\"点估计过线\"式判读：Δ=1.05 而 CI=[0.20,1.90] 时，")
    print(f"       真值可能只有 0.2 trial，没有把握说它超过功能门槛。")
    o2, lo2, hi2, p2, sig2 = verdict[("main", "dE")]
    print(f"  secondary H1  {'✓' if sig2 else '✗'}   Δ={o2:+.4f}"
          f"  [{lo2:+.4f}, {hi2:+.4f}]  p={p2:.4f}")
    print(f"     ⛔ H1 不得替代 primary：H2 不显著 → H1 显著 ≠ 027 成功")

    print("\n  控制三/四（泄漏检测器）：")
    for arm in ("hist_blind", "trait_level"):
        z = all(abs(x) < 1e-12 for x in res[arm]["dL"] + res[arm]["dE"])
        print(f"    {arm:<12}{'✓ 逐位为零（无泄漏）' if z else '✗ 非零 —— 存在泄漏，整批作废'}")
    print("    ⚠ 历史进任务的唯一路径是 history→curiosity/caution→novelty_style→β_i，")
    print("      所以这两个控制在【构造上等价】，必然同时为零。")
    print("      它们查的是两个不同实现层（NovelTask 内部 / agent state 侧），")
    print("      工程上不重复，但**科学证据上不算两个独立 negative control**。")
    print("      ✅ 可说：history effect 按设计经 novelty style 进入新任务")
    print("      ⛔ 不可说：搜索了所有历史载体，发现只有 traits")

    out = os.path.join(HERE, "final_027_result.txt" if a.final
                       else "final_027_rehearsal.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"027 {tag}  seeds {seed0}-{seed0+N-1}  n={len(pairs)}  fp={fp}\n")
        f.write(f"attrition rich={dead_a:.4f} poor={dead_b:.4f} keep={keep:.4f}\n")
        for (arm, key), v in verdict.items():
            f.write(f"{arm}\t{key}\t{v[0]:+.6f}\t{v[1]:+.6f}\t{v[2]:+.6f}\t{v[3]:.6f}\n")
    print(f"\n已写入 {out}")


if __name__ == "__main__":
    mp.freeze_support()
    main()
