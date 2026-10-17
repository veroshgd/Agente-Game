"""Product adapter for sim.py; gardening/social rules are new, unvalidated design.

The core still chooses actions and updates needs, traits, goals and knowledge.
Product memories add a bounded, auditable exploration bonus. An exploration can
be a garden activity or a visit; an invitation creates an opportunity, not an act.
"""
import importlib.util
from pathlib import Path
import math

# A private module avoids the research tools' sys.path / 'sim' import switching.
spec = importlib.util.spec_from_file_location('lifeengine_product_core', Path(__file__).resolve().parents[1] / 'sim.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

MAX_TICKS = 10000
MAX_COMMANDS = 12000
LABELS = {'eat': '吃点东西', 'sleep': '休息', 'gather_food': '收集食物',
          'gather_material': '收集材料', 'build': '整理小屋', 'explore': '四处探索',
          'read': '读书', 'garden': '照料花园', 'visit': '和米粒一起种花'}

class PetAgent(core.Agent):
    def __init__(self, seed, world):
        super().__init__(seed, world)
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

    def score(self, action, day):
        base = super().score(action, day)
        if base is None or action != 'explore' or not self.world.has('garden'):
            return base
        bonus, _ = self.influence()
        # Needs still gate discretionary activity. No permanent friendship flag.
        slack = max(0, min(1, (70 - self.hunger) / 40, self.energy / 60))
        invitation = 12 if self.now < self.invitation_until else 0
        return base + (6 + bonus + invitation) * slack

    def act(self, action, day, hour=0):
        before = dict(self.traits)
        # Capture prior causes BEFORE executing or creating the new memory.
        bonus, ids = self.influence()
        invited = self.now < self.invitation_until
        core_score = super().score(action, day)
        chosen_score = self.score(action, day)
        outcome = action
        if action == 'explore' and self.world.has('garden'):
            # Scheduling is deterministic: this system neighbor is home 8-19h.
            neighbor_home = 8 <= hour < 20
            wants_visit = invited or (ids and self.rng.random() < min(.75, .15 + bonus / 14))
            outcome = 'visit' if neighbor_home and wants_visit else 'garden'
        super().act(action, day, hour)
        self.last = {'action': outcome, 'core_action': action,
                     'cause_ids': ids if action == 'explore' else [],
                     'memory_bonus': round(bonus, 3) if action == 'explore' else 0,
                     'score_bonus': round(chosen_score - core_score, 3),
                     'invited': invited and outcome == 'visit',
                     'before': before, 'after': dict(self.traits)}

class Session:
    def __init__(self, seed=42):
        self.seed = seed
        self.tick = 0
        self.name = '芽芽'
        self.world = core.World(seed=seed ^ 0x5EED, food_regen=8, food_cap=20,
                                storm_chance=0, season_amplitude=0)
        self.agent = PetAgent(seed, self.world)
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
        if a.hunger > 85:
            a.hunger = 65
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
        if set(command) != {'kind', 'value'} or len(self.commands) >= MAX_COMMANDS:
            raise ValueError('指令无效或本次原型的记录上限已到')
        if kind == 'advance':
            if type(value) is not int or value not in (1, 6, 24) or self.tick + value > MAX_TICKS:
                raise ValueError('时间步长无效或已达到 10000 小时演示上限，请导出存档')
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

    def archive(self):
        return {'version': 1, 'seed': self.seed, 'commands': self.commands}

    @classmethod
    def restore(cls, data):
        if not isinstance(data, dict) or set(data) != {'version','seed','commands'} or type(data['version']) is not int or data['version'] != 1:
            raise ValueError('不支持的存档版本')
        if type(data['seed']) is not int or not 0 <= data['seed'] <= 2**31:
            raise ValueError('存档种子无效')
        if not isinstance(data['commands'], list) or len(data['commands']) > MAX_COMMANDS:
            raise ValueError('存档指令数量无效')
        result = cls(data['seed'])
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
                'energy': round(a.energy), 'satiety': round(100-a.hunger),
                'objects': sorted(self.world.objects), 'flowers': len(a.shared),
                'shared_count': len(a.shared), 'relationship': '还没一起玩过' if not a.shared else ('熟悉的伙伴' if len(a.shared)>=3 else '开始熟悉'),
                'memory_bonus': round(bonus,2), 'memory_ids': ids,
                'invitation_pending': self.tick < a.invitation_until,
                'last': last, 'events': self.events[-90:], 'total_events': len(self.events),
                'goal': a.context_packet(self.tick//24)['goal'],
                'limits': {'max_ticks':MAX_TICKS}}
