"""The single write path. Wraps verification.memory_guard before any write.

No other file in this repo may import chromadb -- there is a test that greps
for it and fails the build (SCOPE_M 4 step 2).

Owner: M. Karthik Reddy
Scope: scope/SCOPE_M_Karthik_Reddy.md
"""
