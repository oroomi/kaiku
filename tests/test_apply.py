import pytest
from kaiku.apply.yext import (holiday_row, merge_holiday_rows, hours_payload, apply_suggestion,
                              YextSandbox, has_key, REGULAR_HOURS)
from kaiku.apply.publishers import publishers_for


def test_row_hours_and_closed():
    assert holiday_row("2026-12-24", [{"start": "09:00", "end": "13:00"}]) == \
        {"date": "2026-12-24", "openIntervals": [{"start": "09:00", "end": "13:00"}]}
    assert holiday_row("2026-12-24", "closed") == {"date": "2026-12-24", "isClosed": True}


@pytest.mark.parametrize("d,p", [("24.12.2026", "closed"), ("2026-13-01", "closed"),
                                 ("2026-12-24", [{"start": "13:00", "end": "09:00"}]),
                                 ("2026-12-24", [{"start": "9:00", "end": "13:00"}])])
def test_row_rejects_bad(d, p):
    with pytest.raises(ValueError):
        holiday_row(d, p)


def test_merge_replaces_same_date_and_sorts():
    ex = [{"date": "2026-12-25", "isClosed": True}, {"date": "2026-12-24", "isClosed": True}]
    out = merge_holiday_rows(ex, [holiday_row("2026-12-24", [{"start": "09:00", "end": "13:00"}])])
    assert [r["date"] for r in out] == ["2026-12-24", "2026-12-25"] and "openIntervals" in out[0]
    assert len(merge_holiday_rows(ex, [], merge=False)) == 0


def test_payload_nests_holiday_inside_hours():
    h = dict(REGULAR_HOURS, holidayHours=[holiday_row("2026-12-24", "closed")])
    assert list(hours_payload(h)) == ["hours"] and "holidayHours" not in hours_payload(REGULAR_HOURS)["hours"]


def test_apply_error_is_dict_not_raise():
    r = apply_suggestion("X", "bad-date", "closed", client=object())
    assert r["yext_status"].startswith("error:") and r["verified"] is False


def test_publishers_honest():
    ps = publishers_for({})
    assert ps and all(p["status"].startswith("sandbox: written to the entity; in production Connect syncs") for p in ps)


@pytest.mark.live
@pytest.mark.skipif(not has_key(), reason="no YEXT_API_KEY")
def test_live_write_verify_remove():
    r = apply_suggestion("SinceAI07", "2027-06-01", [{"start": "10:00", "end": "12:00"}])
    try:
        assert r["yext_status"] == "ok" and r["verified"]
    finally:
        c = YextSandbox()
        c.remove_holiday_hours("SinceAI07", "2027-06-01")
    assert all(x["date"] != "2027-06-01" for x in c.get_hours("SinceAI07").get("holidayHours", []))
