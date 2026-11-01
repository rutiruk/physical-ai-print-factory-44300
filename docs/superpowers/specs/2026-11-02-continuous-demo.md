# Continuous submission video

User requirement: no jumps in the SIM clock; at most 3 minutes; three jobs are not required. Prior constraints remain: actual Jeff image/task decisions, real public ViNT and NoMaD inference, Genesis contact transport, no training or synthetic motion.

Use one B job arriving at SIM 0: a 4-page folded leaflet, 100 copies, 100 consumed SRA3 sheets. Preserve all machine durations, actuator limits, camera geometry, and policy checkpoints. Keep the previous three-job run separately. Both AMRs must actually infer and transport in the new run; success requires one completed job, 100 copies, four supported contact transfers, and the correct wire-bypass finishing recipe.

Record every 0.05 SIM seconds, including four actual SIM seconds after completion. End on a capture boundary. Encode every source frame at 40 fps: exactly 2x playback, no cuts, no frame dropping, no interpolation, no static closing card. Reject a run exceeding 360 SIM seconds rather than skipping time or silently increasing playback speed.

Update the primary video, report, source bundle, README, and the already-authorized public GitHub repository only after actual completion and verification. The multi-job run remains reference evidence; do not reuse its completion or inference counts for the single-job video.
