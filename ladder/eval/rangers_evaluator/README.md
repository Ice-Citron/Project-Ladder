# Rangers Evaluator

Repeatable Gazebo evaluation runner for AIC policies.

This package automates the benchmark flow that was previously manual:

- launch Gazebo
- launch `aic_engine`
- launch a chosen policy
- run `N` trials
- collect `scoring.yaml`
- print a concise evaluation summary

The public entrypoint is:

- `rangers_evaluator/run_aic_eval.py`

## Layout

```text
rangers_evaluator/
├── README.md
├── run_aic_eval.py
└── src/
    ├── cli.py
    ├── errors.py
    ├── main.py
    ├── reporting.py
    ├── runtime.py
    └── workspace.py
```

## Default Behavior

The runner is Docker-first by default.

- `eval` runs in Docker
- `model` runs in Docker
- local Pixi is only used if `--local-model` is supplied

This is the intended portable path for teammates on different local setups.

In the commands below, replace `~/%REPO_DIRECTORY%/aic-rangers` with the location of your local checkout.

## Requirements

Expected host prerequisites:

- Docker with GPU support for the AIC stack
- a working Linux desktop/X11 session if using `--gazebo-gui` or `--launch-rviz`
- the repo checked out locally

The runner does **not** require `xhost +si:localuser:root` anymore on this machine. It now creates a per-run X11 cookie file for GUI access.

## Before vs After

The old manual benchmark flow required two terminals.

### Before: 2 terminals

Terminal 1: eval container

```bash
/entrypoint.sh \
  ground_truth:=true \
  start_aic_engine:=true \
  aic_engine_config_file:=/home/starforge-sf95/Black-Projects/Project-Automaton/aic-rangers/rangers_scenario_generator/config/config_template.yaml
```

Terminal 2: CheatCode policy

```bash
pixi run ros2 run aic_model aic_model --ros-args -p use_sim_time:=true -p policy:=aic_example_policies.ros.CheatCode
```

The evaluator collapses that into one command.

### After: 1 terminal (`rangers_evaluator`)

```bash
cd ~/%REPO_DIRECTORY%/aic-rangers
python3 rangers_evaluator/run_aic_eval.py \
  --local-model \
  --scenario rangers_scenario_generator/config/config_template.yaml \
  --policy aic_example_policies.ros.CheatCode \
  --ground-truth \
  --num-trials 3 \
  --gazebo-gui \
  --launch-rviz
```

This will:

- create a timestamped run directory under `aic_eval_runs/`
- trim the configured trials if `--num-trials` is supplied
- launch the eval stack
- launch the local policy process for you
- print the final score summary

Window titles to look for:

- `Gazebo Sim`
- `RViz`

## Expected Output

For the command above, a successful run should end with a summary in this shape:

```text
Total score: 273.424
trial_1: total=91.271 (tier_1=1.000, tier_2=15.271, tier_3=75.000)
trial_2: total=91.315 (tier_1=1.000, tier_2=15.315, tier_3=75.000)
trial_3: total=90.837 (tier_1=1.000, tier_2=14.837, tier_3=75.000)
```

Exact floating-point values may vary slightly across runs, but the important success signal is:

- `results/scoring.yaml` exists
- all three trials show `tier_3=75.000`
- total score lands around the low/mid `270s`

## Scenario Generator Integration

The runner is config-driven, so it can evaluate generated scenarios as long as they produce a normal `aic_engine` YAML file.

Example:

```bash
cd ~/%REPO_DIRECTORY%/aic-rangers
python3 rangers_evaluator/run_aic_eval.py \
  --scenario rangers_scenario_generator/scenarios/scenario.yaml \
  --policy aic_example_policies.ros.WaveArm \
  --num-trials 1
```

Related generator:

- `rangers_scenario_generator/src/scenario_generator.py`

## Policy Contract

The evaluator expects a Python policy module path, not a raw checkpoint file.

