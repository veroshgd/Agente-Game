"""Round 13 of 2026-10-25: causal diagnosis of why memory changes show so little in behaviour.
Diagnostics only: no product candidate, no validation, no criterion of rounds 11-12 changed.
Development seeds 3001-3010 + 6001-6010 only. Default stays v5; every switch here is off by default.

    python -m pet.diag_round13 [out_dir]      # default docs/pet_round13; refuses to overwrite

Agent: DiagPetAgent subclasses round 12's SocialPetAgentB2 (round 11-12 files are not edited). With every
switch off it is B2 exactly (tests; and the run checks R1/R2 per seed against round 12's saved result).

PROTOCOL, FIXED 2026-10-25 BEFORE ANY RUN OF THIS MODULE (sha256 in docs/pet_round13/)

Part 1 - reading: does the count close of 'learn' and the satiation after it limit cumulative adaptation?
  Code reviewed (engine PetAgent._update_goal_ordered, sim.Agent._close_goal / _satiation):
    a 'learn' plan ends 'done' at the morning update once 12 reads were made since it started; _close_goal
    then writes goal_satiation['learn'] = day, and propose_goals subtracts 0.9 * (6 - days since) / 6 from
    learn's priority for 6 days. A plan with no progress gain for 4 days ends 'stalled' (also satiation).
    Boredom (engine BOREDOM, repetition in the last 24 h, on the hourly score) is a different mechanism.
  Interventions (from the common day-30 state, days 30-60 only):
    current     B2 as it is
    no_close    the 'done' close of a learn plan by count is skipped (learn_no_count_close); the plan goes on
    no_sat      a learn 'done' close writes no new satiation (learn_no_done_satiation); the old value stays
    both        both switches
  Kept: the learn bonus, switching (min stay, margin), the stall exit and its satiation, needs, home
  protections, boredom, every memory formula, weight and rate. No read is forced, no plan is kept on.
  Documented dependencies (limit causal reading): (i) the core tests the stall exit only in the else-branch
  of the count test; under no_close the stall exit is therefore applied explicitly at that point with the
  unchanged rule. The plan's progress stays clamped at 1.0 after 12 reads, so the stall rule ends it 4
  days later as 'stalled', WITH the stall satiation, unless a switch comes first: no_close replaces
  "done at 12 + done satiation" by "up to 4 more days + stall satiation" (or an earlier 'switched' with no
  satiation); it does not remove satiation altogether; the 'done' memory is not written.
  (ii) no_sat only acts at learn 'done' closes; under no_close there are none, so 'both' is predicted to be
  identical to 'no_close' (checked: identical lives); its interaction is then -(no_sat effect) by design.
  (iii) a satiation written before day 30 stays as it was in every condition (identical starting states).
  Design: the B2 round-12 design (2 x 2 cells, growth, 30 common days, actual + 5 reseeded continuations
  from common day 0); at common day 30 every condition starts from the SAME copies, branches keep and
  read_change, 30 days.
  Primary contrast (per birth seed, cells and continuations averaged first; bootstrap 95 %):
    dR1(X) = R1(X) - R1(current), X in no_close, no_sat, both;  interaction = R1(both) - R1(no_close) -
    R1(no_sat) + R1(current). R1 = book effect on read share, read_change - keep, days 30-60 (round 11).
  Interpretation rule: a factor is SUPPORTED as limiting adaptation if dR1 <= -0.5 pp with CI upper < 0
  (more adaptation); 'not supported' if dR1 CI includes 0 or is > 0; a level change of reading alone is
  not adaptation. Conditions with more phase-safety failures or any whole-life failure than current are
  flagged as not product options. If no factor is supported: "mecanismo no identificado con este diagnóstico".
  Recorded: reads per day and in total, inside / outside learn, every plan in days 30-60 (start, end,
  duration, progress, outcome), the learn satiation at each morning (after the update), per hour the
  memory (S + I), plan and boredom contributions to the read score and the instant memory effect
  (promote / suppress), days without reading and the per-pet distribution, needs, upkeep, home and the
  v4 safety checks of each 30-day branch phase and of the whole life.

Part 2 - social: going out (B2: max(g, s + t)) and the later visit draw (unchanged chance).
  Instrumented on B2 and B2+A trajectories, pure (no decision changed, no extra random number; the draw is
  the one act() already makes, read back from the event): her availability, g, s, t, which option wins
  the max with and without t, explore chosen, visit chance (and, on the same state, the chance with and
  without the A entry), the draw's outcome, final activity, spontaneous vs invited.
  Counted per seed: (a) t < 0 had no effect on going out because garden dominated both with and without t,
  and the hour ended in a visit; (b) t raised the explore score and the hour ended in garden.
  Factorial (from identical common day-0 states, the round-11/12 design, branches keep and social_change):
    ref (no social entry), B2, A (round 11's A entry), B2A (both; diagnostic: same signal in two stages).
  Contrasts per seed: neighbor effects on going out (explore in available hours), spontaneous visits,
  reading, garden; R2 and its paired differences; interaction = B2A - B2 - A + ref. Visits per outing are
  descriptive (who goes out changes); the same-state chance comparison complements it.
  Interpretation rule: A adds social adaptation beyond B2 if R2(B2A) - R2(B2) <= -1/14 with CI upper < 0;
  amplification is flagged if the interaction's CI excludes 0 with the sign of the main effects.
Immediate (same state) and cumulative (whole trajectory) effects are reported apart and never stand for each
other. Once actions diverge, later events are not the same even with the same seed.
"""
import copy
import hashlib
import json
import sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

