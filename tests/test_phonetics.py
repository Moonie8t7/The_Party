import pytest
from party.context.phonetics import is_direct_address, PhoneticMatchResult

@pytest.mark.parametrize("text,expected_target,expected_type,is_group", [
    # 1. Exact/Alias Character matches
    ("Clauven, what do you think?", "clauven", "exact", False),
    ("Hey clovin, how's it going?", "clauven", "alias", False),
    ("@grokthar, you ready?", "grokthar", "exact", False),
    ("deep villa: check this out", "deepwilla", "alias", False),
    
    # 2. Group matches (Strict)
    ("Party, listen up!", "group", "alias", True), # "party" is an alias of the "group" target
    ("Hey party, thoughts?", "group", "alias", True),
    ("The potty: weigh in", "group", "alias", True),

    # 3. Group matches (Broad - Start of line / Wake word only)
    ("everyone, thoughts?", "group", "alias", True),
    ("Hey guys!", "group", "alias", True),
    
    # 4. Fuzzy matches
    ("Grokthrr what was that?", "grokthar", "fuzzy", False),
    ("Hey Clauve", "clauven", "fuzzy", False),
    ("Yo deep willoo", "deepwilla", "fuzzy", False),
    ("Partyy what do you think", "group", "fuzzy", True),
    
    # 5. False Positives (Should NOT match)
    ("I think everyone knows that", None, None, False),
    ("The guys were saying...", None, None, False),
    ("Just a party in the game", None, None, False),
    ("The clauven approach is slow", None, None, False),
])
def test_direct_address_detection(text, expected_target, expected_type, is_group):
    result = is_direct_address(text)
    if expected_target is None:
        assert result["matched"] is False, f"Should not have matched: {text}"
    else:
        assert result["matched"] is True, f"Should have matched: {text}"
        assert result["target"] == expected_target
        if expected_type:
            assert result["match_type"] == expected_type
        assert result["is_group"] == is_group
        assert result["score"] >= 0.8
        assert result["matched_text"] is not None

def test_wake_word_stripping():
    from party.context.phonetics import strip_leading_wake_words
    assert strip_leading_wake_words("hey clauven") == "clauven"
    assert strip_leading_wake_words("yo clauven") == "clauven"
    assert strip_leading_wake_words("ok clauven") == "ok clauven" # Not in WAKE_WORDS
    assert strip_leading_wake_words("ask the party") == "the party"
