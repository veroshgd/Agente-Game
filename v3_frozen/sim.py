"""
AI SANDBOX — Life Engine（核心模型）
=====================================

纯代码，零 LLM，零依赖。

★ v2 的核心变化：**这个文件里没有"用户"这个概念。**

以前是：
    User type → Feeding → Personality

现在是：
    World → Experience → Memory → Personality → Behavior

Agent 只知道自己身处一个世界，世界里有资源、天气、物件。
"谁在投喂""投喂得勤不勤"是**实验脚本**的事，见 scenarios.py。
Life Engine 本身不知道用户是什么。

这不是洁癖。核心卖点不是"用户怎么养 → NPC 怎么长"，
而是"用户像上帝一样改变世界，生命根据环境自己长成不同的样子"。
模型里留着 USER_ARCHETYPES，就会一直把实验拉回投喂频率上。

分成三层：

    Agent               World              Influence
    ├─ personality      ├─ resources       ├─ give_food
    ├─ needs            ├─ weather         ├─ add_book
    ├─ memory           ├─ objects         ├─ play_music
    ├─ goals            └─ events          └─ change_environment
    └─ history

⚠ 兼容性：v2 重排了随机数的消费顺序（世界和个体现在是两条独立的流），
   所以数值结果与实验 011–017 不能直接比较。分界线记在实验 018。

★ v3（2026-08-15）：体质稳定性修正 —— 只改了一个数 ★
------------------------------------------------------
    COND_RECOVER_AT   30.0 → 65.0

其余参数、其余机制**逐位不变**。v2 完整快照在 `v2_frozen/`。

> Experiments 011–022 were conducted under model v2 and are retained as
> development history rather than overwritten by subsequent model correction.

为什么是 65（记录 3h 节 / 规则 46、47、49）：
  规则 46/47  v2 的体质只有单向漏，移植后 90–98% 的 tick 待在死区，
              第 30 天后**没有任何球有正收支** —— 结构上不存在稳态，
              120 天死亡率 40.7%（地板全关），污染了所有长时程结论。
  规则 49     但抬阈值不是单调有效的。存在一个【怠惰谷】：
                  抬阈值 → 体质↑ → survival urgency↓（见 score() 的 urgency）
                        → 富养 agent 减少觅食 → 饥饿反升 → 死亡率**上升**
              实测丰富世界 24.3% →(T=55) 36.3% →(T=60) 18.0% →(T=65) 2.0%。
              贫瘠世界养出来的球有 hardship 棘轮撑着勤劳地板，扛得住怠惰；
              富养的球没有这个刹车。
              **65 是越过怠惰谷之后的第一个整十值** —— 不是扫出来的最优点。
  余量方向    危险的是**下调**（掉回谷里），上调是安全的。
"""

import math
import random
from collections import Counter

# ============================================================
# 版本标记 —— 所有 CSV / 原始结果都要带上这个
# ============================================================
MODEL_VERSION = "v3"       # v3 = condition-stability correction (2026-08-15)

# ============================================================
# 参数
# ============================================================

PERSONALITY_WEIGHT = 30.0  # 性格对行动打分的影响强度。★核心旋钮★
                           #   太小 → 所有球行为一样 → 趋同
                           #   太大 → 球无视饥饿而饿死 → 变成漫画角色
TRAIT_DRIFT        = 1.20  # 每次行动对性格的推动幅度（正反馈的增益）
TRAIT_SATURATION   = 0.90  # 性格越极端，越难继续极端化（0 = 关掉）
# ★为什么需要★ 正反馈本身没有刹车：探索 → 好奇↑谨慎↓ → 更想探索。
# v1 里永久 trait_floor 恰好当了刹车；v2 让地板会消退（笔记 ⑤），刹车就没了，
# 于是 60 天有一批球漂到 谨慎 8 / 好奇 100，只顾探索、饿死。
# 这一项也顺手治了实验 017 的天花板问题（60 天 78% 的球 caution 顶到 100）。
LANDMARK_BONUS     = 25.0  # 关键经历带来的行动加成
HUNGER_RATE        = 2.2   # 每 tick 饥饿增长

FOOD_NUTRITION     = 20.0  # 一份食物能压下多少饥饿
                           # 一次采集 ≠ 一天口粮，否则球完全自给自足

# 探索的产出。★不受资源上限约束的行为会变成无限龙头★（实验 013 的教训）
EXPLORE_FOOD_CHANCE = 0.28
EXPLORE_FOOD_YIELD  = 0.5

TICKS_PER_DAY = 24
SIM_DAYS      = 30

TRAITS = ["caution", "curiosity", "industry"]   # 谨慎 / 好奇 / 勤劳

INITIAL_TRAIT_SPREAD = 6.0   # 出生时性格的随机偏移（±）
# ★规则 12★ 正反馈放大的是最先进入循环的差异。种子第 0 天就进去了，
# 环境的影响要几天才见效 → 这个数字是环境信号的竞争对手，不是"多样性旋钮"。

# --- 受苦 → 性格 的连续传导（实验 013）---
HARDSHIP_SCALE     = 1.5   # 饱和曲线时间常数（体质完全归零的天数当量）
HARDSHIP_MAX_BOOST = 22.0  # 饱和时性格地板最多抬多高
HARDSHIP_FLOOR_WEIGHT = {"industry": 1.0, "curiosity": 0.27}
HARDSHIP_STORY_AT  = 0.5   # 累积到这里记一笔关键经历（叙事用）

# --- ★性格的时间结构★（笔记 ⑤：快形成，慢消退）-----------------
# 以前：关键经历 → trait_floor → 永远回不去。作为实验很好证明，
#       但真实的人格不是这样，它更像"快形成，慢消退"：
#           暴雨让 caution +15，之后半年风平浪静 → +15→+13→+11→+9
#       只有真正重大的 landmark 才留下永久 bias。
#
#   short-term adaptation → medium-term habit → long-term personality
#                                                   → landmark identity
#
# 实现：两层地板。soft 会慢慢往下退，perm 不退，soft 永远不低于 perm。
FLOOR_DECAY_PER_DAY  = 0.35   # 软地板每天消退多少
LANDMARK_PERMANENT   = 0.40   # landmark 抬升里有多少比例变成永久 bias
HARDSHIP_FORGET      = 0.015  # 吃饱穿暖时，受苦记忆每天淡忘多少


def clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


# ============================================================
# World —— 世界。Agent 生活在里面，但不知道"用户"是什么
# ============================================================

WORLD_DEFAULTS = {
    "food_regen":       2.4,   # 每天再生几份食物（需求 ≈ 2.64 → 天然赤字）
    "food_cap":         6.0,
    "material_yield":   1.0,   # 采集一次拿到几份材料
    "storm_chance":     0.04,  # 每天暴雨概率
    "storm_damage":     (10.0, 40.0),
    "season_days":      12,    # 丰季/荒季周期
    "season_amplitude": 0.55,  # ★产生梯度的是波动，不是平均值★（规则 4）
    "objects":          (),    # 世界里有什么：{"book", "music"}
}


class World:
    """资源、天气、物件、事件。

    注意 `objects`：世界里有没有书、有没有音乐，是**环境**属性，
    不是 Agent 的属性。同一个 Agent 放进不同的世界，会长成不同的样子——
    这正是我们要验证的东西。
    """

    def __init__(self, seed=0, **params):
        self.rng = random.Random(seed)
        self.p = dict(WORLD_DEFAULTS)
        unknown = set(params) - set(WORLD_DEFAULTS)
        if unknown:
            raise ValueError(f"未知的世界参数: {sorted(unknown)}")
        self.p.update(params)
        self.objects = set(self.p["objects"])
        self.food = self.p["food_cap"]
        self.events = []          # 世界层面发生过什么（不是 agent 的记忆）
        self.weather = "clear"

    def season_multiplier(self, day):
        """丰季 ~1.5×，荒季 ~0.45×。全世界共享（是世界，不是个人运气）"""
        return 1.0 + self.p["season_amplitude"] * math.sin(
            2 * math.pi * day / self.p["season_days"])

    def has(self, obj):
        return obj in self.objects

    def tick(self, day, tick_of_day):
        """世界自己的演化：资源再生 + 天气"""
        self.food = min(self.p["food_cap"],
                        self.food + self.p["food_regen"]
                        * self.season_multiplier(day) / TICKS_PER_DAY)

        self.weather = "clear"
        if tick_of_day == 3 and self.rng.random() < self.p["storm_chance"]:
            lo, hi = self.p["storm_damage"]
            self.weather = "storm"
            self.storm_damage = self.rng.uniform(lo, hi)
            self.events.append((day, "storm"))

    def take_food(self, rng):
        """Agent 来采集。采空了就没有了 —— 这个上限是环境给的，不是个体给的"""
        if self.food >= 1 and rng.random() < 0.85:
            self.food -= 1
            return 1
        return 0


# ============================================================
# Influence —— 外部干预（用户/上帝）
# ============================================================
#
# ★关键设计★ Agent 不知道这些东西是"用户"做的。
# 从 Agent 的角度看，只是"世界里突然多了食物/多了一本书"。
# 每个 influence 是一个 (world, agent, day, tick, rng) -> None 的函数。

def give_food(amount=2.0, every_days=3.0, at_tick=8):
    """定期投喂。every_days 越大 = 越少来看它。"""
    def apply(world, agent, day, tick, rng):
        if tick == at_tick and rng.random() < 1.0 / every_days:
            agent.receive("food", amount, day, "有人给了我食物")
    return apply


def add_book(day=0, at_tick=9):
    """某一天往世界里放一本书。之后 read 这个行为才合法。"""
    def apply(world, agent, day_now, tick, rng):
        if day_now == day and tick == at_tick and not world.has("book"):
            world.objects.add("book")
            world.events.append((day_now, "book_appeared"))
            agent.remember(day_now, "世界里出现了一本书", tags=("book", "new"),
                           importance=0.5)
    return apply


def play_music(from_day=0):
    """从某天起世界里一直有音乐。被动影响：休息效率更好、更安定。"""
    def apply(world, agent, day_now, tick, rng):
        if day_now >= from_day and not world.has("music"):
            world.objects.add("music")
            world.events.append((day_now, "music_started"))
            agent.remember(day_now, "开始有音乐了", tags=("music", "new"),
                           importance=0.4)
    return apply


def change_environment(day, **new_params):
    """某一天改变世界的物理参数（食物变少、常下雨……）"""
    def apply(world, agent, day_now, tick, rng):
        if day_now == day and tick == 0:
            world.p.update(new_params)
            world.events.append((day_now, f"environment_changed:{new_params}"))
    return apply


def give_object(obj, day=0, at_tick=9):
    """给世界加一个任意物件"""
    def apply(world, agent, day_now, tick, rng):
        if day_now == day and tick == at_tick:
            world.objects.add(obj)
            world.events.append((day_now, f"object:{obj}"))
    return apply


# ============================================================
# 行为定义
# ============================================================

# 每个行为"符合"哪些性格 —— 打分时用
ACTION_TRAIT_MATCH = {
    "eat":            {},
    "sleep":          {"caution":  0.5},
    "gather_food":    {"industry": 1.0, "caution":  0.4},
    # 实验 016/017：只挂 industry 会导致"照顾它反而害它"（industry 只靠饥饿
    # 棘轮上涨 → 被喂饱的球从不收集材料 → 永远没有家）。加 caution 修方向，
    # 但权重 1.2 会让 60 天团灭（材料吃掉 30% 行动预算），退到 0.6。
    "gather_material":{"industry": 1.0, "caution": 0.6},
    "build":          {"caution":  1.0, "industry": 0.6},
    "explore":        {"curiosity": 1.2, "caution": -1.0},
    "read":           {"curiosity": 1.0, "caution": 0.2},   # 需要世界里有书
}

# 做了这件事 → 强化促使你做这件事的性格。★这就是正反馈循环★
ACTION_TRAIT_FEEDBACK = {
    "eat":            {},
    "sleep":          {"caution":  0.05},
    "gather_food":    {"industry": 0.10, "caution":   0.05},
    "gather_material":{"industry": 0.12},
    "build":          {"caution":  0.15, "industry":  0.08},
    "explore":        {"curiosity": 0.20, "caution": -0.10},
    "read":           {"curiosity": 0.16},
}

