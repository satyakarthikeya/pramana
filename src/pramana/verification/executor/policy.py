"""Sandbox policy: import whitelist (numpy, pandas, scipy, sklearn stats),
no network, no writes outside a temp dir, memory/CPU caps (AGENTS.md 4).
This module SPECIFIES the constraints; the container that enforces them is
shared tooling (see docker/OWNERSHIP.md).

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md
"""
