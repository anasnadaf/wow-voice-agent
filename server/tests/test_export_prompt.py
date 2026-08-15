from scripts.export_prompt import _space_lists


def test_list_after_prose_gets_its_own_block():
    src = "Keep these in mind:\n- Divyasree\n- Nandi"
    assert _space_lists(src) == "Keep these in mind:\n\n- Divyasree\n- Nandi"


def test_prose_after_list_is_not_absorbed():
    src = "1. intent\n2. budget\nRules:"
    assert _space_lists(src) == "1. intent\n2. budget\n\nRules:"


def test_wrapped_item_stays_with_its_bullet():
    src = "- a long item\n  wrapped here\n- next item"
    assert _space_lists(src) == src


def test_already_spaced_text_is_unchanged():
    src = "Intro:\n\n- one\n- two\n\nOutro."
    assert _space_lists(src) == src


def test_full_prompt_renders_every_section():
    """The PDF deliverable must not silently lose a section."""
    from app.prompts import full_system_prompt

    document = _space_lists(full_system_prompt())
    for heading in (
        "## Persona",
        "## Pronunciation dictionary",
        "## Bilingual behaviour",
        "## Stage policies",
        "## Edge-case playbook",
        "## Project knowledge base",
    ):
        assert heading in document, f"missing {heading}"
    for term in ("Div-yaa-shree", "Nun-dhee", "laakh", "kror"):
        assert term in document
