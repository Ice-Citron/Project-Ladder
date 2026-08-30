# Cable Logger

`cable_logger.py` records ground-truth cable poses at 10 Hz in JSONL format.
Start the simulator with `ground_truth:=true`, then run one command from `submodules/aic`.
Use the plug frame from the active scenario, and stop the logger with `Ctrl+C` after the high traverse.

```bash
# SC task
pixi run python ./ladder/diagnostics/cable_logger.py \
  --output_path /tmp/cable_sc.jsonl \
  --plug-frame cable_1/sc_tip_link

# SFP task
pixi run python ./ladder/diagnostics/cable_logger.py \
  --output_path /tmp/cable_sfp.jsonl \
  --plug-frame cable_0/sfp_tip_link
```
