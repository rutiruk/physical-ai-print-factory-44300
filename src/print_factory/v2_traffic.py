"""Traffic permissions are selected by Jeff; this module only executes their guards."""
import math

AISLE_WIDTH=.90
ROBOT_WIDTH=.56
ROBOT_LENGTH=.64
BAYS={0:(-1.95,-1.45),1:(1.95,-1.45)}
ENTRIES={0:(-1.95,0.),1:(1.95,0.)}


def stopping_envelope(speed):
    return .06+.3*abs(speed)+speed*speed/(2*.5)


def corridor_clearance(pose):
    return AISLE_WIDTH/2-abs(pose['y'])-(ROBOT_LENGTH/2*abs(math.sin(pose['yaw']))+ROBOT_WIDTH/2*abs(math.cos(pose['yaw'])))


def pair_envelope(a,b):
    """Conservative separating-axis braking envelope for measured rigid poses.

    A side-by-side vehicle can leave a pocket without a false circular-footprint
    deadlock. This veto never chooses priority, a bay, or a replacement route.
    """
    delta=(b['x']-a['x'],b['y']-a['y'])
    def axes(p):
        return ((math.cos(p['yaw']),math.sin(p['yaw'])),(-math.sin(p['yaw']),math.cos(p['yaw'])))
    aa,bb=axes(a),axes(b);gaps=[];safe=False
    va,vb=a.get('velocity',[0,0]),b.get('velocity',[0,0])
    spin=abs(a.get('angular_velocity',[0,0,0])[2])+abs(b.get('angular_velocity',[0,0,0])[2])
    for axis in (*aa,*bb):
        dot=lambda x,y:x[0]*y[0]+x[1]*y[1]
        projection=dot(delta,axis)
        radius=lambda basis:ROBOT_LENGTH/2*abs(dot(axis,basis[0]))+ROBOT_WIDTH/2*abs(dot(axis,basis[1]))
        gap=abs(projection)-radius(aa)-radius(bb);gaps.append(gap)
        relative=dot((vb[0]-va[0],vb[1]-va[1]),axis)
        closing=max(0.,-math.copysign(1.,projection or 1.)*relative)
        envelope=.06+stopping_envelope(closing)+spin*.43*.3
        if gap>envelope:safe=True
    return dict(stop=not safe,clearance=max(gaps),center_distance=math.hypot(*delta))


class TrafficCoordinator:
    def __init__(self):
        self.winner=None
        self.granted=set()
        self.crossed=set()
        self.last_choice=None

    def candidates(self,poses):
        if self.winner is None:
            result=[dict(id=f'priority_{i}',description=
                f'FIRST deliver job{("A","B")[i]} (deadline {(180,140)[i]} seconds; '
                f'{("printed stock to folder","folded stock to trimmer")[i]}) using AMR{i+1}. '
                f'AMR{2-i} carrying job{("B","A")[i]} (deadline {(140,180)[i]} seconds) '
                'must physically withdraw to its own side bay and wait, so that job is delayed. '
                f'Only after that clearance may AMR{i+1} cross. Both loaded transports can approach concurrently outside the aisle.') for i in (0,1)]
        else:
            other=1-self.winner
            result=[dict(id=f'release_{other}',description=
                f'Release waiting AMR{other+1} after AMR{self.winner+1} has crossed and physically cleared the exit turn. '
                'The first robot keeps its destination task; no automatic priority reversal.')] if self.winner in self.crossed and other not in self.granted else []
        return result+[dict(id='hold',description='Keep existing permissions and waiting robots stopped. No new delivery progresses; use only when useful passage is unsafe.')]

    def select(self,choice):
        if choice=='hold':self.last_choice=choice;return
        if choice in ('priority_0','priority_1') and self.winner is None:
            self.winner=int(choice[-1]);self.granted.add(self.winner)
        elif self.winner is not None and choice==f'release_{1-self.winner}' and self.winner in self.crossed and 1-self.winner not in self.granted:
            self.granted.add(1-self.winner)
        else:raise ValueError('Unavailable traffic decision: '+str(choice))
        self.last_choice=choice

    def can_cross(self,index,poses):
        if index not in self.granted or index in self.crossed:return False
        if index==self.winner:
            other=1-index;p=poses[other]
            return math.dist((p['x'],p['y']),BAYS[other])<.18
        # A second explicit Jeff permission is insufficient if the first vehicle
        # still physically occupies the exit turn of the waiting vehicle.
        p=poses[self.winner]
        return math.dist((p['x'],p['y']),ENTRIES[index])>.96

    def mark_crossed(self,index):
        if index not in self.granted:raise ValueError('No Jeff passage permission')
        self.crossed.add(index)

    def state(self):
        return dict(winner=self.winner,granted=sorted(self.granted),crossed=sorted(self.crossed),
                    last_choice=self.last_choice,aisle_width=AISLE_WIDTH,robot_width=ROBOT_WIDTH,
                    bay_locations={str(i):list(xy) for i,xy in BAYS.items()})
