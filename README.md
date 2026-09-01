# Project-Ladder

Our entry to the Intrinsic × Google **AI for Industry Challenge (AIC) 2026**: a UR robotic
arm inserting fiber-optic cables (SFP / SC / LC) into server-rack ports in a Gazebo + ROS 2
simulation, scored by the challenge's tiered evaluation engine.

The system is a **perception-driven ladder** (giving us inspiration for the name): scripted, force-guarded motion whose only learned components are perception modules. 

---

## Why a 'ladder' 
Two measurements we made ourselves, side by side (toolkit commit `66af77f`,
sample config, 3 trials):

| System | Score /300 | What it tells us |
|---|---|---|
| Stock **CheatCode** (scripted, reads ground-truth port poses from TF) | **278.64** | Motion is a solved problem *when the port pose is known* |
| Public pretrained **ACT** checkpoint (`grkw/aic_act_policy`) | **34.36** | Trained end-to-end BC ≈ the floor |
| Frozen policy (essentially does nothing)| ≈ 34 | The floor (validity + incidental proximity credit) |
| *(external)* Datameister (qualification winner), ~160 teams | 293.38 | Step-specific policies over strong perception, no end-to-end learning |

Ground-truth poses are **disabled during scored evaluation**. Therefore the task is not a
manipulation problem, it is a **perception problem**: the entirety of scored difficulty is
replacing the ground-truth TF lookup with vision. End-to-end Behavioural Cloning (BC) fails here because it
forces a network to relearn the solved part (motion) entangled with the unsolved part
(perception), under a scoring function that punishes exactly the sloppiness BC produces.
An independent team's public (Open Robotics Discourse #54899) reports the
same ceiling (~40/300) for the same pipeline.

## System architecture

```
1. Read target port from Task spec              [scripted]
2. Estimate port pose from wrist cams           [LEARNED: keypoint CNN + PnP]
3. Approach: safe-height corridor above port    [scripted: rise, translate, descend]
4. Fine align near port                         [LEARNED: InsertionNet-style corrector,
                                                 optional, funnel-gated]
5. Insert: compliant descent, wrench-guarded    [scripted]
6. Retry on failure (re-estimate pose first)    [scripted]
```

You may notice that the approach taken by most competitors, Action-Chunking Tranformers (ACT) appears nowhere in the primary system. It survives only as the **baseline** we train
once and report honestly, since the experimental control that makes the ladder result meaningful.

All scene knowledge enters [`ladder/MyCheatCode.py`](ladder/MyCheatCode.py) through **two
seam methods**; nothing else may read TF or scene state:

- `_get_port_pose(target_frame)` — **the swap point.** v1 = ground-truth TF lookup
  (dev / measurement ceiling); v2 = keypoint CNN + PnP/triangulation from the wrist
  cameras (eval-legal). Swapping v1 → v2 is a one-function change by design.
- `_get_plug_tip_pose()` — the plug-tip seam. Stock CheatCode consumes ground-truth
  *plug* TF on every tick of its descent — that TF also disappears in scored eval, so a
  one-seam swap would not be eval-legal. (This gap was found during reimplementation;
  it is not in the original plan docs.) Candidate fix: capture the TCP→plug transform
  once per trial and compose it with the controller's TCP pose; the fixed-offset test
  decides. If the plug shifts under contact, the v3 corrector owns the last ~2 cm.

Version ladder: **v1** GT poses (ceiling) → **v2** learned pose estimation (headline,
eval-legal) → **v3** learned fine-alignment corrector (only if the eval funnel shows the
leak is at fine-alignment/insertion).

## Progress Thus Far 2026-08-24

**Done**
- Working toolkit environment verified end-to-end; harness interfaces reverse-engineered
  and live-measured (topics, rates, controller pipeline, scoring internals). Baselines
  measured (table above).
- `MyCheatCode` skeleton: Policy integration verified against the toolkit loader
  (`-p policy:=ladder.MyCheatCode` with the repo root on `PYTHONPATH`), correct frame
  naming, target port taken from the `Task` object only, retry loop that re-estimates
  pose through the seam. Both seams implemented (v1 = GT TF).
