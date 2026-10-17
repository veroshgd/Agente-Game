"""
NOVEL-SITUATION 机制层 —— 两个 probe + 拉平 + sibling 分叉 + 序列化对照
=========================================================================

自检：  python novel_situation.py            （跑全部机制层测试，~1 分钟）

★ 冻结声明 ★
本模块从 `v3_frozen/` 导入模型，**不修改 v3 的任何一行**。
Probe A 用 `World` 子类（改**取用规则**，不改存量）；
Probe B 用 influence（v3 自带扩展点）。

设计依据：`NOVEL_SITUATION_DESIGN.md` v3。相关规则：

  规则 60  可供性门控必须 non-destructive —— 改取用规则，不改存量
  规则 61  counterfactual sibling branches —— 同一 snapshot 分叉，互不反馈
  规则 62  decision window（行为/G1）与 consequence window（后果/G2）分离
  规则 55  子进程里的全局量每个任务显式设定，不靠继承
"""

import copy
import hashlib
import os
import pickle
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
V3DIR = os.path.join(HERE, "v3_frozen")
if V3DIR not in sys.path:
    sys.path.insert(0, V3DIR)

import sim                                      # noqa: E402
import scenarios                                # noqa: E402
import persistence_ablation as PA               # noqa: E402

for _m in (sim, scenarios, PA):
    assert os.path.abspath(_m.__file__).startswith(V3DIR), \
        f"✗ {_m.__name__} 不是来自 v3_frozen：{_m.__file__}"
assert sim.MODEL_VERSION == "v3"

WA, WB, COMMON = "丰富世界", "贫瘠世界", "基准"

# 拉平点（沿用 leveling.py / 实验 020）。★ shelter 必须低于 gate S ★
LEVEL = {"hunger": 30.0, "energy": 80.0, "shelter": 50.0,
         "condition": 100.0, "food": 3.0, "material": 0.0}

# Probe B 的自然单位（一维 λ 校准，见设计 §2）
K_FOOD = 1.0        # 一次 gather_food 的产出        （sim.py:185）
K_SHELTER = 22.0    # 一次 build 的 shelter 增量      （sim.py:882）


# ---------------------------------------------------------------- Probe A
class GatedWorld(sim.World):
    """冻土：world.food 只在 agent.shelter ≥ gate_S 时**可取**。

    ★ 规则 60 ★ 绝不改写 `self.food`（那是存量）。库存照常 regen、照常保存，
    改的是**取用规则**。写 `world.food = 0` 等于每 tick 烧掉世界存粮，
    下一 tick 从 0 重新 regen —— 那是"毁掉食物"，不是"取不到食物"。

    `agent` 在换世界时绑定 → shelter 在**调用时刻**读取，无一 tick 延迟。
    门关闭时按 v3 相同的条件消耗一次 rng 抽样，让门**只改变可供性、
    不额外扰动随机流**。
    """

    def __init__(self, seed=0, gate_S=60.0, **params):
        super().__init__(seed, **params)
        self.gate_S = gate_S
        self.agent = None

    def take_food(self, rng):
        if self.agent is not None and self.agent.shelter >= self.gate_S:
            return super().take_food(rng)
        if self.food >= 1:          # 与 sim.py:183 相同的抽样条件
            rng.random()
        return 0


# ---------------------------------------------------------------- Probe B
def salt_flat(lam):
    """盐碱地：采材料额外扣 world.food；觅食额外扣 shelter。

    ⚠ 一 tick 延迟：influence 在 `agent.tick()` **之前**运行，
      只能对**上一 tick** 的动作施加代价。论文里如实写明，不假装同 tick 生效。
    """
    c_f, c_s = lam * K_FOOD, lam * K_SHELTER
    prev = {}

    def apply(world, agent, day, tick, rng):
        key = id(agent)
        last = prev.get(key)
        now = (agent.action_log["gather_material"], agent.action_log["gather_food"])
        if last is not None:
            if now[0] > last[0]:
                world.food = max(0.0, world.food - c_f)
            if now[1] > last[1]:
                agent.shelter = sim.clamp(agent.shelter - c_s)
        prev[key] = now
    return apply


