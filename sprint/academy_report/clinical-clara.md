# Academy report: Clinical Clara

Aggression 1.0, caution 0.45; car speed 3  accel 3  handling 3  brakes 3  medium.  Enrolled 2026-11-15 17:59.

## Summary

- Training: 30 generations; candidate = generation 20 (chosen on the seen scenarios only).
- Pass rate on UNSEEN scenarios: **36% -> 27%** (seen: 41% -> 41%).
- Challenges completed (unseen, at least half the variants passed): 16 -> 13 of 32.
- Overall assessment: **E (novice)** (before: E (novice)).

## By module (unseen pass rate)

| Module | Before | After | Change |
|---|---|---|---|
| 1. Vehicle control and racing lines | 62% | 38% | -25% |
| 2. Braking, cornering and the grip limit | 50% | 25% | -25% |
| 3. Understeer, oversteer and recovery | 50% | 50% | +0% |
| 4. Controlled sliding and adverse surfaces | 62% | 62% | +0% |
| 5. Traffic awareness and race management | 12% | 0% | -12% |
| 6. Defensive driving and overtaking | 50% | 12% | -38% |
| 7. Passing judgement, patience and opportunity | 0% | 25% | +25% |
| 8. Competitive racecraft and full races | 0% | 0% | +0% |

## Challenges

Unseen variants passed (of 2), before -> after. Seen variants in brackets.

| Challenge | Level | Objectives | Before | After |
|---|---|---|---|---|
| M1L1 Clean laps | beginner | laps >= 1.8, offtrack <= 0.05, damage <= 0.05 | 2/2 (2/2) | 1/2 (2/2) |
| M1L2 Holding the line | intermediate | pace <= 1.05, line_error <= 0.45, offtrack <= 0.03 | 2/2 (2/2) | 1/2 (2/2) |
| M1L3 Precision lines | advanced | pace <= 1.02, line_error <= 0.4, offtrack <= 0.02 | 0/2 (1/2) | 0/2 (1/2) |
| M1L4 Master of the line | master | pace <= 1.0, line_error <= 0.35, offtrack <= 0.01, damage <= 0.02 | 1/2 (0/2) | 1/2 (0/2) |
| M2L1 Brake before the bend | beginner | pace <= 1.06, slide <= 0.15, damage <= 0.05 | 2/2 (2/2) | 2/2 (2/2) |
| M2L2 Using the grip | intermediate | pace <= 0.97, limit_use >= 0.14, damage <= 0.05 | 2/2 (0/2) | 0/2 (0/2) |
| M2L3 On the limit | advanced | pace <= 0.95, limit_use >= 0.17, damage <= 0.05 | 0/2 (0/2) | 0/2 (0/2) |
| M2L4 Fast and tidy | master | pace <= 0.93, slide <= 0.06, damage <= 0.02 | 0/2 (0/2) | 0/2 (0/2) |
| M3L1 Catch a twitch | beginner | recovered <= 3.0, walls <= 0, damage <= 0.03 | 2/2 (2/2) | 2/2 (2/2) |
| M3L2 Wide-eyed moment | intermediate | recovered <= 3.0, walls <= 0, damage <= 0.05 | 1/2 (2/2) | 1/2 (1/2) |
| M3L3 Spin rescue | advanced | recovered <= 2.5, walls <= 0, damage <= 0.05 | 0/2 (1/2) | 0/2 (1/2) |
| M3L4 Hero recovery | master | recovered <= 2.0, walls <= 0, damage <= 0.03 | 1/2 (0/2) | 1/2 (0/2) |
| M4L1 Back from the grass | beginner | recovered <= 3.0, damage <= 0.05 | 2/2 (2/2) | 2/2 (2/2) |
| M4L2 Greasy track | intermediate | laps >= 1.8, pace <= 1.08, damage <= 0.05 | 1/2 (2/2) | 2/2 (2/2) |
| M4L3 Slippery and tight | advanced | laps >= 1.8, offtrack <= 0.05, damage <= 0.05 | 1/2 (1/2) | 1/2 (1/2) |
| M4L4 Ice dancer | master | laps >= 1.6, pace <= 1.15, damage <= 0.1, recovered <= 4.0 | 1/2 (0/2) | 0/2 (0/2) |
| M5L1 Catch the slow cars | beginner | reached >= 2, contacts <= 2, damage <= 0.08 | 0/2 (0/2) | 0/2 (0/2) |
| M5L2 Wreck ahead | intermediate | fault <= 1, damage <= 0.1, laps >= 1.5 | 0/2 (0/2) | 0/2 (1/2) |
| M5L3 Busy track | advanced | contacts <= 4, place <= 3, damage <= 0.15 | 0/2 (1/2) | 0/2 (1/2) |
| M5L4 Full field | master | contacts <= 6, place <= 5, damage <= 0.2 | 1/2 (0/2) | 0/2 (1/2) |
| M6L1 First pass | beginner | clean_passes >= 1, contacts <= 2 | 1/2 (1/2) | 0/2 (1/2) |
| M6L2 Hold the lead | intermediate | place <= 1, fault <= 0.5 | 1/2 (2/2) | 1/2 (2/2) |
| M6L3 Pass a defender | advanced | clean_passes >= 1, contacts <= 1 | 2/2 (1/2) | 0/2 (1/2) |
| M6L4 Keep a faster car behind | master | place <= 1, fault <= 0.5 | 0/2 (2/2) | 0/2 (1/2) |
| M7L1 Wait for the gap | beginner | clean_passes >= 1, clean_ratio >= 0.5, contacts <= 1 | 0/2 (1/2) | 0/2 (0/2) |
| M7L2 Three defenders | intermediate | clean_passes >= 1, contacts <= 2 | 0/2 (0/2) | 1/2 (0/2) |
| M7L3 Narrow track, busy field | advanced | clean_passes >= 2, contacts <= 4 | 0/2 (0/2) | 0/2 (0/2) |
| M7L4 Through the pack | master | clean_passes >= 3, contacts <= 5, clean_ratio >= 0.4 | 0/2 (0/2) | 1/2 (0/2) |
| M8L1 Beat the scripted field | beginner | place <= 3, damage <= 0.2 | 0/2 (0/2) | 0/2 (1/2) |
| M8L2 Mixed field | intermediate | place <= 4, damage <= 0.25 | 0/2 (1/2) | 0/2 (1/2) |
| M8L3 House rivals from the back | advanced | place <= 3, fault <= 3 | 0/2 (0/2) | 0/2 (0/2) |
| M8L4 Championship pressure | master | place <= 2, damage <= 0.25 | 0/2 (0/2) | 0/2 (0/2) |

