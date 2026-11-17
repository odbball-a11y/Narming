# Dangerous Dave: adaptive Academy curriculum

Started from the original brain. 122 generations in 30 blocks of 4; each check uses 6 fresh random scenarios; a stage is mastered at 67% at full difficulty. Rivals are matched to the driver's own measured lap pace (following 95%, overtaking 85%); pace targets compare with the scripted driver in the same car. The original is untouched and the candidate is not promoted.

## Placement

Measured typical (median) flying laps, alone, and the scripted driver's best lap in the same car:

| Track | Driver | Scripted, same car |
|---|---|---|
| Oval | 10.954 s | 11.312 s |
| Speedway | 14.179 s | 13.807 s |
| Esses | 15.119 s | 17.126 s |
| Technical | 22.673 s | 21.983 s |
| Grand Prix | 28.669 s | 23.745 s |

| Skill | Passed on entry | Started at | First lesson weights |
|---|---|---|---|
| Vehicle control and racing lines | 3 of 4 | 4. Precision everywhere | 16% |
| Braking, cornering and the grip limit | 1 of 4 | 2. Use the grip | 19% |
| Understeer, oversteer and recovery | 2 of 4 | 3. Spin rescue | 17% |
| Adverse conditions | 2 of 4 | 3. Slippery and tight | 17% |
| Racecraft | 0 of 10 | 1. Catch and follow a car without damage | 31% |

## A. Has he become more competent?

| Stage | Status | Checks | Hardest ease | Before | After |
|---|---|---|---|---|---|
| Vehicle 1: Smooth laps on a wide track | Passed on entry | 0 | 0.00 | 100% | 100% |
| Vehicle 2: Hold the racing line | Passed on entry | 0 | 0.00 | 100% | 100% |
| Vehicle 3: Tight tracks | Passed on entry | 0 | 0.00 | 67% | 83% |
| Vehicle 4: Precision everywhere | Stalled - moved on, competency not demonstrated - stalled at gen 40: failed 4 checks in a row at the easiest setting | 10 | 1.00 | 0% | 0% |
| Braking, 1: Brake before the bend | Passed on entry | 0 | 0.00 | 100% | 100% |
| Braking, 2: Use the grip | Recovered on retest (after stalling) - stalled at gen 48: reached the 12-check limit without passing at full difficulty | 12 | 1.00 | 33% | 33% |
| Braking, 3: On the limit | Stalled - moved on, competency not demonstrated - stalled at gen 90: failed 4 checks in a row at the easiest setting | 10 | 1.00 | 33% | 0% |
| Braking, 4: Fast and tidy | In training | 8 | 0.68 | 0% | 0% |
| Understeer, 1: Catch a twitch | Passed on entry | 0 | 0.00 | 100% | 100% |
| Understeer, 2: A big moment | Passed on entry | 0 | 0.00 | 100% | 100% |
| Understeer, 3: Spin rescue | Recovered on retest (after stalling) - stalled at gen 52: reached the 12-check limit without passing at full difficulty | 13 | 1.00 | 33% | 50% |
| Understeer, 4: Hero recovery | Stalled - moved on, competency not demonstrated - stalled at gen 106: reached the 12-check limit without passing at full difficulty | 13 | 0.34 | 0% | 17% |
| Adverse 1: Back from the grass | Passed on entry | 0 | 0.00 | 83% | 83% |
| Adverse 2: Greasy track | Passed on entry | 0 | 0.00 | 67% | 100% |
| Adverse 3: Slippery and tight | Stalled - moved on, competency not demonstrated - stalled at gen 52: reached the 12-check limit without passing at full difficulty | 13 | 1.00 | 17% | 50% |
| Adverse 4: Ice dancer | Mastered in training | 9 | 0.34 | 50% | 67% |
| Racecraft 1: Catch and follow a car without damage | Mastered in training | 5 | 0.00 | 17% | 100% |
| Racecraft 2: Safe following distance through corners | Stalled - moved on, competency not demonstrated - stalled at gen 62: failed 4 checks in a row at the easiest setting | 10 | 1.00 | 0% | 0% |
| Racecraft 3: Spot the chance to pass a slower car | Mastered in training | 2 | 0.00 | 0% | 100% |
| Racecraft 4: Simple overtakes on predictable cars | Stalled - moved on, competency not demonstrated - stalled at gen 118: reached the 12-check limit without passing at full difficulty | 12 | 1.00 | 0% | 67% |
| Racecraft 5: Overtake with little room | In training | 1 | 0.00 | 0% | 17% |
| Racecraft 6: Pass defensive drivers | Not reached | 0 | 0.00 | 0% | 17% |
| Racecraft 7: Attack, wait or abandon | Not reached | 0 | 0.00 | 0% | 0% |
| Racecraft 8: Through traffic | Not reached | 0 | 0.00 | 0% | 33% |
| Racecraft 9: Defend fairly: no weaving, no blocking | Not reached | 0 | 0.00 | 17% | 17% |
| Racecraft 10: Complete racecraft: full races | Not reached | 0 | 0.00 | 0% | 0% |

