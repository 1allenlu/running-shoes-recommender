"""Stage 1 ranker: sub-scores, filters, sizing and the pipeline (no database needed)."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.ranking.config import default_config
from app.ranking.features import FootFeatures, ShoeSpec
from app.ranking.filters import apply_filters
from app.ranking.fit_scorer import (
    HistoryContext,
    budget_fit,
    combo_fit,
    effective_weights,
    heel_fit,
    history_fit,
    ride_fit,
    score_shoe,
    volume_fit,
    width_fit,
)
from app.ranking.pipeline import Catalog, main, rank
from app.ranking.sizing import ChartRow, size_to_order
from app.schemas.foot_profile import FootProfile
from app.schemas.preferences import HistoryEntry, Preferences

FIXTURE = Path("data/sample_scans/expected_profile.json")
PROFILES = sorted(Path("data/profiles").glob("0*.json"))
CFG = default_config()


def fixture_profile() -> FootProfile:
    return FootProfile.model_validate_json(FIXTURE.read_text())


def profile(width="D", instep=0.5, heel=0.5, size=9.0, sex="men", right_size=None) -> FootProfile:
    def band(pos, names):
        return {"band": names[min(int(pos * 3), 2)], "position": pos}

    def foot(us):
        return {
            "us_size": us,
            "width": width,
            "arch_height": band(0.5, ("low", "medium", "high")),
            "instep_height": band(instep, ("low", "medium", "high")),
            "heel_width": band(heel, ("narrow", "medium", "wide")),
        }

    return FootProfile.model_validate(
        {"sex_scale": sex, "left": foot(size), "right": foot(right_size or size)}
    )


def feet(**kw) -> FootFeatures:
    return FootFeatures.from_profile(profile(**kw))


def shoe(i=1, **kw) -> ShoeSpec:
    base = dict(
        id=i, brand="Acme", model=f"Model{i}", version="1", category="daily",
        drop_mm=8.0, stack_heel_mm=36.0, weight_g=260.0, price_usd=140.0,
        widths_available=("standard",), toe_box="medium", upper_volume="medium",
        heel_lock=True, toebox_width_mm=None, upper_stretch="medium",
        heel_counter="medium", midsole_softness="balanced", stability_features=False,
    )  # fmt: skip
    base.update(kw)
    return ShoeSpec(**base)


# --- Features -----------------------------------------------------------------------------


def test_fixture_is_wide_forefoot_low_instep_from_longer_foot():
    foot = FootFeatures.from_profile(fixture_profile())
    assert (foot.us_size, foot.width_letter, foot.shoe_width) == (8.3, "E", "wide")
    assert foot.wide_forefoot and foot.instep_band == "low"
    # Heel bands disagree (wide / medium): mean position 0.685 is in the wide band.
    assert foot.heel_band == "wide"


def test_womens_scale_d_is_wide():
    assert feet(width="D", sex="women").wide_forefoot
    assert not feet(width="D", sex="men").wide_forefoot


# --- width_fit ----------------------------------------------------------------------------


def test_width_fit_scores_distance_from_target_and_penalizes_narrow_harder():
    foot = feet(width="D")  # target 98 mm
    exact = width_fit(foot, shoe(toebox_width_mm=98.0), CFG)
    narrow = width_fit(foot, shoe(toebox_width_mm=95.0), CFG)
    wide = width_fit(foot, shoe(toebox_width_mm=101.0), CFG)
    assert exact.value == 1.0
    assert narrow.value < wide.value < 1.0
    assert "3 mm narrower" in narrow.note


def test_width_fit_scores_the_wide_version_for_a_wide_foot():
    foot = feet(width="2E")  # target 104 mm
    without = width_fit(foot, shoe(toebox_width_mm=99.0), CFG)
    with_wide = width_fit(
        foot, shoe(toebox_width_mm=99.0, widths_available=("standard", "wide")), CFG
    )
    assert with_wide.value > without.value
    assert "wide version" in with_wide.note


def test_width_fit_falls_back_to_toe_box_then_widths_then_unknown():
    wide_foot = feet(width="2E")
    assert width_fit(wide_foot, shoe(toe_box="roomy"), CFG).value == 1.0
    assert width_fit(wide_foot, shoe(toe_box="narrow"), CFG).value == 0.2
    offered = shoe(toe_box=None, widths_available=("standard", "wide"))
    assert width_fit(wide_foot, offered, CFG).value == CFG.width.wide_version_score
    unknown = width_fit(feet(), shoe(toe_box=None, widths_available=None), CFG)
    assert unknown.status == "unknown" and unknown.value is None


# --- volume_fit / heel_fit ----------------------------------------------------------------


def test_volume_fit_low_instep_prefers_lower_volume_and_heel_lock():
    foot = feet(instep=0.1)
    low = volume_fit(foot, shoe(upper_volume="low", heel_lock=False), CFG)
    high = volume_fit(foot, shoe(upper_volume="high", heel_lock=False), CFG)
    medium_lock = volume_fit(foot, shoe(upper_volume="medium", heel_lock=True), CFG)
    medium = volume_fit(foot, shoe(upper_volume="medium", heel_lock=False), CFG)
    assert low.value > high.value
    assert medium_lock.value > medium.value


def test_volume_fit_high_instep_penalizes_low_volume():
    foot = feet(instep=0.9)
    assert volume_fit(foot, shoe(upper_volume="low"), CFG).value < 0.5
    assert volume_fit(foot, shoe(upper_volume="high"), CFG).value == 1.0


def test_heel_fit_rewards_firm_counter_and_lock_for_narrow_heel_wide_forefoot():
    foot = feet(width="2E", heel=0.1)
    firm = heel_fit(foot, shoe(heel_counter="firm", heel_lock=True), CFG)
    soft = heel_fit(foot, shoe(heel_counter="soft", heel_lock=False), CFG)
    assert firm.value == 1.0 and soft.value < 0.5


def test_heel_fit_is_flat_without_a_special_need():
    foot = feet(width="D", heel=0.1)  # narrow heel but standard forefoot
    a = heel_fit(foot, shoe(heel_counter="firm"), CFG)
    b = heel_fit(foot, shoe(heel_counter="soft"), CFG)
    assert a.value == b.value == CFG.heel.no_special_need


# --- combo_fit (wide forefoot + low instep) -----------------------------------------------


def test_combo_fit_only_applies_to_wide_forefoot_low_instep():
    foot = feet(width="D", instep=0.1)
    assert combo_fit(foot, shoe(), width_fit(foot, shoe(), CFG), CFG).status == "n/a"


def test_combo_fit_rewards_roomy_low_volume_locked_and_penalizes_volume_everywhere():
    foot = FootFeatures.from_profile(fixture_profile())
    ideal = shoe(1, toe_box="roomy", upper_volume="low", heel_lock=True)
    bulky_wide = shoe(2, toe_box="medium", upper_volume="medium", heel_lock=True,
                      widths_available=("standard", "wide"))  # fmt: skip
    high_volume = shoe(3, toe_box="roomy", upper_volume="high", heel_lock=True)
    scores = {
        s.id: combo_fit(foot, s, width_fit(foot, s, CFG), CFG)
        for s in (ideal, bulky_wide, high_volume)
    }
    assert scores[1].value == 1.0
    assert scores[2].value < scores[1].value and "wide version" in scores[2].note
    assert scores[3].value == 0.0


def test_fixture_ranks_the_combo_shoe_above_a_plush_wide_version():
    """The key case: the fixture's wide-forefoot, low-instep foot."""
    ideal = shoe(1, model="Snug", toe_box="roomy", upper_volume="low", heel_lock=True,
                 heel_counter="firm")  # fmt: skip
    plush = shoe(2, model="Plush", toe_box="medium", upper_volume="high", heel_lock=False,
                 widths_available=("standard", "wide"), heel_counter="soft")  # fmt: skip
    plain = shoe(3, model="Plain", toe_box="narrow", upper_volume="medium")
    result = rank(fixture_profile(), Preferences(), [], Catalog([plush, plain, ideal], {}))
    assert result.top[0].name == "Acme Snug 1"
    assert result.top[0].subscores["combo_fit"].value == 1.0
    # The plush wide version adds volume everywhere: no combo credit, ranked last.
    assert result.top[-1].name == "Acme Plush 1"
    assert result.top[-1].subscores["combo_fit"].value == 0.0


