# Continuous Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A complete printed leaflet job in a continuous video no longer than 180 seconds.
**Architecture:** Add a named single-job scenario with a separate output directory. Capture through completion, then encode every original 20 fps frame at 40 fps and audit source/output correspondence, completion, quantities, and both learned models.
**Tech Stack:** Existing Python, Genesis, PyAV, Jeff, ViNT, NoMaD, ReportLab, Git.
**Spec:** docs/superpowers/specs/2026-11-02-continuous-demo.md

## Global Constraints
- 1 job B, 4 pages, 100 copies, 4 supported pushes; both navigation policies must infer.
- No changed machine times or speed limits; no fallback learned-motion replacement.
- Playback exactly 2x, every captured frame retained, maximum 180 seconds, zero cuts.
- Root source workspace is non-Git; use its existing isolated publication checkout only after verification. Existing authorization covers updating the public project.

## Review Focus
- Wrong run/metrics mixed with old three-job evidence: scenario-aware audits and report folder.
- Last output frame before completion: four actual post-completion seconds, capture-aligned exit.
- Hidden frame dropping/time jumps: synthetic color-sequence encode test and continuous frame-count/PTS audit.
- Duration over budget: fail explicitly, preserve old deliverable.
- Only one learned model used: require both inference counts in actual final audit.

### Task 1: Scenario and capture lifecycle
- [x] RED: test single B job configuration and scenario-aware completion/push validation.
- [x] GREEN: add scenario helper; extend runner with --scenario and separate output directory, 4s completion capture.
- [x] Verify selected CPU tests; real single-job run completed at185.70 SIMs without overwriting three-job evidence.

### Task 2: Continuous video and artifact audit
- [x] RED: test >180s rejection and preservation/order of every actual synthetic source frame.
- [x] GREEN: implement continuous composer and strict scenario/frame-count/PTS audit.
- [x] Actual run verified: both models, 100 copies, 4 supported pushes, zero cuts,3714frames40fps92.85s.

### Task 3: Deliver and publish consistent evidence
- [x] Update report/README/submission/package for single-job primary and three-job reference.
- [x] Rendered all3 report pages; artifact audit passed; 76 CPU tests passed.
- [ ] Obtain one final read-only review, then publish the verified source/video/PDF and verify remote blob identities.

## Ledger
- Ruling: proceed inline without another design approval — prior user instruction to proceed and current explicit video constraints; no unresolved product preference blocks implementation.
- Ruling: use a leaflet job rather than an 8-page booklet — full printing/folding/trimming/packing remains, and four rather than eight contact transfers gives a feasible uncut 2x duration. Wire stitching is correctly bypassed for a folded leaflet.

- Final read-only review: no remaining critical/important findings. Source/output3714 frame pairs preserve order and unchanged-image content (worst sampled mean RGB difference1.242/255); zero input/output PTS errors. Worker/adaptor, dispatch/machine and motion controller files match the published baseline.
- Fixed review finding: removed nonexistent test_scenarios.py from package allowlist; scenario tests reside in test_continuous_demo.py.