- Hard-set scenario configs `hc01–hc03` ([scenarios/m1_hard_set/](scenarios/m1_hard_set/)):
  single-axis variations of the toolkit's sample trial (a NIC card placed in the arm's
  diagonal approach path — the known stock snag failure). Each header records hypothesis,
  expected stock failure, exact delta vs `sample_config.yaml`, and a legality check
  against the documented rail bounds. Schema validated against the engine parser.
- Salvage from the qualification repo: DR scenario generator + fixed-scene batch tools
  ([scenario_generator/](scenario_generator/), schema-compatible), repeatable eval runner
  ([eval/rangers_evaluator/](eval/rangers_evaluator/)), camera geometry drafts.
- Toolkit pinned as a submodule fork (`submodules/aic`) carrying reverse-engineering
  annotations only — verified functionally identical to upstream.

**In progress / next (critical path)**
1. Implement the four ladder stages (approach / align / insert / retry) — currently
   loud-failing stubs. **M1 gate: ≥ 270/300 on `sample_config` with `ground_truth:=true`,
   correct port in every trial.** Everything below is blocked on this number.
2. Run *stock* CheatCode on `hc01–hc03` to confirm the snag hypothesis (baseline
   evidence for the corridor design).
3. Expand the hard set (`hc04–hc12` + `CERTIFICATION.md`) only after the gate.

**Known repo debt**
- `training/` and `scripts/train_port_localization.py` are incomplete salvage — they
  import modules (`rangers_training`, `training.schema`) that were not carried over and
  fail on import. Repair or archive before planning around them.
- `.gitignore` blanket-ignores `results/`; intended policy is bags ignored,
  `scoring.yaml` + logs committed.
- The recovery supervisor ([ladder/guarded_insertion_recovery.py](ladder/guarded_insertion_recovery.py))
  defaults to wall-clock `time.time()`; callers must pass sim time (`now_s`) when wiring
  it into the insert stage.

## Milestones and gates

