from app.parser.content_classifier import classify
from app.parser.ue3_ini import parse_text


def _c(text: str):
    return classify(parse_text(text))


def test_clean_chaosengine_content_classified_even_if_renamed():
    text = """
[Engine.Engine]
bSmoothFrameRate=TRUE
MaxSmoothedFrameRate=62

[TextureStreaming]
PoolSize=600
"""
    res = _c(text)
    assert res.classified_type == "ChaosEngine"
    assert res.score > 0


def test_willow_engine_is_unsupported():
    text = """
[WillowEngine.WillowEngineSettings]
BulletPhysicsTick=30

[Engine.WillowEngine]
SomethingElse=1
"""
    res = _c(text)
    assert res.classified_type == "Unsupported"


def test_empty_is_unsupported():
    assert _c("").classified_type == "Unsupported"


def test_mixed_dump_is_mixed():
    text = """
[Engine.Engine]
bSmoothFrameRate=TRUE

[SystemSettings]
MaxAnisotropy=16
"""
    res = _c(text)
    assert res.classified_type == "Mixed"
    # mixed_types should include both primary candidates
    assert set(res.mixed_types) == {"ChaosEngine", "ChaosSystemSettings"}


def test_fragment_with_single_signature_hit():
    # No required_section present, but one signature key in a section we
    # happen to name arbitrarily. The classifier only counts a signature
    # hit when the key is in its declared section. So we must put it in
    # the right section for it to count — this represents the real-world
    # case of a paste missing its header.
    text = "[Engine.PlayerInput]\nbEnableMouseSmoothing=TRUE\n"
    # Engine.PlayerInput IS a required_section for ChaosInput, so this will
    # classify as ChaosInput instead of Fragment. Construct a true fragment
    # with only a signature key and no required section:
    text_fragment = "[TextureStreaming]\nPoolSize=600\n"
    res = _c(text_fragment)
    assert res.classified_type == "Fragment"


def test_foreign_sections_in_classified_file_are_listed():
    text = """
[Engine.Engine]
bSmoothFrameRate=FALSE

[Random.Garbage]
ThisKeyIsInvented=1
"""
    res = _c(text)
    assert res.classified_type == "ChaosEngine"
    assert "Random.Garbage" in res.foreign_sections