# ------------------------------------------------- Probe A2「探路」（候选 1）
def discovery_gather(tau, alpha, base=None):
    """探索历史 → 材料可及性（规则 65/66/67 下的新赛道）

    ★ 精确形式（不是"explore 越多自动得材料"）★
        必须执行 `gather_material` 才拿得到材料；
        **该次采集的 yield 取决于最近 τ 个 tick 内 explore 的比例。**

        explore → 短暂的"已探明区域"状态 → gather_material 收益提高

        纯 explore   拿不到材料（不采就没有）
        纯 gather    只能低效拿材料
        受益的是      explore → gather 的**时序组合**

    这是一条**跨行动 contingency**，两个发育世界都不存在
    （那里 `material_yield` 是常数）。而且它**不碰食物经济**（规则 65）：
    `world.food` / `hunger` / `condition` 一律不动。

    ⚠ 射程：v3 没有在场因果学习，**agent 不会"意识到应该先探路再采集"**。
      它只是带着既有 policy 进入这个新动力学，不同 policy 与新 contingency
      恰好产生不同交互。文案里不许写成"它学会了先探路"。

    实现：每 tick 依据滑动窗口内的 explore 次数改写 `world.p["material_yield"]`
    —— 改的是**速率参数**，不是存量（规则 60）。α=0 时逐位等价于无干预。
    """
    from collections import deque
    hist, prev = deque(maxlen=tau), {}

    def apply(world, agent, day, tick, rng):
        b = world.p["material_yield"] if base is None else base
        apply.base = getattr(apply, "base", b)
        key = id(agent)
        now = agent.action_log["explore"]
        last = prev.get(key)
        if last is not None:
            hist.append(1 if now > last else 0)
        prev[key] = now
        f = (sum(hist) / tau) if tau else 0.0          # 最近 τ tick 的 explore 占比
        world.p["material_yield"] = apply.base * (1.0 + alpha * f)

    apply.hit = lambda: (sum(hist) > 0)
    return apply


# ------------------------------------------- Probe C「离家失修」（正式放行）
SHELTER_FLOOR = 40.0        # 硬下限：避开 sim.py:792 睡眠打分在 shelter=30 的阶跃
STORM_OFF = {"storm_chance": 0.0}   # ★ON/OFF 两支都必须用这个★


def home_neglect(kappa, floor=SHELTER_FLOOR):
    """离家失修：每执行一次 explore，shelter 发生很小的"无人维护损耗"。

    `build` 仍按 v3 原规则修复 shelter —— 不改 v3 任何一行。

        explore --新关系--> shelter 轻微下降
                              ↓
                    improve_home 进度倒退 / 优先级上升（sim.py:611/662）
                              ↓
                    goal stall / switch → 动作打分重新分配

    以前 `see_the_world` 与 `improve_home` 只是**争时间**；
    现在第一次变成「探索会主动破坏修家已取得的进展」。
    所以它同时是 **N1**（新因果关系 explore → shelter loss）
    与 **N2**（新目标冲突）。

    ★ 为什么 shelter 在这里是 goal-progress 变量而不是 survival 变量 ★
      · 硬下限 40 > sim.py:792 的阶跃点 30 —— 不碰睡眠生理
      · 40–75 全落在 improve_home 优先级有响应的区间（sim.py:662）
      · 食物 / hunger / condition 一律不动（规则 65）
      · ON / OFF 两支都用 `storm_chance = 0`（否则同时改了两个东西）

    ⚠ 一 tick 延迟：influence 在 `agent.tick()` 之前运行，只能对**上一 tick**
      的 explore 施加损耗。论文里如实写明。
    ⚠ 射程：agent **不会"意识到"探索会毁家**。它只是按 v3 既有机制反应。
    """
    prev = {}
    ctr = {"explore": 0, "saturated": 0, "clipped": 0}

    def apply(world, agent, day, tick, rng):
        key = id(agent)
        now = agent.action_log["explore"]
        last = prev.get(key)
        if last is not None and now > last:
            ctr["explore"] += 1
            # ⚠ 不能写成 max(floor, shelter - kappa)：若自然衰减（0.35/tick）
            #   已把 shelter 压到 floor 以下，那样会把它**抬回** floor ——
            #   下限变成了"抬升器"，等于给失修的球发福利。
            #   正确语义：损耗不得把 shelter 压到 floor 以下，但也绝不抬高。
            if agent.shelter > floor:
                if agent.shelter - kappa < floor:
                    ctr["clipped"] += 1        # 本该扣 κ，被截到 floor
                agent.shelter = max(floor, agent.shelter - kappa)
            else:
                # ★ 真正的饱和 ★ shelter 已 ≤ floor（自然衰减也会把它压下去），
                #   此后 explore 再也产生不了任何额外损耗 —— Probe C 已失效。
                #   注意：这不等于 shelter == floor，所以**不能**用
                #   "贴边时间比例"来度量饱和（那会严重低估）。
                ctr["saturated"] += 1
        prev[key] = now

    apply.kappa = kappa
    apply.floor = floor
    apply.counters = ctr        # 只读计数，不影响任何状态或随机流
    return apply


