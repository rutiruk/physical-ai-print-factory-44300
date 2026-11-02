# Mechanical Fleet V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan. Independent drive and gantry mechanisms are delegated under dispatching-parallel-agents; parent integrates traffic/runtime/HUD.

**Goal:** Real wheel-driven simultaneous paper transport with Jeff-resolved one-lane conflict, observable bounded mechanisms and interpretable AI HUD.
**Architecture:** Separate V2 vehicle, machine, scene, traffic and dashboard modules; shared existing pretrained policy workers, new V2 runtime and output folder. Preserve V1 source/artifacts/default entry points.
**Tech Stack:** Genesis1.4.5, MJCF, Python, Jeff2B, ViNT/NoMaD, PyAV/Pillow.
**Spec:** docs/superpowers/specs/2026-11-02-mechanical-fleet-v2.md

## Constraints and review focus
- Actual wheel contact, no planar base actuators/pose writes; payload1.44kg; finite torque/stroke.
- .90m corridor <two .56m robot widths; real cabinets plus withdrawal bays, no outer walls.
- Jeff chooses priorities/releases; safety can stop only. Never hide a learned-policy failure with rule steering.
- Both carried loads and both models must actually move; measurable concurrency and no inter-robot collision.
- Distinguish initial WIP, actual driven mechanics and approximated material/process internals.
- Current camera vs saved AI-input capture timestamps clearly labeled; no fabricated model reasoning.

## Tasks
- [x] Vehicle: wheel/torque/loaded drive/lift CPU tests and actual GPU probe.
- [x] Machines: nested supports/limits/interlocks CPU tests and contact/roller/clamp GPU probe.
- [x] Traffic: RED/GREEN tests for both priority alternatives, physical bay clearance, no implicit release, stopping envelope.
- [x] Scene/runtime: build no-wall factory, both actual navigation policies and Jeff, physical payload support/unload.
- [x] HUD/video: show actual tasks, policy outputs/inputs, Jeff decisions and independent safety veto.
- [x] Verify real loaded concurrence, yields, minimum separation, no contacts, successful destinations; review complete changes.

## Ledger
- Final printing integration: A raw stock on roller press→measured print operation→contact AMR loading→folder; B folded initial WIP→trim. Material transformations remain explicit state approximations.
- Final run `output/v2/fleet_20261102_101250`: success,246.75SIMs,10.31s supported loaded concurrence, no detected contacts, A folded/B finished. Jeff4 applied decisions, ViNT189/187 total/accepted responses, NoMaD172/169.
- Full video audit:4935frames,123.375s,40fps,uniform2x,zero timestamp errors,43 source snapshots verified.54 focused CPU tests passed; independent reviewer reports no remaining important issues. Actual decoded frames atSIM1,14,65,246.75 visually checked.
- Mechanical corrections validated with actual replays: whole-strip continuous convex collision profiles eliminate internal bevel seams; quaternion-derived paper extents place the blade outside skewed stock; actual blade engagement height must be within1.5mm before pushing. Force/stroke caps unchanged, no runtime paper/base pose writes.
- Ruling: current source root is non-Git; retain V1 by adding only V2-named source/assets/output. Existing publication checkout is untouched. No new worktree or overwrite of submitted artifacts.
- Ruling: start with explicitly declared printed/folded WIP to isolate the requested opposing-flow coordination and mechanics; do not claim this new experiment reproduces all upstream material transformations.
- Vehicle GPU: .5811m loaded travel, .4652rad turn, torque5.875Nm<=6, lift.05831m<=.06, payload1.44kg stable. Skid turning understeers, so pose feedback is essential.
- Machine GPU:10mm pile moved.214966m by contact, gantry target.400m actual.399903m, rollers rotated28.7356rad, clamp stroke.065101m. Guard/pile logic and unloaded clamp force remain approximations; no physical paper fracture/folding.
