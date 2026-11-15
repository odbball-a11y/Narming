# Academy report: Careful Keith

Aggression 0.0, caution 1.0; car speed 3  accel 3  handling 3  brakes 3  medium.  Enrolled 2026-11-15 17:36.

## Summary

- Training: 30 generations; candidate = generation 20 (chosen on the seen scenarios only).
- Pass rate on UNSEEN scenarios: **36% -> 33%** (seen: 34% -> 44%).
- Challenges completed (unseen, at least half the variants passed): 14 -> 15 of 32.
- Overall assessment: **E (novice)** (before: E (novice)).

## By module (unseen pass rate)

| Module | Before | After | Change |
|---|---|---|---|
| 1. Vehicle control and racing lines | 50% | 50% | +0% |
| 2. Braking, cornering and the grip limit | 38% | 38% | +0% |
| 3. Understeer, oversteer and recovery | 88% | 75% | -12% |
| 4. Controlled sliding and adverse surfaces | 100% | 75% | -25% |
| 5. Traffic awareness and race management | 0% | 12% | +12% |
| 6. Defensive driving and overtaking | 12% | 12% | +0% |
| 7. Passing judgement, patience and opportunity | 0% | 0% | +0% |
| 8. Competitive racecraft and full races | 0% | 0% | +0% |

## Challenges

Unseen variants passed (of 2), before -> after. Seen variants in brackets.

| Challenge | Level | Objectives | Before | After |
|---|---|---|---|---|
| M1L1 Clean laps | beginner | laps >= 1.8, offtrack <= 0.05, damage <= 0.05 | 2/2 (2/2) | 2/2 (2/2) |
| M1L2 Holding the line | intermediate | pace <= 1.05, line_error <= 0.45, offtrack <= 0.03 | 1/2 (1/2) | 1/2 (1/2) |
| M1L3 Precision lines | advanced | pace <= 1.02, line_error <= 0.4, offtrack <= 0.02 | 0/2 (1/2) | 0/2 (2/2) |
| M1L4 Master of the line | master | pace <= 1.0, line_error <= 0.35, offtrack <= 0.01, damage <= 0.02 | 1/2 (0/2) | 1/2 (0/2) |
| M2L1 Brake before the bend | beginner | pace <= 1.06, slide <= 0.15, damage <= 0.05 | 2/2 (2/2) | 2/2 (2/2) |
| M2L2 Using the grip | intermediate | pace <= 0.97, limit_use >= 0.14, damage <= 0.05 | 0/2 (1/2) | 1/2 (2/2) |
| M2L3 On the limit | advanced | pace <= 0.95, limit_use >= 0.17, damage <= 0.05 | 0/2 (0/2) | 0/2 (0/2) |
| M2L4 Fast and tidy | master | pace <= 0.93, slide <= 0.06, damage <= 0.02 | 1/2 (0/2) | 0/2 (1/2) |
| M3L1 Catch a twitch | beginner | recovered <= 3.0, walls <= 0, damage <= 0.03 | 2/2 (2/2) | 2/2 (2/2) |
| M3L2 Wide-eyed moment | intermediate | recovered <= 3.0, walls <= 0, damage <= 0.05 | 2/2 (2/2) | 2/2 (2/2) |
| M3L3 Spin rescue | advanced | recovered <= 2.5, walls <= 0, damage <= 0.05 | 2/2 (1/2) | 1/2 (1/2) |
| M3L4 Hero recovery | master | recovered <= 2.0, walls <= 0, damage <= 0.03 | 1/2 (1/2) | 1/2 (2/2) |
| M4L1 Back from the grass | beginner | recovered <= 3.0, damage <= 0.05 | 2/2 (2/2) | 2/2 (2/2) |
| M4L2 Greasy track | intermediate | laps >= 1.8, pace <= 1.08, damage <= 0.05 | 2/2 (2/2) | 2/2 (2/2) |
| M4L3 Slippery and tight | advanced | laps >= 1.8, offtrack <= 0.05, damage <= 0.05 | 2/2 (2/2) | 1/2 (2/2) |
| M4L4 Ice dancer | master | laps >= 1.6, pace <= 1.15, damage <= 0.1, recovered <= 4.0 | 2/2 (1/2) | 1/2 (1/2) |
| M5L1 Catch the slow cars | beginner | reached >= 2, contacts <= 2, damage <= 0.08 | 0/2 (0/2) | 0/2 (0/2) |
| M5L2 Wreck ahead | intermediate | fault <= 1, damage <= 0.1, laps >= 1.5 | 0/2 (0/2) | 1/2 (1/2) |
| M5L3 Busy track | advanced | contacts <= 4, place <= 3, damage <= 0.15 | 0/2 (0/2) | 0/2 (0/2) |
| M5L4 Full field | master | contacts <= 6, place <= 5, damage <= 0.2 | 0/2 (0/2) | 0/2 (0/2) |
| M6L1 First pass | beginner | clean_passes >= 1, contacts <= 2 | 0/2 (0/2) | 0/2 (0/2) |
| M6L2 Hold the lead | intermediate | place <= 1, fault <= 0.5 | 1/2 (2/2) | 1/2 (2/2) |
| M6L3 Pass a defender | advanced | clean_passes >= 1, contacts <= 1 | 0/2 (0/2) | 0/2 (0/2) |
| M6L4 Keep a faster car behind | master | place <= 1, fault <= 0.5 | 0/2 (0/2) | 0/2 (1/2) |
| M7L1 Wait for the gap | beginner | clean_passes >= 1, clean_ratio >= 0.5, contacts <= 1 | 0/2 (0/2) | 0/2 (0/2) |
| M7L2 Three defenders | intermediate | clean_passes >= 1, contacts <= 2 | 0/2 (0/2) | 0/2 (0/2) |
| M7L3 Narrow track, busy field | advanced | clean_passes >= 2, contacts <= 4 | 0/2 (0/2) | 0/2 (0/2) |
| M7L4 Through the pack | master | clean_passes >= 3, contacts <= 5, clean_ratio >= 0.4 | 0/2 (0/2) | 0/2 (0/2) |
| M8L1 Beat the scripted field | beginner | place <= 3, damage <= 0.2 | 0/2 (0/2) | 0/2 (0/2) |
| M8L2 Mixed field | intermediate | place <= 4, damage <= 0.25 | 0/2 (0/2) | 0/2 (0/2) |
| M8L3 House rivals from the back | advanced | place <= 3, fault <= 3 | 0/2 (0/2) | 0/2 (0/2) |
| M8L4 Championship pressure | master | place <= 2, damage <= 0.25 | 0/2 (0/2) | 0/2 (0/2) |

