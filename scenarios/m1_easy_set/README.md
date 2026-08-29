# M1 easy set

Stock CheatCode passes each config here with `ground_truth:=true`. Use them
for dataset generation and as regression controls in each MyCheatCode
benchmark sweep. 

| File | Task | Case | Score |
|------|------|------|------:|
| ec01.yaml | SC | arm starts on the opposite side, free path | 92.73 |
| ec02.yaml | SC | NIC card on rail 1 at the min bound | 92.65 |
| ec03.yaml | SC | NIC card on rail 2 at the max bound | 91.38 |
| ec04.yaml | SFP | neighbor cards wall in the target | 92.93 |
| ec05.yaml | SFP | one card in the drag corridor | 93.19 |
| ec06.yaml | SFP | two-card wall before the edge target | 93.09 |
| ec07.yaml | SC | target at far end (+0.055), two cards at 0.005 | 93.18 |
| ec08.yaml | SC | board yaw -1.8, eval_config trial_3 verbatim | 92.98 |
