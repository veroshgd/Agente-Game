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
# 5 = long-term preferences formed by lived activities: reading, gardening alone and
# gardening with the neighbor each leave their own slow trace, which then makes that
# activity more attractive (needs still come first). A pet that has met the neighbor can
# also seek her out again after old memories have faded (v4: 2/8 audited seeds stopped
# visiting for good once the 7-day memories expired).
# A v6 candidate (4 h rest after each shared activity instead of 2 visits a day) passed its
# own pre-set criteria on 2026-10-17 but broke the v4 safe-home standard (seed 42, garden:
# lowest home 2.9 < 3), so it was NOT adopted; see PET_VALIDATION.md. It stays available as
# an experiment switch (PetAgent.visit_cap / visit_rest_hours).
RULES = 5
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
# v5 long-term preferences (0 = neutral at birth, 1 = a strong, well-practised liking).
PREF_OF = {'read': 'read', 'garden': 'garden'}   # lived leisure activity -> activity preference
# Activity liking (read, garden): each lived hour of leisure moves both a small step, the
# activity done toward how much it was enjoyed, the other toward 0. It is a slow, enjoyment-
# weighted share of free time: it saturates, needs practice to stay, and can be relearned.
# Liking for the neighbor's company (social) learns only from real chances to meet her: an
# hour she was free and the pet went out. Going to her moves it toward the enjoyment,
# gardening alone instead moves it toward 0. So it measures company vs solitude when both
# were possible, not how many hours she happens to be free.
PREF_RATE = 0.005            # per leisure hour (~10 leisure hours a day; dev sweep 0.005-0.01)
SOCIAL_RATE = 0.02           # per real chance to meet her (a few a day; 0.05 forgot in ~3 days)
PREF_DULL = 0.5              # enjoyment lost when the activity filled the whole boredom window
PREF_WEIGHT = 60.0           # score points at preference 1, before need gating (dev sweep 16-60)
VISIT_BASE = 0.10            # chance to seek out a neighbor she has met, with no recent memory
VISIT_PREF = 1.5             # added per unit of liking for the neighbor's company
VISIT_MIN, VISIT_MAX = 0.02, 0.85
VISIT_MEMORY = 1 / 40        # v5: recent shared memories in the visit chance (v1-v4: 1/14). At 1/14
                             # one recent visit pulled every pet into the same visit-every-day loop,
                             # so short-term memory, not liking, decided who seeks her company.
PREF_GOAL = 1.0              # goal priority added per unit of liking (learn / see_the_world)
# Why the neighbor could not meet. Invitations skip 'away' and 'full', never 'off_hours'.
NEIGHBOR_FREE, NEIGHBOR_OFF_HOURS, NEIGHBOR_AWAY, NEIGHBOR_FULL = 'free', 'off_hours', 'away', 'full'
NEIGHBOR_REST = 'rest'       # resting after a shared activity (only when a rest interval is set)
LABELS = {'eat': '吃点东西', 'sleep': '休息', 'gather_food': '收集食物',
          'gather_material': '收集材料', 'build': '整理小屋', 'explore': '四处探索',
          'read': '读书', 'garden': '照料花园', 'visit': '和米粒一起种花'}
