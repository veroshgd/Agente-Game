"""Product regression tests; never run confirmatory research experiments."""
import copy
import json
from pathlib import Path
import sys
import threading
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pet.engine import Session
from pet.server import AWAY_CAP_HOURS, create_server, hours_owed, save_atomic, split_clock

def run(s, days):
    for _ in range(days):
        s.apply({'kind':'advance','value':24})

def garden():
    s=Session()
    s.apply({'kind':'object','value':'garden'})
    return s

def test_invitation_is_not_experience_and_does_not_force_action():
    s=garden()
    s.agent.hunger=80
    s.apply({'kind':'invite','value':None})
    assert s.agent.shared == []
    s.apply({'kind':'advance','value':1})
    assert s.agent.last['action']=='eat'
    assert s.agent.shared==[]

def test_real_memories_change_scores_and_reference_prior_events():
    s=garden()
    s.apply({'kind':'invite','value':None})
    run(s,3)
    visits=[e for e in s.events if e.get('action')=='visit']
    assert visits and visits[0]['invited'] and not visits[0]['cause_ids']
    assert any(not v['invited'] and v['cause_ids'] for v in visits)
    for event in s.events:
        for eid in event.get('cause_ids',[]):
            cause=s.events[eid-1]
            assert cause['action']=='visit' and eid<event['id']
    a=copy.deepcopy(s.agent)
    a.hunger=25; a.energy=90; a.invitation_until=-1
    with_memory=a.score('explore',3)
    a.shared=[]
    assert with_memory>a.score('explore',3)
    assert a.influence()==(0,[])

def test_no_invented_shared_memories_without_meeting():
    s=garden();run(s,10)
    assert not s.agent.shared
    assert s.view()['shared_count']==0
    assert all(not e.get('cause_ids') for e in s.events)

def test_same_seed_different_experiences_changes_behavior():
    a=Session();b=garden()
    b.apply({'kind':'invite','value':None})
    run(a,8);run(b,8)
    assert a.birth_traits==b.birth_traits
    assert a.agent.action_log!=b.agent.action_log
    assert a.agent.traits!=b.agent.traits

def test_restore_replays_rng_and_continues_exactly(tmp_path):
    s=garden();s.apply({'kind':'name','value':'小芽🌱'})
    s.apply({'kind':'invite','value':None});run(s,4)
    path=tmp_path/'pet.json';save_atomic(path,s)
    other=Session.restore(json.loads(path.read_text(encoding='utf-8')))
    assert other.view()==s.view()
    run(s,3);run(other,3)
    assert other.view()==s.view()

@pytest.mark.parametrize('command',[{'kind':'advance','value':True},{'kind':'advance','value':-1},{'kind':'object','value':'code'},{'kind':'name','value':' '},{'kind':'invite','value':None}])
def test_invalid_commands(command):
    s=Session()
    with pytest.raises(ValueError):s.apply(command)
    assert not s.commands

def test_safe_home_and_bounded_memory_influence():
    for seed in (1,42,901):
        s=Session(seed);s.apply({'kind':'object','value':'garden'})
        s.apply({'kind':'invite','value':None});run(s,30)
        assert s.agent.alive and s.agent.condition>0
        assert 0<=s.agent.influence()[0]<=10
        assert all(0<=v<=100 for v in s.agent.traits.values())

def test_traits_stay_individual_and_no_hunger_trauma():
    # Audit 2026-10-14: under rules v1 every pet reached curiosity 100 and a hunger trauma.
    finals=[]
    for seed in (1,42,901):
        s=Session(seed);s.apply({'kind':'object','value':'garden'})
        s.apply({'kind':'invite','value':None});run(s,60)
        assert 'fears_hunger' not in s.agent.flags and s.agent.condition>=99
        assert all(20<=v<=90 for v in s.agent.traits.values())
        finals.append(s.agent.traits['curiosity'])
    assert len({round(v) for v in finals})>1

def test_old_saves_keep_their_rules():
    old=Session(42,rules=1);old.apply({'kind':'object','value':'garden'});run(old,40)
    assert old.archive()['version']==1
    again=Session.restore(json.loads(json.dumps(old.archive())))
    assert again.rules==1 and again.view()==old.view()
    assert again.view()['traits']!=Session.restore({**old.archive(),'version':2}).view()['traits']