# --- ride_fit / history_fit / budget_fit --------------------------------------------------


def test_ride_fit_matches_feel_and_stack_to_goals():
    soft = Preferences(feel="soft")
    assert ride_fit(soft, shoe(midsole_softness="soft"), CFG).value == 1.0
    assert ride_fit(soft, shoe(midsole_softness="firm"), CFG).value == 0.0
    marathon = Preferences(goals=["Marathon"])
    assert ride_fit(marathon, shoe(stack_heel_mm=38.0), CFG).value == 1.0
    assert ride_fit(marathon, shoe(stack_heel_mm=28.0), CFG).value < 1.0
    assert ride_fit(Preferences(), shoe(), CFG).status == "n/a"


def test_history_fit_prefers_shoes_like_loved_ones_over_hated_ones():
    loved = shoe(
        10, toe_box="roomy", upper_volume="low", midsole_softness="soft", toebox_width_mm=103.0
    )
    hated = shoe(
        11, toe_box="narrow", upper_volume="high", midsole_softness="firm", toebox_width_mm=93.0
    )
    ctx = HistoryContext.build(
        [HistoryEntry(shoe_id=10, raw_name="x", rating="loved"),
         HistoryEntry(shoe_id=11, raw_name="y", rating="hated")],
        {10: loved, 11: hated},
    )  # fmt: skip
    like_loved = history_fit(replace(loved, id=1), ctx, CFG)
    like_hated = history_fit(replace(hated, id=2), ctx, CFG)
    assert like_loved.value > 0.8 > 0.2 > like_hated.value
    assert history_fit(shoe(), HistoryContext(), CFG).status == "n/a"


