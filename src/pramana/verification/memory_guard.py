"""THE gate. Single function every ChromaDB write flows through; enforces
verdict == PASS. Integration point with the memory module.

Invariant: memory_write => verdict == PASS (AGENTS.md 0).

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md
"""