from . import engine
from . import lifestats as L
from . import validate_read as VR
from . import validate_social as VS
from . import validate_social_b2 as VB
from .engine import core
from .social_interest_b2 import SocialPetAgentB2

ROOT = Path(__file__).resolve().parents[1]
R12 = ROOT / 'docs' / 'pet_social_b2' / 'social_b2_dev_result.json'
R11 = ROOT / 'docs' / 'pet_social' / 'social_dev_result.json'
SEEDS = VS.DEV_SEEDS
READ_CONDS = {'current': {}, 'no_close': {'learn_no_count_close': True}, 'no_sat': {'learn_no_done_satiation': True},
              'both': {'learn_no_count_close': True, 'learn_no_done_satiation': True}}
SOCIAL_ARMS = {'ref': {}, 'B2': {'entry': 'B2'}, 'A': {'entry': 'A'}, 'B2A': {'entry': 'B2', 'entry_A': True}}
SUPPORT_DR1 = -0.005
SUPPORT_DR2 = -1 / 14


class DiagPetAgent(SocialPetAgentB2):
    def __init__(self, seed, world, rules=engine.RULES):
        super().__init__(seed, world, rules)
        self.learn_no_count_close = False
        self.learn_no_done_satiation = False
        self.entry_A = False
        self.social_trace = False
        self.social_rows = []
        self._skip_close = False

    # ---- reading interventions
    def _plan_log(self, day, event, goal, **extra):
        if (self.learn_no_count_close and event == 'closed' and extra.get('reason') == 'done' and goal
                and goal['type'] == 'learn'):
            # The core tests the stall exit only in the else-branch of the count test, so once the count is
            # reached it would never run. Keep it: the plan is closed 'stalled' (with its satiation) when the
            # unchanged stall rule holds, else it goes on.
            stalled = day - goal.get('last_gain_day', day) >= core.GOAL_STALL_DAYS
            self._skip_close = 'stalled' if stalled else 'skip'
            return super()._plan_log(day, 'count_close_neutralized_stalled' if stalled else 'count_close_neutralized', goal, **extra)
        return super()._plan_log(day, event, goal, **extra)

    def _close_goal(self, day, why):
        if self._skip_close:
            mode, self._skip_close = self._skip_close, False
            if mode == 'skip':
                return                                       # the plan goes on
            why = 'stalled'
        g = self.goal
        prev = self.goal_satiation.get('learn', None)
        super()._close_goal(day, why)
        if self.learn_no_done_satiation and why == 'done' and g is not None and g['type'] == 'learn':
            if prev is None:
                self.goal_satiation.pop('learn', None)
            else:
                self.goal_satiation['learn'] = prev

    # ---- A entry on top of B2
    def visit_chance(self, bonus):
        p, pref = super().visit_chance(bonus)
        if self.entry_A and self.social_entry != 'A' and self.exp_decide:
            raw = engine.VISIT_BASE + pref + bonus * engine.VISIT_MEMORY + engine.VISIT_PREF * self.social_term()
            p = max(engine.VISIT_MIN, min(engine.VISIT_MAX, raw))
        return p, pref

    def _chance_with(self, a_on):
        saved = (self.entry_A, self.social_entry)
        try:
            self.entry_A = a_on
            if not a_on and self.social_entry == 'A':
                self.social_entry = None
            return self.visit_chance(self.influence()[0])[0]
        finally:
            self.entry_A, self.social_entry = saved

    # ---- social instrumentation (pure)
    def act(self, action, day, hour=0):
        rec = None
        if self.social_trace and self.world.has('garden'):
            invited = self.now < self.invitation_until
            avail = self.can_meet(day, hour, invited)
            G = self.need_gate() * (1 - self.home_need())
            g = engine.PREF_WEIGHT * self.prefs['garden'] * G
            s = engine.PREF_WEIGHT * self.prefs['social'] * G
            t = engine.READ_VALUE_WEIGHT * self.social_term() * G
            rec = {'tick': self.now, 'avail': avail, 'invited': invited, 'g': g, 's': s, 't': t,
                   'win_without': 'social' if s > g else 'garden', 'win_with': 'social' if s + t > g else 'garden',
                   'delta': (max(g, s + t) - max(g, s)) if avail else 0.0, 'explore': action == 'explore',
                   'chance_A_on': self._chance_with(True) if avail else None,
                   'chance_A_off': self._chance_with(False) if avail else None}
        super().act(action, day, hour)
        if rec is not None:
            rec.update(outcome=self.last['action'], chance=(self.last.get('visit_chance') or {}).get('chance'),
                       drawn=(self.last.get('social_diag') or {}).get('drew'), wanted=(self.last.get('social_diag') or {}).get('wanted'))
            self.social_rows.append(rec)


