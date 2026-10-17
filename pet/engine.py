"""Product adapter for sim.py; gardening/social rules are new, unvalidated design.

The core still chooses actions and updates needs, traits, goals and knowledge.
Product memories add a bounded, auditable exploration bonus. An exploration can
be a garden activity or a visit; an invitation creates an opportunity, not an act.
"""
import importlib.util
from pathlib import Path
import math
import random

# A private module avoids the research tools' sys.path / 'sim' import switching.
spec = importlib.util.spec_from_file_location('lifeengine_product_core', Path(__file__).resolve().parents[1] / 'sim.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

MAX_TICKS = 10000
MAX_COMMANDS = 12000
# Saves replay under the rules they were created with, so old pets never rewrite history.
# 1 = original prototype. 2 = trait homeostasis + eating before hunger harms the body
# (audit 2026-10-14: under v1 every pet drifted to curiosity 100 / caution 0 and all
# 24 audited pets formed a hunger trauma in the "safe" home).
# 3 = boredom with repeated leisure + a neighbor with her own schedule (audit 2026-10-17:
# under v2 the garden filled 33-52% of the day, ~5 visits/day, and the home sat at 0
# because gathering material lost to the garden by 4-7 points every single hour).
# 4 = a run-down home becomes a felt need, and the diary names the real reason the
# neighbor could not meet (review 2026-10-17: under v3 the home still reached 0 in
# 16/16 audited runs, for up to 136 h, and "she is out" was also written when her
# daily visits were simply used up).
RULES = 4
TRAIT_HOME_PULL = 0.004      # per hour, fraction of the gap back to the trait's anchor
EAT_URGENCY_FROM = 55        # hunger where eating starts to outrank leisure
EAT_URGENCY = 6.0            # extra eat score per hunger point above that
BOREDOM_WINDOW = 24          # hours of recent activity that count towards boredom
BOREDOM = 60.0               # penalty if one leisure activity filled the whole window (swept 20-80)
LEISURE = ('explore', 'read')  # = core DISCRETIONARY; needs and home chores never get boring
MILI_AWAY_CHANCE = 0.3       # share of days the neighbor is out (fixed per seed and day)
MILI_VISITS_PER_DAY = 2      # unprompted visits she has time for; invitations always count
HOME_CARE_FROM = 45          # v4: home state below which the pet feels it needs care
HOME_CARE = 1.0              # v4: extra gather_material/build score per point below that
HOME_GOAL = 1.2              # v4: improve_home goal priority added at a fully run-down home (swept 0-1.2)
GARDEN_PULL = 6              # garden as a place to go (explore), before need gating
INVITATION_PULL = 12         # a pending invitation, before need gating
# Why the neighbor could not meet. Invitations skip 'away' and 'full', never 'off_hours'.
NEIGHBOR_FREE, NEIGHBOR_OFF_HOURS, NEIGHBOR_AWAY, NEIGHBOR_FULL = 'free', 'off_hours', 'away', 'full'
LABELS = {'eat': '吃点东西', 'sleep': '休息', 'gather_food': '收集食物',
          'gather_material': '收集材料', 'build': '整理小屋', 'explore': '四处探索',
          'read': '读书', 'garden': '照料花园', 'visit': '和米粒一起种花'}
# v4 diary: the real reason a wished-for visit did not happen.
NEIGHBOR_TEXT = {NEIGHBOR_AWAY: '想去找米粒，可她今天外出了，就自己照料了花园。',
                 NEIGHBOR_FULL: '想去找米粒，可她今天的接待次数已经满了，就自己照料了花园。',
                 NEIGHBOR_OFF_HOURS: '想去找米粒，可现在不是她的接待时间（08:00-20:00），就自己照料了花园。'}

class LimitReached(ValueError):
    """The prototype's tick or command budget is used up. The pet stays viewable/exportable."""

class PetAgent(core.Agent):
    def __init__(self, seed, world, rules=RULES):
        super().__init__(seed, world)
        self.seed = seed
        self.rules = rules
        self.recent = []
        self.birth = dict(self.traits)
        self.shelter = 80.0
        self.inventory['food'] = 6.0
        self.shared = []
        self.garden_memories = []
        self.invitation_until = -1
        self.now = 0
        self.last = None

    def influence(self):
        # A real event id carries each contribution. Time weakens its influence.
        recent = [m for m in self.shared if self.now - m['tick'] < 168]
        sources = recent[-5:]
        bonus = sum(2 * math.exp(-(self.now - m['tick']) / 96) for m in sources)
        return bonus, [m['id'] for m in sources]

    def boredom(self, action):
        if self.rules < 3 or action not in LEISURE:
            return 0.0
        return BOREDOM * self.recent.count(action) / BOREDOM_WINDOW

    def neighbor_status(self, day, hour, invited=False):
        """Can the neighbor meet now, and if not, why. Her schedule depends only on the
        seed and the day, never on the pet's rng, so it cannot shift other draws."""
        if not 8 <= hour < 20:
            return NEIGHBOR_OFF_HOURS
        if self.rules < 3 or invited:
            return NEIGHBOR_FREE
        if random.Random(self.seed * 100003 + day).random() < MILI_AWAY_CHANCE:
            return NEIGHBOR_AWAY
        if sum(1 for m in self.shared if m['tick'] // 24 == day) >= MILI_VISITS_PER_DAY:
            return NEIGHBOR_FULL
        return NEIGHBOR_FREE

    def mili_free(self, day, hour):
        return self.neighbor_status(day, hour) == NEIGHBOR_FREE

    def home_care(self, action):
        if self.rules < 4 or action not in ('gather_material', 'build'):
            return 0.0
        # A felt need, like hunger: it grows as the home runs down and is silent above
        # HOME_CARE_FROM, so a cared-for home leaves the day to everything else.
        return max(0.0, HOME_CARE_FROM - self.shelter) * HOME_CARE

    def propose_goals(self, day):
        """v4: the same felt need also forms the intention. Without it a curious pet kept
        'see the world' as its goal with the home at 10, and the core's 6-day satiation
        after a finished repair let the home fall back to 0 before it cared again."""
        out = super().propose_goals(day)
        if self.rules < 4:
            return out
        need = max(0.0, HOME_CARE_FROM - self.shelter) / HOME_CARE_FROM
        return [(g, pri + HOME_GOAL * need if g == 'improve_home' else pri, src)
                for g, pri, src in out]

    def score_parts(self, action, day):
        """Every product contribution to one action's score, from the current state.
        final = core - boredom + eat_urgency + home_care + gated, with
        gated = (garden + invitation + memory) * gate. Same arithmetic order as rules 1-3."""
        core_score = super().score(action, day)
        if core_score is None:
            return None
        p = {'core': core_score, 'boredom': self.boredom(action), 'eat_urgency': 0.0,
             'home_care': 0.0, 'garden': 0, 'invitation': 0, 'memory': 0.0,
             'memory_ids': [], 'gate': 0.0, 'gated': 0.0}
        base = core_score - p['boredom']
        if action == 'eat' and self.rules >= 2:
            # Product safe-home: eat before the core's condition drain (hunger 70) starts.
            p['eat_urgency'] = max(0, self.hunger - EAT_URGENCY_FROM) * EAT_URGENCY
            p['final'] = base + p['eat_urgency']
        elif action in ('gather_material', 'build') and self.rules >= 4:
            p['home_care'] = self.home_care(action)
            p['final'] = base + p['home_care']
        elif action == 'explore' and self.world.has('garden'):
            bonus, ids = self.influence()
            # Needs still gate discretionary activity. No permanent friendship flag.
            slack = max(0, min(1, (70 - self.hunger) / 40, self.energy / 60))
            invitation = INVITATION_PULL if self.now < self.invitation_until else 0
            p.update(garden=GARDEN_PULL, invitation=invitation, memory=bonus,
                     memory_ids=ids, gate=slack)
            p['gated'] = (GARDEN_PULL + bonus + invitation) * slack
            p['final'] = base + p['gated']
        else:
            p['final'] = base
        return p

    def score(self, action, day):
        p = self.score_parts(action, day)
        return None if p is None else p['final']

    def explain(self, action, day, p):
        """The decision record shown in the diary, built from the values this choice used."""
        rivals = [(s, a) for a in core.ACTIONS if a != action
                  for s in [self.score(a, day)] if s is not None]
        runner_up, rival = max(rivals) if rivals else (None, None)
        r = lambda v: round(v, 4)
        memory = p['memory'] * p['gate']
        return {'core': r(p['core']), 'garden': r(p['garden'] * p['gate']),
                'invitation': r(p['invitation'] * p['gate']), 'memory': r(memory),
                'memory_raw': r(p['memory']), 'memory_ids': list(p['memory_ids']),
                'gate': r(p['gate']), 'gated': r(p['gated']), 'boredom': r(p['boredom']),
                'eat_urgency': r(p['eat_urgency']), 'home_care': r(p['home_care']),
                'net': r(p['final'] - p['core']), 'final': r(p['final']),
                'runner_up': None if runner_up is None else r(runner_up),
                'runner_up_action': rival,
                # Taking the memory term away would have let another action win.
                'memory_decisive': bool(memory > 0 and runner_up is not None
                                        and p['final'] - memory < runner_up)}

    def act(self, action, day, hour=0):
        before = dict(self.traits)
        # Capture prior causes BEFORE executing or creating the new memory.
        p = self.score_parts(action, day)
        decision = self.explain(action, day, p)
        bonus, ids = self.influence()
        invited = self.now < self.invitation_until
        outcome = action
        missed = False
        neighbor = None
        if action == 'explore' and self.world.has('garden'):
            # Scheduling is deterministic: this system neighbor is home 8-19h,
            # and from v3 on she keeps a card you left for her even on busy days.
            status = self.neighbor_status(day, hour, invited)
            neighbor_home = status == NEIGHBOR_FREE
            wants_visit = invited or (ids and self.rng.random() < min(.75, .15 + bonus / 14))
            outcome = 'visit' if neighbor_home and wants_visit else 'garden'
            missed = bool(wants_visit) and not neighbor_home and 8 <= hour < 20
            if wants_visit and not neighbor_home:
                neighbor = status
        super().act(action, day, hour)
        if self.rules >= 2:
            self.settle()
        if self.rules >= 3:
            self.recent = (self.recent + [action])[-BOREDOM_WINDOW:]
        self.last = {'action': outcome, 'core_action': action,
                     'cause_ids': ids if action == 'explore' else [],
                     'memory_bonus': round(bonus, 3) if action == 'explore' else 0,
                     # Legacy: net product change (final - core). 'decision' has the parts.
                     'score_bonus': round(p['final'] - p['core'], 3),
                     'invited': invited and outcome == 'visit',
                     'before': before, 'after': dict(self.traits),
                     'decision': decision}
        if self.rules == 3:
            # v3 diary rule, kept as recorded: one flag for every reason she was unavailable.
            self.last['missed_neighbor'] = missed
        if self.rules >= 4:
            self.last['neighbor'] = neighbor

    def settle(self):
        """Homeostasis: the safe home removes the storms and scarcity that balanced
        exploration in the research world, so pull each trait gently back toward its
        anchor. Daily life still shapes it; it just cannot run away to 0 or 100.
        Landmark identity (sim.py) raises the anchor, so key experiences still last."""
        for t, v in self.traits.items():
            anchor = max(self.birth[t], self.trait_identity[t])
            self.traits[t] = max(self.trait_floor[t], min(100.0, v + (anchor - v) * TRAIT_HOME_PULL))

class Session:
    def __init__(self, seed=42, rules=RULES):
        self.seed = seed
        self.rules = rules
        self.tick = 0
        self.name = '芽芽'
        self.world = core.World(seed=seed ^ 0x5EED, food_regen=8, food_cap=20,
                                storm_chance=0, season_amplitude=0)
        self.agent = PetAgent(seed, self.world, rules)
        self.birth_traits = dict(self.agent.traits)
        self.events = []
        self.commands = []
        self.event('birth', '你好，小世界', '小家伙诞生了。先取个名字，再一起认识这个家。')

    def event(self, kind, title, text, **extra):
        event = {'id': len(self.events) + 1, 'tick': self.tick, 'kind': kind,
                 'title': title, 'text': text, **extra}
        self.events.append(event)
        return event

    def step(self):
        day, hour = divmod(self.tick, 24)
        a = self.agent
        a.now = self.tick
        self.world.tick(day, hour)
        # Product safe-home policy: no repeated feeding chore or survival death.
        # This is environment support, explicitly separate from research settings.
        if a.inventory['food'] < 1:
            a.inventory['food'] += 3
            self.event('home', '厨房补充了食物', '小屋会自动补充食物，饿了它会自己决定去吃。')
        # v2 steps in before this tick's hunger would cross the core's condition drain.
        limit, reset = (core.COND_DRAIN_AT - core.HUNGER_RATE, 60) if self.rules >= 2 else (85, 65)
        if a.hunger > limit:
            a.hunger = reset
            self.event('home', '小屋提供了应急照料', '原型的安全照料降低了饥饿，避免生存惩罚。')
        old_memory_count = len(a.memories)
        a.tick(day, hour)
        for memory in a.memories[old_memory_count:]:
            self.event('core_memory', '记住了一件事', memory['text'])
        move = a.last
        action = move['action']
        causes = move['cause_ids']
        if action == 'visit':
            text = '接受了这次邀请，和米粒种下一株花。' if move['invited'] else '想起之前一起种花的经历，主动去找米粒，种下一株花。'
        elif action == 'garden' and move.get('neighbor'):
            text = NEIGHBOR_TEXT[move['neighbor']]
        elif action == 'garden' and move.get('missed_neighbor'):
            text = '想去找米粒，可她今天不在家，就自己照料了花园。'   # v3 wording, kept for v3 saves
        elif action == 'garden':
            text = '出门照料了花园。' + ('之前的共同经历增加了出门的吸引力。' if causes else '今天还没有发生新的共同活动。')
        else:
            text = {'eat':'饿了，自己去厨房吃东西。','sleep':'累了，回家休息。','read':'拿起家里的书读了一会儿。','build':'用收集的材料改善了小屋。','gather_material':'收集了一些整理小屋用的材料。','gather_food':'在附近找到了一些食物。','explore':'独自探索了周围的环境。'}[action]
        e = self.event('action', LABELS[action], text, **move)
        if action in ('garden', 'visit'):
            a.garden_memories.append({'id': e['id'], 'tick': self.tick})
        if action == 'visit':
            a.shared.append({'id': e['id'], 'tick': self.tick})
            a.invitation_until = -1
            a.remember(day, f'和米粒一起种花（事件 #{e["id"]}）', event='shared_garden',
                       tags=('garden', 'neighbor'), importance=.7,
                       consequence='future_exploration_bonus')
        self.tick += 1
        a.now = self.tick
        if self.tick % 24 == 0:
            a.daily(day)

    def apply(self, command):
        if not isinstance(command, dict):
            raise ValueError('指令格式错误')
        kind, value = command.get('kind'), command.get('value')
        if set(command) != {'kind', 'value'}:
            raise ValueError('指令无效')
        if len(self.commands) >= MAX_COMMANDS:
            raise LimitReached('已达到本原型的操作上限。角色仍可查看，也可以导出存档。')
        if kind == 'advance':
            if type(value) is not int or value not in (1, 6, 24):
                raise ValueError('时间步长无效')
            if self.tick + value > MAX_TICKS:
                raise LimitReached('剩余游戏时间不足以前进这么久（演示上限 10000 小时）。角色仍可查看，也可以导出存档。')
            for _ in range(value):
                self.step()
        elif kind == 'name':
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 20 or any(ord(c) < 32 for c in value):
                raise ValueError('名字请输入 1-20 个可见字符')
            self.name = value.strip()
            self.event('name', '有了自己的名字', f'现在叫 {self.name}。')
        elif kind == 'object':
            if value not in ('book', 'music', 'garden'):
                raise ValueError('未知物品')
            if value in self.world.objects:
                raise ValueError('家里已经有这个了')
            self.world.objects.add(value)
            label = {'book':'一本书','music':'小音乐盒','garden':'花园入口'}[value]
            self.event('object', '家里有了新东西', f'你准备了{label}。是否使用，由它自己决定。')
        elif kind == 'invite':
            if value is not None or not self.world.has('garden'):
                raise ValueError('先布置花园，再邀请邻居')
            if self.tick < self.agent.invitation_until:
                raise ValueError('邀请还在等待回应')
            self.agent.invitation_until = self.tick + 24
            self.event('invitation', '给米粒留了一张邀请卡', '邀请持续一天；米粒在 08:00-20:00 有空。角色需要自己决定是否出门。')
        else:
            raise ValueError('未知指令')
        self.commands.append(dict(command))

    def limits(self):
        ticks_left, commands_left = MAX_TICKS - self.tick, MAX_COMMANDS - len(self.commands)
        return {'max_ticks': MAX_TICKS, 'max_commands': MAX_COMMANDS, 'ticks_left': ticks_left,
                'commands_left': commands_left, 'can_act': commands_left > 0,
                'can_advance': ticks_left > 0 and commands_left > 0}

    def archive(self):
        return {'version': self.rules, 'seed': self.seed, 'commands': self.commands}

    @classmethod
    def restore(cls, data):
        if not isinstance(data, dict) or set(data) != {'version','seed','commands'} or type(data['version']) is not int or not 1 <= data['version'] <= RULES:
            raise ValueError('不支持的存档版本')
        if type(data['seed']) is not int or not 0 <= data['seed'] <= 2**31:
            raise ValueError('存档种子无效')
        if not isinstance(data['commands'], list) or len(data['commands']) > MAX_COMMANDS:
            raise ValueError('存档指令数量无效')
        result = cls(data['seed'], data['version'])
        for command in data['commands']:
            result.apply(command)
        return result

    def view(self):
        a = self.agent
        bonus, ids = a.influence()
        last = next((e for e in reversed(self.events) if e['kind'] == 'action'), None)
        return {'name': self.name, 'tick': self.tick, 'day': self.tick // 24 + 1,
                'hour': self.tick % 24, 'stage': '幼年' if self.tick < 72 else ('成长中' if self.tick < 240 else '成年'),
                'traits': {t: round(v,1) for t,v in a.traits.items()},
                'birth_traits': {t:round(v,1) for t,v in self.birth_traits.items()},
                'energy': round(a.energy), 'satiety': round(100-a.hunger), 'home': round(a.shelter),
                'objects': sorted(self.world.objects), 'flowers': len(a.shared),
                'shared_count': len(a.shared), 'relationship': '还没一起玩过' if not a.shared else ('熟悉的伙伴' if len(a.shared)>=3 else '开始熟悉'),
                'memory_bonus': round(bonus,2), 'memory_ids': ids,
                'invitation_pending': self.tick < a.invitation_until,
                'last': last, 'events': self.events[-90:], 'total_events': len(self.events),
                'goal': a.context_packet(self.tick//24)['goal'],
                'limits': self.limits(), 'rules': self.rules, 'latest_rules': RULES}
