"""Known-answer calibration of the four unanchored effect-size floors.

Plants relationships of known strength, measures the null sampling spread of each
metric, and reports what true effect each configured floor corresponds to. It reads the
floors from configs/verification.yaml and CHANGES nothing. Reproduce:
    python scripts/calibration/simulate_bands.py
"""
from __future__ import annotations

import numpy as np
import yaml

from pramana.verification.stats.effect_size import (
    cliffs_delta, epsilon_squared, kendall_tau_b, spearman_rho)

SEED, REPS = 20261020, 400
SIZES = (40, 200, 1500)
rng = np.random.default_rng(SEED)
bands = yaml.safe_load(open("configs/verification.yaml"))["evidence"]["effect_thresholds"]


def null_q99(fn, make, n):
    return float(np.quantile([abs(fn(*make(n, 0.0))) for _ in range(REPS)], 0.99))


def biv(n, r):
    x = rng.standard_normal(n)
    return x, r * x + np.sqrt(1 - r * r) * rng.standard_normal(n)


def two(n, d):
    return rng.standard_normal(n // 2) + d, rng.standard_normal(n // 2)


def kgrp(n, shift):
    return ([rng.standard_normal(n // 3) + s for s in (0, shift, 2 * shift)],)


def mean_eff(fn, make, n, p):
    return float(np.mean([fn(*make(n, p)) for _ in range(REPS)]))


print("Null 99th percentile of |effect| (chance alone) vs configured floor")
for name, fn, make in (("spearman_rho", spearman_rho, biv), ("kendall_tau_b", kendall_tau_b, biv),
                       ("cliffs_delta", cliffs_delta, two)):
    print(f"{name:14s} floor {bands[name]['min']:.2f} | " +
          "  ".join(f"n={n}: {null_q99(fn, make, n):.3f}" for n in SIZES))
sq = [np.sqrt(max(epsilon_squared(*kgrp(n, 0.0)), 0)) for n in (300,) for _ in range(REPS)]
print(f"epsilon_squared floor {bands['epsilon_squared']['min']:.2f} on sqrt(eps^2), i.e. eps^2 {bands['epsilon_squared']['min']**2:.3f} "
      f"| null sqrt q99 n=300: {np.quantile(sq, .99):.3f}")

print("\nTrue effect each floor corresponds to (planted, n=1500)")
for r in (0.05, 0.10, 0.15, 0.20, 0.30):
    print(f"  planted r={r:.2f}: rho={mean_eff(spearman_rho, biv, 1500, r):.3f} "
          f"tau={mean_eff(kendall_tau_b, biv, 1500, r):.3f}")
for d in (0.2, 0.5, 0.8):
    print(f"  planted mean shift d={d}: cliffs_delta={mean_eff(cliffs_delta, two, 1500, d):.3f}")
for s in (0.2, 0.4, 0.6):
    e = np.mean([epsilon_squared(*kgrp(1500, s)) for _ in range(REPS)])
    print(f"  planted k=3 shift={s}: epsilon^2={e:.3f} sqrt={np.sqrt(e):.3f}")
