# Academy report: Clinical Clara

Aggression 1.0, caution 0.45; car speed 3  accel 3  handling 3  brakes 3  medium.  Enrolled 2026-11-15 17:59.

## Summary

- Training: 30 generations; candidate = generation 30 (chosen on the seen scenarios only).
- Pass rate on UNSEEN scenarios: **32% -> 16%**, change -16% (real) (each +-3%; 192 runs). Seen: 44% -> 39%.
- Challenges completed (unseen, at least half the variants passed): 11 -> 6 of 32.
- Overall assessment: **E (novice)** (before: E (novice)).

## By module (unseen pass rate)

| Module | Before | After | Change |
|---|---|---|---|
| 1. Vehicle control and racing lines | 54% | 25% | -29% (real) |
| 2. Braking, cornering and the grip limit | 38% | 12% | -25% (real) |
| 3. Understeer, oversteer and recovery | 50% | 33% | -17% (within noise) |
| 4. Controlled sliding and adverse surfaces | 62% | 25% | -38% (real) |
| 5. Traffic awareness and race management | 8% | 0% | -8% (within noise) |
| 6. Defensive driving and overtaking | 25% | 25% | +0% (within noise) |
| 7. Passing judgement, patience and opportunity | 4% | 8% | +4% (within noise) |
| 8. Competitive racecraft and full races | 12% | 0% | -12% (within noise) |

## Challenges

Share of unseen runs passed, before -> after (seen in brackets).

| Challenge | Level | Objectives | Before | After |
|---|---|---|---|---|
| M1L1 Clean laps | beginner | laps >= 1.8, offtrack <= 0.05, damage <= 0.05 | 6/6 (6/6) | 3/6 (6/6) |
| M1L2 Holding the line | intermediate | pace <= 1.05, line_error <= 0.45, offtrack <= 0.03 | 6/6 (6/6) | 3/6 (3/6) |
| M1L3 Precision lines | advanced | pace <= 1.02, line_error <= 0.4, offtrack <= 0.02 | 0/6 (3/6) | 0/6 (3/6) |
| M1L4 Master of the line | master | pace <= 1.0, line_error <= 0.35, offtrack <= 0.01, damage <= 0.02 | 1/6 (0/6) | 0/6 (0/6) |
| M2L1 Brake before the bend | beginner | pace <= 1.06, slide <= 0.15, damage <= 0.05 | 6/6 (6/6) | 3/6 (6/6) |
| M2L2 Using the grip | intermediate | pace <= 0.97, limit_use >= 0.14, damage <= 0.05 | 3/6 (0/6) | 0/6 (0/6) |
| M2L3 On the limit | advanced | pace <= 0.95, limit_use >= 0.17, damage <= 0.05 | 0/6 (0/6) | 0/6 (0/6) |
| M2L4 Fast and tidy | master | pace <= 0.93, slide <= 0.06, damage <= 0.02 | 0/6 (0/6) | 0/6 (0/6) |
| M3L1 Catch a twitch | beginner | recovered <= 3.0, walls <= 0, damage <= 0.03 | 6/6 (6/6) | 3/6 (6/6) |
| M3L2 Wide-eyed moment | intermediate | recovered <= 3.0, walls <= 0, damage <= 0.05 | 3/6 (6/6) | 3/6 (3/6) |
| M3L3 Spin rescue | advanced | recovered <= 2.5, walls <= 0, damage <= 0.05 | 1/6 (3/6) | 0/6 (4/6) |
| M3L4 Hero recovery | master | recovered <= 2.0, walls <= 0, damage <= 0.03 | 2/6 (0/6) | 2/6 (0/6) |
| M4L1 Back from the grass | beginner | recovered <= 3.0, damage <= 0.05 | 6/6 (5/6) | 5/6 (6/6) |
| M4L2 Greasy track | intermediate | laps >= 1.8, pace <= 1.08, damage <= 0.05 | 3/6 (6/6) | 0/6 (6/6) |
| M4L3 Slippery and tight | advanced | laps >= 1.8, offtrack <= 0.05, damage <= 0.05 | 3/6 (3/6) | 1/6 (2/6) |
| M4L4 Ice dancer | master | laps >= 1.6, pace <= 1.15, damage <= 0.1, recovered <= 4.0 | 3/6 (0/6) | 0/6 (0/6) |
| M5L1 Catch the slow cars | beginner | reached >= 2, contacts <= 2, damage <= 0.08 | 1/6 (4/6) | 0/6 (6/6) |
| M5L2 Wreck ahead | intermediate | fault <= 1, damage <= 0.1, laps >= 1.5 | 0/6 (1/6) | 0/6 (0/6) |
| M5L3 Busy track | advanced | contacts <= 4, place <= 3, damage <= 0.15 | 0/6 (3/6) | 0/6 (1/6) |
| M5L4 Full field | master | contacts <= 6, place <= 5, damage <= 0.2 | 1/6 (1/6) | 0/6 (0/6) |
| M6L1 First pass | beginner | clean_passes >= 1, contacts <= 2 | 1/6 (4/6) | 2/6 (6/6) |
| M6L2 Hold the lead | intermediate | place <= 1, fault <= 0.5 | 3/6 (6/6) | 2/6 (4/6) |
| M6L3 Pass a defender | advanced | clean_passes >= 1, contacts <= 1 | 2/6 (3/6) | 0/6 (5/6) |
| M6L4 Keep a faster car behind | master | place <= 1, fault <= 0.5 | 0/6 (6/6) | 2/6 (4/6) |
| M7L1 Wait for the gap | beginner | clean_passes >= 1, clean_ratio >= 0.5, contacts <= 1 | 0/6 (3/6) | 0/6 (1/6) |
| M7L2 Three defenders | intermediate | clean_passes >= 1, contacts <= 2 | 1/6 (1/6) | 2/6 (0/6) |
| M7L3 Narrow track, busy field | advanced | clean_passes >= 2, contacts <= 4 | 0/6 (0/6) | 0/6 (0/6) |
| M7L4 Through the pack | master | clean_passes >= 3, contacts <= 5, clean_ratio >= 0.4 | 0/6 (0/6) | 0/6 (0/6) |
| M8L1 Beat the scripted field | beginner | place <= 3, damage <= 0.2 | 0/6 (0/6) | 0/6 (0/6) |
| M8L2 Mixed field | intermediate | place <= 4, damage <= 0.25 | 2/6 (2/6) | 0/6 (1/6) |
| M8L3 House rivals from the back | advanced | place <= 3, fault <= 3 | 1/6 (0/6) | 0/6 (1/6) |
| M8L4 Championship pressure | master | place <= 2, damage <= 0.25 | 0/6 (0/6) | 0/6 (0/6) |

