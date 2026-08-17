"""Run generated code in a subprocess/Celery worker with a timeout; capture the
raw statistic + p-value. Crash or timeout => fail-closed, never PASS.

TODO(satya): SCOPE.md 4 step 5.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md
"""
