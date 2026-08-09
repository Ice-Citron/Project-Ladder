#!/usr/bin/env bash
set -euo pipefail

export AIC_ACT_STAGED_ENABLE_STAGED_WRAPPER=true

export AIC_ACT_POLICY_PATH_DEFAULT="/home/starforge-sf95/Black-Projects/Project-Automaton/aic-rangers-isaac-training/rangers_training/outputs/sc_stage_fixed_scene_curated_001_v1_approach/2026-05-06_00-36-06/checkpoints/010000/pretrained_model"
export AIC_ACT_POLICY_PATH_APPROACH="/home/starforge-sf95/Black-Projects/Project-Automaton/aic-rangers-isaac-training/rangers_training/outputs/sc_stage_fixed_scene_curated_001_v1_approach/2026-05-06_00-36-06/checkpoints/010000/pretrained_model"
export AIC_ACT_POLICY_PATH_ALIGN="/home/starforge-sf95/Black-Projects/Project-Automaton/aic-rangers-isaac-training/rangers_training/outputs/sc_stage_fixed_scene_curated_001_v1_align/2026-05-06_00-41-13/checkpoints/010000/pretrained_model"
export AIC_ACT_POLICY_PATH_GUARDED_INSERT="/home/starforge-sf95/Black-Projects/Project-Automaton/aic-rangers-isaac-training/rangers_training/outputs/sc_stage_fixed_scene_curated_001_v1_guarded_insert/2026-05-06_00-46-05/checkpoints/010000/pretrained_model"
export AIC_ACT_POLICY_PATH_RETRY_OR_FINISH="/home/starforge-sf95/Black-Projects/Project-Automaton/aic-rangers-isaac-training/rangers_training/outputs/sc_stage_fixed_scene_curated_001_v1_retry_or_finish/2026-05-06_00-51-10/checkpoints/010000/pretrained_model"

export AIC_ACT_STAGE_ROUTE_APPROACH="approach"
export AIC_ACT_STAGE_ROUTE_ALIGN="align"
export AIC_ACT_STAGE_ROUTE_GUARDED_INSERT="guarded_insert"
export AIC_ACT_STAGE_ROUTE_RETRY_OR_FINISH="retry_or_finish"

echo "Configured staged SC ACT48 v1 checkpoints:"
echo "  approach        -> ${AIC_ACT_POLICY_PATH_APPROACH}"
echo "  align           -> ${AIC_ACT_POLICY_PATH_ALIGN}"
echo "  guarded_insert  -> ${AIC_ACT_POLICY_PATH_GUARDED_INSERT}"
echo "  retry_or_finish -> ${AIC_ACT_POLICY_PATH_RETRY_OR_FINISH}"