class DiagSession(L.TracedSession):
    def __init__(self, seed=42, rules=engine.RULES):
        super().__init__(seed, rules)
        self.agent = DiagPetAgent(seed, self.world, rules)
        self.birth_traits = dict(self.agent.traits)


ALL_ARMS = {'B2': {'entry': 'B2'}, 'ref': {}, 'A': {'entry': 'A'}, 'B2A': {'entry': 'B2'}, 'none': {'no_read_term': True}}


def new_pet(seed, arm):
    s = VS.configure(DiagSession(seed, 5), arm)
    if arm == 'B2A':
        s.agent.entry_A = True
    return s


def patch():
    VS.new_pet, VS.ARMS, VS.CATALOGUE_ARMS = new_pet, ALL_ARMS, tuple(SOCIAL_ARMS)
    VS.CANDIDATE, VS.FROZEN = 'B2', 'B2'


def rng_digest(s):
    return hashlib.sha256(repr(s.agent.rng.getstate()).encode()).hexdigest()[:16]


# ---------------------------------------------------------------- part 1: reading factorial
def run_branch(x, days, instrument):
    """Day by day; morning record after the hour-0 step (after update_goal)."""
    a = x.agent
    if instrument:
        a.read_audit = True
    out = []
    for _ in range(days):
        n0, day = len(x.events), x.tick // 24
        VR.run_hours(x, 1)
        morning = {'goal': a.goal['type'] if a.goal else None, 'learn_sat': a._satiation('learn', day)}
        VR.run_hours(x, 23)
        if not instrument:
            continue
        ev = [e for e in x.events[n0:] if e['kind'] == 'action']
        au = [e['decision']['audit'] for e in ev]
        mean = lambda xs: sum(xs) / len(xs) if xs else None
        out.append({'reads': sum(e['core_action'] == 'read' for e in ev),
                    'reads_in_learn': sum(e['core_action'] == 'read' and u.get('goal_type') == 'learn' for e, u in zip(ev, au)),
                    'mem': mean([u['S'] + u['I'] for u in au if 'S' in u]), 'plan': mean([u['goal'] for u in au if 'S' in u]),
                    'boredom': mean([u['boredom'] for u in au if 'S' in u]),
                    'promote': sum(u.get('effect', {}).get('term') == 'promote' for u in au),
                    'suppress': sum(u.get('effect', {}).get('term') == 'suppress' for u in au),
                    'hunger': mean([u['body'][0] for u in au if 'body' in u]), 'energy': mean([u['body'][1] for u in au if 'body' in u]),
                    **morning})
    return out


def plans_in(a, d0):
    out = [{'type': g['type'], 'start': g['created_day'] - d0, 'end': g['closed_day'] - d0, 'outcome': g['outcome'],
            'progress': g.get('progress'), 'duration': g['closed_day'] - g['created_day']}
           for g in a.goal_history if g.get('closed_day', -1) >= d0]
    if a.goal:
        out.append({'type': a.goal['type'], 'start': a.goal['created_day'] - d0, 'end': None, 'outcome': 'open',
                    'progress': a.goal.get('progress'), 'duration': None})
    return out