def novel_world(seed, kappa=0.0):
    """Probe C 的世界。★ON/OFF 唯一差异是 kappa★ —— 背景完全同构。"""
    return sim.World(seed, **{**scenarios.WORLDS[COMMON], **STORM_OFF})


def enter_novel(life, clear_goal=True):
    """进入 novel/familiar 分支时的统一处理。

    ★ 只清当前正在执行的 intention ★ —— 否则"rich 分身恰好正在 see_the_world、
    poor 分身恰好正在 improve_home"就会让结果退化成
    「它只是把进场前正在做的事继续做下去」。

    **不清** traits / trait_floor / knowledge / flags / goal_satiation /
    memories / hardship —— 那些正是"过去留下的内部结构"，是要测的东西。
    """
    if clear_goal:
        life.agent.goal = None


# ---------------------------------------------------------------- 拉平
def level_state(agent):
    """状态拉平（实验 020 口径）。只动资源态，不动历史携带的东西。"""
    agent.hunger = LEVEL["hunger"]
    agent.energy = LEVEL["energy"]
    agent.shelter = LEVEL["shelter"]
    agent.condition = LEVEL["condition"]
    agent.inventory = {"food": LEVEL["food"], "material": LEVEL["material"]}


# --------------------------------------- 字段审计（规则 63）+ 状态序列化
#
# ★ 规则 63 ★「完整可执行状态」必须是**逐项审计**出来的，不能凭印象列。
#   审计方法：对 v3 的 Agent / World 逐字段 grep 读取点，
#   **有回读 → EXEC（进 hash、全拉平时必须一起拉平）；只写不读 → LOG。**
#
#   第一版犯的错：`"memories": len(ag.memories)` ——
#   **"有 5 条 memory" ≠ "5 条 memory 内容相同"**，而 memories 会被
#   `recall()` 回读（sim.py:517/554/563）。同类漏网还有 goal_satiation。
#
# ── Agent ────────────────────────────────────────────────────────────
#  EXEC  traits/trait_floor/trait_identity   动作打分直接读
#  EXEC  hunger/energy/shelter/condition/inventory   状态项
#  EXEC  hardship/_hardship_anchor           → trait_floor 棘轮
#  EXEC  flags/knowledge/knowledge_strength  score() 回读
#  EXEC  memories          ★ recall() 回读（sim.py:517/554/563）★ 必须全量
#  EXEC  goal                                当前目标影响打分
#  EXEC  goal_satiation    ★ sim.py:694 回读 —— 目标的不应期 ★
#  EXEC  action_log        ★ sim.py:619/626 回读 —— 目标进度 ★
#  EXEC  alive / rng(state)
#  LOG   action_by_hour    sim.py 内无回读，纯记录（分析用）
#  LOG   goal_by_day       无回读
#  LOG   goal_history      无回读
#  STRUCT world            引用，不是状态
#
# ── World ────────────────────────────────────────────────────────────
#  EXEC  food / objects / p / weather / rng(state)
#  EXEC  storm_damage      ★ 动态属性，仅暴雨后存在；sim.py:942 回读 ★
#  LOG   events            仅 influence 写入，无回读
#
# ── Life ─────────────────────────────────────────────────────────────
#  EXEC  inf_rng(state)          STRUCT  agent / world / influences

