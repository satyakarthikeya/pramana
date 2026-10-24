"""Order the Exact figures as an analyst would present them (PLAN_data_analyst.md s5-6).

Code only: figures are grouped into sections (what happened, why, what stands out), the
same story told on several measures is shown once with the others listed as "also", the
lead is the few figures that matter most, and "what to watch" questions are filled in
from fixed templates using each figure's own numbers. Nothing here is a model call, a
claim, or advice; weights come from `configs/analysis.yaml` and only order the reading.
"""

from __future__ import annotations

from collections.abc import Callable

from pramana.analysis.computed.config import ComputedConfig
from pramana.analysis.computed.models import (
    ComputedAnalysis,
    ExactItem,
    Story,
    StorySection,
    WatchQuestion,
)

#: (key, title, kinds) in reading order.
SECTIONS: list[tuple[str, str, frozenset[str]]] = [
    ("happened", "What happened", frozenset({"period_change", "margins"})),
    (
        "why",
        "Why it moved",
        frozenset(
            {"variance_decomposition", "price_volume_mix", "segment_growth", "concentration"}
        ),
    ),
    (
        "stands_out",
        "What stands out",
        frozenset({"outliers", "customer_view", "rfm", "seasonality", "segment_ranking"}),
    ),
    ("measures", "Measures", frozenset({"prevalence", "weighted_means", "rates"})),
    ("checks", "Checks on the data", frozenset({"identity", "data_quality"})),
]
_SECTION_OF = {kind: key for key, _, kinds in SECTIONS for kind in kinds}
_DEFAULT_WEIGHT = 30.0


def _fmt(value: float) -> str:
    text = f"{value:,.2f}"
    return text[:-3] if text.endswith(".00") else text