## Skill measures (unseen scenarios, averages)

| Measure | Modules | Before | After |
|---|---|---|---|
| lap pace v scripted | 1-2 | 0.960 | 0.924 |
| distance from the ideal line | 1-1 | 0.401 | 0.404 |
| corner time at the grip limit | 2-2 | 0.113 | 0.159 |
| time sliding | 2-4 | 0.047 | 0.067 |
| seconds to recover | 3-4 | 1.082 | 1.075 |
| contacts | 5-7 | 2.167 | 0.208 |
| clean passes | 6-7 | 0.000 | 0.000 |
| finishing place | 8-8 | 5.875 | 5.875 |

## Race performance (six-car five-lap races, original and candidate in the same field)

| Driver | Races | Wins | Avg place | Damage |
|---|---|---|---|---|
| zappy-zoe | 10 | 1 | 2.40 | 42% |
| clinical-clara | 10 | 5 | 2.60 | 24% |
| zoe-bold | 10 | 3 | 2.80 | 32% |
| dangerous-dave | 10 | 0 | 3.50 | 42% |
| **Careful Keith (original)** | 10 | 1 | 4.30 | 16% |
| **Careful Keith (Academy candidate)** | 10 | 0 | 5.40 | 24% |

## Assessment

- Strengths: Understeer, oversteer and recovery (75%), Controlled sliding and adverse surfaces (75%).
- Weaknesses: Passing judgement, patience and opportunity (0%), Competitive racecraft and full races (0%).
- Improved: lap pace v scripted, corner time at the grip limit, seconds to recover, contacts.
- Got worse: distance from the ideal line, time sliding.
- Still to develop (17 challenges not completed on unseen scenarios): M1L3 Precision lines, M2L3 On the limit, M2L4 Fast and tidy, M5L1 Catch the slow cars, M5L3 Busy track, M5L4 Full field, M6L1 First pass, M6L3 Pass a defender, M6L4 Keep a faster car behind, M7L1 Wait for the gap ....
- In races the candidate races worse than the original (avg place 5.40 v 4.30, wins 0 v 1).

The original brain is unchanged; `python -m ai.academy promote "Careful Keith"` would make the candidate race in its place.