_AG_EXEC = ("traits", "trait_floor", "trait_identity", "hunger", "energy",
            "shelter", "condition", "inventory", "hardship", "_hardship_anchor",
            "flags", "knowledge", "knowledge_strength", "memories", "goal",
            "goal_satiation", "action_log", "alive", "rng")
_AG_LOG = ("action_by_hour", "goal_by_day", "goal_history")
_AG_STRUCT = ("world",)

_W_EXEC = ("food", "objects", "p", "weather", "rng", "storm_damage",
           "gate_S", "agent")          # 后两项来自 GatedWorld（agent 是引用，单独处理）
_W_LOG = ("events",)

_L_EXEC = ("inf_rng",)
_L_STRUCT = ("agent", "world", "influences")


def audit_fields(life):
    """★ 完整性断言 ★ 任何未被分类的字段都会让它失败。

    v3 已冻结，但**这条断言防的是"我漏看了一个字段"**，
    而不只是"以后 v3 变了"。第一版就漏了 memories 内容与 goal_satiation。
    """
    known = {
        "agent": set(_AG_EXEC) | set(_AG_LOG) | set(_AG_STRUCT),
        "world": set(_W_EXEC) | set(_W_LOG),
        "life": set(_L_EXEC) | set(_L_STRUCT),
    }
    for name, obj in (("agent", life.agent), ("world", life.world), ("life", life)):
        unknown = set(vars(obj)) - known[name]
        if unknown:
            raise AssertionError(
                f"✗ {name} 出现未分类字段 {sorted(unknown)} —— "
                f"必须先判定它是否会被回读（EXEC）再决定入不入 hash。")


def _norm(v):
    """把值规范成可确定性 pickle 的形式"""
    import random as _r
    from collections import Counter
    if isinstance(v, _r.Random):
        return ("rngstate", v.getstate())
    if isinstance(v, (set, frozenset)):
        return ("set", sorted(map(repr, v)))
    if isinstance(v, Counter):
        return ("counter", sorted(v.items()))
    if isinstance(v, dict):
        return ("dict", sorted((k, _norm(x)) for k, x in v.items()))
    if isinstance(v, (list, tuple)):
        return ("seq", [_norm(x) for x in v])
    return v


def exec_state(life):
    """**可执行**状态（EXEC）—— 全拉平阴性对照用这个。
    只含会被回读、从而能影响未来行为的字段。"""
    audit_fields(life)
    ag, w = life.agent, life.world
    st = {f"ag.{k}": _norm(getattr(ag, k)) for k in _AG_EXEC if hasattr(ag, k)}
    st.update({f"w.{k}": _norm(getattr(w, k))
               for k in _W_EXEC if hasattr(w, k) and k != "agent"})
    st["life.inf_rng"] = _norm(life.inf_rng)
    return st


def full_state(life):
    """EXEC + LOG —— 分叉隔离 / 确定性测试用这个（更严格）。"""
    st = exec_state(life)
    ag, w = life.agent, life.world
    st.update({f"ag.{k}": _norm(getattr(ag, k)) for k in _AG_LOG if hasattr(ag, k)})
    st.update({f"w.{k}": _norm(getattr(w, k)) for k in _W_LOG if hasattr(w, k)})
    return st


def _h(d):
    return hashlib.sha256(pickle.dumps(sorted(d.items()), protocol=4)).hexdigest()


def exec_hash(life):
    return _h(exec_state(life))


def full_hash(life):
    return _h(full_state(life))