def test_issue_tags_raise_the_matching_weight():
    ctx = HistoryContext.build(
        [HistoryEntry(raw_name="x", rating="fine", issues=["toe_pressure", "heel_slip"])], {}
    )
    weights = effective_weights(CFG, ctx)
    assert weights["width_fit"] == pytest.approx(CFG.weights["width_fit"] * 1.5)
    assert weights["heel_fit"] == pytest.approx(CFG.weights["heel_fit"] * 1.5)
    assert weights["volume_fit"] == CFG.weights["volume_fit"]


def test_budget_fit_rewards_being_under_budget():
    prefs = Preferences(budget_usd=150)
    assert budget_fit(prefs, shoe(price_usd=100.0), CFG).value == 1.0
    assert 0.5 <= budget_fit(prefs, shoe(price_usd=145.0), CFG).value < 1.0
    assert budget_fit(prefs, shoe(price_usd=160.0), CFG).value == 0.0
    assert budget_fit(prefs, shoe(price_usd=None), CFG).status == "unknown"
    assert budget_fit(Preferences(), shoe(), CFG).status == "n/a"


def test_score_is_weighted_sum_over_applicable_weights():
    foot = feet()
    scored = score_shoe(foot, Preferences(), HistoryContext(), shoe(), CFG)
    applied = {k: v for k, v in scored.subscores.items() if v.status != "n/a"}
    assert scored.contributions.keys() == applied.keys()
    total_weight = sum(CFG.weights[k] for k in applied)
    assert scored.score == pytest.approx(sum(scored.contributions.values()) / total_weight)
    assert 0 <= scored.score <= 1