Stages: 2 in training, 3 mastered in training, 5 not reached, 8 passed on entry, 2 recovered on retest (after stalling), 6 stalled - moved on, competency not demonstrated.

| Skill | Before | After | Change |
|---|---|---|---|
| Vehicle control and racing lines | 67% | 71% | +4% (within noise) |
| Braking, cornering and the grip limit | 42% | 33% | -8% (within noise) |
| Understeer, oversteer and recovery | 58% | 67% | +8% (within noise) |
| Adverse conditions | 54% | 75% | +21% (within noise) |
| Racecraft | 3% | 35% | +32% (real) |

Strongest: Adverse conditions, Vehicle control and racing lines.  Weakest: Racecraft, Braking, cornering and the grip limit.

## B. Has he become a better racer?

### Fixed-grid benchmark (the verdict): 30 races, 5 laps, every version in every race with zoe-bold, zappy-zoe, clinical-clara; the same tracks, grids and seeds for all.

| Version | Avg place | Wins | Podiums | DNFs | Damage | Car contacts / race | Wall hits / race |
|---|---|---|---|---|---|---|---|
| original | 4.53 +- 0.38 | 3 | 10 | 11 | 55% | 17.3 | 5.4 |
| previous candidate | 4.20 +- 0.38 | 4 | 11 | 6 | 45% | 13.5 | 3.7 |
| first adaptive candidate | 5.67 +- 0.29 | 1 | 4 | 9 | 56% | 16.1 | 6.7 |
| new candidate | 3.67 +- 0.33 | 3 | 13 | 3 | 40% | 13.5 | 2.8 |

By track (average place):

| Version | Oval | Speedway | Esses | Technical | Grand Prix |
|---|---|---|---|---|---|
| original | 2.83 | 4.17 | 3.33 | 6.83 | 5.50 |
| previous candidate | 5.17 | 4.17 | 4.17 | 3.00 | 4.50 |
| first adaptive candidate | 5.33 | 5.67 | 6.17 | 5.50 | 5.67 |
| new candidate | 4.17 | 5.00 | 3.17 | 3.83 | 2.17 |

### Head to head (same races)

| Pair | Races | Ahead - behind | Mean places better | Sign test p | Verdict |
|---|---|---|---|---|---|
| new candidate v original | 30 | 19 - 11 | +0.87 +- 0.53 | 0.201 | no real difference |
| new candidate v previous candidate | 30 | 17 - 13 | +0.53 +- 0.58 | 0.585 | no real difference |
| new candidate v first adaptive candidate | 30 | 24 - 6 | +2.00 +- 0.37 | 0.001 | better |
| previous candidate v original | 30 | 16 - 14 | +0.33 +- 0.61 | 0.856 | no real difference |

### All-car tournament (context only: divisions differ), 8 rounds

| # | Driver | Rating | +- | Races | Wins | Podiums | Avg place | DNFs |
|---|---|---|---|---|---|---|---|---|
| 1 | Bold Zoe | 1148 | 34 | 40 | 14 | 24 | 2.85 | 7 |
| 2 | Clinical Clara | 1142 | 34 | 40 | 5 | 27 | 2.92 | 1 |
| 3 | Zappy Zoe | 1091 | 34 | 40 | 6 | 23 | 3.30 | 2 |
| 4 | Grip Dave | 1077 | 34 | 40 | 8 | 17 | 3.58 | 5 |
| 5 | **Dangerous Dave (previous candidate)** | 1064 | 35 | 40 | 7 | 20 | 3.40 | 1 |
| 6 | **Dangerous Dave (new candidate)** | 1000 | 36 | 40 | 10 | 23 | 3.08 | 1 |
| 7 | **Dangerous Dave (original)** | 977 | 41 | 40 | 20 | 24 | 2.70 | 9 |
| 8 | **Dangerous Dave (first adaptive candidate)** | 744 | 42 | 40 | 4 | 36 | 2.23 | 4 |
| 9 | Careful Keith | 686 | 44 | 40 | 5 | 27 | 2.95 | 9 |

## Verdicts

- **A. Competence:** 3 stages mastered in training, 8 passed on entry, 2 recovered on retest after stalling, 6 still stalled, 7 not finished.
- **B. Racing (fixed grid, against the original):** no real difference (finished ahead in 19 of 30 races, +0.87 places a race).
- Not promoted: promotion is a separate decision.
