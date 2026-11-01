"""Physical cassette reservations must outlive logical AMR assignment."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from jeff_factory_demo import Demo,GATHER_X,PARKS
from print_factory.dispatch import Factory,Job


def bare():
    d=Demo.__new__(Demo)
    d.factory=Factory([Job('A',0,100,pages=8),Job('B',1,50,pages=4)])
    d.factory.advance(1)
    d.source_slots=[0,1,2,3];d.slots={};d.gather_owner=None
    d.cooldown=[0.,0.];d.robot_generators=[None,None]
    d.navigation=[{},{}]
    return d


def ids(d):return {c['id'] for c in d.eligible()}


def test_new_urgent_job_can_compete_for_same_interchangeable_stock():
    d=bare()
    assert {'print:A:2','print:B:1'}<=ids(d)
    assert 'print:A:1' not in ids(d) # one folder cassette: inner signature release first
    choice=next(c for c in d.eligible() if c['id']=='print:B:1')
    d.apply(choice)
    assert d.slots[('B',1)]==3


def test_blank_stock_is_not_reassigned_until_actual_pickup():
    d=bare();d.apply(next(c for c in d.eligible() if c['id']=='print:A:2'))
    d.factory.advance(10)
    d.factory.select('carry:A:2:press:folder:0',d.factory.version)
    assert not any(x.startswith('print:') for x in ids(d))
    d.factory.amrs[0]['picked_up']=True;d.source_slots.pop()
    assert 'print:B:1' in ids(d)


def test_folder_outbound_reserves_cassette_until_physical_pickup():
    d=bare();a=d.factory.jobs['A'];a.locations[2]='folder'
    d.slots[('A',2)]=3;d.slots[('B',1)]=2
    d.source_slots=[0,1,2]
    d.factory.jobs['B'].locations[1]='press'
    d.factory.select('carry:A:2:folder:gather:0',d.factory.version)
    assert not any(x.startswith('carry:B:1:press:folder:') for x in ids(d))
    d.factory.amrs[0]['picked_up']=True
    assert any(x.startswith('carry:B:1:press:folder:') for x in ids(d))


def test_urgent_job_has_its_own_gather_cassette_while_regular_set_is_incomplete():
    d=bare();d.factory.jobs['A'].locations[2]='gather';d.factory.jobs['A'].received=[2]
    d.factory.jobs['B'].locations[1]='folder';d.slots[('B',1)]=2;d.gather_owner='A'
    assert any(x.startswith('carry:B:1:folder:gather:') for x in ids(d))


def test_cassette_spacing_clears_neighbor_paper_and_pusher_at_allowed_pose_error():
    import xml.etree.ElementTree as ET
    xs=sorted(GATHER_X.values())
    assert min(b-a for a,b in zip(xs,xs[1:]))>.18+.225/2+.065+.02
    path=Path(__file__).resolve().parents[1]/'assets/gather_bridge_multi.xml'
    half=float(ET.parse(path).find('.//geom').attrib['size'].split()[0])
    assert all(abs(x-2)+.225/2+.065<half for x in xs)
    assert abs(PARKS[0][0]-PARKS[1][0])>.75


def test_recovery_is_an_explicit_policy_action_and_does_not_change_the_job():
    from types import SimpleNamespace
    d=bare();d.args=SimpleNamespace(policy='jeff')
    d.navigation[0]=dict(model='ViNT',needs_recovery=True,goal=[2,.55])
    c=next(c for c in d.eligible() if c['id']=='recover:0')
    before=d.factory.observation()['jobs']
    assert not d.navigation[0].get('resume_requested')
    d.apply(c)
    assert d.navigation[0]['resume_requested'] is True
    assert d.factory.observation()['jobs']==before