Examples:

- `aic_example_policies.ros.WaveArm`
- `aic_example_policies.ros.RunACT`
- `my_team_policies.ros.MyPolicy`

Important:

- a bare `.pt` file is not enough
- the checkpoint must be loaded by a Python policy class that satisfies the AIC `Policy` interface
- that wrapper class is what you pass to `--policy`

So the intended path for an Isaac-trained model is:

1. train and save a checkpoint
2. wrap it in an AIC policy module
3. pass that module path to this evaluator

## Useful Flags

### Use a custom scenario

```bash
--scenario path/to/scenario.yaml
```

### Limit to the first `N` trials

```bash
--num-trials 3
```

### Rebuild the Dockerized model image first

```bash
--build
```

### Keep containers after the run

```bash
--keep-containers
```

### Run the policy locally instead of in Docker

```bash
--local-model
```

Important:

- `--local-model` still requires an `aic_model` ROS node
- the difference is that the node is launched on the host instead of in the Docker `model` service
- by default, the evaluator starts it with `pixi run --as-is ros2 run aic_model aic_model ...`
- so the host must have a working local Pixi environment and the `aic_model` package available
- `aic_engine` still waits for the lifecycle node named `aic_model`

### Override the full local policy launch command

```bash
--policy-cmd 'pixi run --as-is ros2 run aic_model aic_model --ros-args ...'
```

This is only valid together with `--local-model`.

## Output Artifacts

Each run writes a directory under `aic_eval_runs/` containing:

- `config.yaml` copied from the selected scenario input
- `docker-compose.override.yaml`
- `compose.log`
- `results/scoring.yaml`
- `run-metadata.yaml`

If `--local-model` is used, the run will also include:

- `eval.log`
- `policy.log`

## Success Criteria

A successful run looks like:

- `aic_engine` exits cleanly
- `results/scoring.yaml` exists
- the script prints `Evaluation summary`
- total and per-trial scores are shown

Example summary shape:

```text
Evaluation summary
Policy: aic_example_policies.ros.WaveArm
Scenario: .../config.yaml
Run dir: .../aic_eval_runs/...
Scoring: .../results/scoring.yaml
Total score: 34.844
trial_1: total=34.844 (tier_1=1.000, tier_2=21.182, tier_3=12.662)
```

## Known Caveat

Gazebo teardown is still noisy after successful runs.

You may see shutdown-time errors such as:

- `double free or corruption (!prev)`
- `corrupted size vs. prev_size while consolidating`

This has been observed after scoring is already written. The evaluator suppresses those known shutdown-only lines from the console once `scoring.yaml` exists, but the full raw logs are still preserved in the run directory. Treat them as teardown noise unless the run fails to produce `scoring.yaml`.

## Troubleshooting

### `No node with name 'aic_model' found`

This usually means the model process did not come up correctly or the non-default local path is misconfigured.

Check:

- `compose.log`
- `policy.log` if using `--local-model`

In the default dockerized-model mode, the runner now assigns the `model`
service a content-fingerprinted image tag and auto-builds that image when the
local cache is missing. This avoids silently reusing an unrelated stale local
`my-solution:v1` image from an older build. Use `--build` if you want to force
an explicit rebuild of that fingerprinted image.

### GUI windows do not seem to appear

Check:

- whether the run finished too quickly
- whether the windows opened behind other apps
- whether the host is actually running X11

Use `--num-trials 5` or more for visual debugging.

### I want to check the CLI quickly

```bash
cd ~/%REPO_DIRECTORY%/aic-rangers
python3 rangers_evaluator/run_aic_eval.py --help
```

## Current Recommendation

Use this package for Gazebo benchmarking and scoring.

Do not build separate MuJoCo and Isaac evaluators unless there is an explicit requirement. The cleaner workflow is:

1. train in Isaac Sim if desired
2. wrap the checkpoint in an AIC policy class
3. benchmark it here in Gazebo 
