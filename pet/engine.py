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
# Candidate 6 (NOT adopted; Session(seed, 6) exists for experiments, saves cannot use it):
# the neighbor rests 4 h after each shared activity instead of 2 unprompted visits a day, and
# a run-down home may end a leisure plan early. The rest rule alone broke the v4 safe-home
# standard (seed 42, garden: lowest home 2.9 < 3): every low point was a core goal lock (a
# leisure plan kept for GOAL_MIN_DAYS while the home lost ~17 points), not a weak need.
# 2026-10-21 (pet/validate_v6.py, PET_VALIDATION.md): a first version cutting plans at any home
# need passed on 5001-5010 but nearly erased reading; the revised one (only below
# HOME_INTERRUPT_BELOW) passed home and social on fresh seeds 6001-6010 but missed the pre-set
# reading criterion R1 (reading-route gap 0.6 pp vs required 0.72 = 80% of v5's 0.9 pp).
# Experiment 'pause' (2026-10-23, pet/validate_pause.py; NOT a rule version, no save can use it):
# the same home interrupt stashes the leisure plan instead of ending it, and re-weighs it once
# the emergency is over. Switched on per pet with PetAgent.goal_pause; v1-v6 never read it.
RULES = 5
V6_REST_HOURS = 4            # neighbor's rest after each shared activity (v6; v3-v5: 2 a day instead)
HOME_INTERRUPT_BELOW = 15    # v6: home level under which a leisure plan may be ended early (dev: 10 too late, 20 cost more reading)
PAUSE_RESUME_AT = 30         # pause: home level that ends the emergency (2x the trigger: no flip-flop near 15)
PAUSE_MAX_DAYS = 4           # pause: a plan not resumed within this many days is dropped (= core GOAL_STALL_DAYS)
PAUSE_MAX_RESUMES = 2        # pause: a plan already resumed this often is ended at its next interrupt (as in v6)
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
# Experiment 'evaluation' (2026-10-24, pet/validate_eval.py; NOT a rule version). An activity
# evaluation Q for read and garden, learnt only from hours that activity was really lived:
#   r      = comfort while doing it (need gate before the hour: hunger and energy, in [0, 1]).
#            It reads no Q, no route, no identity, and is the same formula for both activities.
#            The environment has no activity-specific outcome (read and garden differ only by
#            fixed energy costs and garden's food finds), so this evaluates experienced STATE,
#            not richer results. Freshness (repetition) is left out on purpose: it is a function
#            of recent frequency and would make Q a second frequency code.
#   Q[a]  <- Q[a] + alpha (r - Q[a]),  alpha = max(1 / (n[a] + 1), EVAL_ALPHA_MIN)
#   n[a]   experienced hours, kept with EVAL_KEEP a day (never lived: n = 0, distinct from
#          disliked: Q below the baseline with n > 0). Q is never pulled back; only its weight fades.
#   R      baseline: mean comfort of all leisure hours (EVAL_BASE_RATE per leisure hour).
#   E[a]   = n / (n + EVAL_N0) * (Q[a] - R): how much better than leisure in general it felt,
#          weighted by confidence. Bounded in [-1, 1]; 0 when never lived.
# It enters ONE decision entry, the activity score (not goal formation), as
#   EVAL_WEIGHT * E[a] * need gate * (1 - home need)    (needs and the home come first).
EVAL_KEYS = ('read', 'garden')
EVAL_WEIGHT = 60.0           # = PREF_WEIGHT: same bound as the v5 liking at 1 (fixed by rule, not tuned)
EVAL_ALPHA_MIN = 0.05        # learning-rate floor: ~20 recent experiences dominate (plasticity)
EVAL_BASE_RATE = 0.02        # baseline update per leisure hour (~5 days of leisure)
EVAL_N0 = 10.0               # experiences for half confidence
EVAL_KEEP = 0.98             # daily keep of n (half-life ~34 days without the activity: no permanent lock)
# Experiment 'reading outcome' (2026-10-23, round 3, pet/validate_read.py; NOT a rule version).
# One real result of reading: comprehension. Each lived reading hour understands
#   gain = book clarity x focus,   focus = need gate before the hour (hunger / energy), in [0, 1]
# and adds it to book_progress (a recorded result). Clarity is a property of the book the player
# offers (world.p['book_clarity'], READ_CLARITY_DEFAULT if unset): the same rule for every pet; it
# never depends on the pet's history, route or counts (reading more does not raise the gain).
# Reading value V learns only from those results: V <- V + alpha (gain - V), alpha as EVAL_*,
# n experiences kept EVAL_KEEP a day. Its term in the READ score only:
#   READ_VALUE_WEIGHT * n/(n + EVAL_N0) * (V - READ_VALUE_REF) * need gate * (1 - home need).
# Recent habit (read_habit: pure frequency per leisure hour) is recorded and never decides.
READ_CLARITY_DEFAULT = 0.6   # the standard book
READ_VALUE_REF = 0.5         # neutral result (middle of the gain scale): above it reading has paid off
READ_VALUE_WEIGHT = 60.0     # = PREF_WEIGHT (same bound as the v5 liking; fixed by rule, not tuned)
# Experiment 'reading interest' (2026-10-23, round 4, pet/validate_interest.py; NOT a rule version).
# Two things kept apart: the short-term result evaluation S (= read_V above: what reading has given
# lately, ~20 results) and a long-term interest I. I starts neutral (READ_VALUE_REF) and learns only
# from S, once a day (consolidation), and only as far as S is CLEAR evidence:
#   w = n/(n + EVAL_N0) * |S - REF| / REF                 (0 = no or neutral results, 1 = confident and extreme)
#   I <- I + INTEREST_RATE * w * (S - I)                  (days with at least one reading result)
#   I <- REF + (I - REF) * EVAL_KEEP                      (days without reading: fades, no permanent lock)
# So ordinary, neutral reading does not rewrite what earlier clear results taught, while clearly
# different results do (a lower learning rate would slow both). Nothing is set by route or count.
# Decision: the SAME single read-score term and bound as the round-3 value, with S replaced by the
# mean of the two (no second bonus): READ_VALUE_WEIGHT * (conf * (S - REF) + (I - REF)) / 2 * gates.
INTEREST_RATE = 1 / 7        # one week of fully clear results consolidates ~63% (fixed by rule, not tuned)
READ_LOWRATE_ALPHA_MIN = 0.01   # control 'just a lower learning rate': the single value with a 5x lower floor
# Round 5 (2026-10-25, pet/diag_interest.py; diagnostics, NOT a rule version). explain_read_value()
# re-made the choice without the reading term only when the CHOSEN action carried it, so a negative
# term that pushed the pet from reading to something else was never counted (hard-book pets 3001,
# 6006, 6010: 51 / 35 / 74 such hours in 60 days, logged 0). With PetAgent.read_audit the whole
# choice is re-made every hour and every legal candidate's parts are recorded. Pure: no state, no
# random draw. pref_score_off / pref_goal_off / goal_read_bonus_off split the v5 liking and the plan
# channels for ablations on copies; all off by default.
LEISURE_GOALS = ('learn', 'see_the_world')   # = core DISCRETIONARY_GOALS
# Experiment 'home foresight' (2026-10-25, round 8, pet/validate_foresight.py; NOT a rule version).
# When the ordered morning update would START a leisure plan (no plan, or a different type than the open
# one), it first projects the home over the plan's minimum stay with the known ageing and no repair:
#   projected = shelter - SHELTER_AGEING * 24 * core.GOAL_MIN_DAYS          (= shelter - 16.8)
# using the home at the entry of the update (before that hour's ageing). If projected < HOME_FORESIGHT_FLOOR,
# that leisure candidate is left out and the existing rules choose among the rest (same sort, same tie
# order as without it; no candidate left = no new plan, as the core does with no candidate). Continuing
# the open plan is never affected. Pure: it reads only the current state, no future event, no random draw.
SHELTER_AGEING = 0.35        # per hour, = sim.Agent.tick's ageing (no named constant there; checked in tests)
HOME_FORESIGHT_FLOOR = 20    # = the v4 safe-home standard's 'below 20' line (fixed by rule, not tuned)
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
        # The neighbor's visiting rule, set by the rule version; experiments change it on copies.
        # Invitations skip both limits.
        v6 = rules >= 6
        self.visit_cap = None if v6 else MILI_VISITS_PER_DAY   # unprompted visits per day (None = no daily cap)
        self.visit_rest_hours = V6_REST_HOURS if v6 else 0     # hours she rests after a shared activity
        self.home_interrupt = v6                 # a run-down home may end a leisure plan early
        self.goal_pause = False                  # experiment 'pause': the interrupt stashes the plan instead
        self.interrupt_open_only = False         # diagnostic arm: end only plans the core would not close today
        self.ordered_goals = False               # experiment base 'ordered': done / stalled / switched in order
        self.home_emergency_unmute = False       # experiment base: no improve_home satiation below HOME_INTERRUPT_BELOW
        self.emergency_no_margin = False         # experiment base2: below HOME_INTERRUPT_BELOW the trigger needs no switch margin
        self.home_foresight = False              # experiment round 8: no new leisure plan the home would not outlast (ordered only)
        # Experiment 'reading outcome' (see READ_*). Off for every rule version.
        self.reading_outcome = False
        self.read_value_in_decision = True       # ablation: False = world and learning as usual, never in a choice
        self.read_value_flat = False             # ablation: the same term on read AND explore (no activity information)
        self.read_value_learning = True
        self.read_V, self.read_n, self.read_habit, self.book_progress = 0.0, 0.0, 0.0, 0.0
        self.read_evidence = {'count': 0, 'recent_ids': []}
        # Experiment 'reading interest' (see INTEREST_*). Off for every rule version.
        self.read_interest = False               # learn the long-term interest I
        self.read_interest_in_decision = True    # ablation: False = I learnt, the term stays the round-3 one
        self.read_alpha_min = EVAL_ALPHA_MIN     # control: READ_LOWRATE_ALPHA_MIN = single value, lower rate
        self.read_I, self.read_today = READ_VALUE_REF, 0
        # Round 5 diagnostics (see above). Off for every rule version.
        self.read_audit = False                  # full counterfactual + candidate parts in every decision record
        self.pref_score_off = False              # ablation: v5 liking out of action scores only
        self.pref_goal_off = False               # ablation: v5 liking out of goal formation only
        self.goal_read_bonus_off = False         # ablation: the current plan neither boosts nor damps 'read'
        # Round 6 (2026-10-25, pet/diag_plan.py): the two halves of goal_read_bonus_off, apart.
        self.goal_read_offtask_off = False       # ablation: a plan without a 'read' weight no longer damps 'read'
        self.goal_read_learn_bonus_off = False   # ablation: a plan with a 'read' weight ('learn') no longer boosts it
        # Experiment 'evaluation' (see EVAL_*). Off for every rule version.
        self.evaluation = False                  # learn and record Q
        self.eval_in_decision = True             # ablation: False = learns, never used in choices
        self.eval_learning = True                # ablation: False = keeps acting, stops learning
        self.eval_flat = False                   # ablation: same mean term for both (no activity information)
        self.Q = {k: 0.0 for k in EVAL_KEYS}
        self.eval_n = {k: 0.0 for k in EVAL_KEYS}
        self.eval_evidence = {k: {'count': 0, 'recent_ids': []} for k in EVAL_KEYS}
        self.eval_base = None
        # Diagnostics only, never read by decisions: pure recent frequency (habit) and Q with the
        # freshness-weighted signal, to test whether Q is just another frequency code.
        self.habit = {k: 0.0 for k in EVAL_KEYS}
        self.Q_fresh = {k: 0.0 for k in EVAL_KEYS}
        self.paused_goal = None                  # at most one stashed plan (no task stack)
        self.plan_log = []                       # interrupts, pauses, resumes, drops; decisions never read it
        self.freeze_prefs = False                # validation only: preferences keep acting, stop learning
        self.diagnostics = False                 # validation only: add 'social_diag' to events, log would-be interrupts

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
        if self.home_emergency_unmute and self.shelter < HOME_INTERRUPT_BELOW:
            # Experiment base: in a home emergency the refractory after a finished or 'stalled'
            # repair no longer mutes improve_home. Under decay (8.4 a day) a repair finished at 80,
            # or 'stalled' because no level beat the old best, was muted 6 days while the home
            # fell to 0-3 (dev 6008, 6009, 6006). Pure: no random draw.
            out = [(g, pri + self._satiation(g, day) if g == 'improve_home' else pri, src) for g, pri, src in out]
        if self.rules < 5 or self.pref_off or self.pref_goal_off:
            if self.pref_goal_off:
                self.goal_pref_boost = {}
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
        if self.ordered_goals:
            return self._update_goal_ordered(day)
        before = self.goal
        paused_before = self.paused_goal
        if ((self.home_interrupt or self.diagnostics) and self.shelter < HOME_INTERRUPT_BELOW
                and self.goal is not None and self.goal['type'] in LEISURE_GOALS):
            # A leisure plan is kept for GOAL_MIN_DAYS; meanwhile the home lost ~17 points and fell
            # from 20 to 3 (seed 3007). Like hunger, a run-down home may end it early, but only when
            # improve_home clearly outranks it (the core's own switch margin). Pure: no random draw.
            # Only when the home is really low: cutting plans at any level of need also cut nearly
            # every multi-day 'learn' plan (reading route - control gap 2.9 -> 0.9 pp on dev seeds).
            pri = {g: p for g, p, _ in self.propose_goals(day)}
            if pri.get('improve_home', -math.inf) >= pri.get(self.goal['type'], 0.0) + core.GOAL_SWITCH_MARGIN:
                closing = self._core_closes(self.goal, day)
                if not self.home_interrupt:
                    # Diagnostics only (v5 rule): the trigger held but the plan goes on.
                    self._plan_log(day, 'trigger_kept', self.goal, pri=pri, core_closes=closing)
                elif (self.goal_pause or self.interrupt_open_only) and closing:
                    # v6 ends such a plan as 'switched' (kept as recorded), which skips the core's
                    # 'done' memory and satiation. A pause must not hide a finished or failed plan:
                    # the core closes it this morning as usual.
                    self._plan_log(day, 'not_interrupted', self.goal, pri=pri, reason=closing)
                elif self.goal_pause and self.goal.get('resumes', 0) < PAUSE_MAX_RESUMES:
                    self._pause_goal(day, pri)
                else:
                    self._plan_log(day, 'ended', self.goal, pri=pri, core_closes=closing,
                                   reason='resume_limit' if self.goal_pause else 'interrupt')
                    self._close_goal(day, 'switched')
        super().update_goal(day)
        if self.paused_goal is not None and self.paused_goal is paused_before:
            self._review_paused(day)
        if self.rules >= 5 and self.goal is not None and self.goal is not before:
            # Trace on the goal itself how much long-term liking went into choosing it.
            self.goal['pref_boost'] = round(getattr(self, 'goal_pref_boost', {}).get(self.goal['type'], 0.0), 4)

    # ---- experiment base 'ordered' (2026-10-24): goal endings in the right order
    def _update_goal_ordered(self, day):
        """The core's morning goal update (sim.Agent.update_goal) with its endings in order:
        1. a finished plan ends 'done' (memory + satiation), a really stalled one 'stalled';
        2. only an open leisure plan may then end 'switched' under the v6 home trigger;
        3. candidates are re-proposed AFTER any ending, so satiation and the new state count.
        Every goal ends once. The core instead picked the next goal from the priorities of
        before the ending (a finished plan could be re-picked the same morning), and v6 ended
        finished plans as 'switched', skipping 'done' and its 6-day satiation. No random draw."""
        before = self.goal
        g = self.goal
        if g is not None:
            prog = self.goal_progress(g)
            if prog > g.get('best_progress', -1.0) + 1e-9:
                g['best_progress'] = prog
                g['last_gain_day'] = day
            g['progress'] = prog
            if prog >= 1.0:
                self._plan_log(day, 'closed', g, reason='done')
                self._close_goal(day, 'done')
            elif day - g.get('last_gain_day', day) >= core.GOAL_STALL_DAYS:
                self._plan_log(day, 'closed', g, reason='stalled')
                self._close_goal(day, 'stalled')
        cands = self.propose_goals(day)
        pri = {t: p for t, p, _ in cands}
        g = self.goal
        if (g is not None and self.home_interrupt and self.shelter < HOME_INTERRUPT_BELOW
                and g['type'] in LEISURE_GOALS
                and pri.get('improve_home', -math.inf) >= pri.get(g['type'], 0.0)
                + (0.0 if self.emergency_no_margin else core.GOAL_SWITCH_MARGIN)):
            # base2: in the emergency the repair only has to be ahead. The switch margin is
            # hysteresis between comparable plans; with the home at 12-15 a new leisure plan ahead
            # of it by less than 0.25 kept the repair waiting (eval arm, dev 6006: 12.0 -> 3.6).
            self._plan_log(day, 'ended', g, pri=pri, reason='interrupt')
            self._close_goal(day, 'switched')
            cands = self.propose_goals(day)
        if self.home_foresight and cands:
            cands = self._foresight_filter(cands, day)
        if cands:
            cands.sort(key=lambda x: -x[1])
            best_type, best_pri, best_src = cands[0]
            g = self.goal
            if g is None:
                self.goal = self._new_goal(best_type, best_pri, best_src, day)
            elif day - g['created_day'] < core.GOAL_MIN_DAYS:
                pass                                   # still in the core's minimum stay
            elif best_type != g['type']:
                cur = next((p for t, p, _ in cands if t == g['type']), 0.0)
                if best_pri >= cur + core.GOAL_SWITCH_MARGIN:
                    self._close_goal(day, 'switched')
                    self.goal = self._new_goal(best_type, best_pri, best_src, day)
            else:
                g['priority'] = best_pri
        if self.rules >= 5 and self.goal is not None and self.goal is not before:
            self.goal['pref_boost'] = round(getattr(self, 'goal_pref_boost', {}).get(self.goal['type'], 0.0), 4)

    def foresight_projection(self):
        return self.shelter - SHELTER_AGEING * 24 * core.GOAL_MIN_DAYS

    def _foresight_filter(self, cands, day):
        """Experiment 'home foresight': leave out leisure plans that would START with a home that cannot stay
        >= HOME_FORESIGHT_FLOOR over GOAL_MIN_DAYS without repair. Order of the rest unchanged."""
        proj = self.foresight_projection()
        if proj >= HOME_FORESIGHT_FLOOR:
            return cands
        cur = self.goal['type'] if self.goal else None
        kept = [c for c in cands if c[0] not in LEISURE_GOALS or c[0] == cur]
        if len(kept) != len(cands):
            self._plan_log(day, 'foresight_excluded', self.goal, projected=proj,
                           excluded=[c[0] for c in cands if c not in kept], left=[c[0] for c in kept])
        return kept

    # ---- experiment 'pause': stash the interrupted plan, re-weigh it after the repair
    def _plan_log(self, day, event, goal, **extra):
        """Validation trace. Appends only: no decision reads it and it draws no random number."""
        self.plan_log.append({'day': day, 'tick': self.now, 'event': event,
                              'plan_id': goal.get('plan_id') if goal else None,
                              'type': goal['type'] if goal else None, 'home': self.shelter,
                              'progress': self.goal_progress(goal) if goal else None, **extra})

    def _core_closes(self, goal, day):
        """'done' / 'stalled' if the core's update_goal would close this plan this morning
        (same tests, read-only), else None."""
        prog = self.goal_progress(goal)
        if prog >= 1.0:
            return 'done'
        gained = prog > goal.get('best_progress', -1.0) + 1e-9
        if not gained and day - goal.get('last_gain_day', day) >= core.GOAL_STALL_DAYS:
            return 'stalled'
        return None

    def _pause_goal(self, day, pri):
        """Stash the current leisure plan: no outcome, satiation, memory or reward is written,
        so nothing reads as done, failed or learnt. Its count progress is frozen while paused."""
        g = self.goal
        g.setdefault('plan_id', f"{g['type']}@{g['created_day']}")   # one goal is created per day at most
        if self.paused_goal is not None:                                # at most one stashed plan
            self._plan_log(day, 'dropped', self.paused_goal['goal'], reason='superseded')
        act = self.GOAL_COUNT_TARGET[g['type']][0]
        self.paused_goal = {'goal': g, 'day': day, 'tick': self.now, 'reason': 'home_low',
                            'home': self.shelter, 'progress': self.goal_progress(g),
                            'count_at_pause': self.action_log[act]}
        self._plan_log(day, 'paused', g, reason='home_low', pri=pri)
        self.goal = None

    def _review_paused(self, day):
        """Each morning after the pause day: resume, keep waiting, or drop the stashed plan.
        Fresh priorities only; the plan's old score is never reused. Body needs come first."""
        P = self.paused_goal
        g = P['goal']
        if day - P['day'] > PAUSE_MAX_DAYS:
            return self._drop_paused(day, 'expired')
        pri = {t: p for t, p, _ in self.propose_goals(day)}
        if g['type'] not in pri:                     # e.g. the book is gone: the plan cannot go on
            return self._drop_paused(day, 'invalid')
        if self.shelter < PAUSE_RESUME_AT:
            return self._plan_log(day, 'waiting', g, reason='home', pri=pri)
        best = max(pri, key=lambda t: (pri[t], t))
        if best != g['type']:
            if best in LEISURE_GOALS:                # another leisure plan is now worth more
                return self._drop_paused(day, 'replaced', by=best, pri=pri)
            # A need (home, food, body) still outranks it: wait, it may come back later.
            return self._plan_log(day, 'waiting', g, reason=best, pri=pri)
        if pri[best] <= 0:                           # no slack at all: body first
            return self._plan_log(day, 'waiting', g, reason='no_slack', pri=pri)
        # Resume. The repair goal the core kept (hysteresis) ends as an ordinary switch; a
        # same-type plan the core formed this very morning is replaced by the stashed one.
        if self.goal is not None:
            replaced = self.goal['type']
            if not (replaced == g['type'] and self.goal['created_day'] == day):
                self._close_goal(day, 'switched')
            self.goal = None
        shift = day - P['day']
        act = self.GOAL_COUNT_TARGET[g['type']][0]
        g['start'] += self.action_log[act] - P['count_at_pause']   # progress = what the plan did
        g['created_day'] += shift                                  # age counts active days only
        if 'last_gain_day' in g:
            g['last_gain_day'] += shift                            # so no false 'stalled' on return
        g['priority'] = pri[best]
        g['resumes'] = g.get('resumes', 0) + 1
        g['paused_days'] = g.get('paused_days', 0) + shift
        self.paused_goal = None
        self.goal = g
        self._plan_log(day, 'resumed', g, pri=pri, paused_days=shift)

    def _drop_paused(self, day, why, **extra):
        self._plan_log(day, 'dropped', self.paused_goal['goal'], reason=why, **extra)
        self.paused_goal = None

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
        if self.rules < 5 or self.pref_off or self.pref_score_off:
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

    # ---- experiment 'evaluation'
    def eval_term(self, key):
        """E[key] = confidence * (Q - baseline), in [-1, 1]; 0 if never lived or no baseline."""
        n = self.eval_n[key]
        if self.eval_base is None or n <= 0:
            return 0.0
        return n / (n + EVAL_N0) * (self.Q[key] - self.eval_base)

    def evaluation_part(self, action):
        if not (self.evaluation and self.eval_in_decision):
            return 0.0, None
        if action == 'read':
            key = 'read'
        elif action == 'explore' and self.world.has('garden'):
            key = 'garden'
        else:
            return 0.0, None
        e = (sum(self.eval_term(k) for k in EVAL_KEYS) / len(EVAL_KEYS)) if self.eval_flat else self.eval_term(key)
        return EVAL_WEIGHT * e * self.need_gate() * (1 - self.home_need()), key

    def evaluate_experience(self, outcome, event_id, comfort, enjoyment):
        """One lived leisure hour. Only the activity really done gets evidence; doing one is
        never a negative experience of the other."""
        if not self.eval_learning:
            return
        self.eval_base = comfort if self.eval_base is None else self.eval_base + EVAL_BASE_RATE * (comfort - self.eval_base)
        for k in EVAL_KEYS:
            self.habit[k] += PREF_RATE * ((1.0 if k == outcome else 0.0) - self.habit[k])
        if outcome in EVAL_KEYS:
            n = self.eval_n[outcome]
            alpha = max(1.0 / (n + 1.0), EVAL_ALPHA_MIN)
            self.Q[outcome] += alpha * (comfort - self.Q[outcome])
            self.Q_fresh[outcome] += alpha * (enjoyment - self.Q_fresh[outcome])
            self.eval_n[outcome] = n + 1.0
            ev = self.eval_evidence[outcome]
            ev['count'] += 1
            ev['recent_ids'] = (ev['recent_ids'] + [event_id])[-3:]

    def daily(self, day):
        super().daily(day)
        if self.evaluation and self.eval_learning:
            for k in EVAL_KEYS:
                self.eval_n[k] *= EVAL_KEEP
        if self.reading_outcome and self.read_value_learning:
            if self.read_interest:
                self.consolidate_interest()
            self.read_n *= EVAL_KEEP

    # ---- experiment 'reading outcome'
    def read_clarity(self):
        return self.world.p.get('book_clarity', READ_CLARITY_DEFAULT)

    def read_value_term(self):
        n = self.read_n
        short = 0.0 if n <= 0 else n / (n + EVAL_N0) * (self.read_V - READ_VALUE_REF)
        if self.read_interest and self.read_interest_in_decision:
            return (short + self.read_I - READ_VALUE_REF) / 2       # same bound [-0.5, 0.5]
        return short

    def interest_weight(self):
        """How clear the short-term evaluation is as evidence: confidence x distance from neutral."""
        n = self.read_n
        return 0.0 if n <= 0 else n / (n + EVAL_N0) * abs(self.read_V - READ_VALUE_REF) / READ_VALUE_REF

    def consolidate_interest(self):
        """Once a day, before the day's confidence decay. Pure: no random draw."""
        if self.read_today:
            self.read_I += INTEREST_RATE * self.interest_weight() * (self.read_V - self.read_I)
        else:
            self.read_I = READ_VALUE_REF + (self.read_I - READ_VALUE_REF) * EVAL_KEEP
        self.read_today = 0

    def read_value_part(self, action):
        if not (self.reading_outcome and self.read_value_in_decision):
            return 0.0, None
        if action == 'read' or (self.read_value_flat and action == 'explore'):
            return READ_VALUE_WEIGHT * self.read_value_term() * self.need_gate() * (1 - self.home_need()), action
        return 0.0, None

    def read_experience(self, outcome, event_id, result):
        """One lived leisure hour: habit (diagnostic) always; value and progress only from a real reading result."""
        if not self.read_value_learning:
            return
        self.read_habit += PREF_RATE * ((1.0 if outcome == 'read' else 0.0) - self.read_habit)
        if result is None:
            return
        self.book_progress += result['gain']
        alpha = max(1.0 / (self.read_n + 1.0), self.read_alpha_min)
        self.read_V += alpha * (result['gain'] - self.read_V)
        self.read_n += 1.0
        self.read_today += 1
        ev = self.read_evidence
        ev['count'] += 1
        ev['recent_ids'] = (ev['recent_ids'] + [event_id])[-3:]

    def choice_without_read_value(self, day):
        saved = self.read_value_in_decision
        self.read_value_in_decision = False
        try:
            return self.choose(day)
        finally:
            self.read_value_in_decision = saved

    def choice_without_evaluation(self, day):
        """Counterfactual: the whole legal choice re-made with the evaluation term off."""
        saved = self.eval_in_decision
        self.eval_in_decision = False
        try:
            return self.choose(day)
        finally:
            self.eval_in_decision = saved

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
        if self.evaluation:
            p['evaluation'], p['eval_key'] = self.evaluation_part(action)
            p['final'] += p['evaluation']
        if self.reading_outcome:
            p['read_value'], p['read_value_on'] = self.read_value_part(action)
            p['final'] += p['read_value']
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
                **(self.explain_evaluation(action, day, p) if self.evaluation else {}),
                **(self.explain_read_value(action, day, p) if self.reading_outcome else {}),
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

    def explain_evaluation(self, action, day, p):
        key = p.get('eval_key')
        rec = {'evaluation': round(p.get('evaluation', 0.0), 4), 'eval_key': key, 'eval_decisive': False,
               'eval_choice_without': None}
        if key:
            ev = self.eval_evidence[key]
            rec.update(eval_Q=round(self.Q[key], 4), eval_n=round(self.eval_n[key], 2),
                       eval_base=None if self.eval_base is None else round(self.eval_base, 4),
                       eval_experiences=ev['count'], eval_recent_ids=list(ev['recent_ids']))
        if p.get('evaluation'):
            without = self.choice_without_evaluation(day)
            rec['eval_decisive'] = without != action
            rec['eval_choice_without'] = without
        return rec

    def explain_read_value(self, action, day, p):
        rec = {'read_value': round(p.get('read_value', 0.0), 4), 'read_V': round(self.read_V, 4),
               **({'read_I': round(self.read_I, 4)} if self.read_interest else {}),
               'read_n': round(self.read_n, 2), 'read_experiences': self.read_evidence['count'],
               'read_recent_ids': list(self.read_evidence['recent_ids']), 'read_value_decisive': False,
               'read_value_choice_without': None}
        if p.get('read_value'):
            without = self.choice_without_read_value(day)
            rec['read_value_decisive'] = without != action
            rec['read_value_choice_without'] = without
        if self.read_audit:
            rec['audit'] = self.read_audit_record(action, day)
        return rec

    # ---- round 5 diagnostics
    def goal_bonus(self, action):
        if action == 'read' and self.goal is not None:
            boosts = bool(core.GOAL_ACTIONS.get(self.goal['type'], {}).get('read'))     # only 'learn'
            if (self.goal_read_bonus_off or (boosts and self.goal_read_learn_bonus_off)
                    or (not boosts and self.goal_read_offtask_off)):
                return 0.0
        return super().goal_bonus(action)

    def read_term_parts(self):
        """(S part, I part) of read_value_term(): the short-term evaluation and the long-term interest."""
        n = self.read_n
        short = 0.0 if n <= 0 else n / (n + EVAL_N0) * (self.read_V - READ_VALUE_REF)
        if self.read_interest and self.read_interest_in_decision:
            return short / 2, (self.read_I - READ_VALUE_REF) / 2
        return short, 0.0

    def _choice_with(self, day, **tmp):
        """The whole legal choice re-made with some attributes set for the moment (restored after)."""
        saved = {k: getattr(self, k) for k in tmp}
        try:
            for k, v in tmp.items():
                setattr(self, k, v)
            return self.choose(day)
        finally:
            for k, v in saved.items():
                setattr(self, k, v)

    def read_audit_record(self, action, day):
        """Every legal candidate's score; read's rank, its gap to the chosen action, its parts, and the
        whole choice re-made without each part. Promote / suppress: the reading term made the pet read /
        kept it from reading. Pure (the tests check state and rng)."""
        sc = {a: s for a in core.ACTIONS for s in [self.score(a, day)] if s is not None}
        order = sorted(sc, key=lambda a: (sc[a], a), reverse=True)
        rec = {'chosen': action, 'scores': sc}
        if 'read' not in sc:
            return rec
        gate = self.need_gate() * (1 - self.home_need()) if self.reading_outcome and self.read_value_in_decision else 0.0
        s_raw, i_raw = self.read_term_parts()
        pref, _ = self.preference_part('read', day)
        rival = max(sc[a] for a in sc if a != 'read') if len(sc) > 1 else None
        rec.update(read_rank=order.index('read') + 1, read_gap=sc['read'] - (sc[action] if action != 'read' else rival),
                   S=READ_VALUE_WEIGHT * s_raw * gate, I=READ_VALUE_WEIGHT * i_raw * gate, pref=pref,
                   goal=self.goal_bonus('read'), goal_type=self.goal['type'] if self.goal else None,
                   boredom=self.boredom('read'), gate=self.need_gate(), home_need=self.home_need(),
                   body=(self.hunger, self.energy, self.shelter))
        cf = {'term': self._choice_with(day, read_value_in_decision=False),
              'S': self._choice_with(day, read_n=0.0),
              'I': self._choice_with(day, read_I=READ_VALUE_REF),
              'pref': self._choice_with(day, pref_score_off=True),
              'goal': self._choice_with(day, goal_read_bonus_off=True)}
        rec['without'] = cf
        rec['effect'] = {k: ('promote' if action == 'read' and w != 'read' else
                             'suppress' if action != 'read' and w == 'read' else
                             'other' if w != action else None) for k, w in cf.items()}
        return rec

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
        comfort = self.need_gate()                 # experiment 'evaluation': state while doing it
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
        if self.evaluation:
            self.last['comfort'] = comfort
        if self.reading_outcome:
            self.last['read_outcome'] = ({'gain': self.read_clarity() * comfort, 'clarity': self.read_clarity(),
                                          'focus': comfort} if action == 'read' else None)
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
        if a.evaluation and move['core_action'] in LEISURE:
            a.evaluate_experience(action, e['id'], move['comfort'], move['enjoyment'])
        if a.reading_outcome and move['core_action'] in LEISURE:
            a.read_experience(action, e['id'], move['read_outcome'])
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
