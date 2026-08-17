"""Shared pytest fixtures.

Owner: shared. Module-specific fixtures belong in that module's test folder.

The toy dataframe fixture is deliberately shared between the analysis acceptance test
and the gateway acceptance test, so both modules are provably testing the same data:
one strong planted relationship, one pure-noise pair, one group difference.

TODO: implement alongside the contracts (SCOPE.md §4 step 1).
"""
