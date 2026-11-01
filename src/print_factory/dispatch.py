"""Event-driven production state. Legal actions are unsorted; a policy chooses every start.

Machine internals are discrete process/PLC approximations; transport completion is
accepted only after the physics runner confirms support at its destination.
"""
from dataclasses import dataclass, field
from copy import deepcopy
from .printing import FormLot, gather


class StaleDecision(ValueError):
    pass


@dataclass
class Job:
    id: str
    arrival: float
    due: float
    pages: int = 16
    copies: int = 100
    revision: int = 1
    description: str = 'A4 saddle-stitched brochure'
    lots: dict = field(default_factory=dict)
    locations: dict = field(default_factory=dict)
    received: list = field(default_factory=list)
    book: object = None
    completed: float | None = None


class Factory:
    def __init__(self, arrivals):
        self.pending=sorted(arrivals,key=lambda j:j.arrival)
        if len({j.id for j in self.pending})!=len(self.pending):
            raise ValueError('Job identifiers must be unique')
        self.jobs={};self.now=0.;self.version=0;self.events=[]
        self.machines={};self.amrs=[None,None];self.faults=set()

    def log(self,event,**data):
        self.events.append(dict(time_s=round(self.now,3),event=event,**data))

    def advance(self, now):
        if now<self.now:raise ValueError('Clock cannot reverse')
        # Keep actual arrival/completion timestamps even when runner advances in large steps.
        while True:
            times=([self.pending[0].arrival] if self.pending else [])
            times += [v['ends'] for v in self.machines.values()]
            if not times or min(times)>now:break
            self.now=min(times)
            while self.pending and self.pending[0].arrival<=self.now:
                j=self.pending.pop(0)
                j.lots={i:FormLot(j.id,j.revision,i,j.copies,j.pages) for i in range(1,j.pages//4+1)}
                j.locations={i:'stock' for i in j.lots};self.jobs[j.id]=j
                self.version+=1;self.log('JOB_ARRIVAL',job=j.id,due=j.due,pages=j.pages,copies=j.copies)
            for machine,active in list(self.machines.items()):
                if active['ends']<=self.now:
                    j=self.jobs[active['job']];form=active.get('form')
                    if machine=='press':
                        lot=j.lots[form];lot.print_side('front',True,True);lot.print_side('back',True,True)
                        lot.cure();lot.inspect(True);lot.jog();j.locations[form]='press'
                    elif machine=='folder':
                        j.lots[form].fold();j.locations[form]='folder'
                    else:
                        j.book=gather([j.lots[i] for i in j.received],j.id,j.revision)
                        if j.book.binding=='saddle_stitch':j.book.stitch()
                        j.book.trim();j.book.pack();j.completed=self.now
                    del self.machines[machine];self.version+=1
                    details={'binding':j.book.binding,'stitched':j.book.stitched,
                             'product_mass_kg':j.book.product_mass_kg,'trim_waste_kg':j.book.trim_waste_kg} if machine=='finishing' else {}
                    self.log('PROCESS_COMPLETE',machine=machine,job=j.id,form=form,**details)
        self.now=now

    def set_fault(self,machine,failed):
        if machine not in ('press','folder','finishing'):raise ValueError('Unknown machine')
        if failed and machine in self.machines:
            raise ValueError('This scenario stops idle equipment only; active cycles cannot be silently completed')
        if failed:self.faults.add(machine)
        else:self.faults.discard(machine)
        self.version+=1;self.log('MACHINE_FAULT' if failed else 'MACHINE_RECOVERED',machine=machine)

    def candidates(self):
        result=[]
        def add(id,description,**details):result.append(dict(id=id,description=description,**details))
        for j in self.jobs.values():
            if j.completed is not None:continue
            for form,location in j.locations.items():
                if location=='stock' and 'press' not in self.machines and 'press' not in self.faults:
                    add(f'print:{j.id}:{form}',f'Print approved job {j.id} F{form}, duplex UV, {j.copies} sheets; due {j.due}s')
                elif location=='folder_in' and 'folder' not in self.machines and 'folder' not in self.faults:
                    add(f'fold:{j.id}:{form}',f'Start folding job {j.id} F{form} now: its stack is physically delivered to folder input, duplex printed, UV cured, inspection accepted and jogged. Folder is available and fault-free. This 3-second local process needs no corridor transport. Due {j.due} seconds.')
                elif location in ('press','folder'):
                    destination='folder' if location=='press' else 'gather'
                    # Dedicated output cassette capacity; gather feeder accepts inner signature first.
                    if destination=='gather' and form!=len(j.lots)-len(j.received):continue
                    for index,task in enumerate(self.amrs):
                        if task is None:
                            add(f'carry:{j.id}:{form}:{location}:{destination}:{index}',
                                f'AMR{index+1} carry job {j.id} F{form} from {location} to {destination}; due {j.due}s',
                                amr=index,job=j.id,form=form,source=location,destination=destination)
            if len(j.received)==len(j.lots) and j.lots and 'finishing' not in self.machines and 'finishing' not in self.faults:
                recipe='Gather, saddle stitch, three-side trim and pack' if j.pages>=8 else 'Trim and pack the folded four-page leaflet; bypass wire stitching for this single-sheet product'
                add(f'finish:{j.id}',f'{recipe}: job {j.id}, {j.copies} copies, due {j.due}s. The finishing machine is ready.')
        add('wait','Remain idle for 0.75 seconds and delay jobs; only useful if other actions are unsafe or a new observation is required. Waiting cannot clear the crate or advance a ready machine.')
        return result

    def select(self,choice,version):
        if version!=self.version:raise StaleDecision(f'Expected generation {self.version}, got {version}')
        candidate=next((c for c in self.candidates() if c['id']==choice),None)
        if candidate is None:raise ValueError('Policy selected an ineligible action')
        if choice=='wait':self.log('HOLD');return candidate
        parts=choice.split(':');kind,jid=parts[:2];j=self.jobs[jid]
        if kind=='carry':
            form=int(parts[2]);index=int(parts[-1]);self.amrs[index]=candidate
            j.locations[form]=f'amr{index}';self.log('TRANSPORT_ASSIGNED',**{k:v for k,v in candidate.items() if k!='description'})
        else:
            machine={'print':'press','fold':'folder','finish':'finishing'}[kind]
            form=int(parts[2]) if len(parts)>2 else None
            if form is not None:j.locations[form]=f'processing:{machine}'
            # Capacity is represented by an explicit machine reservation, never by option ordering.
            duration={'print':4.,'fold':3.,'finish':7.}[kind]
            self.machines[machine]=dict(job=jid,form=form,ends=self.now+duration)
            self.log('PROCESS_START',machine=machine,job=jid,form=form)
        self.version+=1
        return candidate

    def complete_transport(self,index,physically_supported):
        task=self.amrs[index]
        if task is None:raise ValueError('AMR has no assigned transport')
        if not physically_supported:raise ValueError('Destination support has not been physically verified')
        j=self.jobs[task['job']];form=task['form'];destination=task['destination']
        j.locations[form]='folder_in' if destination=='folder' else 'gather'
        if destination=='gather':j.received.append(form)
        self.amrs[index]=None;self.version+=1
        self.log('TRANSPORT_COMPLETE',amr=index,job=j.id,form=form,destination=destination)

    def observation(self):
        return deepcopy(dict(time_s=round(self.now,2),generation=self.version,
                    jobs=[dict(id=j.id,due=j.due,pages=j.pages,copies=j.copies,product='saddle_booklet' if j.pages>=8 else 'folded_leaflet',locations=j.locations,
                               received=j.received,completed=j.completed) for j in self.jobs.values()],
                    amrs=self.amrs,machines=self.machines,faults=sorted(self.faults)))
