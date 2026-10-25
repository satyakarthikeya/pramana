"""Turn the gate report card's JSON files into the markdown tables of the calibration note.

    python scripts/calibration/render_gate_calibration.py artifacts/ > /tmp/tables.md

Reads gate_card_attacks.json, gate_card_flaws.json, gate_card_sensitivity.json and
gate_card_families.json (whichever exist) from the given directory. Rendering only: it
computes nothing the card has not already counted, apart from Wilson intervals.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate_report_card as card  # noqa: E402

ARM_LABEL = {"point": "A2 point (current default)", "interval": "A2 interval (kappa 0.10)"}


def _label(arm: str) -> str:
    if arm in ARM_LABEL:
        return ARM_LABEL[arm]
    return f"A2 interval (kappa {arm.split('@')[1]})" if "@" in arm else arm


def _rate(k: int, n: int) -> str:
    lo, hi = card.wilson(k, n)
    return "n/a" if n == 0 else f"{100 * k / n:.1f}% [{100 * lo:.1f}, {100 * hi:.1f}]"


def pooled_table(cells: list[dict], title: str) -> str:
    rows = card.pooled_attack_rows(cells)
    out = [
        f"**{title}**",
        "",
        "| tables that cleared the gate | arm | any check broke | "
        + " | ".join(card.ATTACK_IDS)
        + " | checks run per table |",
        "|---|---|---|" + "---|" * (len(card.ATTACK_IDS) + 1),
    ]
    names = {
        "true": "true effect (false KILL)",
        "null": "luck-pass, no effect (false SURVIVE = 1 - this)",
        "flaw": "planted late-only effect (should be broken)",
    }
    for r in rows:
        k = r["cleared"]
        out.append(
            f"| {names[r['kind']]} (n={k}) | {_label(r['a2_rule'])} | "
            f"{_rate(r['any_broken'], k)} | "
            + " | ".join(_rate(r["per_attack"][a], k) for a in card.ATTACK_IDS)
            + f" | {r['checks_ran'] / max(k, 1):.1f} |"
        )
    return "\n".join(out)


def by_n_table(cells: list[dict]) -> str:
    arms = list(cells[0]["rules"])
    out = [
        "| shape | rho | n | cleared | " + " | ".join(_label(a) for a in arms) + " |",
        "|---|---|---|---|" + "---|" * len(arms),
    ]
    for c in sorted(cells, key=lambda c: (c["rho"] == 0, c["shape"], c["rho"], c["n"])):
        k = c["cleared"]
        out.append(
            f"| {c['shape']} | {c['rho']} | {c['n']} | {k} | "
            + " | ".join(_rate(c["rules"][a]["any_broken"], k) for a in arms)
            + " |"
        )
    return "\n".join(out)


def compact_table(cells: list[dict], null: bool) -> str:
    """Rows = shape; columns = (n, rho); cells 'point % / interval %' of cleared tables broken."""
    chosen = [c for c in cells if (c["rho"] == 0) == null]
    cols = sorted({(c["n"], c["rho"]) for c in chosen})
    shapes = list(dict.fromkeys(c["shape"] for c in chosen))
    head = (
        "| shape | " + " | ".join(f"n={n}" + ("" if null else f", rho={r}") for n, r in cols) + " |"
    )
    out = [head, "|---|" + "---|" * len(cols)]
    for shape in shapes:
        row = []
        for n, r in cols:
            c = next(c for c in chosen if c["shape"] == shape and (c["n"], c["rho"]) == (n, r))
            k = c["cleared"]
            row.append(
                f"{100 * c['rules']['point']['any_broken'] / k:.0f} / "
                f"{100 * c['rules']['interval']['any_broken'] / k:.0f}"
            )
        out.append(f"| {shape} | " + " | ".join(row) + " |")
    return "\n".join(out)


def per_attack_by_shape(cells: list[dict], null: bool) -> str:
    """Per attack, A2 point rule: % of cleared tables broken, pooled over n and rho, by shape."""
    chosen = [c for c in cells if (c["rho"] == 0) == null]
    out = ["| shape | tables | " + " | ".join(card.ATTACK_IDS[:5]) + " |", "|---|---|" + "---|" * 5]
    for shape in dict.fromkeys(c["shape"] for c in chosen):
        cs = [c for c in chosen if c["shape"] == shape]
        k = sum(c["cleared"] for c in cs)
        out.append(
            f"| {shape} | {k} | "
            + " | ".join(
                _rate(sum(c["rules"]["point"]["broken"][a] for c in cs), k)
                for a in card.ATTACK_IDS[:5]
            )
            + " |"
        )
    return "\n".join(out)


def family_table(rows: list[dict]) -> str:
    out = [
        "| design | stage | false discovery proportion (mean +/- MC SE) | any false PASS in a run "
        "[95% Wilson] | power (mean +/- SE) |",
        "|---|---|---|---|---|",
    ]
    stage = {
        "none": "no correction",
        "bh": "BH q < 0.05",
        "holm": "Holm",
        "pass": "gateway PASS (BH + floor + attacks)",
    }
    for r in rows:
        power = "-" if r["power"] is None else f"{r['power']:.3f} +/- {r['power_se']:.3f}"
        out.append(
            f"| {r['scenario']} | {stage[r['arm']]} | {r['fdp']:.3f} +/- {r['fdp_se']:.3f} | "
            f"{100 * r['any_false_pass']:.1f}% [{100 * r['any_false_lo']:.1f}, "
            f"{100 * r['any_false_hi']:.1f}] | {power} |"
        )
    return "\n".join(out)


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts")
    parts = []
    for name, title in (
        ("gate_card_attacks", "Main grid (6 shapes x n 60/120/300 x rho 0.2/0.3/0)"),
        ("gate_card_sensitivity", "Gaussian cells, A2 interval at three budgets"),
        ("gate_card_flaws", "Planted flaw: link present only in the last third of the months"),
    ):
        path = root / f"{name}.json"
        if path.exists():
            cells = json.loads(path.read_text())
            parts += [pooled_table(cells, title), "", "Per cell:", "", by_n_table(cells), ""]
            if name == "gate_card_attacks":
                parts += [
                    "True effects, % broken (A2 point / A2 interval):",
                    "",
                    compact_table(cells, False),
                    "",
                    "Luck-passes, % broken (A2 point / A2 interval):",
                    "",
                    compact_table(cells, True),
                    "",
                    "True effects, per attack under the current (point) rule:",
                    "",
                    per_attack_by_shape(cells, False),
                    "",
                    "Luck-passes, per attack under the current (point) rule:",
                    "",
                    per_attack_by_shape(cells, True),
                    "",
                ]
    path = root / "gate_card_families.json"
    if path.exists():
        parts += [
            "**Correlated families (real gateway)**",
            "",
            family_table(json.loads(path.read_text())),
            "",
        ]
    print("\n".join(parts))


if __name__ == "__main__":
    main()
