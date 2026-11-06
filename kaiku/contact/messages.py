"""Finnish customer messages for the Kaiku contact step (WhatsApp, and the same words for the call).

All builders take a Suggestion dict (see CLAUDE.md data contracts) and are tolerant of missing optional fields.
Rules: correct Finnish, no em dashes, dates "24.12.", times "9-13".
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

WEEKDAY_ESSIVE = ["maanantaina", "tiistaina", "keskiviikkona", "torstaina", "perjantaina", "lauantaina", "sunnuntaina"]
WEEKDAY_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Genitive of common holiday names (used in "Jouluaaton aukioloajat").
_GENITIVE = {
    "jouluaatto": "Jouluaaton", "joulupäivä": "Joulupäivän", "tapaninpäivä": "Tapaninpäivän",
    "uudenvuodenpäivä": "Uudenvuodenpäivän", "uudenvuodenaatto": "Uudenvuodenaaton", "loppiainen": "Loppiaisen",
    "vappu": "Vapun", "vapunpäivä": "Vapun", "juhannusaatto": "Juhannusaaton", "juhannuspäivä": "Juhannuspäivän",
    "itsenäisyyspäivä": "Itsenäisyyspäivän", "pitkäperjantai": "Pitkäperjantain", "pääsiäispäivä": "Pääsiäispäivän",
    "toinen pääsiäispäivä": "Toisen pääsiäispäivän", "2. pääsiäispäivä": "2. pääsiäispäivän",
    "helatorstai": "Helatorstain", "pyhäinpäivä": "Pyhäinpäivän", "pääsiäislauantai": "Pääsiäislauantain",
}

PUBLISHERS_DEFAULT = ["Google", "Apple Maps", "Bing"]


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def fi_date(d) -> str:
    """'2026-12-24' or date -> '24.12.'"""
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    return f"{d.day}.{d.month}."


def _weekday(d) -> int:
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    return d.weekday()


def fi_time(t: str) -> str:
    """'09:00' -> '9', '09:30' -> '9.30'"""
    h, _, m = t.partition(":")
    h = str(int(h))
    return h if not m or int(m) == 0 else f"{h}.{m}"


def fi_hours(hours) -> str:
    """[{'start':'09:00','end':'13:00'}] -> '9-13'; 'closed'/[]/None -> 'suljettu'."""
    if not hours or hours == "closed":
        return "suljettu"
    return ", ".join(f"{fi_time(h['start'])}-{fi_time(h['end'])}" for h in hours)


def en_hours(hours) -> str:
    return "closed" if (not hours or hours == "closed") else fi_hours(hours).replace("-", " to ")


def holiday_name(s: dict) -> str:
    return (s.get("holiday_name_fi") or s.get("name_fi") or "Pyhäpäivä").strip()


def holiday_name_genitive(s: dict) -> str:
    n = holiday_name(s)
    key = n.lower()
    if key in _GENITIVE:
        return _GENITIVE[key]
    if key.endswith("nen"):
        return _cap(key[:-3] + "sen")
    return _cap(key) + "n"


def essive(name: str) -> str:
    """'Jouluaatto' -> 'jouluaattona', 'Loppiainen' -> 'loppiaisena', 'Isänpäivä' -> 'isänpäivänä'."""
    n = name.strip().lower()
    last = next((c for c in reversed(n) if c in "aouäöy"), "a")
    back = last in "aou"
    if n.endswith("nen"):
        return n[:-3] + ("sena" if back else "senä")
    return n + ("na" if back else "nä")


def business_name(s: dict) -> str:
    return s.get("business_name") or (s.get("business") or {}).get("name") or "yrityksenne"


def _signal(s: dict, key: str):
    return (s.get("signals") or {}).get(key)


def _last_year(s: dict):
    v = s.get("last_year_hours")
    if v is None:
        v = _signal(s, "last_year")
    return v


def _google_now(s: dict):
    v = s.get("google_now")
    if v is None:
        v = _signal(s, "google_now")
    return v


def _hours_of(v):
    """Signal values may be a bare hours list, 'closed', or a dict with 'hours'."""
    if isinstance(v, dict):
        return v.get("hours", v.get("value"))
    return v


def _when_fi(s: dict) -> str:
    d = s["holiday_date"]
    return f"{WEEKDAY_ESSIVE[_weekday(d)]} {fi_date(d)}"


def _when_en(s: dict) -> str:
    d = s["holiday_date"]
    return f"{WEEKDAY_EN[_weekday(d)]} {fi_date(d)}"


def _why_wrong_fi(s: dict, proposed_txt: str) -> str:
    g = _hours_of(_google_now(s))
    if g is None:
        return "Hakukoneissa ei ole vielä tälle päivälle erillisiä aukioloaikoja, joten asiakkaat näkevät tavalliset aukioloajat."
    g_txt = fi_hours(g)
    if g_txt == proposed_txt:
        return f"Googlessa näkyy jo {g_txt}, joten ehdotus vain varmistaa sen."
    return (f"Googlessa näkyy nyt {g_txt}, mikä ei vastaa ehdotustamme, "
            f"joten asiakas voi saapua suljetun oven eteen.")


def suggestion_text(s: dict) -> str:
    kind = s.get("kind")
    if kind == "ask":
        return ask_text(s)
    if kind == "no_change":
        return no_change_text(s)
    name = business_name(s)
    hol = holiday_name(s)
    proposed = "closed" if kind == "closed" else s.get("proposed")
    p_txt = fi_hours(proposed)
    ly = _hours_of(_last_year(s))
    parts = [f"Hei, {name}!", ""]
    parts.append(f"{_cap(hol)} on {_when_fi(s)}")
    if ly is not None:
        parts.append(f"Viime vuonna aukioloaikanne tuona päivänä oli {fi_hours(ly)}.")
    parts.append(_why_wrong_fi(s, p_txt))
    parts.append("")
    if proposed == "closed":
        parts.append(f"Ehdotamme, että {essive(hol)} ({fi_date(s['holiday_date'])}) olette suljettu.")
    else:
        parts.append(f"Ehdotamme, että {essive(hol)} ({fi_date(s['holiday_date'])}) aukioloaika on {p_txt}.")
    parts.append("Voit hyväksyä yhdellä napautuksella, muokata aikaa tai jättää ehdotuksen väliin. Päätös on aina sinun.")
    return "\n".join(parts)


def suggestion_text_en(s: dict) -> str:
    kind = s.get("kind")
    if kind == "ask":
        return ask_text_en(s)
    if kind == "no_change":
        return no_change_text_en(s)
    hol = s.get("holiday_name_en") or "the holiday"
    proposed = "closed" if kind == "closed" else s.get("proposed")
    ly = _hours_of(_last_year(s))
    g = _hours_of(_google_now(s))
    lines = [f"Hi, {business_name(s)}!", "", f"{_cap(hol)} falls on {_when_en(s)}"]
    if ly is not None:
        lines.append(f"Last year your hours that day were {en_hours(ly)}.")
    if g is not None:
        lines.append(f"Google currently shows {en_hours(g)}, which does not match our suggestion, so customers may arrive at a closed door.")
    else:
        lines.append("Search engines have no special hours for that day yet, so customers see your regular hours.")
    lines.append("")
    lines.append(f"We suggest {'being closed' if proposed == 'closed' else 'hours of ' + en_hours(proposed)} on {hol.lower()} ({fi_date(s['holiday_date'])}).")
    lines.append("Approve with one tap, edit the hours, or skip it. The decision is always yours.")
    return "\n".join(lines)


def ask_text(s: dict) -> str:
    return (f"Hei, {business_name(s)}!\n\n"
            f"{_cap(holiday_name(s))} on {_when_fi(s)} Emme ole varmoja, mitkä aukioloaikanne silloin ovat, "
            f"emmekä halua arvata väärin.\n\n"
            f"Kerro vastaamalla tähän viestiin, esimerkiksi \"9-13\" tai \"suljettu\". "
            f"Tallennamme ajan vasta kun olet vahvistanut sen.")


def ask_text_en(s: dict) -> str:
    return (f"Hi, {business_name(s)}!\n\n"
            f"{_cap(s.get('holiday_name_en') or 'The holiday')} falls on {_when_en(s)} We are not sure what your hours are then, "
            f"and we do not want to guess wrong.\n\n"
            f"Reply to this message, for example \"9-13\" or \"closed\". We only save the time after you confirm it.")


def no_change_text(s: dict) -> str:
    return (f"Hei, {business_name(s)}!\n\n"
            f"{_cap(holiday_name(s))} on {_when_fi(s)}, mutta tavalliset aukioloaikanne pätevät silloinkin. "
            f"Mitään ei tarvitse tehdä, eikä aukioloaikoihinne ole tulossa muutoksia.")


def no_change_text_en(s: dict) -> str:
    return (f"Hi, {business_name(s)}!\n\n"
            f"{_cap(s.get('holiday_name_en') or 'The holiday')} falls on {_when_en(s)}, but your regular hours apply then too. "
            f"Nothing to do, and no changes are coming to your hours.")


def _hours_from_result(r: dict):
    return r.get("hours_text") or r.get("hours")


def receipt_text(r: dict) -> str:
    """r: ApplyResult dict, optionally enriched with holiday_name_fi, hours (list|'closed') or hours_text."""
    h = _hours_from_result(r)
    h_txt = h if isinstance(h, str) and h != "closed" else fi_hours(h)
    pubs = r.get("publishers") or PUBLISHERS_DEFAULT
    pub_txt = _join_fi(pubs)
    gen = holiday_name_genitive(r)
    if h_txt == "suljettu":
        what = f"{gen} sulkeutuminen on nyt tallennettu."
    else:
        what = f"{gen} aukioloajat {h_txt} on nyt tallennettu."
    return f"Kiitos! {what} Ne näkyvät {pub_txt}."


def receipt_text_en(r: dict) -> str:
    h = _hours_from_result(r)
    h_txt = h.replace("-", " to ") if isinstance(h, str) and h != "closed" else en_hours(h)
    pubs = r.get("publishers") or PUBLISHERS_DEFAULT
    hol = r.get("holiday_name_en") or "holiday"
    return f"Thank you! The {hol.lower()} hours ({h_txt}) are now saved. They show on {_join_en(pubs)}."


def _join_fi(items) -> str:
    # Finnish: "Googlessa, Apple Mapsissa ja Fonectan palveluissa" needs inflection, so use fixed forms for known ones.
    forms = {"google": "Googlessa", "apple maps": "Apple Mapsissa", "apple": "Apple Mapsissa", "bing": "Bingissä",
             "yext": "Fonectan palveluissa", "fonecta": "Fonectan palveluissa"}
    out = []
    for p in items:
        f = forms.get(str(p).lower(), f"{p}-palvelussa")
        if f not in out:
            out.append(f)
    if "Fonectan palveluissa" not in out:
        out.append("Fonectan palveluissa")
    return out[0] if len(out) == 1 else ", ".join(out[:-1]) + " ja " + out[-1]


def _join_en(items) -> str:
    items = list(items) + (["Fonecta services"] if not any("fonecta" in str(i).lower() for i in items) else [])
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def edit_prompt_text() -> str:
    return "Selvä. Kirjoita uusi aukioloaika vastaamalla tähän viestiin, esimerkiksi \"9-13\" tai \"suljettu\"."


def edit_prompt_text_en() -> str:
    return "Sure. Reply with the new hours, for example \"9-13\" or \"closed\"."


def decline_thanks_text() -> str:
    return "Selvä, aukioloaikoihin ei tehdä muutoksia. Kiitos vastauksesta! Voit muuttaa päätöstä milloin tahansa."


def decline_thanks_text_en() -> str:
    return "Understood, no changes will be made to your hours. Thanks for replying! You can change your mind any time."


def unknown_reply_text() -> str:
    return "En ymmärtänyt vastausta. Voit painaa jotakin painikkeista tai kirjoittaa esimerkiksi \"9-13\" tai \"suljettu\"."


def unknown_reply_text_en() -> str:
    return "I did not understand that. Tap one of the buttons or write for example \"9-13\" or \"closed\"."


# ---------------------------------------------------------------- export

_SAMPLE_BASE = {
    "id": "sample", "business_name": "Furry Paw Vet Clinic", "holiday_date": "2026-12-24",
    "holiday_name_fi": "Jouluaatto", "holiday_name_en": "Christmas Eve",
    "last_year_hours": [{"start": "09:00", "end": "13:00"}],
    "google_now": [{"start": "09:00", "end": "17:00"}],
}


def all_final_messages(path: str | Path | None = None) -> str:
    """Write docs/final_messages.md: every customer-facing message as text, with English glosses. Returns the markdown."""
    hours = {**_SAMPLE_BASE, "kind": "hours", "proposed": [{"start": "09:00", "end": "13:00"}]}
    closed = {**_SAMPLE_BASE, "kind": "closed", "proposed": None}
    ask = {**_SAMPLE_BASE, "kind": "ask", "proposed": None, "last_year_hours": None, "google_now": None}
    nochg = {**_SAMPLE_BASE, "kind": "no_change", "holiday_date": "2026-11-08", "holiday_name_fi": "Isänpäivä",
             "holiday_name_en": "Father's Day"}
    rec = {"holiday_name_fi": "Jouluaatto", "holiday_name_en": "Christmas Eve", "hours": [{"start": "09:00", "end": "13:00"}],
           "publishers": ["Google", "Apple Maps", "Bing"]}
    items = [
        ("1. Suggestion with proposed hours (WhatsApp buttons: Hyväksy / Muokkaa / Ei kiitos)", suggestion_text(hours), suggestion_text_en(hours)),
        ("2. Suggestion, proposal is closed", suggestion_text(closed), suggestion_text_en(closed)),
        ("3. Ask instead of guess (low confidence or cold start)", ask_text(ask), ask_text_en(ask)),
        ("4. No change needed (reliability: we do not invent work)", no_change_text(nochg), no_change_text_en(nochg)),
        ("5. Receipt after apply", receipt_text(rec), receipt_text_en(rec)),
        ("6. Edit prompt after Muokkaa", edit_prompt_text(), edit_prompt_text_en()),
        ("7. Thanks after Ei kiitos", decline_thanks_text(), decline_thanks_text_en()),
        ("8. Reply not understood", unknown_reply_text(), unknown_reply_text_en()),
    ]
    out = ["# Final customer messages", "",
           "Demo business: Furry Paw Vet Clinic (fictional Yext sandbox entity). Text as sent over WhatsApp, with English glosses.", ""]
    for title, fi, en in items:
        out += [f"## {title}", "", "Finnish:", "", *["> " + l if l else ">" for l in fi.split("\n")], "",
                "English gloss:", "", *["> " + l if l else ">" for l in en.split("\n")], ""]
    md = "\n".join(out)
    p = Path(path) if path else Path(__file__).resolve().parents[2] / "docs" / "final_messages.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(md, encoding="utf-8")
    return md


if __name__ == "__main__":
    all_final_messages()
    print("wrote docs/final_messages.md")
