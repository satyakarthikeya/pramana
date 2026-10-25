"""Check what a sentence claims against the table: recompute it, or say why a table cannot."""

from pramana.analysis.statements.check import check_statement
from pramana.analysis.statements.models import CheckedStatement, CheckResult, Statement

__all__ = ["CheckResult", "CheckedStatement", "Statement", "check_statement"]
