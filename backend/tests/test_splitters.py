from datetime import date

from app.ingest.splitters import find_date, line_spans, split_dated_headers

TEXT = "\n20200105_Специалист А\n\tЖалобы: нет.\n\tРекомендовано: наблюдение.\n\n20200210_Неизвестная_строка\n\n20201301_Специалист А\n\tТекст.\n"


def test_split_dated_headers_offsets_and_dates():
    segs = split_dated_headers(TEXT)
    assert [s.header_label for s in segs] == ["Специалист А", "Неизвестная_строка", "Специалист А"]
    assert segs[0].header_date == date(2020, 1, 5)
    assert segs[1].header_date == date(2020, 2, 10)
    # 13-й месяц — ошибка даты попадает в замечания, сегмент не теряется
    assert segs[2].header_date is None and segs[2].issues
    for s in segs:
        body = TEXT[s.start : s.end]
        assert body.startswith(TEXT[s.start : s.start + 8]) and not body.endswith("\n")


def test_text_before_first_header_is_kept():
    segs = split_dated_headers("Вступление\n20200105_А\nтекст")
    assert segs[0].header_label is None and segs[0].issues
    assert len(segs) == 2


def test_no_headers_gives_one_segment_with_issue():
    segs = split_dated_headers("просто текст")
    assert len(segs) == 1 and segs[0].issues


def test_line_spans_strip_whitespace_and_keep_offsets():
    text = "Заголовок\n\tпервая строка  \n\n  вторая"
    spans = line_spans(text, "paragraph", first_kind="header")
    assert [text[s.start : s.end] for s in spans] == ["Заголовок", "первая строка", "вторая"]
    assert spans[0].kind == "header" and spans[1].kind == "paragraph"


def test_find_date_formats():
    assert find_date("Беседа 20250301") == date(2025, 3, 1)
    assert find_date("от 2025-03-02") == date(2025, 3, 2)
    assert find_date("осмотр 03.03.2025 г.") == date(2025, 3, 3)
    assert find_date("99999999 и 31.02.2025") is None