# 有些行为需要世界里有对应的物件才合法 —— 环境决定了"能做什么"，
# 而不只是"做同一件事的收益不同"。这是环境影响个体最硬的一条通路。
ACTION_REQUIRES_OBJECT = {"read": "book"}

ACTIONS = list(ACTION_TRAIT_MATCH)


# ============================================================
# Goal —— 从"反应式代理"到"自主生命"
# ============================================================
#
# 以前的循环是：
#     tick → 给所有 action 打分 → 选最高 → 执行
# 这是一个很好的 **Reactive Agent**，但不是生命。用户看到的是
#     "这个 tick 恰好 build 分最高"
# 而我们想要的是
#     "它这几天正在盖自己的家"。
#
# 差别就在**跨 tick 的意图连续性**。Goal 是这样一个跨 tick 的东西：
# 它由状态和记忆生成，持续存在，偏置行动打分，有进度，会完成。
#
# ★关键是迟滞（GOAL_SWITCH_MARGIN）★
# 没有迟滞，goal 每天都会被当天最紧急的需求顶掉 —— 那它就只是需求的
# 另一个名字，什么都没改变。有了迟滞，它才会"坚持做完一件事"。

GOAL_ACTIONS = {
    "improve_home":  {"gather_material": 1.0, "build": 1.4},
    "stock_food":    {"gather_food": 1.2, "explore": 0.3},
    "see_the_world": {"explore": 1.4},
    "learn":         {"read": 1.4},
    "recover":       {"sleep": 1.0, "eat": 0.6},
}

GOAL_LABEL = {
    "improve_home":  "把家弄得更结实",
    "stock_food":    "多存点吃的",
    "see_the_world": "去远处看看",
    "learn":         "多读一点",
    "recover":       "把身体养回来",
}

GOAL_BONUS         = 32.0   # 目标对行动打分的最大加成
GOAL_OFF_TASK      = 14.0   # 与当前意图无关的【消遣类】行动会被压低 = 专注
# ★为什么必须有 OFF_TASK★ 只给目标行动加分是不够的：一只已经漂到
# 好奇 90 / 谨慎 25 的球，explore 的性格加成就有 +44，光靠 +22 的目标加成
# 盖不住 —— 实测它会连着 13 天"想修房子"却一直在外面跑，房子烂到 0。
# 专注不只是"更想做 A"，还包括"暂时没那么想做 B"。
DISCRETIONARY = ("explore", "read")   # 消遣类。生存类行动永远不压
GOAL_SWITCH_MARGIN = 0.25   # 新目标要高出这么多才值得换 —— 这就是"专注"
GOAL_MIN_DAYS      = 2      # 一个目标至少坚持这么多天（除非已完成）
GOAL_REFRACTORY    = 6      # 刚做完一件事，这么多天内不会立刻again
GOAL_STALL_DAYS    = 4      # 连着这么多天毫无进展 → 放弃
GOAL_SLACK_FOOD    = 4.0    # 余裕（规则 27）：存粮到这个数才算"有饭吃"
GOAL_SLACK_COND    = 90.0   # 余裕：体质到这个数才算"身体撑得住"

# ---------------------------------------------------------------------------
# ★实验 022★ 语义记忆接进决策
# ---------------------------------------------------------------------------
# 规则 30/31：`knowledge` 此前只写不读，`score()` 从来没读过它 —— 语义记忆
# 是装饰品。实验 021 第 3 节的后果：关掉性状地板后移植比值只剩 1.044
# （CI 含 1.0），"你不是发现了不可逆性，你是把不可逆性写进去了"答不上来。
#
# 预注册见 [[实验022 预注册 —— 记忆接入决策]]。三条预测在改代码前已冻结。
#
# ⚠ 全部设为 0 时，行为必须和实验 021 逐位一致（回归检查 test_022_regression.py）。
KNOWLEDGE_WEIGHT      = 12.0   # 一条知识对动作打分的加成（参照 LANDMARK_BONUS = 25）
KNOWLEDGE_GOAL_WEIGHT = 0.25   # 对目标优先级的加成（参照 flags 的 +0.35）
KNOWLEDGE_FORGET      = 0.02   # 每天衰减；执行对应动作就回满（用进废退）

# knowledge key → 受影响的动作 / 目标。四个 key 都是 landmark() 写出来的，
# 映射是现成的语义，不是编出来的。
KNOWLEDGE_ACTIONS = {
    "far_places": ("explore",),                  # 远处有食物更多的地方
    "books":      ("read",),                     # 书里有我没见过的世界
    "shelter":    ("build", "gather_material"),  # 没有坚固的住所，下雨很危险
    "food":       ("gather_food",),              # 存粮见底的日子很难熬
}
KNOWLEDGE_GOALS = {
    "far_places": "see_the_world",
    "books":      "learn",
    "shelter":    "improve_home",
    "food":       "stock_food",
}
# 消遣类目标 —— 它们的知识加成必须过 slack 门（规则 27），否则饿着肚子
# 也要往远处跑。第一版漏了这个，移植档死亡率 4.0% → 39.3%。
DISCRETIONARY_GOALS = ("see_the_world", "learn")

# ---------------------------------------------------------------------------
# ★规则 43★ 睡眠死亡螺旋的三种候选改法（默认全关 = 现状，逐位一致）
# ---------------------------------------------------------------------------
# 诊断（mortality_diagnose.py）：死者体质 0、饥饿 74–87、死前 10 天睡眠占
# 53–56%，而 62–79% 死时正在追求 stock_food ——「不是没想找吃的，是没时间醒着」。
# 体质↓ → 睡眠效率↓（0.35 下限）→ 睡更久 → 采不到 → 更饿 → 体质更↓。
# ---------------------------------------------------------------------------
# ★规则 47★ 体质收支 —— 恢复通道在移植后完全关闭，系统没有稳态
# ---------------------------------------------------------------------------
# 实测（3f 节）：移植后 90–98% 的 tick 待在「饿 30–70」的死区，什么都不发生；
# 「饿<30」占比塌到 0–2%，+0.16 那条恢复通道几乎从不触发。
# 第 30 天之后没有任何球有正收支，最健康的幸存者也是 −0.12/天。
# ★ v3 起 COND_RECOVER_AT 默认 65.0 ★ 其余三个仍默认关闭（= v2 行为）。
# 要复现 v2：设 COND_RECOVER_AT = 30.0，或直接跑 v2_frozen/。
COND_DRAIN_AT        = 70.0  # 饥饿超过这里开始掏空身体
COND_DRAIN           = 0.40  # 每 tick 扣多少
COND_RECOVER_AT      = 65.0  # v3: condition-stability correction（v2 是 30.0）
                             # 抬高 = 削掉死区。为什么是 65：见文件头 v3 说明 +
                             # 记录 3h 节规则 49（怠惰谷）。★下调有风险，上调安全★
