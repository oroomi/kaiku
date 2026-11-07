"""Customer messages for the Kaiku contact step (WhatsApp, and the same words for the call).

English is the default (owner_language "en"); Finnish stays per owner (owner_language "fi"). Dispatchers pick via owner_lang().

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
    return "closed" if (not hours or hours == "closed") else fi_hours(hours)  # the demo writes times as 9-13 everywhere


def holiday_name(s: dict) -> str:
    """Holiday name from the engine; the generic 'Kyseinen päivä' (that day) only when no name is known."""
    return (s.get("holiday_name_fi") or s.get("name_fi") or "Kyseinen päivä").strip()


def _has_name(s: dict) -> bool:
    return bool(s.get("holiday_name_fi") or s.get("name_fi"))


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


def _why_wrong_fi(s: dict, proposed_txt: str) -> str | None:
    g = _hours_of(_google_now(s))
    if g is None:
        return None  # unknown: state nothing we cannot back up
    g_txt = fi_hours(g)
    if g_txt == proposed_txt:
        return f"Googlessa näkyy jo {g_txt}, joten ehdotus vain varmistaa sen."
    return (f"Googlessa näkyy nyt {g_txt}, mikä ei vastaa ehdotustamme, "
            f"joten asiakas voi saapua suljetun oven eteen.")


DECIDE_FI = "Voitte hyväksyä yhdellä napautuksella, muokata aikaa tai jättää ehdotuksen väliin. Päätös on aina teidän."
DECIDE_EN = "Approve with one tap, edit the hours, or skip it. The decision is always yours."


def _url_line_fi(s: dict) -> str | None:
    return f"Voitte myös päättää selaimessa: {s['decide_url']}" if s.get("decide_url") else None


def _url_line_en(s: dict) -> str | None:
    return f"You can also decide in the browser: {s['decide_url']}" if s.get("decide_url") else None


def _join_lines(lines) -> str:
    return "\n".join(l for l in lines if l is not None)


def suggestion_text_fi(s: dict) -> str:
    kind = s.get("kind")
    if kind == "ask":
        return ask_text_fi(s)
    if kind == "no_change":
        return no_change_text_fi(s)
    if s.get("message_fi"):  # the engine's own facts, verbatim
        return _join_lines([s["message_fi"], "", DECIDE_FI, _url_line_fi(s)])
    name = business_name(s)
    hol = holiday_name(s)
    proposed = "closed" if kind == "closed" else s.get("proposed")
    p_txt = fi_hours(proposed)
    ly = _hours_of(_last_year(s))
    d = fi_date(s["holiday_date"])
    parts = [f"Hei, {name}!", ""]
    if _has_name(s):
        parts.append(f"{_cap(hol)} on {_when_fi(s)}")
    else:
        parts.append(f"{_cap(_when_fi(s))} on poikkeuspäivä.")
    if ly is not None:
        parts.append(f"Viime vuonna aukioloaikanne tuona päivänä oli {fi_hours(ly)}.")
    why = _why_wrong_fi(s, p_txt)
    if why:
        parts.append(why)
    parts.append("")
    when = f"{essive(hol)} ({d})" if _has_name(s) else f"{d}"
    if proposed == "closed":
        parts.append(f"Ehdotamme, että {when} olette suljettuna.")
    else:
        parts.append(f"Ehdotamme, että {when} aukioloaikanne on {p_txt}.")
    parts += [DECIDE_FI, _url_line_fi(s)]
    return _join_lines(parts)


def suggestion_text_en(s: dict) -> str:
    kind = s.get("kind")
    if kind == "ask":
        return ask_text_en(s)
    if kind == "no_change":
        return no_change_text_en(s)
    if s.get("message_en"):
        return _join_lines([s["message_en"], "", DECIDE_EN, _url_line_en(s)])
    named = bool(s.get("holiday_name_en"))
    hol = s.get("holiday_name_en") or "that day"
    proposed = "closed" if kind == "closed" else s.get("proposed")
    ly = _hours_of(_last_year(s))
    g = _hours_of(_google_now(s))
    lines = [f"Hi, {business_name(s)}!", "", f"{_cap(hol)} falls on {_when_en(s)}" if named else f"{_when_en(s)} is an exception day."]
    if ly is not None:
        lines.append(f"Last year your hours that day were {en_hours(ly)}.")
    if g is not None:
        lines.append(f"Google currently shows {en_hours(g)}, which does not match our suggestion, so customers may arrive at a closed door.")
    lines.append("")
    lines.append(f"We suggest {'that you are closed' if proposed == 'closed' else 'your hours are ' + en_hours(proposed)} on {hol if named else 'that day'} ({fi_date(s['holiday_date'])}).")
    lines += [DECIDE_EN, _url_line_en(s)]
    return _join_lines(lines)


def ask_text_fi(s: dict) -> str:
    if s.get("message_fi"):
        return _join_lines([s["message_fi"], "", _url_line_fi(s)] if s.get("decide_url") else [s["message_fi"]])
    return _join_lines([
        f"Hei, {business_name(s)}!", "",
        (f"{_cap(holiday_name(s))} on {_when_fi(s)} " if _has_name(s) else f"{_cap(_when_fi(s))} ") +
        "Emme ole varmoja, mitkä aukioloaikanne silloin ovat, emmekä halua arvata väärin.", "",
        "Kertokaa vastaamalla tähän viestiin, esimerkiksi \"9-13\" tai \"suljettu\". "
        "Tallennamme ajan vasta kun olette vahvistaneet sen.",
        _url_line_fi(s)])


def ask_text_en(s: dict) -> str:
    if s.get("message_en"):
        return _join_lines([s["message_en"], "", _url_line_en(s)] if s.get("decide_url") else [s["message_en"]])
    return _join_lines([
        f"Hi, {business_name(s)}!", "",
        (f"{_cap(s.get('holiday_name_en') or 'That day')} falls on " if s.get("holiday_name_en") else "") + f"{_when_en(s)} " +
        "We are not sure what your hours are then, and we do not want to guess wrong.", "",
        "Reply to this message, for example \"9-13\" or \"closed\". We only save the time after you confirm it.",
        _url_line_en(s)])


def no_change_text_fi(s: dict) -> str:
    if s.get("message_fi"):
        return s["message_fi"]
    lead = f"{_cap(holiday_name(s))} on {_when_fi(s)}" if _has_name(s) else f"{_cap(_when_fi(s))}"
    return (f"Hei, {business_name(s)}!\n\n"
            f"{lead}, mutta tavalliset aukioloaikanne pätevät silloinkin. "
            f"Mitään ei tarvitse tehdä, eikä aukioloaikoihinne ole tulossa muutoksia.")


def no_change_text_en(s: dict) -> str:
    if s.get("message_en"):
        return s["message_en"]
    lead = f"{_cap(s['holiday_name_en'])} falls on {_when_en(s)}" if s.get("holiday_name_en") else _when_en(s)
    return (f"Hi, {business_name(s)}!\n\n"
            f"{lead}, but your regular hours apply then too. "
            f"Nothing to do, and no changes are coming to your hours.")


def unknown_suggestion_text_fi() -> str:
    return "En löytänyt ehdotusta, johon tämä vastaus liittyy."


def unknown_suggestion_text_en() -> str:
    return "I could not find the suggestion this reply belongs to."


def _hours_from_result(r: dict):
    return r.get("hours_text") or r.get("hours")


def receipt_text_fi(r: dict) -> str:
    """r: ApplyResult dict, optionally enriched with holiday_name_fi, hours (list|'closed') or hours_text."""
    h = _hours_from_result(r)
    h_txt = h if isinstance(h, str) and h != "closed" else fi_hours(h)
    pubs = r.get("publishers") or PUBLISHERS_DEFAULT
    pub_txt = _join_fi(pubs)
    gen = holiday_name_genitive(r) if _has_name(r) else "Poikkeuspäivän"
    if h_txt == "suljettu":
        what = f"{gen} sulkeutuminen on nyt tallennettu."
        return f"Kiitos! {what} Se näkyy {pub_txt}."
    what = f"{gen} aukioloajat {h_txt} on nyt tallennettu."
    return f"Kiitos! {what} Ne näkyvät {pub_txt}."


CHANNELS_EN = "Google, Fonecta Finder, 020202 and the other channels Connect publishes to"


def receipt_text_en(r: dict) -> str:
    h = _hours_from_result(r)
    h_txt = h.replace("-", " to ") if isinstance(h, str) and h != "closed" else en_hours(h)
    h_txt = h_txt.replace(" to ", "-") if h_txt != "closed" else h_txt
    hol = r.get("holiday_name_en") or "Exception day"
    day = f"{hol} {fi_date(r['holiday_date'])}" if r.get("holiday_date") else hol
    if h_txt == "closed":
        return f"Done. {day} closure is saved and will show on {CHANNELS_EN}."
    return f"Done. {day} hours {h_txt} are saved and will show on {CHANNELS_EN}."


def standing_question_text_en(s: dict) -> str:
    """Asked after an approval, only when the business changed this day last year as well: offer to make it recurring."""
    return "You changed this last year as well. Do you want to make it recurring, this time of the year?"


def standing_question_text_fi(s: dict) -> str:
    return "Muutit tämän myös viime vuonna. Haluatko tehdä tästä toistuvan, joka vuosi tähän aikaan?"


def standing_question_text(s: dict) -> str:
    return standing_question_text_fi(s) if owner_lang(s) == "fi" else standing_question_text_en(s)


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


def edit_prompt_text_fi() -> str:
    return "Selvä. Kirjoittakaa uusi aukioloaika vastaamalla tähän viestiin, esimerkiksi \"9-13\" tai \"suljettu\"."


def edit_prompt_text_en() -> str:
    return "Reply with the new hours, like 9-13, or 'closed'."


def decline_thanks_text_fi() -> str:
    return "Selvä, aukioloaikoihin ei tehdä muutoksia. Kiitos vastauksesta! Voitte muuttaa päätöstä milloin tahansa."


def decline_thanks_text_en() -> str:
    return "Understood, no changes will be made to your hours. Thanks for replying! You can change your mind any time."


def unknown_reply_text_fi() -> str:
    return "En ymmärtänyt vastausta. Voitte painaa jotakin painikkeista tai kirjoittaa esimerkiksi \"9-13\" tai \"suljettu\"."


def unknown_reply_text_en() -> str:
    return ("No rush at all, take your time. I'll leave everything as it is until you tell me. "
            "When you're ready, just reply yes, or tell me the hours, like 9-13 or closed.")


# ---------------------------------------------------------------- language dispatch (English is the default)

DEFAULT_LANG = "en"
_seed_lang: str | None = None


def _seed_language() -> str:
    """owner_language of the demo business seed (data/furry_paw.json); 'en' when absent."""
    global _seed_lang
    if _seed_lang is None:
        import json
        try:
            v = json.loads((Path(__file__).resolve().parents[2] / "data" / "furry_paw.json").read_text(encoding="utf-8")).get("owner_language")
        except (OSError, ValueError):
            v = None
        _seed_lang = v if v in ("en", "fi") else DEFAULT_LANG
    return _seed_lang


def owner_lang(x=None) -> str:
    """'en' | 'fi' from a Business or Suggestion (dict or object): x.owner_language, x.business.owner_language,
    else the demo seed's setting, else 'en'."""
    def pick(o):
        if o is None:
            return None
        v = o.get("owner_language") if isinstance(o, dict) else getattr(o, "owner_language", None)
        return str(v).lower()[:2] if v else None
    for cand in (x, (x.get("business") if isinstance(x, dict) else getattr(x, "business", None))):
        v = pick(cand)
        if v in ("en", "fi"):
            return v
    return _seed_language()


