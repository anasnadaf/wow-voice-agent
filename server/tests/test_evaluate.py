"""The scorer is pure logic, so it is testable without any model."""

from types import SimpleNamespace

from scripts.evaluate import EXPECTED, score
from scripts.simulate import PERSONAS


def judgement(**overrides) -> SimpleNamespace:
    base = dict(
        asked_permission=True,
        checkpoints_covered=4,
        repeated_a_question=False,
        pitch_quality="strong",
        made_cta="yes",
        tone="premium",
        brevity="good",
        handled_edge_case="not_applicable",
        notes="",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_perfect_call_scores_one():
    total, parts = score(judgement(), EXPECTED["eager_investor"], "qualified", "qualified")
    assert total == 1.0
    assert all(v == 1.0 for v in parts.values())


def test_missing_permission_and_repeats_are_penalised():
    total, parts = score(
        judgement(asked_permission=False, repeated_a_question=True),
        EXPECTED["eager_investor"],
        "qualified",
        "qualified",
    )
    assert parts["asked_permission"] == 0.0
    assert parts["no_repeats"] == 0.0
    assert total < 1.0


def test_early_exit_is_not_penalised_for_skipped_stages():
    """A caller who refuses permission should not cost the agent pitch and CTA."""
    total, parts = score(
        judgement(
            checkpoints_covered=0,
            pitch_quality="not_applicable",
            made_cta="not_applicable",
            handled_edge_case="well",
        ),
        EXPECTED["irritated"],
        "declined",
        "not_qualified",
    )
    assert parts["pitch"] == 1.0 and parts["cta"] == 1.0
    assert parts["checkpoints"] == 0.0  # still reflects that nothing was learned
    assert total > 0.8


def test_wrong_outcome_is_marked_incorrect():
    _, parts = score(judgement(), EXPECTED["busy_callback"], "qualified", "qualified")
    assert parts["outcome_correct"] == 0.0
    assert parts["disposition_correct"] == 0.0


def test_pushy_tone_scores_zero_on_that_component():
    _, parts = score(judgement(tone="pushy"), EXPECTED["eager_investor"], "qualified", "qualified")
    assert parts["tone"] == 0.0


def test_every_persona_has_expectations():
    assert set(EXPECTED) == set(PERSONAS), "each simulated persona needs a graded expectation"
