#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/home/starforge-sf95/Black-Projects/Project-Automaton/aic-rangers"
TRAINING_ROOT="/home/starforge-sf95/Black-Projects/Project-Automaton/aic-rangers-isaac-training"

export AIC_HYBRID_ENRIK_POLICY_PATH="${REPO_ROOT}/submission_assets/checkpoints/enrik_sc_delta16/pretrained_model"

export AIC_HYBRID_INSERTION_POLICY_PATH_DEFAULT="${TRAINING_ROOT}/rangers_training/outputs/sc_stage_fixed_scene_curated_001_v1_approach/2026-05-06_00-36-06/checkpoints/010000/pretrained_model"
export AIC_HYBRID_INSERTION_POLICY_PATH_APPROACH="${TRAINING_ROOT}/rangers_training/outputs/sc_stage_fixed_scene_curated_001_v1_approach/2026-05-06_00-36-06/checkpoints/010000/pretrained_model"
export AIC_HYBRID_INSERTION_POLICY_PATH_ALIGN="${TRAINING_ROOT}/rangers_training/outputs/sc_stage_fixed_scene_curated_001_v1_align/2026-05-06_00-41-13/checkpoints/010000/pretrained_model"
export AIC_HYBRID_INSERTION_POLICY_PATH_GUARDED_INSERT="${TRAINING_ROOT}/rangers_training/outputs/sc_stage_fixed_scene_curated_001_v1_guarded_insert/2026-05-06_00-46-05/checkpoints/010000/pretrained_model"
export AIC_HYBRID_INSERTION_POLICY_PATH_RETRY_OR_FINISH="${TRAINING_ROOT}/rangers_training/outputs/sc_stage_fixed_scene_curated_001_v1_retry_or_finish/2026-05-06_00-51-10/checkpoints/010000/pretrained_model"

export AIC_HYBRID_INSERTION_STAGE_ROUTE_APPROACH="approach"
export AIC_HYBRID_INSERTION_STAGE_ROUTE_ALIGN="align"
export AIC_HYBRID_INSERTION_STAGE_ROUTE_GUARDED_INSERT="guarded_insert"
export AIC_HYBRID_INSERTION_STAGE_ROUTE_RETRY_OR_FINISH="retry_or_finish"

export AIC_HYBRID_HANDOFF_MODE="${AIC_HYBRID_HANDOFF_MODE:-shadow}"
export AIC_HYBRID_ALLOW_TIMEOUT_GUARD_HANDOFF="${AIC_HYBRID_ALLOW_TIMEOUT_GUARD_HANDOFF:-0}"
export AIC_HYBRID_MAX_INSERTION_SECONDS="${AIC_HYBRID_MAX_INSERTION_SECONDS:-12.0}"
export AIC_HYBRID_REQUIRE_INSERTION_EVENT="${AIC_HYBRID_REQUIRE_INSERTION_EVENT:-1}"

echo "Configured hybrid Enrik -> staged insertion checkpoints:"
echo "  enrik           -> ${AIC_HYBRID_ENRIK_POLICY_PATH}"
echo "  approach        -> ${AIC_HYBRID_INSERTION_POLICY_PATH_APPROACH}"
echo "  align           -> ${AIC_HYBRID_INSERTION_POLICY_PATH_ALIGN}"
echo "  guarded_insert  -> ${AIC_HYBRID_INSERTION_POLICY_PATH_GUARDED_INSERT}"
echo "  retry_or_finish -> ${AIC_HYBRID_INSERTION_POLICY_PATH_RETRY_OR_FINISH}"
echo "  handoff_mode    -> ${AIC_HYBRID_HANDOFF_MODE}"