## Skill measures (unseen scenarios, averages)

| Measure | Modules | Before | After |
|---|---|---|---|
| lap pace v scripted | 1-2 | 0.965 | 1.243 |
| distance from the ideal line | 1-1 | 0.415 | 0.429 |
| corner time at the grip limit | 2-2 | 0.169 | 0.120 |
| time sliding | 2-4 | 0.093 | 0.087 |
| seconds to recover | 3-4 | 1.729 | 1.487 |
| contacts | 5-7 | 3.917 | 4.208 |
| clean passes | 6-7 | 0.438 | 0.250 |
| finishing place | 8-8 | 4.875 | 5.375 |

## Race performance (six-car five-lap races, original and candidate in the same field)

| Driver | Races | Wins | Avg place | Damage |
|---|---|---|---|---|
| **Clinical Clara (original)** | 10 | 4 | 2.30 | 38% |
| zoe-bold | 10 | 4 | 2.70 | 38% |
| zappy-zoe | 10 | 1 | 3.20 | 46% |
| **Clinical Clara (Academy candidate)** | 10 | 1 | 3.60 | 40% |
| dangerous-dave | 10 | 0 | 4.10 | 53% |
| careful-keith | 10 | 0 | 5.10 | 41% |

## Assessment

- Strengths: Controlled sliding and adverse surfaces (62%), Understeer, oversteer and recovery (50%).
- Weaknesses: Traffic awareness and race management (0%), Competitive racecraft and full races (0%).
- Improved: time sliding, seconds to recover.
- Got worse: lap pace v scripted, distance from the ideal line, corner time at the grip limit, contacts, clean passes, finishing place.
- Still to develop (19 challenges not completed on unseen scenarios): M1L3 Precision lines, M2L2 Using the grip, M2L3 On the limit, M2L4 Fast and tidy, M3L3 Spin rescue, M4L4 Ice dancer, M5L1 Catch the slow cars, M5L2 Wreck ahead, M5L3 Busy track, M5L4 Full field ....
- In races the candidate races worse than the original (avg place 3.60 v 2.30, wins 1 v 4).

The original brain is unchanged; `python -m ai.academy promote "Clinical Clara"` would make the candidate race in its place.
