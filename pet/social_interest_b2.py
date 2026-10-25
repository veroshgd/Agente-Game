"""Round 12 of 2026-10-25: the social term with the right scope (entry 'B2'). A new extension; round 11's
pet/social_interest.py (entry 'B'), its criteria and its results are not edited.

Round 11's 'B' added the social term to the WHOLE explore score whenever the neighbor could meet, so a
negative social memory also lowered going out to garden alone. 'B2' changes only the social option of the
v5 liking, before it is compared with the garden option (engine PetAgent.preference_part takes the max):
    G   = need gate * (1 - home need)                      (the gates preference_part uses)
    g   = PREF_WEIGHT * prefs['garden'] * G,   s = PREF_WEIGHT * prefs['social'] * G   (0 if the liking is off)
    t   = READ_VALUE_WEIGHT * social term * G               (READ_VALUE_WEIGHT = PREF_WEIGHT: same units)
    explore score += max(g, s + t) - max(g, s)              only in hours she can meet now; else 0
So the explore score becomes max(g, s + t) where preference_part gave max(g, s): the gates are applied
once, the garden option is never lowered, and t = 0 gives the reference exactly. The visit chance is
unchanged (that is arm 'A', not used here).
"""
from . import engine
from .social_interest import SocialPetAgent
from . import lifestats as L


class SocialPetAgentB2(SocialPetAgent):
    def social_option_delta(self, action, day):
        if not (self.social_entry == 'B2' and self.exp_decide and action == 'explore' and self.world.has('garden')):
            return 0.0
        hour, invited = self.now % 24, self.now < self.invitation_until
        if not self.can_meet(day, hour, invited):
            return 0.0
        G = self.need_gate() * (1 - self.home_need())
        liking_on = self.rules >= 5 and not (self.pref_off or self.pref_score_off)
        g = engine.PREF_WEIGHT * self.prefs['garden'] * G if liking_on else 0.0
        s = engine.PREF_WEIGHT * self.prefs['social'] * G if liking_on else 0.0
        t = engine.READ_VALUE_WEIGHT * self.social_term() * G
        return max(g, s + t) - max(g, s)

    def score_parts(self, action, day):
        p = super().score_parts(action, day)
        if p is not None and self.social_entry == 'B2':
            p['social_term'] = self.social_option_delta(action, day)
            p['final'] += p['social_term']
        return p


class SocialSessionB2(L.TracedSession):
    def __init__(self, seed=42, rules=engine.RULES):
        super().__init__(seed, rules)
        self.agent = SocialPetAgentB2(seed, self.world, rules)
        self.birth_traits = dict(self.agent.traits)