# v4 diary: the real reason a wished-for visit did not happen.
NEIGHBOR_TEXT = {NEIGHBOR_AWAY: '想去找米粒，可她今天外出了，就自己照料了花园。',
                 NEIGHBOR_FULL: '想去找米粒，可她今天的接待次数已经满了，就自己照料了花园。',
                 NEIGHBOR_OFF_HOURS: '想去找米粒，可现在不是她的接待时间（08:00-20:00），就自己照料了花园。',
                 NEIGHBOR_REST: '想去找米粒，可她刚一起种过花，想先歇一会儿，就自己照料了花园。'}

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
        # v5: rebuilt by replaying the command log like every other state.
        self.prefs = {k: 0.0 for k in ('read', 'garden', 'social')}
        self.pref_evidence = {k: {'count': 0, 'recent_ids': []} for k in self.prefs}
        self.pref_off = False        # validation only: removes the preference term from decisions
        # The neighbor's visiting rule. Defaults are the v3-v5 rule; experiments change them on
        # copies (and a future rule version could set them). Invitations skip both limits.
        self.visit_cap = MILI_VISITS_PER_DAY     # unprompted visits per day (None = no daily cap)
        self.visit_rest_hours = 0                # hours she rests after a shared activity
        self.freeze_prefs = False                # validation only: preferences keep acting, stop learning
        self.diagnostics = False                 # validation only: add 'social_diag' to events

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
        if self.visit_cap is not None and sum(1 for m in self.shared if m['tick'] // 24 == day) >= self.visit_cap:
            return NEIGHBOR_FULL
        if self.visit_rest_hours and self.shared and day * 24 + hour - self.shared[-1]['tick'] < self.visit_rest_hours:
            return NEIGHBOR_REST
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
        need = self.home_need()
        out = [(g, pri + HOME_GOAL * need if g == 'improve_home' else pri, src)
               for g, pri, src in out]
        if self.rules < 5 or self.pref_off:
            return out
        # v5: what it has come to like also shapes what it sets out to do for a few days.
        # Only the leisure goals, gated by slack like the core's own leisure goals, and by
        # the home: a run-down home crowds out leisure plans (without this gate the liking
        # for the garden out-bid home repairs and homes reached 0 again on dev seeds).
        liking = {'learn': self.prefs['read'], 'see_the_world': max(self.prefs['garden'], self.prefs['social'])}
        slack = self._slack() * (1 - need)
        self.goal_pref_boost = {g: PREF_GOAL * v * slack for g, v in liking.items()}
        return [(g, pri + self.goal_pref_boost.get(g, 0.0), src) for g, pri, src in out]

    def update_goal(self, day):
        before = self.goal
        super().update_goal(day)
        if self.rules >= 5 and self.goal is not None and self.goal is not before:
            # Trace on the goal itself how much long-term liking went into choosing it.
            self.goal['pref_boost'] = round(getattr(self, 'goal_pref_boost', {}).get(self.goal['type'], 0.0), 4)

    def need_gate(self):
        # Needs still gate discretionary activity (same formula as the garden pull).
        return max(0, min(1, (70 - self.hunger) / 40, self.energy / 60))

    def can_meet(self, day, hour, invited):
        return (self.neighbor_status(day, hour, invited) == NEIGHBOR_FREE
                and bool(invited or self.shared))

    def home_need(self):
        return max(0.0, HOME_CARE_FROM - self.shelter) / HOME_CARE_FROM if self.rules >= 4 else 0.0

    def preference_part(self, action, day):
        """v5: (contribution, preference key) of the long-term liking for this action.
        Explore takes the best sub-activity available right now (max, not sum), so a
        second option never adds attraction by itself and no liking is counted twice."""
        if self.rules < 5 or self.pref_off:
            return 0.0, None
        if action == 'read':
            key = 'read'
        elif action == 'explore' and self.world.has('garden'):
            hour, invited = self.now % 24, self.now < self.invitation_until
            options = ['garden'] + (['social'] if self.can_meet(day, hour, invited) else [])
            key = max(options, key=lambda k: self.prefs[k])
        else:
            return 0.0, None
        # Needs first: hunger/energy gate it, and a run-down home crowds it out.
        return PREF_WEIGHT * self.prefs[key] * self.need_gate() * (1 - self.home_need()), key

    def visit_chance(self, bonus):
        """v5: chance to seek the neighbor out (invitations are always accepted): long-term
        liking for her company plus fading recent memories. Not a difference with gardening
        alone: she is free fewer hours, so that liking is smaller by construction."""
        pref = 0.0 if self.pref_off else VISIT_PREF * self.prefs['social']
        p = max(VISIT_MIN, min(VISIT_MAX, VISIT_BASE + pref + bonus * VISIT_MEMORY))
        return p, pref

    def social_experience(self, visited, event_id, enjoyment):
        """v5: one real chance to meet the neighbor: company (visited) or solitude."""
        v = self.prefs['social']
        if not self.freeze_prefs:
            self.prefs['social'] = v + SOCIAL_RATE * ((enjoyment if visited else 0.0) - v)
        ev = self.pref_evidence['social']
        ev['count'] += 1
        if visited:
            ev['recent_ids'] = (ev['recent_ids'] + [event_id])[-3:]

    def experience(self, key, event_id, enjoyment):
        # key None: leisure spent on something without an activity preference
        # (plain exploring, or gardening with the neighbor, which teaches 'social').
        """v5: an activity that really happened moves its preference a bounded step toward
        how much it was enjoyed. Repeating it while bored, hungry or tired teaches less."""
        for k in PREF_OF.values():
            if self.freeze_prefs:
                break
            v = self.prefs[k]
            self.prefs[k] = v + PREF_RATE * ((enjoyment if k == key else 0.0) - v)
        if key:
            ev = self.pref_evidence[key]
            ev['count'] += 1
            ev['recent_ids'] = (ev['recent_ids'] + [event_id])[-3:]

    def score_parts(self, action, day):
        """Every product contribution to one action's score, from the current state.
        final = core - boredom + eat_urgency + home_care + gated, with
        gated = (garden + invitation + memory) * gate. Same arithmetic order as rules 1-3."""
        core_score = super().score(action, day)
        if core_score is None:
            return None
        p = {'core': core_score, 'boredom': self.boredom(action), 'eat_urgency': 0.0,
             'home_care': 0.0, 'garden': 0, 'invitation': 0, 'memory': 0.0,
             'memory_ids': [], 'gate': 0.0, 'gated': 0.0, 'preference': 0.0, 'pref_key': None}
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
        if self.rules >= 5:
            p['preference'], p['pref_key'] = self.preference_part(action, day)
            p['final'] += p['preference']
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
                **(self.explain_preference(action, day, p) if self.rules >= 5 else {}),
                'runner_up': None if runner_up is None else r(runner_up),
                'runner_up_action': rival,
                # Taking the memory term away would have let another action win.
                'memory_decisive': bool(memory > 0 and runner_up is not None
                                        and p['final'] - memory < runner_up)}

    def choose(self, day):
        """The core's own choice rule (sim.Agent.tick): highest (score, action) tuple."""
        return max((s, a) for s, a in ((self.score(x, day), x) for x in core.ACTIONS) if s is not None)[1]

    def choice_without(self, key, day):
        """Instant counterfactual: the action chosen if this one preference were 0 right now,
        all else as it is (today's goal, needs, memories, other preferences). Scoring is
        pure, so nothing real changes and no random number is drawn."""
        saved = self.prefs[key]
        self.prefs[key] = 0.0
        try:
            return self.choose(day)
        finally:
            self.prefs[key] = saved

    def explain_preference(self, action, day, p):
        key = p['pref_key']
        ev = self.pref_evidence[key] if key else {'count': 0, 'recent_ids': []}
        record = {'preference': round(p['preference'], 4), 'pref_key': key,
                  'pref_value': round(self.prefs[key], 4) if key else 0.0,
                  # A liking built over many hours: report how many, never one cause.
                  'pref_experiences': ev['count'], 'pref_recent_ids': list(ev['recent_ids']),
                  'pref_decisive': False, 'pref_counterfactual': None}
        if p['preference'] > 0:
            # Removing the whole contribution (final - preference) is wrong for explore: the
            # other liking can take over the max. So re-choose with only this liking at 0.
            # Scope: the action category; garden vs visit is not re-drawn here.
            without = self.choice_without(key, day)
            record['pref_decisive'] = without != action
            record['pref_counterfactual'] = {'removed': key, 'choice_without': without,
                                             'scope': 'category'}
        return record

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
        visit_record = None
        chance_to_meet = False
        drawn = wants = None
        diag = self.social_diag(day, hour, invited) if self.diagnostics else None
        # Enjoyment of this hour, from the state it was chosen in (v5 preference learning).
        dull = self.recent.count(action) / BOREDOM_WINDOW
        enjoyment = self.need_gate() * (1 - PREF_DULL * dull)
        if action == 'explore' and self.world.has('garden'):
            # Scheduling is deterministic: this system neighbor is home 8-19h,
            # and from v3 on she keeps a card you left for her even on busy days.
            status = self.neighbor_status(day, hour, invited)
            neighbor_home = status == NEIGHBOR_FREE
            if self.rules >= 5:
                # Having met her once is enough to look for her again; no fixed schedule.
                chance, chance_pref = self.visit_chance(bonus)
                drawn = not invited and bool(self.shared)        # a real draw happens below
                wants_visit = invited or (bool(self.shared) and self.rng.random() < chance)
                wants = bool(wants_visit) if (drawn or invited) else None
                visit_record = {'chance': round(chance, 4), 'pref': round(chance_pref, 4),
                                'memory': round(bonus * VISIT_MEMORY, 4), 'base': VISIT_BASE}
            else:
                wants_visit = invited or (ids and self.rng.random() < min(.75, .15 + bonus / 14))
            outcome = 'visit' if neighbor_home and wants_visit else 'garden'
            missed = bool(wants_visit) and not neighbor_home and 8 <= hour < 20
            if wants_visit and not neighbor_home:
                neighbor = status
            # v5: a real chance to choose company or solitude (she was free, they had met).
            chance_to_meet = neighbor_home and bool(invited or self.shared)
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
        if self.rules >= 5:
            self.last['enjoyment'] = round(enjoyment, 4)
            self.last['visit_chance'] = visit_record
            self.last['chance_to_meet'] = chance_to_meet
        if diag is not None:
            diag.update(chose_explore=action == 'explore', drew=bool(drawn), wanted=wants,
                        chance=visit_record, outcome=outcome)
            self.last['social_diag'] = diag

    def social_diag(self, day, hour, invited):
        """Validation-only record of the neighbor situation this hour. It draws no random
        number (her schedule has its own generator) and claims a wish to visit only when a
        real draw happened in act(); 'blocked' is her rule for an unprompted visit."""
        uninvited = self.neighbor_status(day, hour)
        return {'met': bool(self.shared), 'in_hours': 8 <= hour < 20,
                'away_today': random.Random(self.seed * 100003 + day).random() < MILI_AWAY_CHANCE,
                'visits_today': sum(1 for m in self.shared if m['tick'] // 24 == day),
                'blocked': uninvited if uninvited in (NEIGHBOR_FULL, NEIGHBOR_REST) else None,
                'available_uninvited': uninvited == NEIGHBOR_FREE, 'invited': invited}

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
        if action == 'visit' and not move['invited'] and not causes and self.rules >= 5:
            text = '有一阵子没见米粒了，主动去找她，一起种下一株花。'
        elif action == 'visit':
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
        if self.rules >= 5 and move['core_action'] in LEISURE:
            a.experience(PREF_OF.get(action), e['id'], move['enjoyment'])
        if self.rules >= 5 and move['chance_to_meet']:
            a.social_experience(action == 'visit', e['id'], move['enjoyment'])
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
                'limits': self.limits(), 'rules': self.rules, 'latest_rules': RULES,
                'preferences': None if self.rules < 5 else {
                    k: {'value': round(v, 3), 'experiences': a.pref_evidence[k]['count']}
                    for k, v in a.prefs.items()}}
