from app.parser.ue3_ini import compose_array, parse_bytes, parse_text


def test_basic_sections_and_keys():
    text = """
[Engine.Engine]
bSmoothFrameRate=TRUE
MaxSmoothedFrameRate=62

[TextureStreaming]
PoolSize=600
"""
    doc = parse_text(text, filename_hint="ChaosEngine.ini")
    assert "Engine.Engine" in doc.sections
    assert "TextureStreaming" in doc.sections
    engine_entries = doc.sections["Engine.Engine"]
    assert [e.key for e in engine_entries] == ["bSmoothFrameRate", "MaxSmoothedFrameRate"]
    assert engine_entries[0].typed_value is True
    assert engine_entries[1].typed_value == 62
    assert doc.sections["TextureStreaming"][0].typed_value == 600


def test_duplicate_keys_are_preserved():
    text = "[S]\nKey=1\nKey=2\nKey=3\n"
    doc = parse_text(text)
    entries = doc.sections["S"]
    assert len(entries) == 3
    assert [e.raw_value for e in entries] == ["1", "2", "3"]
    assert [e.line_no for e in entries] == [2, 3, 4]


def test_array_ops_classified():
    text = """
[Engine.PlayerInput]
+Bindings=(Name="A",Command="")
-Bindings=(Name="B",Command="")
.Bindings=(Name="C",Command="")
!Bindings
"""
    doc = parse_text(text)
    ops = [e.op for e in doc.sections["Engine.PlayerInput"]]
    assert ops == ["+", "-", ".", "!"]


def test_comments_and_blanks():
    text = "; top\n// also\n[S]\n  ; indented\nKey=1\n\n"
    doc = parse_text(text)
    assert doc.sections["S"][0].key == "Key"


def test_compose_array_semantics():
    from app.parser.ue3_ini import Entry

    def e(op, value):
        return Entry(line_no=1, op=op, key="K", raw_value=value, typed_value=value)

    # append unique, then duplicate-allowed append, then remove, then clear+append
    result = compose_array(
        [e("+", "x"), e("+", "x"), e(".", "x"), e("-", "x"), e("!", ""), e("+", "y")],
        "K",
    )
    assert result == ["y"]


def test_bom_and_utf16():
    text = "\ufeff[S]\nK=1\n"
    doc = parse_text(text)
    assert "S" in doc.sections

    data_utf16 = ("[S]\nK=2\n").encode("utf-16-le")
    data_utf16 = b"\xff\xfe" + data_utf16
    doc2 = parse_bytes(data_utf16)
    assert doc2.sections["S"][0].typed_value == 2


def test_entry_before_section_is_warning():
    text = "Key=1\n[S]\nK=2\n"
    doc = parse_text(text)
    assert doc.warnings
    assert doc.warnings[0].reason == "entry_before_section"


def test_struct_value_with_equals_sign():
    text = "[S]\nBinding=(Name=\"W\",Command=\"MoveForward\")\n"
    doc = parse_text(text)
    entry = doc.sections["S"][0]
    assert entry.raw_value == '(Name="W",Command="MoveForward")'
