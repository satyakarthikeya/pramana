# Effect-size band calibration (WP5, 14 October 2026)

Resolves what can be resolved of `OPEN_ISSUES.md` 11. Reproduce with
`scripts/calibration/measure_effects.py` (effects + permutation p) and
`scripts/calibration/check_demo_gate.py` (full `verify_batch`, template generator,
10,000 permutations). Data: `data/demo/nhanes_demo.csv` (NHANES 2017-18, 1,500 adults,
gitignored), seed 20260817, 34 candidates.

## Outcome

**No band number changed.** The measurement showed the existing floors are safe, and
that a floor cannot do the separating job `OPEN_ISSUES` 11 feared it might.

| role | pair | metric | effect (gated) | p (10k perms) | verdict |
|---|---|---|---|---|---|
| TRUE | age ~ systolic BP | spearman_rho | +0.483 | 1.0e-4 | PASS |
| TRUE | BMI ~ HDL | spearman_rho | -0.328 | 1.0e-4 | PASS |
| DECOY | hba1c ~ moon phase (n=40) | spearman_rho | +0.298 | 0.062 (q 0.070) | REJECT, inconclusive |
| chance-null | hdl ~ moon (n=40) | spearman_rho | +0.278 | 0.076 (q 0.083) | REJECT |
| chance-null | income ~ moon (n=35) | spearman_rho | -0.239 | 0.168 | REJECT |
| chance-null | waist ~ moon (n=39), sex ~ moon (n=40) | rho / delta | 0.151 / 0.157 | 0.36 / 0.42 | REJECT |
| unplanted-real | 14 further rho pairs, n~1500 | spearman_rho | 0.160 to 0.904 | at p floor | PASS |
| unplanted-real | 4 sex ~ x pairs | cliffs_delta | 0.155 to 0.817 | at p floor | PASS |
| unplanted-real | 9 race/ethnicity ~ x pairs | epsilon_squared (sqrt) | 0.120 to 0.279 | 1e-4 to 8e-4 | PASS |

There are no trend (tau) candidates and no planted group difference in this frame.

## What the numbers say

* **True signals clear the rho floor (0.10) by 0.23 (BMI ~ HDL) and 0.38 (age ~ SBP).**
  SE of rho at n=1500 is about 0.026, so the weaker margin is about 8 SE.
* **The floor cannot separate truth from chance nulls.** The decoy (0.298) and a chance
  pair (0.278) sit within 0.05 of the weaker true signal (0.328). Any floor between them
  leaves about 1 SE of margin on a real finding. The chance nulls are rejected by
  `q < alpha`, not by the band, which is the design (the floor exists for large-n trivial
  effects, AGENTS.md 3.5).
* **Most "other" pairs are not nulls.** At n=1500 nearly every candidate is a genuine
  NHANES association (sex ~ height, BMI ~ waist). They pass correctly.

## Why the floors were not raised

* Rho, tau, delta and sqrt(epsilon^2) at their current values are each Cohen's / Romano's
  "small" edge, so they are on a common footing. Raising some and not others breaks it.
* `test_evidence.py::test_epsilon_squared_is_gated_on_its_square_root` requires
  sqrt(0.02) = 0.1414 to PASS, so the epsilon-squared floor cannot exceed 0.141 without
  editing that test. Cramer's V is likewise pinned to (0.09, 0.18] by the k=2 / k=5 test.
* tau, delta and epsilon-squared have no planted anchor here: they remain
  convention-based and provisional. Cramer's V is unreachable (`OPEN_ISSUES` 10).

## Decision for the team: a stricter tier

A floor of 0.20 on rho and delta is safe for the planted truth (margin 0.13 on the weaker
pair, about 5 SE) but would turn these real, small effects into NEGLIGIBLE: age ~ waist
0.160, total_chol ~ hdl 0.160, height ~ diastolic 0.169, hba1c ~ hdl 0.182, sex ~ waist
0.155, sex ~ diastolic 0.187. It would take PASS from 29 to 23. Epsilon-squared cannot
follow (test cap above), so the metrics would be on different footings. This is a policy
choice, not a calibration necessity, and is left to the team.

## Decoy (`build_demo_nhanes.py`, `decoy_target_rho` 0.20)

Different frame from the one above (`data/demo_nhanes_small.csv`, 600 rows, glucose).
Checked across six seeds (42, 1-5; seed varies row sample, shuffle and pilot). The
targeted decoy, LBXGLU ~ BIRTH_MOON_PHASE_PCT, is proposed and REJECTed in all six
(p 0.21 to 0.22, q 0.22 to 0.33). One caveat: in seed 5 an unrelated pair, BMI ~ moon
phase, PASSes by chance (p 0.0069, q 0.011, rho +0.42 on n=40), a forking-paths hit on
the nonsense column rather than the planted decoy. Seed 42, the script's own, is clean.

## Known-answer simulation of the unanchored floors (2026-10-20)

`scripts/calibration/simulate_bands.py` (seed 20261020, 400 reps) plants relationships of
known strength and reads the floors from the config. No band value was changed. This is a
consistency check, not a fit: it does not use the demo's PASS/REJECT outcome.

| metric (floor) | null 99th pct of abs(effect), n=40 / 200 / 1500 | planted truth at the floor (n=1500) |
|---|---|---|
| spearman_rho (0.10) | 0.396 / 0.195 / 0.066 | planted r 0.10 gives rho 0.096 |
| kendall_tau_b (0.07) | 0.290 / 0.127 / 0.044 | planted r 0.10 gives tau 0.064, so tau 0.07 matches rho 0.10 |
| cliffs_delta (0.15) | 0.485 / 0.193 / 0.071 | mean shift d 0.2 gives 0.113, d 0.5 gives 0.277; the floor sits near d 0.27 |
| epsilon_squared (0.10 on sqrt, eps^2 0.01) | sqrt null 99th pct 0.169 at n=300 | k=3 shift 0.2 gives eps^2 0.026 |

Findings:
* **tau and rho are mutually consistent**: the tau floor is the rho floor for the same
  planted relationship. This anchors tau to the measured rho.
* **Every floor is below chance noise at n <= 200 and above it at n = 1500.** That is the
  intended role (AGENTS.md 3.5): small samples are gated by q < alpha, the floor only
  removes large-n trivial effects. It is not a separator of truth from chance.
* **cliffs_delta is slightly stricter than rho** (about d 0.27 versus r 0.10). It is the
  Romano convention and is left alone; the gap is disclosed, not tuned away.
* **No metric was found mis-set**, so the remaining open item is only the policy choice of
  a stricter 0.20 tier above. Cramer's V stays uncalibrated because it is out of scope
  (SCOPE.md section 7 row 2).