COND_RECOVER         = 0.16  # 每 tick 补多少
COND_DEADZONE_RECOVER = 0.0  # 修法②：死区里也缓慢恢复
COND_SHELTER_RECOVER = 0.0   # 修法③：住所也贡献体质（× shelter/100）

HUNGER_CRISIS        = 70.0  # 超过这个饥饿度算"命悬一线"，A/B 共用
SLEEP_SUPPRESS       = 0.0   # 改法A：危机时压制睡眠意图（1.0 = 饥饿100时压到0）
HUNGER_URGENCY       = 0.0   # 改法B：危机时抬高 eat / gather_food 的急迫度
SLEEP_EFF_FLOOR      = 0.35  # 改法C：睡眠效率下限（现状 0.35，抬高则螺旋变缓）


def hunger_crisis(hunger):
    """0 → 不饿；1 → 饿到极限。A/B 共用的危机强度。"""
    if hunger <= HUNGER_CRISIS:
        return 0.0
    return min(1.0, (hunger - HUNGER_CRISIS) / (100.0 - HUNGER_CRISIS))
# ★为什么要有停滞放弃★ 一只已经漂到好奇 100 / 谨慎 18 的球，
# 性格上根本不会去收集材料。但不应期会把"修房子"顶上来，于是出现
# **连着 8 天"想修房子"却一根木头都没捡** —— 意图和行为脱节，
# 那这个 goal 层就白加了。人也一样："我一直想修屋顶，但一直没修"，
# 那个念头最终会自己消失。
# ★为什么需要不应期★ 没有它，"去远处看看"完成之后当天就会重新立一次
# （因为好奇心还是最高的），球会连续 27 天只做这一件事，房子永远是 0。
# 现实里"刚做完一件事会暂时满足"，这就是那个满足感。
# 而且探索会压低 caution → 更想探索 → 正反馈锁死。不应期是打断锁死的闸。


# ============================================================
# Agent
# ============================================================

