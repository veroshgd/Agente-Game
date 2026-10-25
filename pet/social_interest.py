"""Round 11 of 2026-10-25: a social memory with the SAME rule as the reading memory, as a separate
extension (NOT a rule version; pet/engine.py, the frozen round-8 candidate, is not edited).

SocialPetAgent subclasses engine.PetAgent; SocialSession is a TracedSession that holds one. With every
switch off it is the parent exactly (tests). Nothing here is reachable from Session / saves / v1-v6.

Social result: each VISIT hour (spontaneous or invited) gives
    gain = warmth x focus,   warmth = world.p['neighbor_warmth'] (SOCIAL_WARMTH_DEFAULT if unset),
                             focus  = need gate before the hour (the reading result's focus)
Social memory: exactly the reading memory's formulas and constants (engine EVAL_ALPHA_MIN, EVAL_N0,
EVAL_KEEP, INTEREST_RATE, READ_VALUE_REF): S <- S + alpha (gain - S), n kept x0.98 a day, I consolidated
once a day from S on days with a visit, faded toward 0.5 on days without; term in [-0.5, 0.5].
Decision entries (one per arm, never both):
  'B'  choosing to go out: + READ_VALUE_WEIGHT * term * need gate * (1 - home need) on the 'explore'
       score, only in hours the neighbor can meet now (engine can_meet: the v5 liking's social option).
       Same bound as the reading term. This is the entry where the interest competes with reading.
  'A'  after going out: + VISIT_PREF * term in the visit chance (the v5 liking's scale), clamped as v5.
Frozen control: freeze() snapshots the reading memory (read_V, read_n, read_I) and the social memory
(S, n, I) that feed the two terms, confidence included; the terms then read the snapshot. Memories keep
learning (never used), needs / home gates stay live, everything else in the agent runs as usual.
explore_offtask_off: a plan without an 'explore' weight no longer damps 'explore' (the symmetric twin of
engine goal_read_offtask_off; secondary arm only).
"""
from . import engine
from . import lifestats as L
from .engine import core

SOCIAL_WARMTH_DEFAULT = 0.6      # the standard neighbor (= READ_CLARITY_DEFAULT, by rule)


class SocialPetAgent(engine.PetAgent):
    def __init__(self, seed, world, rules=engine.RULES):
        super().__init__(seed, world, rules)
        self.social_memory = False          # learn the social memory
        self.social_entry = None            # None / 'A' / 'B'
        self.exp_decide = True              # growth: False = no experimental term decides
        self.explore_offtask_off = False
        self.s_V, self.s_n, self.s_I, self.s_today = 0.0, 0.0, engine.READ_VALUE_REF, 0
        self.frozen = None                  # {'read': (V, n, I), 'social': (V, n, I)} or None
        self.social_log = []                # (tick, gain, invited) per visit hour; never read by decisions
        self._focus = None

    # ---- the social memory (the reading rule, other inputs)
    def warmth(self):
        return self.world.p.get('neighbor_warmth', SOCIAL_WARMTH_DEFAULT)

    @staticmethod
    def _term(V, n, I, interest=True):
        short = 0.0 if n <= 0 else n / (n + engine.EVAL_N0) * (V - engine.READ_VALUE_REF)
        return (short + I - engine.READ_VALUE_REF) / 2 if interest else short

    def social_term(self):
        V, n, I = self.frozen['social'] if self.frozen else (self.s_V, self.s_n, self.s_I)
        return self._term(V, n, I)

    def read_value_term(self):
        if not self.frozen:
            return super().read_value_term()
        V, n, I = self.frozen['read']
        return self._term(V, n, I, self.read_interest and self.read_interest_in_decision)

    def freeze(self):
        self.frozen = {'read': (self.read_V, self.read_n, self.read_I), 'social': (self.s_V, self.s_n, self.s_I)}

    def social_result(self, invited):
        gain = self.warmth() * self._focus
        n = self.s_n
        self.s_V += max(1.0 / (n + 1.0), engine.EVAL_ALPHA_MIN) * (gain - self.s_V)
        self.s_n = n + 1.0
        self.s_today += 1
        self.social_log.append((self.now, gain, invited))

    def consolidate_social(self):
        n = self.s_n
        w = 0.0 if n <= 0 else n / (n + engine.EVAL_N0) * abs(self.s_V - engine.READ_VALUE_REF) / engine.READ_VALUE_REF
        if self.s_today:
            self.s_I += engine.INTEREST_RATE * w * (self.s_V - self.s_I)
        else:
            self.s_I = engine.READ_VALUE_REF + (self.s_I - engine.READ_VALUE_REF) * engine.EVAL_KEEP
        self.s_today = 0

    # ---- hooks
    def act(self, action, day, hour=0):
        self._focus = self.need_gate()          # before the hour, like the reading result's focus
        super().act(action, day, hour)
        if self.social_memory and self.last['action'] == 'visit':
            self.social_result(bool(self.last['invited']))

    def daily(self, day):
        super().daily(day)
        if self.social_memory:
            self.consolidate_social()
            self.s_n *= engine.EVAL_KEEP

    def social_score_part(self, action, day):
        if not (self.social_entry == 'B' and self.exp_decide and action == 'explore' and self.world.has('garden')):
            return 0.0
        hour, invited = self.now % 24, self.now < self.invitation_until
        if not self.can_meet(day, hour, invited):
            return 0.0
        return engine.READ_VALUE_WEIGHT * self.social_term() * self.need_gate() * (1 - self.home_need())

    def score_parts(self, action, day):
        p = super().score_parts(action, day)
        if p is not None and self.social_entry == 'B':
            p['social_term'] = self.social_score_part(action, day)
            p['final'] += p['social_term']
        return p

    def visit_chance(self, bonus):
        p, pref = super().visit_chance(bonus)
        if self.social_entry == 'A' and self.exp_decide:
            raw = engine.VISIT_BASE + pref + bonus * engine.VISIT_MEMORY + engine.VISIT_PREF * self.social_term()
            p = max(engine.VISIT_MIN, min(engine.VISIT_MAX, raw))
        return p, pref

    def read_value_part(self, action):
        if not self.exp_decide:
            return 0.0, None
        return super().read_value_part(action)

    def goal_bonus(self, action):
        if (self.explore_offtask_off and action == 'explore' and self.goal is not None
                and not core.GOAL_ACTIONS.get(self.goal['type'], {}).get('explore')):
            return 0.0
        return super().goal_bonus(action)


class SocialSession(L.TracedSession):
    """A TracedSession whose pet is a SocialPetAgent (same seed, created before any step: same draws)."""

    def __init__(self, seed=42, rules=engine.RULES):
        super().__init__(seed, rules)
        self.agent = SocialPetAgent(seed, self.world, rules)
        self.birth_traits = dict(self.agent.traits)