def read_job(seed):
    pets, same, _ = VS.grow(seed, 'B2')
    res = {'seed': seed, 'same_growth': same, 'reps': [], 'instrument_ok': True, 'both_equals_no_close': True}
    for rep in range(VS.REPS + 1):
        cur = {}
        for c, p in pets.items():
            x = copy.deepcopy(p)
            if rep:
                x.agent.rng.seed(seed * 1000 + rep)
            VR.run_hours(x, VS.COMMON1 * 24)
            cur[c] = x
        R = {}
        for cond, flags in READ_CONDS.items():
            R[cond] = {}
            for br in ('keep', 'read_change'):
                R[cond][br] = {}
                for (b, n), x in cur.items():
                    pair = []
                    for instr in (True, False):
                        y = copy.deepcopy(x)
                        for k, v in flags.items():
                            setattr(y.agent, k, v)
                        if br == 'read_change':
                            y.world.p['book_clarity'] = VS.HARD if b == 'clear' else VS.CLEAR
                        y.phase(br)
                        d0, i0 = y.tick // 24, len(y.trace)
                        days = run_branch(y, VS.COMMON2, instr)
                        pair.append((y, days))
                    (y, days), (z, _) = pair
                    res['instrument_ok'] &= L.fingerprint(y.trace) == L.fingerprint(z.trace) and rng_digest(y) == rng_digest(z)
                    win = y.trace[i0:]
                    m = L.metrics(win)
                    rec = L.life_record(y, life_id=f'{cond}|{seed}|rep{rep}|{b}|{n}|{br}', cond=cond)
                    R[cond][br][f'{b}|{n}'] = {
                        'days': days, 'plans': plans_in(y.agent, d0), 'read': m['read'], 'upkeep': m['upkeep'], 'leisure': m['leisure'],
                        'min_home': m['min_home'], 'below20': m['below20'], 'fingerprint': rec['fingerprint'],
                        'h_pass': rec['h_pass'], 'branch_fails': rec['phases'][br]['fails'], 'whole_fails': rec['fails']}
        for br in ('keep', 'read_change'):
            for c in R['both'][br]:
                if R['both'][br][c]['fingerprint'] != R['no_close'][br][c]['fingerprint']:
                    res['both_equals_no_close'] = False
        res['reps'].append(R)
    return res


def book_effect(job, cond, br, key):
    """Per seed: mean over continuations and neighbor levels of clear - hard."""
    vals = []
    for R in job['reps']:
        X = R[cond][br]
        for n in ('warm', 'cold'):
            vals.append(X[f'clear|{n}'][key] - X[f'hard|{n}'][key])
    return sum(vals) / len(vals)