class Agent:
    """一个个体。它只认识：自己的状态、自己的记忆、以及它所处的世界。"""

    def __init__(self, seed, world):
        self.rng = random.Random(seed)
        self.world = world

        # 差异来源 #1：初始随机种子。作用是"打破对称"，不是制造差异本身
        self.traits = {t: 50.0 + self.rng.uniform(-INITIAL_TRAIT_SPREAD,
                                                  INITIAL_TRAIT_SPREAD)
                       for t in TRAITS}

        # 状态（不是记忆，就是数据库的一行，别喂给 LLM）
        self.hunger  = 30.0    # 100 = 饿死边缘
        self.energy  = 80.0
        self.shelter = 0.0
        self.inventory = {"food": 2.0, "material": 0.0}

        # ★体质★ 给"失败"一个比死亡轻的等级（实验 006）
        self.condition = 100.0

        # ★受苦累积★ 连续量，取代二值开关（实验 013）
        self.hardship = 0.0
        self._hardship_anchor = None

        # ★性格的两层地板★（笔记 ⑤）soft 会慢慢消退，perm 不会
        self.trait_floor = {t: 0.0 for t in TRAITS}       # 软地板（会消退）
        self.trait_identity = {t: 0.0 for t in TRAITS}    # landmark identity

        self.flags = set()
        self.memories = []        # 见 remember()
        self.knowledge = {}       # 语义记忆：对世界的一般性认识
        # ★022★ 每条知识的强度 ∈ (0,1]，与 knowledge 同生共死。
        # 单独存而不是把 knowledge 改成 (text, strength)，是为了不破坏
        # context_packet / environment.py / persistence.py 里现有的读法。
        self.knowledge_strength = {}

        # ★意图★ 跨 tick 存在的东西。见 GOAL_ACTIONS 上面那段说明。
        self.goal = None            # {type, priority, created_from, created_day, progress}
        self.goal_history = []      # 完成/放弃过的目标，用来讲"它这几天在干嘛"
        self.goal_by_day = []       # 每天在追求什么（demo 素材）
        self.goal_satiation = {}    # 目标类型 → 上次完成的日子（不应期）

        self.action_log = Counter()
        self.action_by_hour = [Counter() for _ in range(TICKS_PER_DAY)]
        self.alive = True

    # ---------- 记忆 ----------

    def remember(self, day, text, *, event=None, tags=(), importance=0.5,
                 emotional_weight=0.0, consequence=None, related_traits=()):
        """★情节记忆（Episodic）★ 具体的一件事，带时间。

        以前是 `flags: set` + `landmarks: [(day, text)]`。作为第一版够用，
        但那个结构里没有"这件事有多重要""它导致了什么""它和哪个性格有关"，
        所以既没法做检索，也没法喂给 LLM。
        """
        self.memories.append({
            "event": event or (tags[0] if tags else "episode"),
            "day": day, "text": text, "tags": tuple(tags),
            "importance": importance, "emotional_weight": emotional_weight,
            "consequence": consequence, "related_traits": tuple(related_traits),
        })

    def learn(self, key, text):
        """★语义记忆（Semantic）★ 从经历里抽出来的一般性认识，不带时间。

            情节：第 12 天下暴雨，屋顶坏了
            语义：没有坚固的住所，下雨很危险

        分开存的理由：情节记忆无限增长，需要遗忘机制；语义记忆几十条封顶，
        而且是行为真正该依赖的东西。
        """
        self.knowledge[key] = text
        self.knowledge_strength[key] = 1.0      # ★022★ 学到/重温 → 回满

    def know(self, key):
        """★022★ 这条知识现在有多强。没学过或已遗忘 → 0。"""
        return self.knowledge_strength.get(key, 0.0)

    def forget_knowledge(self):
        """★022★ 用进废退：每天衰减，掉到 0 就整条删掉。

        这一步是实验 022 的重点：它把"有没有 hardcode 不可逆性"从一个
        二元指控变成**一个可测参数** —— 可以扫遗忘率画曲线，
        顺带堵掉"你的 knowledge 永不遗忘，还是写死的"这句反驳。
        """
        if not KNOWLEDGE_FORGET:
            return
        for key in list(self.knowledge_strength):
            self.knowledge_strength[key] -= KNOWLEDGE_FORGET
            if self.knowledge_strength[key] <= 0.0:
                del self.knowledge_strength[key]
                self.knowledge.pop(key, None)

    def recall(self, tags=(), k=5, day=None, recent_days=7):
        """按【结构化标签】检索，不用向量相似度。

        为什么不用向量（[[设计要点与风险]] §3.4）：
        这里没有 query，只有一个持续的状态；语义相似度会把历史上每一次
        饥饿都捞出来，而不是那次*有意义*的。Generative Agents 最常见的
        失败就是检索错误（Tom 记得"要在派对上聊选举"却不记得派对存在）。

        规则：标签命中 + 重要性 + 最近 —— 便宜、快、确定、可调试。
        """
        want = set(tags)
        scored = []
        for m in self.memories:
            s = m["importance"]
            if want & set(m["tags"]):
                s += 1.0
            if day is not None and day - m["day"] <= recent_days:
                s += 0.4
            s += abs(m["emotional_weight"]) * 0.3
            scored.append((s, m))
        scored.sort(key=lambda x: (-x[0], x[1]["day"]))
        return [m for _, m in scored[:k]]

    def context_packet(self, day):
        """★给 LLM 的那一包东西★

        LLM 不需要读 30 天所有 tick，只需要：
            当前状态 + 当前目标 + 相关记忆 + 世界知识 + 性格
        然后它才能自然地回答"你为什么最近一直在修房子"：
            "前几天下雨的时候屋顶坏了，我不太想再经历一次。"

        注意这里【没有】把 traits 交给 LLM 去改 —— 性格是代码持有的数字，
        LLM 只负责把它说成人话（§四）。
        """
        goal_tags = ()
        if self.goal:
            goal_tags = (self.goal["type"], self.goal["created_from"])
        return {
            "state": {"hunger": round(self.hunger), "energy": round(self.energy),
                      "shelter": round(self.shelter),
                      "condition": round(self.condition),
                      "food": round(self.inventory["food"], 1)},
            "personality": {t: round(v) for t, v in self.traits.items()},
            "goal": None if not self.goal else {
                "type": self.goal["type"],
                "label": GOAL_LABEL[self.goal["type"]],
                "created_from": self.goal["created_from"],
                "days_on_it": day - self.goal["created_day"],
                "progress": round(self.goal["progress"], 2)},
            "memories": self.recall(goal_tags, k=5, day=day),
            "knowledge": dict(self.knowledge),
            "world": {"objects": sorted(self.world.objects),
                      "weather": self.world.weather},
        }

    @property
    def landmarks(self):
        """兼容旧脚本：重要记忆的 (day, text) 列表"""
        return [(m["day"], m["text"]) for m in self.memories
                if m["importance"] >= 0.7]

    def mark(self, day, text, flag, floors, *, emotional_weight=0.8,
             consequence=None, knowledge=None):
        """一段关键经历：记下来 + 在性格上留下痕迹（一部分永久）"""
        if flag in self.flags:
            return
        self.flags.add(flag)
        self.remember(day, text, tags=(flag,), importance=0.9,
                      emotional_weight=emotional_weight,
                      consequence=consequence,
                      related_traits=tuple(floors))
        if knowledge:
            self.learn(*knowledge)
        for t, boost in floors.items():
            base = self.traits[t]
            self.trait_floor[t] = max(self.trait_floor[t],
                                      min(base + boost, 90.0))
            # 只有一部分变成永久身份 —— 其余会慢慢消退
            self.trait_identity[t] = max(
                self.trait_identity[t],
                min(base + boost * LANDMARK_PERMANENT, 90.0))

    def receive(self, what, amount, day, text=None):
        """从外部得到东西。Agent 不知道是谁给的。"""
        self.inventory[what] = self.inventory.get(what, 0.0) + amount
        if text:
            self.remember(day, text, tags=("gift", what), importance=0.35,
                          emotional_weight=0.3)

    @property
    def hardship_norm(self):
        """受苦程度归一化到 0→1 的饱和曲线。中间连续，这是关键。"""
        return 1.0 - math.exp(-self.hardship / HARDSHIP_SCALE)

    # ---------- 目标 ----------

    # 计数型目标：进度要从【立下目标那一刻】起算。
    # ⚠ 第一版直接用累计次数，结果 see_the_world 一立就已经"完成"，
    #   于是每天完成、每天重立，而重立会刷新 created_day →
    #   永远处在 GOAL_MIN_DAYS 保护期内 → 球被锁死在这个目标上活活饿死。
    #   计数型指标必须存基线，这和实验 009 是同一类错误。
    GOAL_COUNT_TARGET = {"learn": ("read", 12), "see_the_world": ("explore", 20)}

    def goal_progress(self, goal):
        gtype = goal["type"] if isinstance(goal, dict) else goal
        if gtype == "improve_home":
            return clamp(self.shelter / 80.0, 0.0, 1.0)
        if gtype == "stock_food":
            return clamp(self.inventory["food"] / 6.0, 0.0, 1.0)
        if gtype == "recover":
            return clamp(self.condition / 95.0, 0.0, 1.0)
        if gtype in self.GOAL_COUNT_TARGET:
            act, target = self.GOAL_COUNT_TARGET[gtype]
            base = goal.get("start", 0) if isinstance(goal, dict) else 0
            return clamp((self.action_log[act] - base) / target, 0.0, 1.0)
        return 0.0

    def _new_goal(self, gtype, pri, src, day):
        g = {"type": gtype, "priority": pri, "created_from": src,
             "created_day": day, "progress": 0.0}
        if gtype in self.GOAL_COUNT_TARGET:
            g["start"] = self.action_log[self.GOAL_COUNT_TARGET[gtype][0]]
        g["progress"] = self.goal_progress(g)
        return g

    def _slack(self):
        """★余裕（规则 27）★ 有饭吃、身体撑得住，才立得起消遣类的志向。"""
        return clamp(self.inventory["food"] / GOAL_SLACK_FOOD, 0.0, 1.0) \
            * clamp(self.condition / GOAL_SLACK_COND, 0.0, 1.0)

    def propose_goals(self, day):
        """目标从【状态 + 记忆 + 性格】里长出来，不是写死的优先级表。

        `created_from` 记的是"这个念头是哪来的"——以后 LLM 要靠它
        回答"你为什么最近一直在修房子"。
        """
        c = (self.traits["caution"] - 50) / 100
        q = (self.traits["curiosity"] - 50) / 100
        out = []

        def add(gtype, pri, src):
            # ★022★ 语义记忆抬高对应目标的优先级。019 第 5 节已证明目标层
            # 是比作息层更强的载体（1.79 vs 0.72），只接 score 大概率浪费。
            #
            # ⚠ 修正（见预注册「实现修正 1」）：第一版把加成直接加在 pri 上，
            #   **绕过了 slack 门** —— 于是"知道远处有食物"变成了在饿肚子时
            #   也要往远处跑，移植档死亡率 4.0% → 39.3%。这正是规则 27 说的
            #   「抑制要作用在意图形成」。消遣类目标的知识加成必须乘 slack。
            if KNOWLEDGE_GOAL_WEIGHT:
                for key, g in KNOWLEDGE_GOALS.items():
                    if g == gtype:
                        bonus = KNOWLEDGE_GOAL_WEIGHT * self.know(key)
                        if gtype in DISCRETIONARY_GOALS:
                            bonus *= self._slack()
                        pri += bonus
            out.append((gtype, pri - self._satiation(gtype, day), src))

        if self.shelter < 75:
            pri = (75 - self.shelter) / 75 * 0.8 + c
            src = "storm_memory" if "fears_storm" in self.flags else "shelter_low"
            if "fears_storm" in self.flags:
                pri += 0.35                      # 被掀过屋顶的球更想修房子
            add("improve_home", pri, src)

        if self.inventory["food"] < 6:
            pri = (6 - self.inventory["food"]) / 6 * 0.7
            pri += self.hardship_norm * 0.6      # 挨过饿的球更想囤粮
            src = "hunger_memory" if self.hardship_norm > 0.3 else "food_low"
            add("stock_food", pri, src)

        # ★消遣类目标要先有余裕才立得起来★
        # goal_bonus 里的抑制是"执行时"的，太晚了：等体质掉到 85 以下，
        # 亏空已经造成。真正的问题是**在没饭吃的时候还立"去远处看看"这个志向**。
        # 实测（90 天）：死掉的球 46% 的时间在探索、2% 在采集，
        # 关掉 goal 层死亡率从 28.5% 掉到 7.0% —— 是这个念头在杀它们。
        slack = self._slack()

        if self.world.has("book"):
            add("learn", (0.35 + q * 1.2) * slack, "book_in_world")

        add("see_the_world", (0.30 + q * 1.4 - c * 0.8) * slack, "curiosity")

        if self.condition < 85:
            add("recover", (85 - self.condition) / 85 * 1.1, "body_weak")

        return out

    def _satiation(self, gtype, day):
        """刚做完的事，暂时没那么想再做一遍。惩罚随时间线性消退。"""
        done = self.goal_satiation.get(gtype)
        if done is None:
            return 0.0
        left = max(0, GOAL_REFRACTORY - (day - done))
        return 0.9 * left / GOAL_REFRACTORY

    def update_goal(self, day):
        """每天早上想一次：还要不要接着做昨天那件事？"""
        cands = self.propose_goals(day)
        if not cands:
            return
        cands.sort(key=lambda x: -x[1])
        best_type, best_pri, best_src = cands[0]

        if self.goal is not None:
            prog = self.goal_progress(self.goal)
            # 有没有在推进？只要涨了就刷新计时
            if prog > self.goal.get("best_progress", -1.0) + 1e-9:
                self.goal["best_progress"] = prog
                self.goal["last_gain_day"] = day
            self.goal["progress"] = prog

            age = day - self.goal["created_day"]
            stalled = day - self.goal.get("last_gain_day", day)
            if prog >= 1.0:
                self._close_goal(day, "done")
            elif stalled >= GOAL_STALL_DAYS:
                self._close_goal(day, "stalled")
            elif age < GOAL_MIN_DAYS:
                return                            # 还在最短坚持期内
            elif best_type != self.goal["type"]:
                # ★迟滞★ 新目标要明显更急才换，否则接着做原来那件
                cur = next((p for t, p, _ in cands if t == self.goal["type"]), 0.0)
                if best_pri < cur + GOAL_SWITCH_MARGIN:
                    return
                self._close_goal(day, "switched")
            else:
                self.goal["priority"] = best_pri
                return

        self.goal = self._new_goal(best_type, best_pri, best_src, day)

    def _close_goal(self, day, why):
        g = dict(self.goal, closed_day=day, outcome=why)
        self.goal_history.append(g)
        if why == "done":
            self.goal_satiation[g["type"]] = day
            self.remember(day, f"终于{GOAL_LABEL[g['type']]}了",
                          tags=("goal", g["type"], "done"),
                          importance=0.7, emotional_weight=0.6,
                          consequence=g["type"])
        elif why == "stalled":
            # 放弃也要冷却一下，否则下一秒又立同一个念头
            self.goal_satiation[g["type"]] = day
            self.remember(day, f"想{GOAL_LABEL[g['type']]}，但一直没做成",
                          tags=("goal", g["type"], "stalled"),
                          importance=0.45, emotional_weight=-0.3,
                          consequence="gave_up")
        self.goal = None

    def goal_bonus(self, action):
        """★意图只在有余裕的时候才说得上话★

        规则（实验 003）："人格需要余裕才能表达"。意图同理，而且更强：
        快饿死的时候没有谁还在想着"去远处看看"。
        没有这个抑制项，goal 会盖过生存需求把球饿死 —— 第一版就是这么死的。
        """
        if self.goal is None:
            return 0.0
        urgency = max((self.hunger - 60) / 40.0, (85 - self.condition) / 85.0, 0.0)
        damp = clamp(1.0 - urgency, 0.0, 1.0)
        pri = clamp(self.goal["priority"], 0.0, 1.5)
        w = GOAL_ACTIONS.get(self.goal["type"], {}).get(action, 0.0)
        if w:
            return w * GOAL_BONUS * pri * damp
        if action in DISCRETIONARY:
            return -GOAL_OFF_TASK * pri * damp      # 分心的代价
        return 0.0

    # ---------- 打分 ----------

    def legal(self, action):
        need = ACTION_REQUIRES_OBJECT.get(action)
        return need is None or self.world.has(need)

    def score(self, action, day):
        if not self.legal(action):
            return None
        s = 0.0

        # 1. 需求紧迫度
        if action == "eat":
            if self.inventory["food"] < 1:
                return None
            s += self.hunger * 1.0
            s += HUNGER_URGENCY * hunger_crisis(self.hunger)        # 改法B
        elif action == "sleep":
            s += (100 - self.energy) * 0.9
            s += 10 if self.shelter > 30 else -5
            if self.world.has("music"):
                s += 4                       # 有音乐更容易安定下来
            # ★改法A（规则 43）★ 快饿死了还在睡 —— 抑制作用在意图形成，
            # 与规则 27 的 slack 门同构。
            if SLEEP_SUPPRESS:
                s *= max(0.0, 1.0 - SLEEP_SUPPRESS * hunger_crisis(self.hunger))
        elif action == "gather_food":
            # 只在真的饿的时候才紧迫（实验 003：那个常数 +12 是趋同的元凶）
            s += max(0.0, self.hunger - 35) * 0.85
            s += HUNGER_URGENCY * hunger_crisis(self.hunger)        # 改法B
            if self.inventory["food"] <= 1:
                s += 20
            if self.world.food < 1:
                return None                  # 附近采空了
        elif action == "gather_material":
            s += (100 - self.shelter) * 0.30
        elif action == "build":
            if self.inventory["material"] < 3:
                return None
            s += (100 - self.shelter) * 0.55
        elif action == "explore":
            s += 18
        elif action == "read":
            s += 12

        # 2. 性格匹配 ★分化引擎在这里★
        for trait, w in ACTION_TRAIT_MATCH[action].items():
            s += (self.traits[trait] - 50) / 50 * w * PERSONALITY_WEIGHT

        # 3. 关键经历的影响
        if action == "gather_food":
            s += LANDMARK_BONUS * self.hardship_norm     # 受过多少苦就多怕饿
        if "fears_storm" in self.flags and action in ("build", "gather_material"):
            s += LANDMARK_BONUS
        if "loves_exploring" in self.flags and action == "explore":
            s += LANDMARK_BONUS

        # 3b. ★语义记忆★（实验 022）与上面的 flags 分支结构平行。
        # 区别：flags 是 0/1 的永久标记，knowledge 带强度、会遗忘。
        if KNOWLEDGE_WEIGHT:
            for key, acts in KNOWLEDGE_ACTIONS.items():
                if action in acts:
                    bonus = KNOWLEDGE_WEIGHT * self.know(key)
                    if action in DISCRETIONARY:      # 规则 27，同 propose_goals
                        bonus *= self._slack()
                    s += bonus

        # 4. ★当前意图★ 这一项让行为跨 tick 连贯起来
        s += self.goal_bonus(action)

        # 5. 成本与风险
        if action in ("gather_food", "gather_material", "explore", "build"):
            s -= (100 - self.energy) * 0.35
        if action == "explore":
            s -= 8

        return s

    # ---------- 执行 ----------

    def act(self, action, day, hour=0):
        self.action_log[action] += 1
        self.action_by_hour[hour][action] += 1

        # ★022★ 用进废退：做了对应的事，这条知识就被重温（只回满已有的，不新建）
        if KNOWLEDGE_FORGET:
            for key, acts in KNOWLEDGE_ACTIONS.items():
                if action in acts and key in self.knowledge_strength:
                    self.knowledge_strength[key] = 1.0

        if action == "eat":
            self.inventory["food"] -= 1
            self.hunger = clamp(self.hunger - FOOD_NUTRITION)
            self.energy = clamp(self.energy + 5)
        elif action == "sleep":
            # 体质差 → 睡再久也恢复不过来 → 能做的事变少 → 行为被塑造
            # 改法C：抬高下限让螺旋变缓（现状 0.35）
            eff = SLEEP_EFF_FLOOR + (1.0 - SLEEP_EFF_FLOOR) * self.condition / 100
            if self.world.has("music"):
                eff *= 1.10
            self.energy = clamp(self.energy + 14 * eff)
        elif action == "gather_food":
            self.inventory["food"] += self.world.take_food(self.rng)
            self.energy = clamp(self.energy - 6)
        elif action == "gather_material":
            self.inventory["material"] += self.world.p["material_yield"]
            self.energy = clamp(self.energy - 6)
        elif action == "build":
            self.inventory["material"] -= 3
            self.shelter = clamp(self.shelter + 22)
            self.energy = clamp(self.energy - 10)
        elif action == "explore":
            self.energy = clamp(self.energy - 9)
            if self.rng.random() < EXPLORE_FOOD_CHANCE:
                self.inventory["food"] += EXPLORE_FOOD_YIELD
                if "loves_exploring" not in self.flags and self.rng.random() < 0.30:
                    self.mark(day, "在远处发现了一片食物丰富的地方",
                              "loves_exploring", {"curiosity": 10},
                              consequence="food_found",
                              knowledge=("far_places", "远处有食物更多的地方"))
        elif action == "read":
            self.energy = clamp(self.energy - 3)
            if "reads" not in self.flags and self.rng.random() < 0.25:
                self.mark(day, "读到了一些以前不知道的事", "reads",
                          {"curiosity": 8}, emotional_weight=0.5,
                          knowledge=("books", "书里有我没见过的世界"))

        # 正反馈：做什么 → 变成什么（但不能跌破关键经历留下的地板）
        # ★边际递减★ 越极端越难继续极端化。没有这一项，探索的
        # `caution -0.10` 会一路把谨慎推到 8、好奇推到 100，球从此只会
        # 在外面跑（实测：60 天死的球 47.7% 的时间在 explore，
        # 只有 1.9% 在采集食物）。v1 靠永久地板挡着，v2 的地板会消退，
        # 于是这个刹车没了 —— 必须换一个。
        for trait, delta in ACTION_TRAIT_FEEDBACK[action].items():
            extremity = abs(self.traits[trait] - 50.0) / 50.0
            pull = max(0.12, 1.0 - extremity * TRAIT_SATURATION)
            v = self.traits[trait] + delta * TRAIT_DRIFT * pull
            self.traits[trait] = clamp(v, self.trait_floor[trait], 100.0)

    # ---------- 每天一次：性格的慢速消退 ----------

    def daily(self, day):
        """★快形成，慢消退★ 软地板往下退，但永远不低于 landmark identity"""
        for t in TRAITS:
            self.trait_floor[t] = max(self.trait_identity[t],
                                      self.trait_floor[t] - FLOOR_DECAY_PER_DAY)
        # 吃饱穿暖的日子里，受苦的记忆也会慢慢淡
        if self.condition >= 99.5 and self.hardship > 0:
            self.hardship = max(0.0, self.hardship - HARDSHIP_FORGET)
        self.forget_knowledge()      # ★022★ 语义记忆也会淡

    # ---------- 一个 tick ----------

    def tick(self, day, tick_of_day):
        if not self.alive:
            return

        # 每天早上想一次要做什么。放在这里（而不是每 tick）就是为了连续性：
        # 一天之内不会因为某个 tick 的分数抖动而改变主意。
        if tick_of_day == 0:
            self.update_goal(day)
            self.goal_by_day.append(self.goal["type"] if self.goal else None)

        self.hunger  = clamp(self.hunger + HUNGER_RATE)
        self.energy  = clamp(self.energy - 1.2)
        self.shelter = clamp(self.shelter - 0.35)      # 房子会老化

        # 世界发生的事落到个体身上
        if self.world.weather == "storm":
            dmg = self.world.storm_damage
            self.shelter = clamp(self.shelter - dmg)
            if dmg > 28:
                self.mark(day, "一场暴雨掀翻了屋顶", "fears_storm",
                          {"caution": 10}, emotional_weight=0.82,
                          consequence="shelter_damage",
                          knowledge=("shelter", "没有坚固的住所，下雨很危险"))

        # ★体质★ 长期吃不饱 → 身体被掏空；吃饱了才慢慢养回来
        # 规则 47：v2 里移植后「饿<30」占比塌到 0–2%，恢复通道几乎从不触发，
        # 系统 90–98% 的时间待在死区里被慢慢掏空 —— 结构上没有稳态。
        # v3 把 COND_RECOVER_AT 抬到 65（跨过规则 49 的怠惰谷），死区收窄到 5 分。
        if self.hunger > COND_DRAIN_AT:
            self.condition = clamp(self.condition - COND_DRAIN)
        else:
            gain = COND_RECOVER if self.hunger < COND_RECOVER_AT \
                else COND_DEADZONE_RECOVER               # 修法①抬阈值 / ②填死区
            gain += COND_SHELTER_RECOVER * (self.shelter / 100.0)   # 修法③
            if gain:
                self.condition = clamp(self.condition + gain)

        # ★受苦 → 性格★ 连续传导
        deficit = (100.0 - self.condition) / 100.0
        if deficit > 0:
            self.hardship += deficit / TICKS_PER_DAY
            if self._hardship_anchor is None:
                self._hardship_anchor = dict(self.traits)

        if self._hardship_anchor is not None:
            boost = HARDSHIP_MAX_BOOST * self.hardship_norm
            for t, w in HARDSHIP_FLOOR_WEIGHT.items():
                self.trait_floor[t] = max(
                    self.trait_floor[t],
                    min(self._hardship_anchor[t] + w * boost, 90.0))
            if (self.hardship_norm >= HARDSHIP_STORY_AT
                    and "fears_hunger" not in self.flags):
                self.mark(day, "熬过了一段吃不饱的日子", "fears_hunger", {},
                          emotional_weight=0.9, consequence="condition_loss",
                          knowledge=("food", "存粮见底的日子很难熬"))

        if self.condition <= 0:
            self.alive = False
            return

        scored = [(self.score(a, day), a) for a in ACTIONS]
        scored = [(s, a) for s, a in scored if s is not None]
        self.act(max(scored)[1], day, tick_of_day)

    # ---------- 可读标签 ----------

    def dominant_style(self):
        """把性格向量翻译成一个可读的标签 —— 差异必须看得见

        ⚠ 这读的是性格【数值】。消融实验（014）证明数值可以和行为脱节，
          用户看到的是行为 —— 主结论请看 behavior.py。
        """
        c, q, i = (self.traits[t] for t in TRAITS)
        if q > 58 and c < 48:  return "冒险家"
        if c > 58 and q < 48:  return "筑巢者"
        dev = {"谨慎型": c - 50.0, "好奇型": q - 50.0, "劳模": i - 50.0}
        top = max(dev, key=dev.get)
        return top if dev[top] >= 8.0 else "平庸型"


