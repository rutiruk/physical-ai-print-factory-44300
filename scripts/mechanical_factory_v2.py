"""Real wheel AMRs, explicit WIP, Jeff traffic decisions, bounded contact machinery."""
import argparse,copy,hashlib,json,math,sys,time
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import numpy as np
from PIL import Image
from print_factory.v2_scene import build_workshop
from print_factory.v2_navigation import LearnedNavigator
from print_factory.v2_traffic import TrafficCoordinator,BAYS,ENTRIES,pair_envelope,corridor_clearance
from print_factory.v2_dashboard import render_v2_dashboard
from print_factory.v2_transfer import transfer_height_targets,transfer_push_targets
from print_factory.v2_printing import PrintJob
from print_factory.json_worker import JsonWorker
from print_factory.video import VideoWriter
from print_factory.scene import numpy
from print_factory.run_artifacts import write_result

LABELS={'priority_0':'AMR2を右へ待避 → AMR1が先行',
        'start_print_A':'ジョブAの白紙を印刷機へ送り出す',
        'priority_1':'AMR1を左へ待避 → AMR2が先行',
        'release_0':'待避中のAMR1に通行許可',
        'release_1':'待避中のAMR2に通行許可',
        'recover_0':'AMR1を再観測・再試行','recover_1':'AMR2を再観測・再試行',
        'hold':'新たな通行許可を保留'}
PHASE={'heading_servo_conventional':'向き合わせ（従来制御）','awaiting_model':'画像から移動を推論中',
       'learned_driving':'基盤モデルの予測で走行','final_18cm_conventional':'終端18cmの位置合わせ',
       'docking_conventional':'機械へ精密接近','needs_recovery':'停止・Jeffの再試行待ち',
       'precision_ready':'位置合わせ完了','heading_ready':'姿勢合わせ完了','idle':'待機',
       'capture_braking':'減速','recovery_reorient':'姿勢を整えて再観測'}