def test_corrupt_save_not_overwritten(tmp_path):
    path=tmp_path/'pet.json';path.write_text('not json')
    with pytest.raises(ValueError):create_server(path,0)
    assert path.read_text()=='not json'

def test_hours_owed_keeps_leftover_and_caps_long_absence():
    assert hours_owed(0, 3*3600+1200, 1) == (3, 3*3600)
    assert hours_owed(0, 30*60, 2) == (1, 1800)
    assert hours_owed(0, 1000*3600, 1) == (AWAY_CAP_HOURS, 1000*3600)
    assert hours_owed(5000, 100, 1) == (0, 5000)

def test_pet_lives_while_page_and_server_are_closed(tmp_path):
    path=tmp_path/'pet.json'
    s=garden();save_atomic(path,s,time.time()-5*3600-60)
    server=create_server(path,0)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        with urlopen(base+'/api/state') as response:data=json.load(response)
        assert data['state']['tick']==5 and data['away']['hours']==5
        assert sum(data['away']['counts'].values())==5
        saved=json.loads(path.read_text(encoding='utf-8'))
        assert 0<time.time()-saved['last_seen']<120
        assert Session.restore(split_clock(saved)[0]).view()==data['state']
        with urlopen(base+'/api/state') as response:again=json.load(response)
        assert again['away'] is None and again['state']['tick']==5
    finally:
        server.shutdown();server.server_close();thread.join()

def test_http_save_restart_and_access_checks(tmp_path):
    path=tmp_path/'pet.json'
    server=create_server(path,0)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        with urlopen(base+'/api/state') as response:data=json.load(response)
        body=json.dumps({'kind':'advance','value':6}).encode()
        with pytest.raises(HTTPError) as exc:urlopen(Request(base+'/api/command',body))
        assert exc.value.code==403
        with pytest.raises(HTTPError) as exc:urlopen(Request(base+'/api/state',headers={'Host':'evil.example'}))
        assert exc.value.code==403
        with urlopen(Request(base+'/api/command',body,headers={'X-Pet-Token':data['token']})) as response:result=json.load(response)
        assert result['state']['tick']==6
        assert Session.restore(split_clock(json.loads(path.read_text()))[0]).view()==result['state']
        with pytest.raises(HTTPError) as exc:urlopen(base+'/../sim.py')
        assert exc.value.code==404
    finally:
        server.shutdown();server.server_close();thread.join()

def test_v3_neighbor_has_her_own_schedule_but_keeps_invitations():
    # Audit 2026-10-17: under rules v2 a pet visited Mili ~5 times a day, every day.
    s=Session(42,rules=3);s.apply({'kind':'object','value':'garden'})
    s.apply({'kind':'invite','value':None});run(s,30)
    per_day={}
    for e in s.events:
        if e.get('action')=='visit':per_day.setdefault(e['tick']//24,[]).append(e)
    assert per_day and all(sum(not v['invited'] for v in vs)<=2 for vs in per_day.values())
    assert len(per_day)<30
    assert any(e.get('missed_neighbor') for e in s.events)
    assert all(not s.agent.mili_free(d,h) for d in range(30) for h in (0,7,20,23))

def test_leisure_gets_boring_but_needs_and_chores_do_not():
    # Long-term home upkeep is checked hour by hour in tests/test_pet_v4.py.
    s=garden();s.apply({'kind':'invite','value':None});run(s,3)
    a=copy.deepcopy(s.agent);a.recent=[]
    fresh=a.score('explore',3)
    a.recent=['explore']*24
    assert a.score('explore',3)<fresh and a.boredom('eat')==0
    assert a.boredom('gather_material')==a.boredom('build')==0

def test_v2_saves_keep_v2_rules():
    old=Session(42,rules=2);old.apply({'kind':'object','value':'garden'})
    old.apply({'kind':'invite','value':None});run(old,20)
    again=Session.restore(json.loads(json.dumps(old.archive())))
    assert again.rules==2 and again.view()==old.view()
    assert all('missed_neighbor' not in e for e in again.events)
    assert again.view()['events']!=Session.restore({**old.archive(),'version':3}).view()['events']