def test_medial_pressure_never_favours_stability_shoes():
    flat = fixture_profile()
    medial = flat.model_copy(deep=True)
    medial.left.pressure.band = medial.right.pressure.band = "medial"
    stability = shoe(1, category="stability", stability_features=True)
    neutral = shoe(2, stability_features=False)
    a = rank(flat, Preferences(), [], Catalog([stability, neutral], {}))
    b = rank(medial, Preferences(), [], Catalog([stability, neutral], {}))
    assert [p.score for p in a.candidates] == [p.score for p in b.candidates]


# --- Filters ------------------------------------------------------------------------------


def _filter(shoes, prefs=None, history=(), **foot_kw):
    prefs = prefs or Preferences()
    return apply_filters(list(shoes), feet(**foot_kw), prefs, list(history), CFG)


def test_filters_exclude_every_version_of_a_hated_model():
    old, new, other = (
        shoe(1, model="Peg", version="40"),
        shoe(2, model="Peg", version="41"),
        shoe(3),
    )
    result = _filter(
        [old, new, other], history=[HistoryEntry(shoe_id=1, raw_name="Peg 40", rating="hated")]
    )
    assert [c.shoe.id for c in result.candidates] == [3]
    assert {e.reason for e in result.excluded} == {"you rated this model hated"}


def test_filters_exclude_specs_behind_a_recurring_issue():
    history = [
        HistoryEntry(raw_name="a", rating="fine", issues=["too_much_volume"]),
        HistoryEntry(raw_name="b", rating="hated", issues=["too_much_volume"]),
    ]
    bulky, snug, unknown = (
        shoe(1, upper_volume="high"),
        shoe(2, upper_volume="low"),
        shoe(3, upper_volume=None),
    )
    result = _filter([bulky, snug, unknown], history=history)
    assert sorted(c.shoe.id for c in result.candidates) == [2, 3]
    one_report = _filter([bulky], history=history[:1])
    assert [c.shoe.id for c in one_report.candidates] == [1]


def test_filters_budget_allows_ten_percent_over_with_a_flag():
    prefs = Preferences(budget_usd=100)
    result = _filter([shoe(1, price_usd=95.0), shoe(2, price_usd=108.0), shoe(3, price_usd=115.0),
                      shoe(4, price_usd=None)], prefs)  # fmt: skip
    flags = {c.shoe.id: c.flags for c in result.candidates}
    assert flags == {1: [], 2: ["over_budget"], 4: ["price_unknown"]}


def test_filters_wide_feet_need_a_wide_version_or_a_wide_toe_box():
    shoes = [
        shoe(1, widths_available=("standard", "wide")),
        shoe(2, widths_available=("standard",), toebox_width_mm=104.0),
        shoe(3, widths_available=("standard",), toebox_width_mm=99.0),
        shoe(4, widths_available=None),
    ]
    result = _filter(shoes, width="2E")
    flags = {c.shoe.id: c.flags for c in result.candidates}
    assert flags == {1: [], 2: [], 4: ["width_unknown"]}
    # E is wide on the men's scale but below the 2E threshold: no hard filter.
    assert len(_filter(shoes, width="E").candidates) == 4


def test_filters_match_categories_to_goals():
    shoes = [shoe(1, category="race"), shoe(2, category="max-cushion"), shoe(3, category="tempo")]
    result = _filter(shoes, Preferences(goals=["Speed work"]))
    assert sorted(c.shoe.id for c in result.candidates) == [1, 3]
    assert len(_filter(shoes).candidates) == 3  # no goals: no restriction


# --- Sizing -------------------------------------------------------------------------------


