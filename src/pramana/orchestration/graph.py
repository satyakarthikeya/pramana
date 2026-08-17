"""LangGraph node graph + conditional edges.

ingest -> subagents -> analysis -> verification -> memory_write -> report
REJECT skips memory_write; executor crash routes to the fail-closed path.

TODO(b-karthikeya): SCOPE_B 4 steps 2 and 5.

Owner: B. Karthikeya
Scope: scope/SCOPE_B_Karthikeya.md
"""