def suggestion_text(s: dict) -> str:
    return suggestion_text_fi(s) if owner_lang(s) == "fi" else suggestion_text_en(s)


def ask_text(s: dict) -> str:
    return ask_text_fi(s) if owner_lang(s) == "fi" else ask_text_en(s)


def no_change_text(s: dict) -> str:
    return no_change_text_fi(s) if owner_lang(s) == "fi" else no_change_text_en(s)


def receipt_text(r: dict) -> str:
    return receipt_text_fi(r) if owner_lang(r) == "fi" else receipt_text_en(r)


def edit_prompt_text(lang: str | None = None) -> str:
    return edit_prompt_text_fi() if owner_lang({"owner_language": lang}) == "fi" else edit_prompt_text_en()


def decline_thanks_text(lang: str | None = None) -> str:
    return decline_thanks_text_fi() if owner_lang({"owner_language": lang}) == "fi" else decline_thanks_text_en()


def unknown_reply_text(lang: str | None = None) -> str:
    return unknown_reply_text_fi() if owner_lang({"owner_language": lang}) == "fi" else unknown_reply_text_en()


def unknown_suggestion_text(lang: str | None = None) -> str:
    return unknown_suggestion_text_fi() if owner_lang({"owner_language": lang}) == "fi" else unknown_suggestion_text_en()


