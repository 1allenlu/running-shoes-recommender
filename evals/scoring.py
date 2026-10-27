"""Eval scores (ROADMAP Phase 9). Pure functions over plain dicts, so they work both in the
local runner and as LangSmith evaluators.

- hit_rate: an expert's pick appears in the top 3
- size_accuracy: recommended size within half a size of the expert's, for matched shoes
- link_validity: share of links that exist in `offers` (must be 1.0)
- parser_accuracy: share of scan fields the parser got right (sizes/widths exact, bands equal,
  positions within the tolerance)
"""

import re

from app.parsing.compare import POSITION_TOLERANCE, SCALES
from app.schemas.foot_profile import FootProfile

SIZE_TOLERANCE = 0.5


def _normalize(text: str) -> str:
    return " " + " ".join(re.findall(r"[a-z0-9]+", text.lower())) + " "


def same_shoe(expert_name: str, pick: dict) -> bool:
    """Expert names may omit the brand ("Ghost 17") but must include model and version."""
    return _normalize(f"{pick['model']} {pick['version']}") in _normalize(expert_name)


def _matches(rec: dict, expert_picks: list[dict]) -> list[tuple[dict, dict]]:
    return [
        (pick, expert)
        for pick in rec["picks"]
        for expert in expert_picks
        if same_shoe(expert["shoe"], pick)
    ]


def hit_rate(rec: dict, expert_picks: list[dict]) -> dict:
    hits = sorted(
        {f"{p['brand']} {p['model']} {p['version']}" for p, _ in _matches(rec, expert_picks)}
    )
    return {
        "key": "hit_rate",
        "score": 1.0 if hits else 0.0,
        "comment": f"matched: {', '.join(hits)}" if hits else "no expert pick in top 3",
    }


def size_accuracy(rec: dict, expert_picks: list[dict]) -> dict:
    matched = _matches(rec, expert_picks)
    if not matched:
        return {"key": "size_accuracy", "score": None, "comment": "no matched shoe to compare"}
    within = [
        abs(pick["size"]["us_size"] - expert["us_size"]) <= SIZE_TOLERANCE
        for pick, expert in matched
    ]
    details = "; ".join(
        f"{p['model']} {p['version']}: {p['size']['us_size']:g} vs {e['us_size']:g}"
        for p, e in matched
    )
    return {"key": "size_accuracy", "score": sum(within) / len(within), "comment": details}


def link_validity(rec: dict, known_urls: set[str]) -> dict:
    urls = [o["url"] for p in rec["picks"] for o in p["offers"]]
    if not urls:
        return {"key": "link_validity", "score": 1.0, "comment": "no links"}
    bad = [u for u in urls if u not in known_urls]
    return {
        "key": "link_validity",
        "score": 1 - len(bad) / len(urls),
        "comment": f"unknown: {bad}" if bad else f"{len(urls)} links, all in offers",
    }


def parser_accuracy(expected: dict, actual: dict, tolerance: float = POSITION_TOLERANCE) -> dict:
    want, got = FootProfile.model_validate(expected), FootProfile.model_validate(actual)
    checks: list[tuple[str, bool]] = [("sex_scale", want.sex_scale == got.sex_scale)]
    for side in ("left", "right"):
        w, g = getattr(want, side), getattr(got, side)
        checks += [
            (f"{side}.us_size", w.us_size == g.us_size),
            (f"{side}.width", w.width == g.width),
        ]
        for scale in SCALES:
            ws, gs = getattr(w, scale), getattr(g, scale)
            if ws is None and gs is None:
                continue
            ok = (
                ws is not None
                and gs is not None
                and ws.band == gs.band
                and abs(ws.position - gs.position) <= tolerance
            )
            checks.append((f"{side}.{scale}", ok))
    wrong = [name for name, ok in checks if not ok]
    return {
        "key": "parser_accuracy",
        "score": 1 - len(wrong) / len(checks),
        "comment": f"wrong: {', '.join(wrong)}" if wrong else "all fields correct",
    }