## Skill measures (unseen scenarios, averages)

| Measure | Modules | Before | After |
|---|---|---|---|
| lap pace v scripted | 1-2 | 0.964 | 1.009 |
| distance from the ideal line | 1-1 | 0.412 | 0.406 |
| corner time at the grip limit | 2-2 | 0.167 | 0.154 |
| time sliding | 2-4 | 0.091 | 0.118 |
| seconds to recover | 3-4 | 1.409 | 1.579 |
| contacts | 5-7 | 4.056 | 4.653 |
| clean passes | 6-7 | 0.292 | 0.312 |
| finishing place | 8-8 | 4.250 | 4.625 |

## Race performance (six-car five-lap races, original and candidate in the same field)

| Driver | Races | Wins | Avg place | Damage |
|---|---|---|---|---|
| **Clinical Clara (Academy candidate)** | 20 | 7 | 2.50 +- 0.31 | 40% |
| zappy-zoe | 20 | 3 | 2.95 +- 0.26 | 55% |
| **Clinical Clara (original)** | 20 | 3 | 3.10 +- 0.34 | 38% |
| dangerous-dave | 20 | 5 | 3.20 +- 0.37 | 45% |
| zoe-bold | 20 | 2 | 3.55 +- 0.31 | 49% |
| careful-keith | 20 | 0 | 5.70 +- 0.20 | 35% |

## Assessment

- Strengths: Understeer, oversteer and recovery (33%), Vehicle control and racing lines (25%).
- Weaknesses: Traffic awareness and race management (0%), Competitive racecraft and full races (0%).
- Improved: distance from the ideal line, clean passes.
- Got worse: lap pace v scripted, corner time at the grip limit, time sliding, seconds to recover, contacts, finishing place.
- Still to develop (26 challenges not completed on unseen scenarios): M1L3 Precision lines, M1L4 Master of the line, M2L2 Using the grip, M2L3 On the limit, M2L4 Fast and tidy, M3L3 Spin rescue, M3L4 Hero recovery, M4L2 Greasy track, M4L3 Slippery and tight, M4L4 Ice dancer ....
- In races the candidate races about the same (within noise) than the original (avg place 2.50 v 3.10, wins 7 v 3).

The original brain is unchanged; `python -m ai.academy promote "Clinical Clara"` would make the candidate race in its place.