def button_titles(s: dict | None = None, lang: str | None = None) -> list[tuple[str, str]]:
    """[(action, title)] for approve/edit/decline in the owner's language."""
    fi = (owner_lang({"owner_language": lang}) if lang else owner_lang(s)) == "fi"
    return [("approve", "Hyväksy"), ("edit", "Muokkaa"), ("decline", "Ei kiitos")] if fi else \
        [("approve", "Approve"), ("edit", "Edit"), ("decline", "No thanks")]


# ---------------------------------------------------------------- export

def _engine_cases() -> dict:
    """Real Suggestion dicts from the suggest engine for the Furry Paw demo business (no network)."""
    import dataclasses
    import json

    from kaiku.suggest.cli import ROOT, load_business, run

    path = str(ROOT / "data" / "furry_paw.json")
    biz = load_business(path)
    cold = json.loads((ROOT / "data" / "furry_paw.json").read_text(encoding="utf-8"))
    cold["last_year_exceptions"] = []
    from kaiku.suggest.schema import Business
    cold_biz = Business.from_dict(cold)

    def sug(b, d, today):
        o = run(b, d, today, network=False)[1]
        return o if isinstance(o, dict) else (o.to_dict() if hasattr(o, "to_dict") else dataclasses.asdict(o))

    return {"hours": sug(biz, "2026-12-24", "2026-12-17"), "closed": sug(biz, "2026-12-25", "2026-12-17"),
            "ask": sug(cold_biz, "2026-12-24", "2026-12-17"), "nochg": sug(biz, "2026-11-08", "2026-11-01")}