def _num(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _worth_showing(item: ExactItem) -> bool:
    """A figure that says something: not a failed one, no empty outlier list, no clean
    data-quality check."""
    if item.status != "ok":
        return False
    if item.kind == "outliers" and not item.values.get("flagged"):
        return False
    return not (item.kind == "data_quality" and not item.values.get("issues"))


def _bonus(item: ExactItem) -> float:
    v = item.values
    match item.kind:
        case "period_change":
            return min(10.0, abs(_num(v.get("change_pct"))) / 5)
        case "variance_decomposition":
            return 10.0 * min(1.0, abs(_num(v.get("top_share"))))
        case "margins":
            move = abs(_num(v.get("change_points")))
            # A margin that did not move is a figure, not a headline.
            return min(10.0, move) if move >= 0.5 else -30.0
        case "outliers":
            return min(10.0, _num(v.get("flagged")))
        case "seasonality":
            spread = _num(v.get("peak_index")) - _num(v.get("low_index"))
            # An index that barely moves is not a pattern worth leading with.
            return min(15.0, 50.0 * spread) if spread >= 0.1 else -30.0
        case "segment_growth":
            return min(10.0, abs(_num(v.get("spread_points"))) / 10)
        case "customer_view":
            return 10.0 * _num(v.get("top_decile_share"))
    return 0.0


def _family(item: ExactItem) -> str:
    """Figures that answer the same question on different measures share a family:
    `outliers:revenue` and `outliers:cost` do; `row_outliers:revenue` does not."""
    return item.id.split(":", 1)[0]


def _primary_measure(result: ComputedAnalysis) -> str | None:
    roles = result.sector.roles
    for item in result.items:
        if item.kind == "period_change" and item.status == "ok" and item.columns:
            if roles.get(item.columns[0]) == "amount":
                return item.columns[0]
    first = next((i for i in result.items if i.status == "ok" and i.columns), None)
    return first.columns[0] if first else None


# --- questions ---------------------------------------------------------------------


def _q_variance(item: ExactItem) -> str | None:
    if not item.table or len(item.columns) < 2:
        return None
    column, group = item.columns[0], item.columns[1]
    total = _num(item.values.get("total_change"))
    fell = [r for r in item.table if _num(r.get("change")) < 0 and r.get("segment") != "other"]
    if total >= 0 and fell:
        worst = min(fell, key=lambda r: _num(r["change"]))
        return (
            f"{group} {worst['segment']} fell by {_fmt(abs(_num(worst['change'])))} in {column}: "
            "what changed there?"
        )
    top = item.values.get("top_segment")
    share = _num(item.values.get("top_share"))
    if top and 0 < share <= 1:
        return f"What is behind {group} {top}, which accounts for {100 * share:.1f}% of the change in {column}?"
    return None


def _q_pvm(item: ExactItem) -> str | None:
    v = item.values
    price, volume = _num(v.get("price_effect")), _num(v.get("volume_effect"))
    sign = lambda x: f"+{_fmt(x)}" if x >= 0 else f"−{_fmt(abs(x))}"  # noqa: E731
    return (
        f"Price moved {sign(price)} and volume {sign(volume)}: was the price change intended, "
        "and did it affect the units sold?"
    )


def _q_outliers(item: ExactItem) -> str | None:
    if not item.table:
        return None
    row = item.table[0]
    column = item.columns[0] if item.columns else "the value"
    if "times_median" in row:
        return (
            f"Is the {column} figure of {_fmt(_num(row['value']))} at {row['where']}, about "
            f"{_num(row['times_median']):.1f} times the median, a data error or a real event?"
        )
    return f"What happened at {row['where']}, when {column} was {_fmt(_num(row['value']))}?"


def _q_margins(item: ExactItem) -> str | None:
    if not item.table:
        return None
    row = item.table[0]
    change = _num(row.get("change_points"))
    if not row.get("level") or abs(change) < 1.0:
        return None
    return (
        f"What lies behind the {'fall' if change < 0 else 'rise'} of {abs(change):.1f} points in "
        f"margin for {row.get('column')} {row['level']}?"
    )


def _q_seasonality(item: ExactItem) -> str | None:
    v = item.values
    if _num(v.get("peak_index")) - _num(v.get("low_index")) < 0.1 or not item.table:
        return None
    names = {int(_num(r["position"])): str(r["name"]) for r in item.table}
    peak = int(_num(v.get("peak_month") or v.get("peak_quarter")))
    return (
        f"Does {names.get(peak, 'the peak')} running {_num(v.get('peak_index')):.2f} times the usual "
        "level match what was expected?"
    )


def _q_growth(item: ExactItem) -> str | None:
    v = item.values
    return (
        f"What is behind {v['fastest_segment']} moving {_num(v['fastest_pct']):+.1f}% while "
        f"{v['slowest_segment']} moved {_num(v['slowest_pct']):+.1f}%?"
    )


def _q_customers(item: ExactItem) -> str | None:
    v = item.values
    amount = item.columns[1] if len(item.columns) > 1 else "the amount"
    return (
        f"How dependent is {amount} on its top {int(_num(v.get('top_n')))} customers, "
        f"who account for {100 * _num(v.get('top_n_share')):.1f}%?"
    )


def _q_rfm(item: ExactItem) -> str | None:
    v = item.values
    pct = v.get("lapsed_regulars_money_pct")
    if pct is None:
        return None
    return (
        f"Lapsed regular customers hold {_num(pct):.1f}% of {item.columns[1]}: "
        "what happened to them, and can it be checked?"
    )


_QUESTIONS: dict[str, Callable[[ExactItem], str | None]] = {
    "variance_decomposition": _q_variance,
    "price_volume_mix": _q_pvm,
    "outliers": _q_outliers,
    "margins": _q_margins,
    "seasonality": _q_seasonality,
    "segment_growth": _q_growth,
    "customer_view": _q_customers,
    "rfm": _q_rfm,
}


# --- the story ---------------------------------------------------------------------


def build_story(result: ComputedAnalysis, config: ComputedConfig) -> ComputedAnalysis:
    """Return `result` with each figure's section, importance and `also`, and a `Story`.

    Guarantees: no figure is removed or changed in content; only the three ordering
    fields are set. Deterministic.
    """
    primary = _primary_measure(result)
    weights = config.story_weights
    scored: dict[str, float] = {}
    for item in result.items:
        base = weights.get(item.kind, _DEFAULT_WEIGHT)
        scored[item.id] = (base + _bonus(item)) if _worth_showing(item) else 0.0

    # One lead per family: the primary measure's figure; the rest are listed under it.
    families: dict[str, list[ExactItem]] = {}
    for item in result.items:
        if _worth_showing(item):
            families.setdefault(_family(item), []).append(item)
    lead_of: dict[str, ExactItem] = {}
    also: dict[str, list[str]] = {}
    for family, members in families.items():
        members = sorted(members, key=lambda i: (primary not in i.columns, -scored[i.id]))
        lead_of[family] = members[0]
        also[members[0].id] = [m.id for m in members[1:]]

    leaders = sorted(lead_of.values(), key=lambda i: (-scored[i.id], result.items.index(i)))
    # Checks only lead when they found something; otherwise they stay in their section.
    lead_pool = [i for i in leaders if _SECTION_OF.get(i.kind) != "checks" or scored[i.id] > 0]
    lead_ids = [i.id for i in lead_pool[: config.lead_items]]

    items = [
        i.model_copy(
            update={
                "section": _SECTION_OF.get(i.kind, "other"),
                "importance": scored[i.id],
                "also": also.get(i.id, []),
            }
        )
        for i in result.items
    ]
    by_id = {i.id: i for i in items}
    hidden = {m for ids in also.values() for m in ids}
    sections = []
    for key, title, kinds in [*SECTIONS, ("other", "Other figures", frozenset())]:
        ids = [
            i.id
            for i in sorted(items, key=lambda i: (-i.importance, items.index(i)))
            if i.status == "ok"
            and (i.section == key)
            and (key != "other" or i.kind not in _SECTION_OF)
            and i.id not in hidden
        ]
        if ids:
            sections.append(StorySection(key=key, title=title, item_ids=ids))

    questions: list[WatchQuestion] = []
    for item in leaders:
        if len(questions) >= config.max_questions:
            break
        make = _QUESTIONS.get(item.kind)
        text = make(by_id[item.id]) if make else None
        if text:
            questions.append(WatchQuestion(text=text, item_id=item.id))
    story = Story(lead_ids=lead_ids, sections=sections, questions=questions)
    return result.model_copy(update={"items": items, "story": story})