# ============================================================
# Life —— 把世界、个体、干预绑在一起跑
# ============================================================

class Life:
    """一次完整的生命过程。

    ★ 干预（influences）挂在这里，不挂在 Agent 上。★
    Agent 不知道有人在照顾它，只知道"今天世界里多了两份食物"。
    """

    def __init__(self, seed, world=None, influences=(), world_seed=None):
        # 世界和个体是两条独立的随机流：
        # 这样才能做"同一颗种子、同样的初始性格，只换世界"的实验
        self.world = world if world is not None else World(
            seed if world_seed is None else world_seed)
        self.agent = Agent(seed, self.world)
        self.influences = list(influences)
        self.inf_rng = random.Random(seed ^ 0x5EED)

    def run(self, days=None):
        days = SIM_DAYS if days is None else days
        for day in range(days):
            for t in range(TICKS_PER_DAY):
                self.world.tick(day, t)
                for inf in self.influences:
                    inf(self.world, self.agent, day, t, self.inf_rng)
                self.agent.tick(day, t)
                if not self.agent.alive:
                    return self.agent
            self.agent.daily(day)
        return self.agent


if __name__ == "__main__":
    print(__doc__)
    print("这是核心模型，本身不定义任何实验。")
    print("要跑实验请用：  python scenarios.py   /   python paired.py   等")
