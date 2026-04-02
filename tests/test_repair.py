import pytest
from party.orchestration.repair import repair_response


def test_repair_strips_leading_trailing_whitespace():
    result = repair_response("   Hello there.   ")
    assert result.text == "Hello there."


def test_repair_removes_stage_directions():
    result = repair_response("*leans forward* That is interesting.")
    assert "*" not in result.text
    assert "leans forward" not in result.text
    assert "That is interesting." in result.text


def test_repair_removes_em_dashes():
    result = repair_response("This is good — very good indeed.")
    assert "—" not in result.text


def test_repair_removes_en_dashes():
    result = repair_response("This is good – very good indeed.")
    assert "–" not in result.text


def test_repair_multiple_stage_directions():
    result = repair_response("*clears throat* Good point. *nods slowly* Indeed.")
    assert "*" not in result.text


def test_repair_marks_repaired_true_when_changed():
    result = repair_response("*sighs* This is a problem.")
    assert result.repaired is True


def test_repair_marks_repaired_false_when_unchanged():
    result = repair_response("This is a clean response with no issues.")
    assert result.repaired is False


def test_repair_raises_on_empty_result():
    """If repair produces empty text, it should raise ProviderError."""
    from party.providers.base import ProviderError
    with pytest.raises(ProviderError):
        repair_response("*does something* *does another thing*")


def test_repair_preserves_content():
    original = "That is an interesting position, however I would need to consider it further."
    result = repair_response(original)
    assert result.text == original
    assert result.repaired is False


def test_repair_detects_length_violation_for_geptima():
    # 5 sentences exceeds Geptima's limit of 3
    long_response = (
        "Right, so that is a lot to process. "
        "We have seen this before in many forms. "
        "The pattern is always the same. "
        "What matters is what we do next. "
        "I think we can find a way through this together."
    )
    result = repair_response(long_response, character_name="geptima")
    assert result.length_violation is True
    assert result.sentence_count == 5


def test_repair_no_violation_within_limit():
    two_sentence = "Right, so accidents happen. The important thing is what we do next."
    result = repair_response(two_sentence, character_name="geptima")
    assert result.length_violation is False


def test_repair_grokthar_short_allowed():
    one_sentence = "Told Moonie this would happen."
    result = repair_response(one_sentence, character_name="grokthar")
    assert result.length_violation is False
    assert result.sentence_count == 1


def test_repair_result_includes_sentence_count():
    text = "First sentence. Second sentence. Third sentence."
    result = repair_response(text, character_name="clauven")
    assert result.sentence_count == 3
