"""Sheetfed UV-offset / folded-signature saddle-stitch production model.

Machine internals are process states, not simulated ink, flexible paper or knife cutting.
Sources and chosen manufacturing assumptions: docs/superpowers/specs/2026-11-01-print-process-design.md.
"""
from dataclasses import dataclass
import math


def supported_pile(position,quat_wxyz,goal_xy,support_top,height,contact):
    w,x,y,z=quat_wxyz
    upright=1-2*(x*x+y*y)>math.cos(math.radians(10))
    heading=abs(math.atan2(2*(w*z+x*y),1-2*(y*y+z*z)))<math.radians(10)
    return bool(contact and upright and heading and
                math.dist(position[:2],goal_xy)<.065 and abs(position[2]-(support_top+height/2))<.008)


def booklet_forms(pages):
    if pages<4 or pages%4:raise ValueError('Saddle stitched page count must be positive multiple of4')
    return [((pages-2*i,1+2*i),(2+2*i,pages-1-2*i)) for i in range(pages//4)]


@dataclass
class FormLot:
    job:str
    revision:int
    form:int
    copies:int
    pages:int=16
    gsm:float=100
    front_printed:bool=False
    back_printed:bool=False
    cured:bool=False
    inspection:bool|None=None
    jogged:bool=False
    head_up:bool=True
    folded:bool=False
    consumed:bool=False

    def __post_init__(self):
        if self.copies<=0 or not 1<=self.form<=len(booklet_forms(self.pages)) or self.gsm<=0:
            raise ValueError('Invalid form/copy/stock specification')

    @property
    def imposition(self):return booklet_forms(self.pages)[self.form-1]

    @property
    def mass_kg(self):return .45*.32*self.gsm/1000*self.copies

    @property
    def size_m(self):
        thickness=self.copies*.0001 # chosen100μm stock, not a general gsm-to-thickness law
        return (.225,.32,thickness*2) if self.folded else (.45,.32,thickness)

    def print_side(self,side,proof_approved,imposition_approved):
        if self.folded or self.consumed or not proof_approved or not imposition_approved:
            raise ValueError('Print requires approved proof/imposition and unprocessed sheets')
        if side not in ('front','back'):raise ValueError('Expected front/back')
        if getattr(self,side+'_printed'):raise ValueError('Side already printed')
        setattr(self,side+'_printed',True)
        self.cured=False;self.inspection=None

    def cure(self):
        if not self.front_printed or not self.back_printed:raise ValueError('Both sides must finish printing')
        self.cured=True # UV-complete PLC signal, not inferred from a ceiling photograph

    def inspect(self,passed):self.inspection=bool(passed)

    def jog(self):self.jogged=True

    def fold(self):
        if not all((self.front_printed,self.back_printed,self.cured,self.inspection is True,
                    self.jogged,self.head_up,not self.folded,not self.consumed)):
            raise ValueError('Folder requires duplex/cured/accepted/jogged/oriented sheets')
        self.folded=True


@dataclass
class BookletLot:
    job:str
    revision:int
    pages:int
    copies:int
    input_mass_kg:float
    gsm:float
    stitched:bool=False
    trimmed:bool=False
    packed:bool=False
    finished_size_m:tuple|None=None
    product_mass_kg:float=0
    trim_waste_kg:float=0

    @property
    def binding(self):return 'fold_only' if self.pages==4 else 'saddle_stitch'

    def stitch(self):
        if self.binding=='fold_only':raise ValueError('A single folded sheet is a leaflet; bypass wire stitching')
        if self.stitched:raise ValueError('Already stitched')
        self.stitched=True

    def trim(self):
        if (self.binding=='saddle_stitch' and not self.stitched) or self.trimmed:
            raise ValueError('Trim requires binding completed or a single-sheet folding recipe')
        self.finished_size_m=(.210,.297)
        # Each two-sided leaf contains two pages. Track paper mass, excluding wire/packaging.
        self.product_mass_kg=.210*.297*(self.pages/2)*self.copies*self.gsm/1000
        self.trim_waste_kg=self.input_mass_kg-self.product_mass_kg
        if self.trim_waste_kg<0:raise ValueError('Invalid paper mass balance')
        self.trimmed=True

    def pack(self):
        if not self.trimmed or self.packed:raise ValueError('Pack only finished, unpacked lot')
        self.packed=True


def gather(lots,job,revision):
    if not lots:raise ValueError('No folded signatures')
    first=lots[0];forms=first.pages//4
    # Actual feeder sequence is innermost first, outermost last (DNP folded-signature route).
    if [lot.form for lot in lots]!=list(range(forms,0,-1)):
        raise ValueError('Missing/duplicate/out-of-sequence signature')
    for lot in lots:
        if (lot.job!=job or lot.revision!=revision or lot.pages!=first.pages or lot.copies!=first.copies
                or lot.gsm!=first.gsm or not lot.folded or lot.consumed or lot.inspection is not True):
            raise ValueError('Job/revision/quantity/stock/readiness mismatch')
    result=BookletLot(job,revision,first.pages,first.copies,sum(l.mass_kg for l in lots),first.gsm)
    for lot in lots:lot.consumed=True
    return result