# ------------------------------------------------- 规则 61：sibling 分叉
def fork(life, floor_off):
    """从同一 snapshot 分叉出一个**完全隔离**的兄弟分支。

    ⚠ 024 的 deepcopy 陷阱：`FrozenZero` 是 dict 子类且 `__setitem__` 是 no-op，
      deepcopy 重建它时正走 `__setitem__` → 复制出**空 dict** → KeyError。
      它不携带状态（读恒 0、写恒丢），重建等价。
    """
    clone = copy.deepcopy(life)
    if floor_off:
        clone.agent.trait_floor = PA.FrozenZero()
        clone.agent.trait_identity = PA.FrozenZero()
    return clone


def run_window(life, day0, days, world=None, extra_inf=()):
    """跑一段窗口，返回 (是否活着, 该窗口内的 [24 小时 × 动作] 计数)"""
    from collections import Counter
    ag = life.agent
    if world is not None:
        life.world = world
        ag.world = world
        if isinstance(world, GatedWorld):
            world.agent = ag                    # 绑定：shelter 在调用时刻读取
    snap = [Counter(c) for c in ag.action_by_hour]
    infl = list(life.influences) + list(extra_inf)
    for day in range(day0, day0 + days):
        for t in range(sim.TICKS_PER_DAY):
            life.world.tick(day, t)
            for inf in infl:
                inf(life.world, ag, day, t, life.inf_rng)
            ag.tick(day, t)
            if not ag.alive:
                return False, [Counter(c) - snap[h]
                               for h, c in enumerate(ag.action_by_hour)]
        ag.daily(day)
    return True, [Counter(c) - snap[h] for h, c in enumerate(ag.action_by_hour)]


# ---------------------------------------------------------------- 自检
def _test_gate_non_destructive():
    """规则 60：门关着时库存必须照常 regen、不被烧掉"""
    w = GatedWorld(1, gate_S=60.0, **scenarios.WORLDS[COMMON])

    class Stub:
        shelter = 0.0
    w.agent = Stub()
    import random
    rng = random.Random(0)
    before = w.food
    got = [w.take_food(rng) for _ in range(50)]
    assert all(g == 0 for g in got), "门关着却取到了食物"
    assert w.food == before, f"门关着库存被改动：{before} → {w.food}"
    for d in range(3):
        for t in range(sim.TICKS_PER_DAY):
            w.tick(d, t)
    assert w.food >= before, "库存没有照常 regen"
    w.agent.shelter = 99.0
    assert sum(w.take_food(rng) for _ in range(10)) > 0, "门开了却取不到食物"
    print("  ✓ 规则 60：门关闭不烧库存、regen 正常、开门可取")


def _test_sibling_isolation():
    """规则 61：突变测试 —— 改一支必须不影响另一支（正反各一次）"""
    life = scenarios.make(20000, WB)
    run_window(life, 0, 3)
    level_state(life.agent)
    h0 = full_hash(life)

    f, n = fork(life, False), fork(life, False)
    assert full_hash(f) == h0 and full_hash(n) == h0, "分叉瞬间状态就不一致"

    hn = full_hash(n)
    f.agent.inventory["food"] += 99
    f.agent.traits["caution"] = 3.0
    f.agent.memories.append({"day": 999, "text": "突变"})     # ★内容级★
    f.agent.goal_satiation["stock_food"] = 999
    f.agent.action_log["explore"] += 7
    f.world.food = 0.0
    f.world.p["food_regen"] = 99.0
    f.agent.rng.random()
    assert full_hash(n) == hn, "✗ 改 clone F 影响了 clone N —— 分支未隔离"

    hf = full_hash(f)
    n.agent.inventory["material"] += 42
    n.agent.trait_floor["industry"] = 88.0
    n.agent.memories.append({"day": 998, "text": "反向突变"})
    n.agent.rng.random()
    assert full_hash(f) == hf, "✗ 改 clone N 影响了 clone F —— 分支未隔离"
    print("  ✓ 规则 61：sibling 突变测试双向通过（含 memories 内容 / goal_satiation / action_log / world.p）")