| | Deliverable | Gate (a number, or it didn't happen) |
|---|---|---|
| M0 (complete) | Environment + harness reverse-engineering, baselines | Stock CheatCode ≈ 278 reproduced |
| M1 (in progress) | `MyCheatCode` v1 (GT ladder) + hard-set certification | **≥ 270/300**, GT on, correct port ×3 |
| M2 | DR config sweep + batch data collection (5090, parallel sims) | ~200 configs → ~35k labeled frames |
| M3 | Keypoint CNN + PnP/triangulation swapped into `_get_port_pose()` | Eval-legal score, `ground_truth:=false`, held-out configs — **the headline number** |
| M4 | Funnel-driven fixes (closed-loop servo / v3 corrector) + ablations | Final eval; ablation table for the paper |

Planned ablations: GT vs estimated pose; open-loop vs servoed align; 2 vs 3 cameras;
corrector on/off (*does a learned local corrector beat pure pose-servoing near contact?*
— the paper's cleanest test of the regression-vs-geometry question).

## Repository layout

```
Project-Ladder/
├── ladder/                  # policy code: MyCheatCode + guarded-insertion supervisor
├── scenarios/
│   └── m1_hard_set/         # hc01..hc03 committed; hc04..hc12 + CERTIFICATION.md planned
│       (planned: dr_train/, heldout/ — M2)
├── scenario_generator/      # DR config generator + fixed-scene batch tools (salvage, schema-checked)
├── eval/rangers_evaluator/  # repeatable Gazebo eval runner (salvage; re-verify before relying on it)
├── camera_utils/            # camera intrinsics / geometry drafts (M3 groundwork)
├── training/                # keypoint model salvage — INCOMPLETE, see repo debt
├── scripts/                 # training entrypoint salvage — INCOMPLETE, see repo debt
├── submodules/aic/          # pinned fork of the official toolkit (annotations only)
├── results/                 # run dirs: scoring.yaml + logs committed, bags ignored
├── dataset/                 # ignored fully: bags, frames, label manifests (M2/M3)
└── models/                  # ignored fully: checkpoints; committed MODELS.md registry
```

**Running v1:** the toolkit's `aic_model` node loads the policy via its `policy`
parameter — set `policy:=ladder.MyCheatCode` with this repo root on `PYTHONPATH`, and run
the engine with `ground_truth:=true` (v1 reads GT TF). Environment setup follows the
toolkit's pixi/docker flow (see `submodules/aic/README.md` and `docs/`). Long-lived runs
(collection, training) go in `tmux` on the 5090.

## Scoring system (to better understand the project aims)
Per trial, max 100 (eval config runs 3 trials → 300):
**Tier 1** validity (1) · **Tier 2** performance — smoothness 0–6, duration 0–12,
path efficiency 0–6, insertion-force penalty to −12, **any off-limit contact −24** ·
**Tier 3** success — correct full insertion **+75**, partial 38–50, proximity 0–25,
**wrong port −12**.

Design consequences: the contact penalty dominates → force-guarded compliance and the
safe-height approach corridor; the corridor deliberately trades a little path-efficiency
(~1–2 pts on unobstructed scenes — measure it) for snag robustness; wrong-port −12 →
the target comes from the `Task` object, never from grabbing the first TF frame found;
duration bonus rewards decisive motion over dithering.

## References and deployment

### The two central method papers

**Schoettler et al. 2019, "Deep RL for Industrial Insertion"
([1906.05841](https://arxiv.org/abs/1906.05841)) — cite, don't implement.** SAC-style RL
on a real robot for connector insertion from pre-aligned starts. Evidence for two claims:
(a) insertion is learnable as a *local* skill, and (b) RL needs hours of interaction even
when scoped that tightly — which at our RTF ≈ 0.84 with no parallel envs means days of
wall-clock for marginal gain over force-guarded compliance + retry. It answers a question
we don't have.

**InsertionNet, Spector & Di Castro 2021 ([2104.14223](https://arxiv.org/abs/2104.14223);
2.0: [2203.01153](https://arxiv.org/abs/2203.01153)) — the v3 corrector recipe.**
No RL needed when the goal pose is known: collect data *backwards* — start at/near the
inserted pose, apply random mm/degree perturbations, record (wrist image, wrench), label
= the corrective delta back to alignment; a small CNN regresses the correction; deployed,
it's a learned visual servo for the last ~2 cm, exactly where the keypoint estimator goes
blind (occlusion, degraded view geometry). Our setting is *easier* than theirs: sim gives
ground-truth alignment for free (`ground_truth:=true`), samples cost ~1–2 s each, an
overnight run yields tens of thousands. ~11M-param regression → trains in under an hour,
runs at 10 Hz, fails gracefully into the retry wrapper.
*Adopt:* backward/perturbation collection; (image + F/T) → delta-pose mapping.
*Skip:* 2.0's contrastive/relation-network machinery (solves unseen sockets; ours are
known). *Consider if underperforming:* multi-view input (we have three wrist cams).
*Code:* no official release exists — **QBIT ([2503.07479](https://arxiv.org/abs/2503.07479))
reimplemented and benchmarked it in simulation and is our reference implementation.**
*Timeline guard:* funnel-gated M4 module. If the eval funnel says the leak is elsewhere,
we cite it as designed-but-not-required.

### Useful references

| Reference | Role here |
|---|---|
| robomimic, Mandlekar et al. 2021 ([2108.03298](https://arxiv.org/abs/2108.03298)) | Why attempt #1 failed: BC outcomes are dominated by action space / history / data quality, not architecture. Checklist for the ACT baseline's corrected interfaces. |
| ResiP, Ankile et al. 2024 ([2407.16677](https://arxiv.org/abs/2407.16677)) | Why chunked BC lacks terminal precision (open-loop within chunks); its residual-correction framing parallels our corrector. |
| ACT, Zhao et al. 2023 ([2304.13705](https://arxiv.org/abs/2304.13705)) | The baseline we compare against — trained once on corrected interfaces, reported honestly. Not load-bearing anywhere else. |
| Datameister qualifying write-up ([blog](https://datameister.ai/blog/intrinsic-ai-for-industry-challenge-qualifying-first)) | The winning pattern: step-specific policies over production-grade perception. External validation of the ladder shape. |
| Open Robotics Discourse [#54899](https://discourse.openrobotics.org/t/54899) | The failure pattern we replicated unknowingly (demos → LeRobot → ACT/SmolVLA ≈ 40/300). |

### Full reading list

Tiers rank *onboarding reading order* from before the challenge, not project centrality —
note that InsertionNet and Schoettler graduated from Tier 3 to the core of the method.

**Tier 1 - read and considered deeply:**
1. robomimic — [2108.03298](https://arxiv.org/abs/2108.03298) — the unglamorous knobs that swing BC results.
2. ACT/ALOHA — [2304.13705](https://arxiv.org/abs/2304.13705) — chunking, temporal ensembling, the CVAE.
3. Diffusion Policy — [2303.04137](https://arxiv.org/abs/2303.04137) — the main alternative action head; multimodality argument.
4. MimicGen — [2310.17596](https://arxiv.org/abs/2310.17596) — demo multiplication across randomized poses; maps onto phase segments.
5. IndustReal — [2305.17110](https://arxiv.org/abs/2305.17110) — RL for tight-tolerance insertion: SDF rewards, curricula, action integrator.
6. HIL-SERL — [2410.21845](https://arxiv.org/abs/2410.21845) — RL + human corrections at ~100% on precision insertion; reward and intervention design.

**Tier 2 - borrowed techniques:**
1. Factory — [2205.03532](https://arxiv.org/abs/2205.03532) — background for IndustReal/AutoMate.
2. AutoMate — [2407.08028](https://arxiv.org/abs/2407.08028)
3. FORGE — [2408.04587](https://arxiv.org/abs/2408.04587) *(ID verified)* — insertion under pose uncertainty with force limits; the closest RL analogue to our uncertainty setting.
4. ResiP — [2407.16677](https://arxiv.org/abs/2407.16677) — residual RL correcting chunked BC; closest recipe to "ACT but it actually inserts".
5. π0 — [2410.24164](https://arxiv.org/abs/2410.24164)
6. π0.5 — [2504.16054](https://arxiv.org/abs/2504.16054)
7. FAST — [2501.09747](https://arxiv.org/abs/2501.09747)
8. Knowledge-Insulating VLAs — [2505.23705](https://arxiv.org/abs/2505.23705) *(ID verified)* — the practical "how to actually train a VLA" paper.
9. GR00T N1 — [2503.14734](https://arxiv.org/abs/2503.14734) — N1.5 is a repo/tech-report update: [NVIDIA/Isaac-GR00T](https://github.com/NVIDIA/Isaac-GR00T)

**Tier 3 - skim/reference:**
1. SERL — [2401.16013](https://arxiv.org/abs/2401.16013)
2. Deep RL for Industrial Insertion — [1906.05841](https://arxiv.org/abs/1906.05841) — **cited in related work (see above)**
3. InsertionNet — [2104.14223](https://arxiv.org/abs/2104.14223) — **the v3 corrector (see above)**
4. DART (noise injection) — [1703.09327](https://arxiv.org/abs/1703.09327)
5. DexMimicGen — [2410.24185](https://arxiv.org/abs/2410.24185) *(ID verified)*
6. EgoMimic — [2410.24221](https://arxiv.org/abs/2410.24221) *(ID verified)* — human-video thread, dormant.
7. SmolVLA — [2506.01844](https://arxiv.org/abs/2506.01844) *(ID verified)* — the one VLA fine-tunable on a consumer GPU; candidate secondary baseline.

Repos worth having open while reading: `Physical-Intelligence/openpi`,
`NVIDIA/Isaac-GR00T`, `huggingface/lerobot`, `NVlabs/mimicgen`, `rail-berkeley/serl` /
`hil-serl`, `ARISE-Initiative/robomimic`.

## Process rules 

- **Nothing counts until it's a number from the scoring engine.** "It should work" has
  burned us repeatedly.
- Coding agents are narrow executors, not project managers: fresh branch → read-first →
  small scoped diffs → commit per step → a numeric verification gate. Review `git status`
  before every commit.
- **Git is the only sync mechanism between machines.** No loose files. Bags and datasets
  stay out of git and are regenerated on the 5090.
- All sim + training + eval runs on the 5090 (collect where you eval); the laptop is for
  code, agent-driving, and the paper. Long runs live in `tmux`.
