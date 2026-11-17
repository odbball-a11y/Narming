# Dangerous Dave: adaptive Academy curriculum

Started from the original brain. 120 generations in 30 blocks of 4; each check uses 6 fresh random scenarios; a stage is mastered at 67% at full difficulty. Rivals are matched to the driver's own measured lap pace (following 95%, overtaking 85%); pace targets compare with the scripted driver in the same car. The original is untouched and the candidate is not promoted.

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
| Vehicle 2: Hold the racing line | Passed on entry | 0 | 0.00 | 100% | 67% |
| Vehicle 3: Tight tracks | Passed on entry | 0 | 0.00 | 67% | 67% |
| Vehicle 4: Precision everywhere | Stalled - moved on, competency not demonstrated - stalled at gen 40: failed 4 checks in a row at the easiest setting | 10 | 1.00 | 0% | 17% |
| Braking, 1: Brake before the bend | Passed on entry | 0 | 0.00 | 100% | 100% |
| Braking, 2: Use the grip | Stalled - moved on, competency not demonstrated - stalled at gen 48: reached the 12-check limit without passing at full difficulty | 12 | 1.00 | 33% | 83% |
| Braking, 3: On the limit | Stalled - moved on, competency not demonstrated - stalled at gen 88: failed 4 checks in a row at the easiest setting | 10 | 1.00 | 33% | 33% |
| Braking, 4: Fast and tidy | In training | 8 | 1.00 | 0% | 0% |
| Understeer, 1: Catch a twitch | Passed on entry | 0 | 0.00 | 100% | 100% |
| Understeer, 2: A big moment | Passed on entry | 0 | 0.00 | 100% | 100% |
| Understeer, 3: Spin rescue | Stalled - moved on, competency not demonstrated - stalled at gen 40: failed 4 checks in a row at the easiest setting | 10 | 1.00 | 33% | 17% |
| Understeer, 4: Hero recovery | Stalled - moved on, competency not demonstrated - stalled at gen 88: reached the 12-check limit without passing at full difficulty | 12 | 0.68 | 0% | 17% |
| Adverse 1: Back from the grass | Passed on entry | 0 | 0.00 | 83% | 67% |
| Adverse 2: Greasy track | Passed on entry | 0 | 0.00 | 67% | 50% |
| Adverse 3: Slippery and tight | Stalled - moved on, competency not demonstrated - stalled at gen 40: failed 4 checks in a row at the easiest setting | 10 | 1.00 | 17% | 0% |
| Adverse 4: Ice dancer | Stalled - moved on, competency not demonstrated - stalled at gen 96: reached the 12-check limit without passing at full difficulty | 14 | 0.68 | 50% | 0% |
| Racecraft 1: Catch and follow a car without damage | Mastered in training | 1 | 0.00 | 17% | 100% |
| Racecraft 2: Safe following distance through corners | Stalled - moved on, competency not demonstrated - stalled at gen 44: failed 4 checks in a row at the easiest setting | 10 | 1.00 | 0% | 0% |
| Racecraft 3: Spot the chance to pass a slower car | Mastered in training | 1 | 0.00 | 0% | 50% |
| Racecraft 4: Simple overtakes on predictable cars | Mastered in training | 1 | 0.00 | 0% | 0% |
| Racecraft 5: Overtake with little room | Stalled - moved on, competency not demonstrated - stalled at gen 100: reached the 12-check limit without passing at full difficulty | 12 | 1.00 | 0% | 0% |
| Racecraft 6: Pass defensive drivers | In training | 5 | 0.68 | 0% | 0% |
| Racecraft 7: Attack, wait or abandon | Not reached | 0 | 0.00 | 0% | 0% |
| Racecraft 8: Through traffic | Not reached | 0 | 0.00 | 0% | 33% |
| Racecraft 9: Defend fairly: no weaving, no blocking | Not reached | 0 | 0.00 | 17% | 33% |
| Racecraft 10: Complete racecraft: full races | Not reached | 0 | 0.00 | 0% | 0% |