def _test_identical_branches():
    """完整可执行状态相同 → 放进同一个世界必须【逐位】相同"""
    life = scenarios.make(20001, WA)
    run_window(life, 0, 5)
    level_state(life.agent)
    a, b = fork(life, False), fork(life, False)
    wa_ = sim.World(20001, **scenarios.WORLDS[COMMON])
    wb_ = sim.World(20001, **scenarios.WORLDS[COMMON])
    ra = run_window(a, 5, 7, world=wa_)
    rb = run_window(b, 5, 7, world=wb_)
    assert ra[0] == rb[0] and ra[1] == rb[1], "✗ 同态双分支不逐位相同 —— 有泄漏"
    assert full_hash(a) == full_hash(b), "✗ 末态 hash 不同 —— 有泄漏"
    print("  ✓ 阴性对照：完整状态相同 → 逐位相同")


def _test_floor_off_fork():
    """024 的 FrozenZero deepcopy 陷阱不能复发"""
    scenarios.make = PA.patched_make(False, True)
    try:
        life = scenarios.make(20002, WB)
        run_window(life, 0, 3)
        level_state(life.agent)
        c = fork(life, True)
        run_window(c, 3, 3, world=sim.World(20002, **scenarios.WORLDS[COMMON]))
    finally:
        scenarios.make = PA._orig_make
    print("  ✓ 地板全关下分叉不触发 FrozenZero 的 deepcopy 陷阱")


def _test_field_audit():
    """规则 63：字段完整性断言必须真的会因为新字段而失败"""
    life = scenarios.make(20004, WA)
    run_window(life, 0, 2)
    audit_fields(life)                       # 正常情况必须通过
    life.agent.some_new_field = 1
    try:
        audit_fields(life)
    except AssertionError as e:
        assert "some_new_field" in str(e)
    else:
        raise AssertionError("✗ 完整性断言没有捕获新字段")
    del life.agent.some_new_field
    # memories 内容变化必须改变 hash（第一版的漏洞）
    h = exec_hash(life)
    life.agent.memories.append({"day": 1, "text": "x"})
    assert exec_hash(life) != h, "✗ memories 内容变化没有改变 hash"
    life.agent.memories.pop()
    assert exec_hash(life) == h
    # goal_satiation 同理
    life.agent.goal_satiation["learn"] = 12345
    assert exec_hash(life) != h, "✗ goal_satiation 变化没有改变 hash"
    print("  ✓ 规则 63：字段审计断言有效，memories 内容 / goal_satiation 都进 hash")


def _test_salt_flat():
    """Probe B：耦合确实生效，且 λ=0 时与无耦合逐位相同"""
    def run(lam):
        life = scenarios.make(20003, WB)
        run_window(life, 0, 3)
        level_state(life.agent)
        c = fork(life, False)
        w = sim.World(20003, **scenarios.WORLDS[COMMON])
        inf = (salt_flat(lam),) if lam else ()
        return run_window(c, 3, 10, world=w, extra_inf=inf), c

    (a0, _), c0 = run(0.0)
    (a1, _), c1 = run(0.0)
    assert full_hash(c0) == full_hash(c1), "λ=0 两次不一致"
    (_, _), c2 = run(0.5)
    assert full_hash(c0) != full_hash(c2), "λ=0.5 与无耦合竟然相同 —— 耦合没生效"
    print("  ✓ Probe B：λ=0 等价于无耦合，λ>0 确实改变轨迹")


def _test_discovery():
    """Probe A2：α=0 逐位等价于无干预；α>0 确实改变轨迹；且不碰食物经济"""
    def run(tau, alpha):
        life = scenarios.make(20005, WB)
        run_window(life, 0, 5)
        level_state(life.agent)
        c = fork(life, False)
        w = sim.World(20005, **scenarios.WORLDS[COMMON])
        inf = (discovery_gather(tau, alpha),) if alpha else ()
        run_window(c, 5, 12, world=w, extra_inf=inf)
        return c

    a, b = run(12, 0.0), run(12, 0.0)
    assert full_hash(a) == full_hash(b), "α=0 两次不一致"
    c = run(12, 0.0)
    d = run(12, 2.0)
    assert full_hash(c) != full_hash(d), "α=2 与无干预相同 —— 规则没生效"
    # ★规则 65★ 不许碰食物经济
    src = discovery_gather.__doc__ or ""
    import inspect
    body = inspect.getsource(discovery_gather)
    for banned in ("world.food", "hunger", "condition", "FOOD_"):
        assert banned not in body.split('"""')[-1], f"✗ 碰了食物经济：{banned}"
    print("  ✓ Probe A2：α=0 等价无干预，α>0 改变轨迹，且不触碰食物经济")


