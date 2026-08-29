# M1 hard set — certification tracking (LADDER-TASKING-04, M1.2)

Working notes, kept outside the research repo on purpose.
Stock CheatCode, `ground_truth:=true`, one trial per config. Nominal ceiling
100/trial; a full-success run measures ≈ 92–93 in practice (tier_1 = 1,
tier_2 ≈ 17–19, tier_3 = 75).
Failure = no full insertion (+75), or any contact penalty, or an observed snag.
Class: CERTIFIED-HARD (stock fails) / EASY-CONTROL (stock passes).

| Config | Axis | Total /100 | tier_3 insertion | Failure mode seen | Class |
|--------|------|-----------:|------------------|-------------------|-------|
| hc01   | 1 — NIC card blocks SC path (rail 2, center) | 61.65 | partial, 0.01 m short | snag: cable caught nic_card_2; z-floor reached; xy_error <1 mm; no contact penalty | CERTIFIED-HARD |
| hc02   | 1 — NIC card blocks SC path (rail 1, at max bound) | 37.06 | none, 0.05 m short | snag: cable caught nic_card_1, arm could not pull it closer; force spike 23.71 N / 0.52 s (no penalty) | CERTIFIED-HARD |
| hc03   | 1 — two-card wall (rails 1+3) | 40.34 | none, 0.02 m short | snag: similar start to hc02, less severe — arm pulled cable nearer the port; force spike 24.61 N / 0.04 s (no penalty) | CERTIFIED-HARD |
| hc04   | 6 — dense forest: 3 NIC cards + 4 mounts, target in the middle | 41.23 | none | snag: cable caught on all 3 cards; plug pressed right above the port, misaligned by half a plug width, and could not budge; force spike 27.39 N / 0.18 s (no penalty) | CERTIFIED-HARD |
| hc05   | 1 — staggered pair on the corridor: rail 1 at max (hc02 point) + rail 2 at center (hc01 point) | 34.99 | none, 0.06 m short | snag: cable caught EARLY on the cards, so little free cable remained beyond the stuck point — the arm could not bring the plug near the port at all; force spike 36.07 N / 0.43 s (no penalty) | CERTIFIED-HARD |

Superseded easy controls (runs parked in `Personal_Miscellaneous/2026-08-26/`):
- hc04-v1 "arm starts opposite" (shoulder_pan +pi): 92.73/100, full insertion — PASS.
- hc04-v2 "weak dense" (one extra mount, shifted mounts): 92.77/100, full insertion — PASS.
- hc05-v1 "board yaw 2.62": never run; judged easy — ground truth hands stock
  the full 6-DOF port pose, so orientation alone does not hurt it.
- hc05-v2 "rail 1 card at min bound" (run 2026-08-29, parked in
  `Personal_Miscellaneous/2026-08-29/hc05-v2-min-bound-easycontrol/`):
  92.65/100, full insertion in 34.10 s — PASS. The cable visibly draped over
  the card, but the arm had room and pulled it through. The min-bound shift
  moved the card OUT of the drag corridor.
- hc05-v3 "rail 2 card at max bound" (run 2026-08-29, parked in
  `Personal_Miscellaneous/2026-08-29/hc05-v3-rail2-max-easycontrol/`):
  91.38/100, full insertion — PASS. The max shift moved the card OUT of
  rail 2's corridor crossing (which sits near the center, per hc01).
Lesson: stock fails only on obstacles in or near the plug-port corridor, and
only when the snag is unrecoverable. The corridor is a diagonal: it crosses
rail 1 near its MAX end and rail 2 near its CENTER, so each rail has its own
narrow band of bad translations, and the band moves toward the negative end
as the rail index grows.