def _charts(offset=0.0):
    ref, acme = [], []
    for i in range(9):
        size = 7 + i * 0.5
        mid = 250 + (size - 7) * 8.4
        ref.append(ChartRow(size, mid - 2.1, mid + 2.1))
        acme.append(ChartRow(size, mid - 2.1, mid + 2.1, size_offset=offset))
    return {"Volumental": ref, "Acme": acme}


def test_sizing_uses_longer_foot_chart_offset_and_allowance():
    foot = feet(size=8.0, right_size=8.4)
    plain = size_to_order("Acme", foot, _charts(), CFG)
    assert plain.confident and plain.us_size == 9.0  # 8.4 foot -> chart 8.5, +0.5
    runs_small = size_to_order("Acme", foot, _charts(offset=0.5), CFG)
    assert runs_small.us_size == 9.5 and "runs small" in runs_small.basis


def test_sizing_rounds_to_nearest_available_size():
    charts = _charts()
    charts["Acme"] = [r for r in charts["Acme"] if r.us_size != 9.0]  # brand skips 9.0
    advice = size_to_order("Acme", feet(size=8.4), charts, CFG)
    assert advice.us_size == 9.5  # 9.0 wanted; 8.5 and 9.5 tie -> larger


def test_sizing_without_charts_is_not_confident():
    advice = size_to_order("Nobody", FootFeatures.from_profile(fixture_profile()), {}, CFG)
    assert (advice.us_size, advice.width, advice.confident) == (9.0, "wide", False)


# --- Pipeline + CLI -----------------------------------------------------------------------


def test_history_raw_names_resolve_to_catalog_shoes():
    catalog = Catalog([shoe(1, brand="Nike", model="Pegasus", version="41"), shoe(2)], {})
    history = [HistoryEntry(raw_name="pegasus 41", rating="hated")]
    result = rank(profile(), Preferences(), history, catalog)
    assert [e.name for e in result.excluded] == ["Nike Pegasus 41"]


def test_pipeline_is_deterministic_and_warns_on_unverified_specs():
    catalog = Catalog.from_seed()
    a = rank(fixture_profile(), Preferences(), [], catalog)
    b = rank(fixture_profile(), Preferences(), [], catalog)
    assert a == b and len(a.top) == 3
    assert any(w.startswith("Low confidence") for w in a.warnings)


@pytest.mark.parametrize("path", [FIXTURE, *PROFILES], ids=lambda p: p.stem)
def test_cli_prints_top_three_with_contributions_and_sizes(path, capsys):
    main(["--profile", str(path), "--prefs", "data/profiles/example_preferences.json",
          "--history", "data/profiles/example_history.json"])  # fmt: skip
    out = capsys.readouterr().out
    assert [line[:2] for line in out.splitlines() if line.startswith("#")] == ["#1", "#2", "#3"]
    assert "width_fit" in out and "size:" in out
    assert "excluded: Nike Pegasus 41" in out


def test_cli_json_output(capsys):
    main(["--profile", str(FIXTURE), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["ranker_version"] == CFG.version
    assert all(set(p["contributions"]) <= set(p["subscores"]) for p in data["top"])


def test_explain_reasons_and_caveat_come_from_sub_scores():
    from app.recommend import FALLBACK_LINES, explain

    bulky = shoe(1, toe_box="medium", upper_volume="medium", widths_available=("standard", "wide"))
    snug = shoe(2, toe_box="roomy", upper_volume="low", heel_lock=True)
    result = rank(fixture_profile(), Preferences(), [], Catalog([bulky, snug], {}))
    top, second = result.top
    notes = lambda p: {s.note[:1].upper() + s.note[1:] for s in p.subscores.values()}  # noqa: E731
    for pick in (top, second):
        why, watch = explain(pick, 1.0)
        assert why and set(why + watch) <= notes(pick) | set(FALLBACK_LINES)
    # The wide-version penalty is a caveat, never a reason.
    why, watch = explain(second, 1.0)
    assert not any("adds volume everywhere" in w for w in why)
    assert any("adds volume everywhere" in w for w in watch)