WA_OPENING_EN = "\n".join([
    "Hi Furry Paw Vet Clinic. I noticed 2 things.", "",
    "Christmas Eve 24.12.: 09:00-13:00. Hi Furry Paw Vet Clinic! Christmas Eve is on Thursday 24.12. Last year you were open 09:00-13:00 that day, but no exception hours have been added this year, so Fonecta Connect now shows your regular Thursday hours (09:00-17:00). We suggest: Thu 24.12. 09:00-13:00.", "",
    "Christmas period: 6 dates. 24.12. 09:00-13:00; 25.12. closed; 26.12. closed; 31.12. 09:00-15:00; 1.1. closed; 6.1. closed. Want me to handle this period every year?. I suggest 24.12. 9-13; 25.12. closed; 26.12. closed; 31.12. 9-15; 1.1. closed; 6.1. closed.", "",
    "Reply in your own words."])
WA_OPENING_FI = ("(Finnish owners get the Finnish suggestion text followed by \"Vastaa omin sanoin.\"; the website chat opening is English only.)\n\n"
                 + suggestion_text_fi({"business_name": "Furry Paw Vet Clinic", "holiday_date": "2026-12-24", "holiday_name_fi": "Jouluaatto", "kind": "hours",
                                       "proposed": [{"start": "09:00", "end": "13:00"}], "last_year_hours": [{"start": "09:00", "end": "13:00"}],
                                       "google_now": [{"start": "09:00", "end": "17:00"}]}) + "\n\nVastaa omin sanoin.")