class Experiment:
    def __init__(self,args):
        self.args=args;self.now=0.;self.ticks=0
        self.out=ROOT/'output/v2'/('fleet_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
        self.out.mkdir(parents=True,exist_ok=False)
        sources=list((ROOT/'src/print_factory').glob('*.py'))+list((ROOT/'assets/v2').glob('*.xml'))+[Path(__file__),ROOT/'scripts/navigation_worker.py',ROOT/'scripts/jeff_worker.py',ROOT/'scripts/compose_v2_video.py']
        manifest={}
        for source in sources:
            relative=source.relative_to(ROOT);destination=self.out/'source'/relative
            destination.parent.mkdir(parents=True,exist_ok=True)
            content=source.read_bytes();destination.write_bytes(content)
            manifest[str(relative)]=hashlib.sha256(content).hexdigest()
        write_result(self.out/'source_manifest.json',manifest)
        self.events=[];self.decisions=[];self.initial_support=[];self.delivered=[False,False]
        self.cycle_done=[False,False];self.stage=['印刷ジョブの投入待ち','折り済仕掛品・搬送待ち'];self.cargo=[False,True]
        self.jobs=[PrintJob('A'),PrintJob('B',stage='folded')]
        self.job_ui=['queued','folded'];self.print_authorized=False;self.ready_to_depart=False
        self.traffic=TrafficCoordinator();self.version=0;self.pending=None;self.next_jeff=0.
        self.jeff_view=dict(labels=LABELS);self.concurrency=0.;self.min_distance=5.6;self.min_clearance=5.
        self.ambiguous_decisions=0
        self.safety_count=0;self.last_safety={};self.robot_contact_count=0;self.rack_contact_count=0
        self.max_torque=0.;self.max_lift_force=0.;self.gantry_owner=None;self.gantry_phase='安全高さで待機'
        self.f=None;self.nav=None;self.nav_worker=None;self.jeff_worker=None;self.writer=None;self.frames=None
        self.result=dict(success=False,status='initializing',experiment='mechanical_fleet_v2',
            initial_wip=[dict(job='A',state='raw',copies=100,mass_kg=1.44,location='press',destination='folder'),
                         dict(job='B',state='folded',copies=100,mass_kg=1.44,destination='trim')],
            limits='Demonstrator assumptions; not manufacturer ratings or certified safety.',
            approximations=['A starts with raw stock and undergoes printing mechanics; B starts as folded WIP',
                            'Rigid paper piles; flexible folding, ink and material cutting not modeled'])
        self.persist('initializing')

    def event(self,kind,**values):
        if kind=='NAV_NEEDS_RECOVERY':self.version+=1
        detail=values.pop('detail',kind)
        self.events.append(dict(time_s=round(self.now,2),event=kind,detail=detail,**values))

    def poses(self):return [r.pose() for r in self.f.robots]

    def choices(self):
        if not self.ready_to_depart:
            if not self.print_authorized and self.now>=.5:
                return [dict(id='start_print_A',description='Start queued print jobA: feed its physically supported raw100sheets through the available printing rollers, then transfer that same printed pile onto AMR1 for the folder. JobB is already folded WIP awaiting the trimmer.'),
                        dict(id='hold',description='Keep the available printing press idle; queued jobA does not progress.')]
            return [dict(id='hold',description='Wait until the actual printing and physical loading are complete.')]
        rows=self.traffic.candidates(self.poses())
        for i,s in enumerate(self.nav.states):
            if s['needs_recovery']:
                rows.insert(0,dict(id=f'recover_{i}',description=
                    f'Reorient AMR{i+1} at its safely stopped pose, refresh its RGB history and resume its assigned visual-navigation goal using {s["model"]}. '
                    'Only the learned navigation model generates the subsequent route motion; holding cannot repair its deviation.'))
        return rows

    def dispatch(self):
        response=self.jeff_worker.poll()
        if response is not None:
            request=self.pending;self.pending=None
            record=dict(**response,input_time_s=request['time_s'],completed_time_s=self.now,
                        image_path=request['image_path'],observation=request['state'],candidates=request['candidates'])
            current={c['id'] for c in self.choices()}
            accepted=request['version']==self.version and response['choice'] in current
            values=sorted(response['probabilities'].values(),reverse=True)
            ambiguous=accepted and response['choice'].startswith('priority_') and len(values)>1 and values[0]-values[1]<.01
            if ambiguous:accepted=False;self.ambiguous_decisions+=1;self.next_jeff=self.now+.3
            record['accepted']=accepted;self.decisions.append(record)
            self.jeff_view=dict(**record,labels=LABELS)
            if ambiguous:
                self.jeff_view.update(choice='ambiguous',labels=dict(LABELS,ambiguous='優先案が拮抗：許可せず再評価'))
                self.event('AMBIGUOUS_JEFF',detail='Jeffの優先案が拮抗したため許可を保留')
                if self.ambiguous_decisions>=3:raise RuntimeError('Three ambiguous Jeff priority decisions; no input-order traffic fallback')
            if accepted:
                choice=response['choice']
                if choice.startswith('recover_'):
                    self.nav.resume(int(choice[-1]))
                    self.event('JEFF_RECOVERY',detail=LABELS[choice],choice=choice)
                elif choice=='start_print_A':
                    self.print_authorized=True
                    self.event('JEFF_START_PRINT',detail=LABELS[choice],choice=choice)
                else:
                    self.traffic.select(choice)
                    self.event('JEFF_TRAFFIC',detail=LABELS[choice],choice=choice)
                self.version+=1;self.next_jeff=self.now+(.75 if choice=='hold' else .1)
            elif not ambiguous:self.event('STALE_JEFF',detail='古い観測の判断を適用せず再観測')
        if self.jeff_worker.busy or self.now<self.next_jeff:return
        candidates=self.choices()
        if len(candidates)==1 and candidates[0]['id']=='hold':return
        image_path=self.out/f'jeff_{len(self.decisions):04d}_{self.ticks:06d}.png'
        Image.fromarray(self.f.overhead.render()[0]).save(image_path)
        robots=[dict(amr=i+1,job=('A','B')[i],wip=self.jobs[i].stage,carrying=self.cargo[i],
                     due=(180,140)[i],pose=self.f.robots[i].pose(),stage=self.stage[i],
                     goal=self.nav.states[i]['goal'],recovery_required=self.nav.states[i]['needs_recovery']) for i in (0,1)]
        state=dict(sim_time=self.now,experiment='Connected printing, folding and trimming workflow with two AMRs. JobA starts raw on the printing press; jobB is folded initial WIP.',
            objective='Progress the connected printing process. Start available queued printing work before transporting it. '
                      'When both loads are ready, minimize the time until the lower-deadline WIP reaches its downstream machine. '
                      'Choose a useful traffic/recovery action. Hold cannot clear a blocked robot or advance an available delivery.',
            camera='Actual overhead RGB of current factory. Blue=AMR1/ViNT, purple=AMR2/NoMaD. Green floor pads are physical withdrawal pockets.',
            physical_constraints='Aisle width0.90m; each robot width0.56m. They CANNOT pass head-on. '
                                 'The loser must physically move into its side bay before the winner crosses. '
                                 'After the first crossing, the waiting robot still needs a NEW explicit Jeff release. '
                                 'Safety can veto unsafe motor motion; it never chooses traffic priority.',
            robots=robots,jobs=[j.state() for j in self.jobs],printing_authorized=self.print_authorized,
            loads_ready=self.ready_to_depart,traffic=self.traffic.state(),delivered=self.delivered.copy())
        self.pending=dict(time_s=self.now,image_path=str(image_path),state=copy.deepcopy(state),
                          candidates=copy.deepcopy(candidates),version=self.version)
        self.jeff_worker.submit(dict(image_path=str(image_path),state=state,candidates=candidates))

    def workflow(self,i):
        if i==0:yield from self.print_and_load()
        while not self.ready_to_depart:yield
        self.job_ui[i]='in_transit'
        yield from self.transport(i)

    def print_and_load(self):
        self.event('PRINT_JOB_ARRIVED',job='A',detail='新規ジョブA：白紙100枚を印刷し折り機へ送る')
        while not self.print_authorized:yield
        machine=self.f.machines['press'];paper=self.f.papers[0]
        supported=lambda:len(numpy(paper.get_contacts(with_entity=machine.entity)['link_a']))>0
        if not supported():raise RuntimeError('Raw jobA is not physically supported on printing press')
        self.stage[0]='白紙を印刷ローラーへ送る';self.job_ui[0]='printing'
        q0=machine.state()['dof_position'][0]
        machine.request('feed',guard_closed=True,pile_present=True);machine.cycle.roller_velocity=.4
        for _ in range(150):yield
        machine.request('stop')
        for _ in range(30):yield
        delta=machine.state()['dof_position'][0]-q0
        self.jobs[0].record_operation('press',paper_supported=supported(),roller_delta=delta)
        self.job_ui[0]='printed';self.stage[0]='印刷済の同じ紙束をAMRへ移載'
        self.event('PRINT_COMPLETE',job='A',roller_delta=delta,detail='A：ローラー駆動と紙の支持を確認し印刷済へ（インキは状態近似）')
        self.gantry_owner=0
        p=numpy(paper.get_pos())
        geometry=transfer_push_targets(p,numpy(paper.get_quat()),(.225,.16,.005),self.f.robots[0].pose()['y'],-1)
        behind=geometry['behind_y']
        deck=float(numpy(self.f.robots[0].entity.get_link('deck').get_pos())[2])+.02
        heights=transfer_height_targets(.395,.01,receiver_top=deck);z=heights['command_z']
        state=self.f.gantry.state()['pose']
        yield from self.gantry_to(state[0],state[1],1.,'印刷機からの取出し前にZを上げる')
        yield from self.gantry_to(float(p[0]),behind,1.,'印刷済Aの後方へ移動')
        yield from self.gantry_to(float(p[0]),behind,z,'印刷機の排紙面へ下降')
        if abs(self.f.gantry.state()['pose'][2]-heights['actual_center'])>=.0015:
            raise RuntimeError('Printing takeout blade did not reach physical engagement height')
        target=geometry['target_blade_y']
        yield from self.gantry_to(float(p[0]),target,z,'同じ印刷済紙束を接触でAMRへ排出',speed=.12)
        yield from self.gantry_to(float(p[0]),target,1.,'押し板を上げてAMRを解放')
        for _ in range(80):yield
        final=numpy(paper.get_pos());r=self.f.robots[0].pose()
        contact=len(numpy(paper.get_contacts(with_entity=self.f.robots[0].entity)['link_a']))>0
        if not contact or math.hypot(final[0]-r['x'],final[1]-r['y'])>.08:
            raise RuntimeError('Printed stock did not physically load onto AMR1')
        self.event('PRINTED_LOAD',job='A',position=final.tolist(),supported=contact,detail='印刷機→AMR1：同じ紙束の接触と支持を確認')
        self.cargo[0]=True;self.ready_to_depart=True;self.gantry_owner=None;self.gantry_phase='安全高さで待機'

    def transport(self,i):
        x=(-2.8,2.8)[i]
        self.stage[i]='機械から直進して離れる'
        yield from self.nav.travel(i,(x,-.10))
        self.stage[i]='狭路の手前へ移動'
        yield from self.nav.travel(i,ENTRIES[i])
        while self.traffic.winner is None:yield
        if i!=self.traffic.winner:
            self.stage[i]='Jeffの指示で待避ポケットへ'
            yield from self.nav.travel(i,BAYS[i])
            self.event('BAY_REACHED',amr=i,detail=f'AMR{i+1}が待避位置に到着')
            self.stage[i]='待避中・Jeffの通行許可待ち'
            while not self.traffic.can_cross(i,self.poses()):yield
            self.stage[i]='Jeffの許可で通路入口へ戻る'
            yield from self.nav.travel(i,ENTRIES[i])
        else:
            self.stage[i]='相手の物理的な待避完了を待つ'
            while not self.traffic.can_cross(i,self.poses()):yield
        self.stage[i]='Jeffの許可で単線通路を通過'
        self.event('CROSS_START',amr=i,detail=f'AMR{i+1}が通路へ進入')
        yield from self.nav.travel(i,ENTRIES[1-i],terminal_capture=.08)
        self.traffic.mark_crossed(i);self.version+=1
        self.event('CROSS_END',amr=i,detail=f'AMR{i+1}が単線通路を通過')
        dock=(2.8,.55) if i==0 else (-2.8,-.55)
        pre=(dock[0],-.10 if i==0 else .10)
        yaw=math.pi/2 if i==0 else -math.pi/2
        self.stage[i]='受入機の手前へ'
        yield from self.nav.travel(i,pre)
        self.stage[i]='機械に正対・精密ドッキング'
        yield from self.nav.orient(i,yaw)
        yield from self.nav.dock(i,dock,yaw)
        self.stage[i]='停止して接触移載'
        yield from self.unload(i,dock)
        self.cargo[i]=False;self.delivered[i]=True
        self.event('DELIVERED',amr=i,detail=f'{("印刷済A→折り機","折り済B→断裁機")[i]}：支持を確認')
        self.stage[i]='受入機の駆動・クランプ確認'
        yield from self.machine_cycle(i)
        self.stage[i]='搬送と機械受入が完了'
        self.cycle_done[i]=True

    def gantry_to(self,x,y,z,phase,speed=None):
        self.gantry_phase=phase
        original=self.f.gantry.trajectory.limits
        if speed is not None:
            from dataclasses import replace
            self.f.gantry.trajectory.limits=replace(original,speed=(.6,speed,.25,1.2))
        self.f.gantry.set_target(float(x),float(y),float(z))
        began=self.now;good=0
        try:
            while good<12:
                state=self.f.gantry.state()
                error=max(abs(state['pose'][n]-v) for n,v in enumerate((x,y,z)))
                good=good+1 if error<.008 else 0
                if self.now-began>30:raise RuntimeError('Gantry cannot reach within physical force/travel constraints')
                yield
        finally:self.f.gantry.trajectory.limits=original

    def unload(self,i,dock):
        while self.gantry_owner not in (None,i):yield
        self.gantry_owner=i
        try:
            self.f.robots[i].set_lift(.005)
            self.gantry_phase='昇降台を受入高さへ合わせる'
            for _ in range(150):yield
            deck_top=float(numpy(self.f.robots[i].entity.get_link('deck').get_pos())[2])+.02
            heights=transfer_height_targets(deck_top,(.01,.02)[i])
            tool_z=heights['command_z']
            self.event('TRANSFER_HEIGHT',amr=i,**heights,detail=f'AMR{i+1}：実測した昇降台高さから押し板の高さを設定')
            p=numpy(self.f.papers[i].get_pos());sign=1 if i==0 else -1
            target_y=sign*1.25
            geometry=transfer_push_targets(p,numpy(self.f.papers[i].get_quat()),
                ((.225,.16,.005),(.1125,.16,.01))[i],target_y,sign)
            behind=geometry['behind_y'];target_blade=geometry['target_blade_y']
            self.event('TRANSFER_GEOMETRY',amr=i,**geometry,detail=f'AMR{i+1}：紙束の実測姿勢から下降位置と押出し終点を設定')
            state=self.f.gantry.state()['pose']
            yield from self.gantry_to(state[0],state[1],1.,'先にZを上げて干渉を回避')
            yield from self.gantry_to(float(p[0]),behind,1.,'レール・台車で紙束の後方へ移動')
            yield from self.gantry_to(float(p[0]),behind,tool_z,'有限ストロークで紙束の高さへ下降')
            if abs(self.f.gantry.state()['pose'][2]-heights['actual_center'])>=.0015:
                raise RuntimeError('Transfer blade did not reach physical engagement height')
            before=numpy(self.f.papers[i].get_pos()).tolist()
            yield from self.gantry_to(float(p[0]),target_blade,tool_z,'押し板の接触で紙束を送り出す',speed=.12)
            yield from self.gantry_to(float(p[0]),target_blade,1.,'押し板を引き上げて機械を解放')
            for _ in range(40):yield
            paper=self.f.papers[i];after=numpy(paper.get_pos());kind='folder' if i==0 else 'trim'
            contact=len(numpy(paper.get_contacts(with_entity=self.f.machines[kind].entity)['link_a']))>0
            valid=contact and abs(after[0]-dock[0])<.08 and abs(after[1]-target_y)<.09 and abs(after[2]-(.4 if i==0 else .405))<.02
            self.event('CONTACT_UNLOAD',amr=i,supported=bool(valid),before=before,after=after.tolist(),
                       detail=f'AMR{i+1}：押出し接触と機械側の支持を確認')
            if not valid:raise RuntimeError(f'Physical unload did not reach receiver: {after}, contact={contact}')
        finally:self.gantry_owner=None;self.gantry_phase='安全高さで待機'

    def machine_cycle(self,i):
        machine=self.f.machines['folder' if i==0 else 'trim']
        contact=len(numpy(self.f.papers[i].get_contacts(with_entity=machine.entity)['link_a']))>0
        clear=self.f.gantry.state()['pose'][2]>.95
        before=machine.state()['dof_position']
        self.job_ui[i]='folding' if i==0 else 'trimming'
        if i==0:
            machine.request('feed',guard_closed=clear,pile_present=contact)
            machine.cycle.roller_velocity=-.4
            for _ in range(150):yield
            machine.request('stop')
        contact=len(numpy(self.f.papers[i].get_contacts(with_entity=machine.entity)['link_a']))>0
        if not contact:raise RuntimeError('Paper lost downstream machine support before clamp')
        machine.request('clamp',guard_closed=clear,pile_present=contact)
        for _ in range(180):yield
        after=machine.state()['dof_position']
        contact=len(numpy(self.f.papers[i].get_contacts(with_entity=machine.entity)['link_a']))>0
        if not contact:raise RuntimeError('Paper lost downstream machine support during processing')
        self.jobs[i].record_operation('folder' if i==0 else 'trim',paper_supported=contact,
            roller_delta=after[0]-before[0],clamp_displacement=after[2]-before[2])
        self.job_ui[i]=self.jobs[i].stage
        self.event('MACHINE_RECEIVE',amr=i,state=machine.state(),detail=f'{machine.cycle.kind}：駆動部とクランプ動作')
        machine.request('release')
        for _ in range(100):yield

    def safety(self):
        states=[r.state() for r in self.f.robots]
        pair=pair_envelope(*states)
        self.min_distance=min(self.min_distance,pair['center_distance']);self.min_clearance=min(self.min_clearance,pair['clearance'])
        reasons={}
        if pair['stop']:reasons={0:'車体間の停止余裕不足',1:'車体間の停止余裕不足'}
        for i,p in enumerate(states):
            future=dict(p,x=p['x']+p['velocity'][0]*.25,y=p['y']+p['velocity'][1]*.25,
                        yaw=p['yaw']+p['angular_velocity'][2]*.25)
            current,fwd=corridor_clearance(p),corridor_clearance(future)
            if min(abs(p['x']),abs(future['x']))<1.73 and fwd<.025 and fwd<current-.002:
                reasons[i]='設備と車体の余裕不足'
                if self.nav.states[i]['mode']=='learned':self.nav.request_recovery(i,'cabinet_clearance')
            self.max_torque=max(self.max_torque,max(abs(v) for v in p['wheel_torque']))
            self.max_lift_force=max(self.max_lift_force,abs(p['lift_force']))
        if reasons!=self.last_safety and reasons:
            self.safety_count+=1;self.event('SAFETY_VETO',detail='非常停止：'+','.join(f'AMR{i+1} {s}' for i,s in reasons.items()))
        self.last_safety=reasons
        return reasons,states

    def frame(self,states,reasons):
        robots=[]
        for i,s in enumerate(self.nav.states):
            robots.append(dict(**{k:s.get(k) for k in ('model','goal','waypoints','latency_ms','input_time_s','input_image')},
                job=('A','B')[i],cargo=('印刷済100枚','折り済100枚')[i] if self.cargo[i] else '荷物なし',
                phase=self.stage[i]+' / '+PHASE.get(s['phase'],s['phase']),actual=states[i],
                policy_active=s['mode']=='learned' and not s['needs_recovery'],
                stop_reason=reasons.get(i) or ('Jeffの再試行待ち' if s['needs_recovery'] else None)))
        data=dict(now=self.now,robots=robots,jeff=self.jeff_view,traffic=self.traffic.state(),
                  gantry=dict(**self.f.gantry.state(),phase=self.gantry_phase),machines={k:v.state() for k,v in self.f.machines.items()},
                  events=self.events,delivered=self.delivered,concurrent_seconds=self.concurrency,
                  min_distance=self.min_distance,min_clearance=self.min_clearance,safety_stops=self.safety_count,playback_speed=2)
        data['papers']=[dict(position=numpy(p.get_pos()).tolist(),quaternion=numpy(p.get_quat()).tolist()) for p in self.f.papers]
        data.update(process_summary='A：白紙 → 印刷機 → AMR → 折り機  /  B：折り済仕掛品 → AMR → 断裁機',
            initial_condition='Aは白紙から印刷 / Bは折り済の初期仕掛品',
            jobs=[dict(id=j.job_id,state=self.job_ui[i],source='印刷機' if i==0 else '折り済仕掛品',destination='折り機' if i==0 else '断裁機') for i,j in enumerate(self.jobs)])
        overview=self.f.overview.render()[0]
        self.writer.append_data(overview)
        self.frames.write(json.dumps(data,ensure_ascii=True,allow_nan=False)+'\n')
        if self.ticks%100==0:
            render_v2_dashboard(overview,None,data).save(self.out/'latest.png')

    def persist(self,status):
        self.result.update(status=status,simulation_seconds=round(self.now,2),events=self.events,decisions=self.decisions,
                           jobs=[j.state() for j in self.jobs],
                           delivered=self.delivered,completed_receive_cycles=self.cycle_done,initial_payload_support=self.initial_support,
                           concurrent_loaded_translation_seconds=round(self.concurrency,3),minimum_center_distance=self.min_distance,
                           minimum_rectangle_clearance=self.min_clearance,robot_contacts=self.robot_contact_count,
                           equipment_contacts=self.rack_contact_count,safety_veto_events=self.safety_count,
                           max_measured_wheel_torque=self.max_torque,max_measured_lift_force=self.max_lift_force,
                           traffic=self.traffic.state(),playback_speed=2,video_fps=40,capture_sim_step_s=.05,cuts=0)
        self.result['video_composition']='deferred; run compose_v2_video.py after simulation'
        if self.nav is not None:
            self.result['navigation_inferences']=dict((model,sum(row['response'].get('model')==model for row in self.nav.inferences)) for model in ('vint','nomad'))
            self.result['models']=dict(jeff=self.jeff_worker.ready,navigation=self.nav_worker.ready)
        write_result(self.out/'result.json',self.result)
        write_result(ROOT/'output/v2/latest_run.json',dict(folder=str(self.out),status=status,success=self.result['success']))

    def run(self):
        began=time.perf_counter();finished=None
        try:
            self.nav_worker=JsonWorker('.venv-nav','navigation_worker.py',str(self.out.relative_to(ROOT)/'navigation_worker.log'))
            self.jeff_worker=JsonWorker('.venv-jeff','jeff_worker.py',str(self.out.relative_to(ROOT)/'jeff_worker.log'),args=('--checkpoint',str(ROOT/'models/jeff-2b-v1.2')))
            self.f=build_workshop()
            for _ in range(150):
                for r in self.f.robots:r.set_twist(0,0,.01)
                self.f.gantry.step(.01)
                for m in self.f.machines.values():m.step(.01)
                self.f.scene.step()
            for r in self.f.robots:r.refresh_pose()
            self.initial_support=[len(numpy(self.f.papers[0].get_contacts(with_entity=self.f.machines['press'].entity)['link_a']))>0,
                                  len(numpy(self.f.papers[1].get_contacts(with_entity=self.f.robots[1].entity)['link_a']))>0]
            if not all(self.initial_support):raise RuntimeError('Initial WIP is not physically supported')
            self.nav=LearnedNavigator(self.f.robots,self.f.front,self.f.goal_camera,self.nav_worker,self.out/'navigation',lambda:self.now,self.event)
            generators=[self.workflow(i) for i in (0,1)]
            self.writer=VideoWriter(self.out/'overview.mp4',40);self.frames=(self.out/'frames.jsonl').open('w',encoding='utf8')
            self.event('INITIAL_WIP',detail='Aは印刷機上の白紙 / Bは折り済仕掛品（各100枚・1.44kg）')
            while self.now<self.args.seconds:
                self.dispatch()
                for i,g in enumerate(generators):
                    if g is not None:
                        try:next(g)
                        except StopIteration:generators[i]=None
                reasons,states=self.safety()
                if all(self.cargo) and all(math.hypot(*p['velocity'][:2])>.03 for p in states):
                    supported=[len(numpy(p.get_contacts(with_entity=r.entity)['link_a']))>0
                               for p,r in zip(self.f.papers,self.f.robots)]
                    if all(supported):self.concurrency+=.01
                self.nav.step(.01,self.now,reasons)
                self.f.gantry.step(.01)
                for m in self.f.machines.values():m.step(.01)
                self.f.scene.step();self.ticks+=1;self.now=self.ticks*.01
                for r in self.f.robots:r.refresh_pose()
                contacts=len(numpy(self.f.robots[0].entity.get_contacts(with_entity=self.f.robots[1].entity)['link_a']))
                self.robot_contact_count+=int(contacts>0)
                if contacts:raise RuntimeError('Actual AMR-AMR contact detected')
                if self.ticks%5==0:
                    for r in self.f.robots:
                        for rack in self.f.contact_obstacles:
                            n=len(numpy(r.entity.get_contacts(with_entity=rack)['link_a']))
                            self.rack_contact_count+=int(n>0)
                            if n:raise RuntimeError('Actual AMR-equipment contact detected')
                    self.frame([r.state() for r in self.f.robots],reasons)
                if self.ticks%100==0:
                    self.persist('running');print(f't={self.now:.1f} delivered={self.delivered} concurrent={self.concurrency:.2f} Jeff={len(self.decisions)}',flush=True)
                if all(self.cycle_done):
                    if finished is None:finished=self.now
                    if self.ticks%5==0 and self.now-finished>=4.:
                        counts={m:sum(x['response'].get('model')==m for x in self.nav.inferences) for m in ('vint','nomad')}
                        if self.concurrency<1. or not all(counts.values()):raise RuntimeError('Required real concurrence/both learned policies not demonstrated')
                        self.result['success']=True;break
            self.persist('complete' if self.result['success'] else 'time_limit')
        except BaseException as exc:
            self.result['error']=f'{type(exc).__name__}: {exc}';self.persist('failed');raise
        finally:
            self.result['wall_seconds']=time.perf_counter()-began
            if self.frames:self.frames.close()
            if self.writer:self.writer.close()
            if self.nav_worker:self.nav_worker.close()
            if self.jeff_worker:self.jeff_worker.close()
            self.persist(self.result['status'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=float,default=360)
    Experiment(p.parse_args()).run()
