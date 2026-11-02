"""Measured-height calibration for a rigid paper slide transfer, in metres."""
import math


def transfer_height_targets(deck_top, paper_thickness, receiver_top=.395, z_sag=.0043):
    """Keep blade off the deck while engaging stock on deck and receiver.

    z_sag is the measured free-space deflection of this finite-force gantry PD
    controller, not a pose correction; the returned command still drives joints.
    """
    if not all(math.isfinite(v) for v in (deck_top, paper_thickness, receiver_top, z_sag)) or paper_thickness <= 0 or z_sag < 0:
        raise ValueError('invalid transfer height measurements')
    actual_center = deck_top + .006
    command_z = actual_center + z_sag
    if actual_center - .003 >= receiver_top + paper_thickness - .001:
        raise ValueError('blade would lose overlap with paper on receiver')
    if not .4 <= command_z <= 1.1:
        raise ValueError('transfer tool command outside gantry stroke')
    return dict(actual_center=actual_center, command_z=command_z, measured_deck_top=deck_top,
                receiver_top=receiver_top, calibrated_sag=z_sag, blade_deck_clearance=.003)


def paper_world_half_extents(quat_wxyz, half_sizes):
    """World AABB half extents of the measured rigid stock: |R(q)| times half sizes."""
    if len(quat_wxyz)!=4 or len(half_sizes)!=3:
        raise ValueError('expected quaternion wxyz and three half sizes')
    values=tuple(float(v) for v in (*quat_wxyz,*half_sizes))
    if not all(math.isfinite(v) for v in values) or min(values[4:])<=0:
        raise ValueError('invalid paper pose or size')
    norm=math.sqrt(sum(v*v for v in values[:4]))
    if norm<1e-12:raise ValueError('zero paper quaternion')
    w,x,y,z=(v/norm for v in values[:4])
    rotation=((1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y)),
              (2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x)),
              (2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)))
    return tuple(sum(abs(r)*h for r,h in zip(row,values[4:])) for row in rotation)


def transfer_push_targets(paper_position, quat_wxyz, half_sizes, receiver_y, direction):
    """Place the blade outside measured stock before lowering; account for skew."""
    if direction not in (-1,1) or len(paper_position)!=3 or not all(math.isfinite(float(v)) for v in (*paper_position,receiver_y)):
        raise ValueError('invalid paper/receiver position or transfer direction')
    extent=paper_world_half_extents(quat_wxyz,half_sizes)
    return dict(x=float(paper_position[0]),extent_y=extent[1],half_extents_xyz=extent,
                behind_y=float(paper_position[1])-direction*(extent[1]+.025),
                target_blade_y=float(receiver_y)-direction*(extent[1]+.012))