def all_final_messages(path: str | Path | None = None) -> str:
    """Write docs/final_messages.md: every customer-facing message as text, with English glosses. Returns the markdown."""
    c = _engine_cases()
    hours, closed, ask, nochg = c["hours"], c["closed"], c["ask"], c["nochg"]
    rec = {"holiday_name_fi": "Jouluaatto", "holiday_name_en": "Christmas Eve", "hours": [{"start": "09:00", "end": "13:00"}],
           "publishers": ["Google", "Apple Maps", "Bing"]}
    rec_closed = {"holiday_name_fi": "Joulupäivä", "holiday_name_en": "Christmas Day", "hours": "closed",
                  "publishers": ["Google", "Apple Maps", "Bing"]}
    from . import email as _E
    em_s = dict(hours, decide_url="https://kaiku.example/d/EXAMPLE-TOKEN")
    em_fi = _E.build_message(dict(em_s, owner_language="fi"), "owner@example.com")[1]
    em_en = _E.build_message(dict(em_s, owner_language="en"), "owner@example.com")[1]
    with_url = dict(hours, decide_url="https://kaiku.example/decide/sug-furry-paw-2026-12-24")
    items = [
        ("0b. Step 2 WhatsApp opening: ONE plain text, the same intro and suggestion lines the website chat shows on load (demo date 17.12., fictional Furry Paw Vet Clinic), no buttons",
         WA_OPENING_FI, WA_OPENING_EN),
        ("1. Suggestion with proposed hours (the plain suggestion text; WhatsApp buttons Approve / Edit / No thanks only with WA_BUTTONS=1)", suggestion_text_fi(hours), suggestion_text_en(hours)),
        ("2. Suggestion, proposal is closed", suggestion_text_fi(closed), suggestion_text_en(closed)),
        ("3. Ask instead of guess (low confidence or cold start)", ask_text_fi(ask), ask_text_en(ask)),
        ("4. No change needed (reliability: we do not invent work)", no_change_text_fi(nochg), no_change_text_en(nochg)),
        ("5. Receipt after apply (hours)", receipt_text_fi(rec), receipt_text_en(rec)),
        ("5b. Receipt after apply (closed day, singular)", receipt_text_fi(rec_closed), receipt_text_en(rec_closed)),
        ("5c. Suggestion when a decide link exists (example URL)", suggestion_text_fi(with_url), suggestion_text_en(with_url)),
        ("5d. Button for a suggestion we do not know", unknown_suggestion_text_fi(), unknown_suggestion_text_en()),
        ("0. Step 1 email (subject, then body)", em_fi["subject"] + "\n\n" + em_fi["text"], em_en["subject"] + "\n\n" + em_en["text"]),
        ("5e. Standing-permission question after an approval", standing_question_text_fi(hours), standing_question_text_en(hours)),
        ("6. Edit prompt after Edit", edit_prompt_text_fi(), edit_prompt_text_en()),
        ("7. Thanks after No thanks", decline_thanks_text_fi(), decline_thanks_text_en()),
        ("8. Reply not understood", unknown_reply_text_fi(), unknown_reply_text_en()),
    ]
    out = ["# Final customer messages", "",
           "Demo business: Furry Paw Vet Clinic (fictional Yext sandbox entity). Items 1 to 4 are the exact Suggestion texts from `python3 -m kaiku.suggest.cli --business data/furry_paw.json` (no network): 24.12. hours, 25.12. closed, 24.12. with no history (ask), 8.11. no change. Text as sent over WhatsApp, with English glosses.", ""]
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