def summarise_read(jobs):
    jobs = sorted(jobs, key=lambda j: j['seed'])
    D = L.describe
    out = {'same_growth_all': all(j['same_growth'] for j in jobs), 'instrument_ok_all': all(j['instrument_ok'] for j in jobs),
           'both_equals_no_close_all': all(j['both_equals_no_close'] for j in jobs)}
    R1 = {c: [book_effect(j, c, 'read_change', 'read') - book_effect(j, c, 'keep', 'read') for j in jobs] for c in READ_CONDS}
    out['R1'] = {c: D(v) for c, v in R1.items()}
    out['dR1'] = {c: D([x - y for x, y in zip(R1[c], R1['current'])]) for c in READ_CONDS if c != 'current'}
    out['interaction'] = D([b - nc - ns + cu for b, nc, ns, cu in zip(R1['both'], R1['no_close'], R1['no_sat'], R1['current'])])
    out['_R1_per_seed'] = R1
    for c in READ_CONDS:
        for br in ('keep', 'read_change'):
            pets = [j['reps'][r][c][br][cell] for j in jobs for r in range(len(j['reps'])) for cell in j['reps'][r][c][br]]
            days = [d for p in pets for d in p['days']]
            reads = sorted(sum(d['reads'] for d in p['days']) for p in pets)
            plans = [pl for p in pets for pl in p['plans']]
            learn = [pl for pl in plans if pl['type'] == 'learn']
            q = lambda xs: [xs[0], xs[len(xs) // 4], xs[len(xs) // 2], xs[3 * len(xs) // 4], xs[-1]] if xs else None
            mean = lambda xs: (sum(xs) / len(xs)) if xs else None
            out[f'{c}|{br}'] = {
                'book_effect_read': D([book_effect(j, c, br, 'read') for j in jobs]),
                'read_level': D([mean([p['read'] for p in (j['reps'][r][c][br][cell] for r in range(len(j['reps'])) for cell in j['reps'][r][c][br])]) for j in jobs]),
                'reads_per_pet_q': q(reads), 'zero_read_pets': sum(x == 0 for x in reads), 'pets': len(pets),
                'days_without_reading_share': mean([d['reads'] == 0 for d in days]),
                'reads_in_learn_share': (sum(d['reads_in_learn'] for d in days) / max(1, sum(d['reads'] for d in days))),
                'learn_plans_per_pet': len(learn) / len(pets),
                'learn_outcomes': dict(Counter(pl['outcome'] for pl in learn)),
                'learn_duration_mean': mean([pl['duration'] for pl in learn if pl['duration'] is not None]),
                'learn_days_share': mean([d['goal'] == 'learn' for d in days]),
                'learn_sat_days_share': mean([d['learn_sat'] > 0 for d in days]),
                'mem_mean': mean([d['mem'] for d in days if d['mem'] is not None]),
                'plan_mean': mean([d['plan'] for d in days if d['plan'] is not None]),
                'boredom_mean': mean([d['boredom'] for d in days if d['boredom'] is not None]),
                'hunger_mean': mean([d['hunger'] for d in days if d['hunger'] is not None]),
                'energy_mean': mean([d['energy'] for d in days if d['energy'] is not None]),
                'upkeep_mean': mean([p['upkeep'] for p in pets]), 'leisure_mean': mean([p['leisure'] for p in pets]),
                'min_home': min(p['min_home'] for p in pets), 'max_below20': max(p['below20'] for p in pets),
                'branch_phase_fails': sum(bool(p['branch_fails']) for p in pets),
                'whole_life_fails': sum(not p['h_pass'] for p in pets),
                'failing': sorted({f"{j['seed']}|rep{r}|{cell}|{p['branch_fails'] or p['whole_fails']}" for j in jobs
                                   for r in range(len(j['reps'])) for cell, p in j['reps'][r][c][br].items()
                                   if p['branch_fails'] or not p['h_pass']})[:40]}
            # immediate (same-state) memory effect, clear - hard, summed over the 30 days, per seed
            out[f'{c}|{br}']['instant_net_hours_clear_minus_hard'] = D([
                sum(VR.mean([sum(d['promote'] - d['suppress'] for d in R[c][br][f'clear|{n}']['days'])
                             - sum(d['promote'] - d['suppress'] for d in R[c][br][f'hard|{n}']['days']) for n in ('warm', 'cold')])
                    for R in j['reps']) / len(j['reps']) for j in jobs])
    return out


# ---------------------------------------------------------------- part 2: social
def social_trace_job(args):
    seed, arm = args
    pets, same, _ = VS.grow(seed, arm)
    res = {'seed': seed, 'arm': arm, 'instrument_ok': True, 'counts': Counter(), 'groups': {}}
    for rep in range(VS.REPS + 1):
        cur = {}
        for c, p in pets.items():
            x = copy.deepcopy(p)
            if rep:
                x.agent.rng.seed(seed * 1000 + rep)
            cur[c] = x
        for (b, n), x in cur.items():
            for br in ('keep', 'social_change'):
                pair = []
                for instr in (True, False):
                    y = copy.deepcopy(x)
                    y.agent.social_trace = instr
                    VR.run_hours(y, VS.COMMON1 * 24)
                    if br == 'social_change':
                        y.world.p['neighbor_warmth'] = VS.COLD if n == 'warm' else VS.WARM
                    VR.run_hours(y, VS.COMMON2 * 24)
                    pair.append(y)
                y, z = pair
                res['instrument_ok'] &= L.fingerprint(y.trace) == L.fingerprint(z.trace) and rng_digest(y) == rng_digest(z)
                rows = [r for r in y.agent.social_rows if r['avail'] and not r['invited']]
                key = f'{br}|{n}'
                G = res['groups'].setdefault(key, Counter())
                G['avail_hours'] += len(rows)
                G['explore'] += sum(r['explore'] for r in rows)
                G['visit'] += sum(r['outcome'] == 'visit' for r in rows)
                G['garden'] += sum(r['outcome'] == 'garden' for r in rows)
                G['neg_t'] += sum(r['t'] < 0 for r in rows)
                G['neg_t_garden_dominates'] += sum(r['t'] < 0 and r['win_without'] == 'garden' and r['win_with'] == 'garden' for r in rows)
                G['a_neg_t_no_effect_then_visit'] += sum(r['t'] < 0 and r['delta'] == 0 and r['explore'] and r['outcome'] == 'visit' for r in rows)
                G['b_t_raised_then_garden'] += sum(r['delta'] > 0 and r['explore'] and r['outcome'] == 'garden' for r in rows)
                G['t_raised'] += sum(r['delta'] > 0 for r in rows)
                G['t_raised_explore'] += sum(r['delta'] > 0 and r['explore'] for r in rows)
                ex = [r for r in rows if r['explore']]
                G['chance_sum'] += sum(r['chance'] or 0 for r in ex)
                G['chance_A_on_sum'] += sum(r['chance_A_on'] for r in ex)
                G['chance_A_off_sum'] += sum(r['chance_A_off'] for r in ex)
                G['spont'] += sum(r['outcome'] == 'visit' for r in rows)
                G['invited'] += sum(1 for r in y.agent.social_rows if r['invited'] and r['outcome'] == 'visit')
    res['groups'] = {k: dict(v) for k, v in res['groups'].items()}
    return res


def social_effects(designs):
    out = {}
    per = {}
    for arm in SOCIAL_ARMS:
        J = sorted((j for j in designs if j['arm'] == arm), key=lambda j: j['seed'])
        per[arm] = {j['seed']: VS.seed_effects(j) for j in J}
        lives = [m for j in J for m in j['lives']]
        from . import recheck_read_phases as RP
        saf = RP.safety_union(lives)
        out[arm] = {'safety': {k: saf[k] for k in ('unique_trajectories', 'pass', 'phase_fails')},
                    'failing': [f['life'] for f in saf['failing']], 'min_home': min(m['min_home'] for m in lives),
                    'same_growth_all': all(j['same_growth'] for j in J)}
    keys = [('C1|explore_in_avail', 'neighbor'), ('C1|spont_per_day', 'neighbor'), ('C1|read', 'neighbor'), ('C1|share_garden', 'neighbor'),
            ('C2|keep|spont_per_day', 'neighbor'), ('C2|keep|explore_in_avail', 'neighbor'), ('C2|social_change|spont_per_day', 'neighbor'),
            ('C1|read', 'book'), ('C1|spont_per_day', 'level'), ('C1|leisure', 'level')]
    D = L.describe
    for arm in SOCIAL_ARMS:
        out[arm]['effects'] = {f'{k}|{f}': D([per[arm][sd][k][f] for sd in SEEDS]) for k, f in keys}
        out[arm]['effects']['R2'] = D([per[arm][sd]['R2'] for sd in SEEDS])
    g = lambda arm, k, f=None: [per[arm][sd][k] if f is None else per[arm][sd][k][f] for sd in SEEDS]
    cont = {}
    for (a, b) in (('B2', 'ref'), ('A', 'ref'), ('B2A', 'B2'), ('B2A', 'A'), ('B2A', 'ref')):
        cont[f'{a} - {b}'] = {'R2': D([x - y for x, y in zip(g(a, 'R2'), g(b, 'R2'))]),
                              **{f'{k}|{f}': D([x - y for x, y in zip(g(a, k, f), g(b, k, f))]) for k, f in keys}}
    inter = lambda k, f=None: D([w - x - y + z for w, x, y, z in zip(g('B2A', k, f), g('B2', k, f), g('A', k, f), g('ref', k, f))])
    cont['interaction'] = {'R2': inter('R2'), **{f'{k}|{f}': inter(k, f) for k, f in keys}}
    return out, cont, per


def checks_against_saved(read_sum, social_per):
    r12 = json.loads(R12.read_text(encoding='utf-8'))['per_seed']
    r11 = json.loads(R11.read_text(encoding='utf-8'))['per_seed']
    same = lambda a, b: abs(a - b) < 1e-12
    return {'read_current_R1_equals_round12_B2': all(same(x, r12['B2'][str(sd)]['R1']) for sd, x in zip(SEEDS, read_sum['_R1_per_seed']['current'])),
            'social_B2_equals_round12_B2': all(same(social_per['B2'][sd]['R2'], r12['B2'][str(sd)]['R2']) for sd in SEEDS),
            'social_ref_equals_round12_ref': all(same(social_per['ref'][sd]['R1'], r12['ref'][str(sd)]['R1']) for sd in SEEDS),
            'social_A_equals_round11_A': all(same(social_per['A'][sd]['R2'], r11['A'][str(sd)]['R2']) for sd in SEEDS)}


def main():
    dst = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'docs' / 'pet_round13'
    dst.mkdir(parents=True, exist_ok=True)
    out_file = dst / 'round13_result.json'
    if out_file.exists():
        raise SystemExit(f'{out_file} exists: results are never overwritten')
    patch()
    with Pool(14, initializer=patch) as pool:
        reads = pool.map(read_job, SEEDS)
        designs = pool.map(VS.design_job, [(sd, a) for a in SOCIAL_ARMS for sd in SEEDS])
        traces = pool.map(social_trace_job, [(sd, a) for a in ('B2', 'B2A') for sd in SEEDS])
    R = summarise_read(reads)
    soc, cont, per = social_effects(designs)
    checks = checks_against_saved(R, per)
    D = L.describe
    tr = {}
    for arm in ('B2', 'B2A'):
        J = sorted((j for j in traces if j['arm'] == arm), key=lambda j: j['seed'])
        tr[arm] = {'instrument_ok_all': all(j['instrument_ok'] for j in J)}
        for key in J[0]['groups']:
            gs = [j['groups'][key] for j in J]
            rate = lambda num, den: D([g.get(num, 0) / g[den] if g.get(den) else None for g in gs])
            tr[arm][key] = {'per_seed_rates': {
                'explore_share_avail': rate('explore', 'avail_hours'), 'visit_share_of_avail': rate('visit', 'avail_hours'),
                'neg_t_share': rate('neg_t', 'avail_hours'), 'neg_t_garden_dominates_share_of_neg': rate('neg_t_garden_dominates', 'neg_t'),
                'a_count_share_of_avail': rate('a_neg_t_no_effect_then_visit', 'avail_hours'),
                'b_count_share_of_t_raised_explore': rate('b_t_raised_then_garden', 't_raised_explore'),
                'visits_per_outing (descriptive)': rate('visit', 'explore'),
                'mean_chance_on_outings': rate('chance_sum', 'explore'),
                'same_state_chance_A_on': rate('chance_A_on_sum', 'explore'), 'same_state_chance_A_off': rate('chance_A_off_sum', 'explore')},
                'totals': {k: sum(g.get(k, 0) for g in gs) for k in gs[0]}}
    dr1 = R['dR1']
    support = {c: dr1[c]['mean'] <= SUPPORT_DR1 and dr1[c]['ci95'][1] < 0 for c in dr1}
    a_adds = cont['B2A - B2']['R2']
    verdict = {'reading_factor_supported': support,
               'reading_conclusion': ('supported: ' + ', '.join(c for c, v in support.items() if v)) if any(support.values())
               else 'mecanismo no identificado con este diagnóstico',
               'social_A_adds_adaptation_beyond_B2': a_adds['mean'] <= SUPPORT_DR2 and a_adds['ci95'][1] < 0,
               'social_amplification_flag': (cont['interaction']['R2']['ci95'][1] < 0 or cont['interaction']['R2']['ci95'][0] > 0)}
    compat = L.compat_check()
    report = {'seeds': SEEDS, 'verdict': verdict, 'checks': {**checks, 'read_same_growth': R['same_growth_all'],
                                                            'read_instrument_ok': R['instrument_ok_all'],
                                                            'read_both_equals_no_close': R['both_equals_no_close_all'],
                                                            'social_trace_instrument_ok': {a: tr[a]['instrument_ok_all'] for a in tr}},
              'compat': compat, 'reading': {k: v for k, v in R.items() if not k.startswith('_')}, 'R1_per_seed': R['_R1_per_seed'],
              'social': soc, 'social_contrasts': cont, 'social_trace': tr}
    out_file.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    print(json.dumps(L.rounded({'verdict': verdict, 'checks': report['checks'], 'compat': compat['pass'],
                                'dR1': {c: {x: v[x] for x in ('mean', 'ci95')} for c, v in dr1.items()},
                                'interaction': {x: R['interaction'][x] for x in ('mean', 'ci95')}}), ensure_ascii=False, indent=1, default=str))


if __name__ == '__main__':
    main()
