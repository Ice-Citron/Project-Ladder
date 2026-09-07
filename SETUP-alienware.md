# Running the AIC sim on the Alienware

Device: `rucha-Alienware-16X-Aurora-AC16251`, RTX 5070 Laptop GPU.
Verified end to end on 2026-09-04.

Use this recipe, not `ladder/eval/rangers_evaluator/run_aic_eval.py`.
The evaluator drives the sim through `docker compose`, which puts the
container on an isolated network. The host policy then cannot reach the
zenoh router, and `aic_engine` loops forever on
`No node with name 'aic_model' found. Retrying...`.

Distrobox gives the container the host's own network
(`NetworkMode=host`), so the same policy connects immediately. This is
also the workflow the upstream docs use (`submodules/aic/docs/getting_started.md`).

## One-time setup

### 1. Pin `empy` in the fork

A fresh `pixi install` resolves `empy` 4.2.1 for the ROS 2 code
generators, which need 3.x. The build then dies in
`rosidl_generator_rs` with a `TransientParseError`.

Four files in `submodules/aic` carry the pin:

```toml
[package.host-dependencies]
empy = "==3.3.4"
```

- `aic_utils/aic_training_interfaces/pixi.toml`
- `aic_interfaces/aic_control_interfaces/pixi.toml`
- `aic_interfaces/aic_task_interfaces/pixi.toml`
- `aic_interfaces/aic_model_interfaces/pixi.toml`

Then:

```bash
cd ~/Project-Ladder/submodules/aic
pixi install --frozen
pixi run --as-is which ros2   # must print a path under .pixi/envs/
```

### 2. Point distrobox at Docker

`distrobox` autodetects its container engine and prefers Podman over
Docker (`/usr/bin/distrobox-enter`, line 262). Podman is installed on
this machine, so a bare `distrobox enter aic_eval` looks in the wrong
engine and reports `Error: no such container aic_eval`.

```bash
mkdir -p ~/.config/distrobox
echo 'container_manager="docker"' > ~/.config/distrobox/distrobox.conf
```

### 3. Create the container

```bash
docker pull ghcr.io/intrinsic-dev/aic/aic_eval:latest
distrobox create --nvidia -i ghcr.io/intrinsic-dev/aic/aic_eval:latest -n aic_eval
distrobox enter aic_eval -- true   # first enter runs distrobox-init
```

The first enter takes a few minutes. It must report
`Setting up host's nvidia integration... [ OK ]`.

Do not use `-r`. That selects root Docker, and this container lives in
your user Docker.

## Every run

### Terminal 1 — the simulator

```bash
distrobox enter aic_eval
# inside the container:
/entrypoint.sh ground_truth:=true start_aic_engine:=true
```

Both arguments matter. `ground_truth` and `start_aic_engine` each
default to `false` (`aic_bringup/launch/aic_gz_bringup.launch.py`).
Without `ground_truth:=true` the TF seam in `MyCheatCode` finds no port
frame. Without `start_aic_engine:=true` no trial runs and no score
appears.

Wait for `No node with name 'aic_model' found. Retrying...`. That
message is the ready signal, not an error. The engine waits for
terminal 2.

### Terminal 2 — the policy

```bash
cd ~/Project-Ladder/submodules/aic
PYTHONPATH=/home/rucha/Project-Ladder pixi run ros2 run aic_model aic_model \
  --ros-args -p use_sim_time:=true -p policy:=ladder.policy.MyCheatCode
```

`pixi run` keeps an inherited `PYTHONPATH` and appends its own
directories, so `ladder.policy.*` imports from the superproject.

Swap the policy name for any other module, for example
`aic_example_policies.ros.CheatCode` for a stock certification run.

## Log messages that look like faults but are not

| Message | Meaning |
|---|---|
| `No node with name 'aic_model' found. Retrying...` | Engine is up and waits for terminal 2. |
| `[ERROR] aic_model lifecycle is not in the active state` | The engine probes with an insert goal before activation. The next engine line says `rejected by the server as expected`. |
| `Gtk-Message: Failed to load module "canberra-gtk-module"` | Sound theme is absent in the container. Harmless. |
| `[ERROR] APPROACH stage not implemented yet` | `MyCheatCode` stage stub. Expected until that stage is built. |

## What a good run looks like

```
✓ Model Ready for trial 'trial_1'
✓ Endpoints Ready for trial 'trial_1'
✓ Simulator Ready for trial 'trial_1'
✓ Scoring Ready for trial 'trial_1'
...
tier_1: score 1   Model validation succeeded.
```

`tier_1: 1` means the harness accepted the policy. It does not mean the
insertion succeeded. `tier_2` and `tier_3` stay at 0 while the ladder
stages are stubs.

Bags land in `~/aic_results/bag_trial_<n>_<timestamp>/`.
