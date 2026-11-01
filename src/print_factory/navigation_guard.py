"""Safety/progress observer. It pauses; only the dispatcher can request a retry."""
import math


def recovery_reason(start,goal,position,capture):
    dx,dy=goal[0]-start[0],goal[1]-start[1];length=math.hypot(dx,dy)
    remaining=math.dist(position,goal)
    if remaining<=capture or length<1e-6:return None
    px,py=position[0]-start[0],position[1]-start[1]
    cross=abs(dx*py-dy*px)/length
    if cross>.25:return 'cross_track_deviation'
    if remaining>length+.15:return 'moving_away_from_goal'
    def margin(p):return max(0.,abs(p[0])-3.6,-2.2-p[1],p[1]-.72)
    # A stopped pose may already be at the inner margin. A Jeff-authorized
    # retry must be able to move inward; only further outward travel is vetoed.
    if margin(position)>margin(start)+.02:return 'floor_margin'
    return None
