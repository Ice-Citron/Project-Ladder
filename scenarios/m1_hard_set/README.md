# M1 hard set — certification (LADDER-TASKING-04, M1.2)

One trial per config. Policy: stock CheatCode, `ground_truth:=true`. A full
success measures 92–93. Failure = no full insertion, or a contact penalty,
or a snag. NIC easy controls: see `../m1_easy_set/README.md`.

| Config | Task | Axis | Total /100 | tier_3 insertion | Failure mode seen | Class |
|--------|------|------|-----------:|------------------|-------------------|-------|
| hc01 | SC | card on rail 2, center | 61.65 | partial, 0.01 m short | snag on nic_card_2; z-floor reached; xy_error <1 mm; no contact penalty | CERTIFIED-HARD |
| hc02 | SC | card on rail 1, max bound | 37.06 | none, 0.05 m short | snag on nic_card_1; the arm could not pull the cable closer; force 23.71 N / 0.52 s, no penalty | CERTIFIED-HARD |
| hc03 | SC | two-card wall, rails 1+3 | 40.34 | none, 0.02 m short | snag; the arm pulled the cable nearer the port; force 24.61 N / 0.04 s, no penalty | CERTIFIED-HARD |
| hc04 | SC | dense forest: 3 cards + 4 mounts | 41.23 | none | snag on all 3 cards; the plug pressed above the port, off by half a plug width; force 27.39 N / 0.18 s, no penalty | CERTIFIED-HARD |
| hc05 | SC | card pair on the corridor: rail 1 max + rail 2 center | 34.99 | none, 0.06 m short | early snag; too little free cable remained after the stuck point; force 36.07 N / 0.43 s, no penalty | CERTIFIED-HARD |
| hc06 | SC | hc05 card pair, target at far end 0.055 (sweep point 3) | 23.05 | none, 0.06 m short | early snag; the stuck point works as a circle center and the free cable as the radius, so each move down needs a move inward; the arm could do neither; lowest score in the set | CERTIFIED-HARD |
| hc07 | SC | far arm start (+pi) + card on rail 2 center | 41.78 | none, 0.01 m short | snag: the cable caught an edge of the card and held; the long path left too little free cable | CERTIFIED-HARD |
| hc08 | SC | hc05 card pair, target moved to mid-rail 0.0 | 24.46 | none, 0.05 m short | early snag; little free cable remained; the plug stayed far off to the side | CERTIFIED-HARD |
| hc09 | SC | board yaw -1.8 (eval trial_3) + target at far end 0.055 + five-card picket | 42.24 | none, 0.02 m short | snag between nic_card_1 and nic_card_2 (lower number = nearer the port); the same tangle held the cable there | CERTIFIED-HARD |

Note: a full board, all five NIC cards on all five NIC rails, is likely the config
with the highest failure probability. This is because, assuming if the NIC cards
are in between the cable's trailing edge and the SC ports, the likelihood where
the cable gets caught up on the NIC cards are much higher compared to less 
NIC-card boards.
