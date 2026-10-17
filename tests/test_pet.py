"""Product regression tests; never run confirmatory research experiments."""
import copy
import json
from pathlib import Path
import sys
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pet.engine import Session
from pet.server import create_server, save_atomic

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

def test_corrupt_save_not_overwritten(tmp_path):
    path=tmp_path/'pet.json';path.write_text('not json')
    with pytest.raises(ValueError):create_server(path,0)
    assert path.read_text()=='not json'

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
        assert Session.restore(json.loads(path.read_text())).view()==result['state']
        with pytest.raises(HTTPError) as exc:urlopen(base+'/../sim.py')
        assert exc.value.code==404
    finally:
        server.shutdown();server.server_close();thread.join()
