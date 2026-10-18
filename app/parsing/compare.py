"""Compare a parsed FootProfile to a hand-checked one (Phase 3 check, Phase 9 parser accuracy)."""

from app.schemas.foot_profile import FootProfile

POSITION_TOLERANCE = 0.15
SCALES = ("arch_height", "instep_height", "heel_width", "pressure", "arch_flexibility")


def _fmt(scale) -> str:
    return "missing" if scale is None else f"{scale.band}@{scale.position:.2f}"


def profile_mismatches(
    expected: FootProfile, actual: FootProfile, tolerance: float = POSITION_TOLERANCE
) -> list[str]:
    """Sizes and widths must match exactly, bands must match, positions within tolerance."""
    problems = []
    if expected.sex_scale != actual.sex_scale:
        problems.append(f"sex_scale: expected {expected.sex_scale}, got {actual.sex_scale}")
    for side in ("left", "right"):
        want, got = getattr(expected, side), getattr(actual, side)
        for field in ("us_size", "width"):
            if getattr(want, field) != getattr(got, field):
                problems.append(
                    f"{side}.{field}: expected {getattr(want, field)}, got {getattr(got, field)}"
                )
        for scale in SCALES:
            w, g = getattr(want, scale), getattr(got, scale)
            if w is None and g is None:
                continue
            if w is None or g is None:
                problems.append(f"{side}.{scale}: expected {_fmt(w)}, got {_fmt(g)}")
                continue
            if w.band != g.band:
                problems.append(f"{side}.{scale}.band: expected {w.band}, got {g.band}")
            if abs(w.position - g.position) > tolerance:
                problems.append(
                    f"{side}.{scale}.position: expected {w.position:.2f}, got {g.position:.2f}"
                )
    return problems
