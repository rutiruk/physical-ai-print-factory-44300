# Mechanical fleet V2

User wants outer walls removed, physical drive/mechanical constraints built out, two simultaneous AMR transports opposing in a corridor too narrow to pass, Jeff controlling their interaction, and video showing what is happening and each AI's role. Submitted V1 must remain usable.

This is a separate mechanical/traffic experiment: initial WIP A is printed stock destined for the folder; WIP B is folded stock destined for trimming. Initial WIP and loaded piles are declared, not claimed as newly produced by this experiment. V1 retains the complete printing-to-packing evidence. No extra training data or model training.

Use two free-base, four-wheel skid AMRs, each .64x.56m, actual frictional wheel drive, bounded6Nm/wheel torque and250N/60mm deck lift. The .90m aisle is formed by collidable equipment cabinets, with no outer walls. Left/right withdrawal pockets physically clear the exit path. Gantry has anchored portal/nested slide bodies, limited strokes/speeds/forces and actual contact pusher; machine rollers and clamps rotate/translate with limits. No runtime paper or robot pose teleports.

Jeff sees actual overhead RGB and factory/traffic state, chooses which loaded robot yields into a bay, which proceeds once it clears, and when the waiting robot is released. It must make a genuine choice between both priority orders. Software may veto unsafe actuation and emergency-stop, but must never choose traffic priority or substitute a conventional route on model failure. ViNT and NoMaD generate actual local RGB-conditioned waypoints; wheel control follows those with measured pose feedback. Heading alignment/precision docking and safety interlocks are declared conventional.

Show both transports active/moving concurrently outside the single-lane crossing, actual yielding, minimum separation, no robot-robot contact, actual wheel forces and moving mechanisms. HUD shows current task/phase for each robot, actual model input timestamp/waypoints, Jeff choice/probabilities/latency and separate safety-stop reason. Summaries must be based on recorded events, not invented model explanations. Retain continuous SIM time and uniform playback.

Limits are demonstrator assumptions rather than manufacturer ratings. No claim of flexible folding, ink, cutting material fracture, certified industrial safety, AI necessity or superiority. Published V1 artifacts and default scripts remain unchanged; V2 files/assets/output are separate.
# Scope amendment after mandatory printing-process reminder

The final combined V2 starts job A as raw stock physically supported by a process-specific roller printing press. Jeff explicitly authorizes the print job; measured paper support and roller rotation gate raw→printed. The same pile is pushed onto AMR1 by real contact before both AMRs depart. A reaches the folder and becomes folded after measured downstream mechanics. B starts as declared folded WIP and becomes finished after trim mechanics. Ink, flexible folding and cutting remain state approximations. This supersedes the earlier two-preprocessed-WIP initial condition for the final V2; earlier runs retain their downstream-only diagnostic scope.

The HUD shows the current factory, actual timestamped Jeff input image, dynamic per-job processing stage, and active versus historical ViNT/NoMaD predictions. No claim of manufacturing 200 new finished products is made: A ends folded and B ends finished.

