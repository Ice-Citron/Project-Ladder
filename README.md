# Project-Ladder
A research exploration in creating a policy s.t. a UR robotic arm inserts fiber optic cables into server racks.

## Repository layout

```
Project-Ladder/
├── ladder/           # policy code
├── eval/             # evaluator harness code (rangers_evaluator)
├── scenarios/        # COMMITTED: light yaml definitions
│   ├── m1_hard_set/  #   hc01..hc12.yaml + CERTIFICATION.md
│   ├── dr_train/     #   later: generated DR configs (M2)
│   └── heldout/      #   later: the held-out eval set
├── results/          # MIXED: run dirs; scoring.yaml + logs committed,
│   │                 #   bag_*/ ignored by pattern
│   └── m1_hard_set-stock/hcNN/
├── dataset/          # IGNORED fully: bags, frames, label manifests (M2/M3)
└── models/           # IGNORED fully: checkpoints; a MODELS.md registry
                      #   (small, committed) records what each model was
```