Stages: 2 in training, 3 mastered in training, 4 not reached, 8 passed on entry, 9 stalled - moved on, competency not demonstrated.

| Skill | Before | After | Change |
|---|---|---|---|
| Vehicle control and racing lines | 67% | 62% | -4% (within noise) |
| Braking, cornering and the grip limit | 42% | 54% | +12% (within noise) |
| Understeer, oversteer and recovery | 58% | 58% | +0% (within noise) |
| Adverse conditions | 54% | 29% | -25% (within noise) |
| Racecraft | 3% | 22% | +18% (real) |

Strongest: Vehicle control and racing lines, Understeer, oversteer and recovery.  Weakest: Adverse conditions, Racecraft.

## B. Has he become a better racer?

### Fixed-grid benchmark (the verdict): 30 races, 5 laps, every version in every race with zoe-bold, zappy-zoe, clinical-clara; the same tracks, grids and seeds for all.

| Version | Avg place | Wins | Podiums | DNFs | Damage | Car contacts / race | Wall hits / race |
|---|---|---|---|---|---|---|---|
| original | 3.97 +- 0.27 | 3 | 11 | 10 | 51% | 16.1 | 4.1 |
| previous candidate | 3.70 +- 0.32 | 4 | 13 | 4 | 46% | 11.6 | 2.9 |
| new candidate | 4.70 +- 0.24 | 1 | 4 | 8 | 52% | 11.5 | 6.6 |

By track (average place):

| Version | Oval | Speedway | Esses | Technical | Grand Prix |
|---|---|---|---|---|---|
| original | 3.17 | 4.00 | 2.83 | 4.83 | 5.00 |
| previous candidate | 4.50 | 3.83 | 3.83 | 3.17 | 3.17 |
| new candidate | 4.00 | 5.50 | 4.50 | 5.17 | 4.33 |

### Head to head (same races)

| Pair | Races | Ahead - behind | Mean places better | Sign test p | Verdict |
|---|---|---|---|---|---|
| new candidate v original | 30 | 11 - 19 | -0.73 +- 0.40 | 0.201 | no real difference |
| new candidate v previous candidate | 30 | 8 - 22 | -1.00 +- 0.42 | 0.016 | worse |
| previous candidate v original | 30 | 18 - 12 | +0.27 +- 0.51 | 0.362 | no real difference |

### All-car tournament (context only: divisions differ), 8 rounds

| # | Driver | Rating | +- | Races | Wins | Podiums | Avg place | DNFs |
|---|---|---|---|---|---|---|---|---|
| 1 | Bold Zoe | 1114 | 33 | 40 | 11 | 20 | 3.38 | 13 |
| 2 | Zappy Zoe | 1090 | 33 | 40 | 10 | 21 | 3.30 | 5 |
| 3 | Clinical Clara | 1076 | 33 | 40 | 8 | 22 | 3.38 | 4 |
| 4 | **Dangerous Dave (previous candidate)** | 1052 | 33 | 40 | 6 | 17 | 3.70 | 8 |
| 5 | Grip Dave | 1011 | 32 | 40 | 5 | 11 | 4.42 | 11 |
| 6 | **Dangerous Dave (original)** | 978 | 32 | 40 | 0 | 9 | 5.08 | 14 |
| 7 | **Dangerous Dave (new candidate)** | 935 | 32 | 40 | 0 | 7 | 5.47 | 12 |
| 8 | Careful Keith | 770 | 35 | 40 | 0 | 2 | 7.28 | 16 |

## Verdicts

- **A. Competence:** 3 stages mastered in training, 8 passed on entry, 0 recovered on retest after stalling, 9 still stalled, 6 not finished.
- **B. Racing (fixed grid, against the original):** no real difference (finished ahead in 11 of 30 races, -0.73 places a race).
- Not promoted: promotion is a separate decision.