def _test_probe_c():
    """Probe C：κ=0 逐位等价；κ>0 改变轨迹；ON/OFF 背景同构；下限生效；goal 被清"""
    from collections import Counter

    def run(seed, kappa, clear=True):
        life = scenarios.make(seed, WB)
        run_window(life, 0, 8)
        level_state(life.agent)
        c = fork(life, False)
        enter_novel(c, clear_goal=clear)
        w = novel_world(seed)                       # ★ON/OFF 同一个背景★
        inf = (home_neglect(kappa),) if kappa else ()
        _, win = run_window(c, 8, 15, world=w, extra_inf=inf)
        acc = Counter()
        for h in win:
            acc.update(h)
        return c, acc["explore"]

    # ⚠ 必须挑真的会 explore 的种子 —— 20006 是只纯盖房球（explore=0），
    #   用它测"κ 有没有生效"永远测不出来（第一版就是这么误报的）。
    diffs = 0
    for sd in range(20010, 20030):
        a, ne = run(sd, 0.0)
        if ne == 0:
            continue
        b, _ = run(sd, 0.0)
        assert full_hash(a) == full_hash(b), f"κ=0 两次不一致（seed {sd}）"
        c2, _ = run(sd, 0.5)
        if full_hash(a) != full_hash(c2):
            diffs += 1
    assert diffs >= 3, f"✗ κ=0.5 几乎不改变轨迹（只有 {diffs} 颗种子变化）"

    # 背景同构：ON/OFF 两支都必须 storm_chance=0
    assert novel_world(1).p["storm_chance"] == 0.0, "背景世界没关掉 storm"
    assert SHELTER_FLOOR > 30.0, "下限必须高于 sim.py:792 的睡眠阶跃点 30"

    # ★ 硬下限只能"兜住损耗"，绝不能把已经低于下限的 shelter 抬回去 ★
    class Stub:
        shelter = 12.0
        action_log = Counter({"explore": 5})
    st = Stub()
    inf = home_neglect(3.0)
    inf(None, st, 0, 0, None)
    st.action_log["explore"] += 1
    inf(None, st, 0, 1, None)
    assert st.shelter == 12.0, f"✗ 下限把 shelter 从 12 抬到了 {st.shelter}"

    # goal 清除只清 intention，不动历史结构
    life = scenarios.make(20007, WA)
    run_window(life, 0, 8)
    level_state(life.agent)
    d = fork(life, False)
    before = (dict(d.agent.traits), dict(d.agent.goal_satiation),
              sorted(d.agent.flags), len(d.agent.memories))
    enter_novel(d)
    assert d.agent.goal is None, "goal 没被清"
    after = (dict(d.agent.traits), dict(d.agent.goal_satiation),
             sorted(d.agent.flags), len(d.agent.memories))
    assert before == after, "✗ 清 goal 时误伤了历史结构"
    print("  ✓ Probe C：κ=0 等价 OFF、κ>0 生效、背景同构、下限兜住、只清 intention")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"机制层自检   模型来自 {os.path.dirname(sim.__file__)}   "
          f"{sim.MODEL_VERSION}  COND_RECOVER_AT={sim.COND_RECOVER_AT}")
    _test_gate_non_destructive()
    _test_sibling_isolation()
    _test_identical_branches()
    _test_floor_off_fork()
    _test_field_audit()
    _test_salt_flat()
    _test_discovery()
    _test_probe_c()
    print("\n全部通过。机制层可用于 group-blind 校准。")
