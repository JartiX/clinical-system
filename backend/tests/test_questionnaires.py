from datetime import datetime

from app.ingest.questionnaires import parse_table

from .conftest import make_form_xlsx, scale_labels


def _two_instrument_codes(content):
    """Два опросника с одной шкалой и ключом — как в общей форме."""
    scored = [c for c, i in content.instruments.items() if i.answer_scale and i.scoring
              and all(s is not None for _, s in content.answer_scales[i.answer_scale].values())]
    assert len(scored) >= 2
    return scored[:2]


def test_scores_two_instruments_in_one_form(content):
    a, b = _two_instrument_codes(content)
    labels = scale_labels(content, a)
    answers = {(a, n): labels[-1] for n in content.instruments[a].items}
    answers |= {(b, n): labels[1] for n in content.instruments[b].items}
    data = make_form_xlsx(content, [{"ts": 46194.5, "name": "П1", "answers": answers}], [a, b])

    parsed = parse_table("форма.xlsx", data, content, aliases=["П1"])
    assert parsed.instruments == sorted([a, b])
    resp = parsed.responses[0]
    assert resp.timestamp == datetime(2026, 6, 21, 12, 0)
    top = max(s for _, s in content.answer_scales[content.instruments[a].answer_scale].values())
    assert resp.instruments[a].total == top * content.instruments[a].item_count
    assert resp.instruments[b].total == content.instruments[b].item_count * 1
    assert not resp.instruments[a].issues


def test_bad_answer_and_missing_item_block_total(content):
    a, _ = _two_instrument_codes(content)
    labels = scale_labels(content, a)
    answers = {(a, n): labels[0] for n in content.instruments[a].items}
    answers[(a, 1)] = "Ответ не из шкалы"
    answers[(a, 2)] = None
    data = make_form_xlsx(content, [{"ts": datetime(2026, 1, 1, 9, 30), "name": "П1", "answers": answers}], [a])

    res = parse_table("форма.xlsx", data, content, aliases=[]).responses[0].instruments[a]
    assert res.total is None
    assert any("не из шкалы" in i for i in res.issues)
    assert any("нет ответа" in i for i in res.issues)


def test_rows_of_other_people_are_skipped(content):
    a, _ = _two_instrument_codes(content)
    labels = scale_labels(content, a)
    answers = {(a, n): labels[0] for n in content.instruments[a].items}
    rows = [{"ts": 46000.0, "name": "П1", "answers": answers}, {"ts": 46001.0, "name": "Другой", "answers": answers}]
    parsed = parse_table("форма.xlsx", make_form_xlsx(content, rows, [a]), content, aliases=["п1"])
    assert len(parsed.responses) == 1 and len(parsed.skipped_rows) == 1


def test_unknown_columns_are_reported(content):
    a, _ = _two_instrument_codes(content)
    labels = scale_labels(content, a)
    answers = {(a, n): labels[0] for n in content.instruments[a].items}
    data = make_form_xlsx(content, [{"ts": 46000.0, "name": "П1", "answers": answers, "extra": {"Новый вопрос": "да"}}],
                          [a], extra_headers=["Новый вопрос"])
    parsed = parse_table("форма.xlsx", data, content, aliases=[])
    assert parsed.unmapped_columns == ["Новый вопрос"]


def test_instrument_without_key_keeps_answers(content):
    no_key = [c for c, i in content.instruments.items()
              if i.answer_scale and any(s is None for _, s in content.answer_scales[i.answer_scale].values())]
    if not no_key:
        return
    code = no_key[0]
    labels = [lab for lab, _ in content.answer_scales[content.instruments[code].answer_scale].values()]
    answers = {(code, n): labels[0] for n in content.instruments[code].items}
    res = parse_table("ф.xlsx", make_form_xlsx(content, [{"ts": 46000.0, "name": "П1", "answers": answers}], [code]),
                      content, aliases=[]).responses[0].instruments[code]
    assert res.total is None and res.complete
    assert any("ключ" in i for i in res.issues)
