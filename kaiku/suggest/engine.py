"""suggest(business, detection) -> Suggestion, with the RELIABILITY gate.

Gate (first match wins):
 0 exception already set for the date            -> no_change 0.95
 1 not a public holiday and regular is closed   -> no_change 0.95
 2 same holiday last year has an exception       -> propose it 0.85 (0.75 if weekday differs)
 3 website quotes exception hours                -> propose 0.80
 4 public holiday and category prior "closed"    -> closed 0.65
 5 peer prior only                               -> 0.50  (below ASK_BELOW -> ask)
Anything below ASK_BELOW becomes kind=ask with a one-line Finnish question. A proposal equal to the regular
hours of that day becomes no_change. Nothing above 0.6 is ever produced from a guess.
"""
from __future__ import annotations

from kaiku.suggest import explain as ex
from kaiku.suggest.schema import Business, Detection, Suggestion

ASK_BELOW = 0.6
WDI = ex.WD_FI_IDX
DS = {"lastyear": "urn:ngsi-ld:dataset:kaiku:lastyear", "website": "urn:ngsi-ld:dataset:kaiku:website",
      "google": "urn:ngsi-ld:dataset:kaiku:google", "peers": "urn:ngsi-ld:dataset:kaiku:peers"}


def _r(source, text_fi, text_en):
    return {"source": source, "dataset_id": DS[source], "text_fi": text_fi, "text_en": text_en}


def _kind(proposed) -> str:
    return "closed" if proposed == "closed" else "hours"


def suggest(business: Business, det: Detection) -> Suggestion:
    s = det.signals
    iso = det.holiday_date
    h = det.holiday or {}
    public = bool(h.get("public_holiday"))
    reg = s["regular_that_day"]
    reg_key = ex.hours_key(reg["hours"])
    nfi = (h.get("name_fi") or "").lower()
    reasons: list = []
    primary, proposed, conf = "ask", None, 0.3

    ly = s["last_year"]
    wk = det.signals["regular_that_day"]["weekday_fi"]
    google_r = _r("google",
                  f"Google näyttää nyt tavalliset {ex.WD_GEN[WDI[wk]]} aukioloajat ({ex.hours_fi(reg['hours'])}).",
                  f"Google currently shows the regular {wk} hours ({ex.hours_en(reg['hours'])}).")

    if s.get("this_year"):
        primary, proposed, conf = "already", s["this_year"]["hours"], 0.95
    elif not public and reg["closed"]:
        primary, proposed, conf = "regular", "closed", 0.95
        reasons.append(_r("google", f"Päivä ei ole arkipyhä ja olette normaalisti kiinni {ex.WD_PLUR[WDI[wk]]}.",
                          f"Not a public holiday and you are normally closed on this weekday."))
    elif ly.get("found"):
        primary, proposed = "lastyear", ly["hours"]
        conf = 0.85 if ly["weekday_same"] else 0.75
        note_fi = "" if ly["weekday_same"] else f" (viikonpäivä oli silloin {ly['weekday_fi_then']})"
        note_en = "" if ly["weekday_same"] else f" (it was a different weekday then: {ly['weekday_fi_then']})"
        reasons.append(_r("lastyear", f"Viime vuonna {ex.d_fi(ly['date'])} olitte {'suljettu' if ly['hours']=='closed' else 'auki ' + ex.hours_fi(ly['hours'])}{note_fi}.",
                          f"Last year on {ex.d_fi(ly['date'])} you were {ex.hours_en(ly['hours'])}{note_en}."))
        reasons.append(google_r)
    elif s.get("website"):
        primary, proposed, conf = "website", s["website"]["hours"], 0.8
        reasons.append(_r("website", f"Verkkosivunne kertoo: \"{s['website']['quote']}\".",
                          f"Your website says: \"{s['website']['quote']}\"."))
        reasons.append(google_r)
    elif s.get("peers"):
        p = s["peers"]
        if p["value"] == "regular":
            primary, proposed, conf = "regular", reg["hours"] or "closed", 0.7
        elif public and p["value"] == "closed":
            primary, proposed, conf = "peers", "closed", 0.65
        else:
            primary, proposed, conf = "peers", p.get("hours"), 0.5
        reasons.append(_r("peers", "Saman alan yritykset ovat yleensä " +
                          ("kiinni" if p["value"] == "closed" else "auki tavallisesti" if p["value"] == "regular" else "auki " + ex.hours_fi(p["hours"])) +
                          " tänä päivänä (käsin tehty oletus).",
                          "Similar businesses are usually " + ("closed" if p["value"] == "closed" else "open as usual" if p["value"] == "regular" else "open " + ex.hours_en(p["hours"])) +
                          " that day (hand-made prior)."))
    elif not public:
        primary, proposed, conf = "regular", reg["hours"] or "closed", 0.7
        reasons.append(_r("google", "Päivä ei ole arkipyhä, eikä muutosta kaipaavaa tietoa löytynyt.",
                          "Not a public holiday and no data suggests a change."))

    # gate
    if primary != "already" and conf < ASK_BELOW:
        kind, proposed, primary = "ask", None, "ask"
    elif primary in ("already", "regular"):
        kind = "no_change"
    else:
        kind = _kind(proposed)
        if ex.hours_key(proposed) == reg_key:
            kind = "no_change"
    msg_in = None if kind == "no_change" else proposed
    fi, en = ex.build_messages(business, det, kind, msg_in, primary)
    if kind == "ask":
        reasons.append(_r("peers" if s.get("peers") else "google",
                          "Tietoa ei ole riittävästi, joten kysymme ennen kuin ehdotamme mitään.",
                          "There is not enough data, so we ask before proposing anything."))
        q = ex.ask_fi(h.get("name_fi") or "", iso)
    else:
        q = None
    return Suggestion(id=f"sug-{business.id}-{iso}", business_id=business.id, holiday_date=iso, kind=kind,
                      proposed=proposed if isinstance(proposed, list) and kind == "hours" else None,
                      confidence=conf, reasons=reasons, message_fi=fi, message_en=en, question_fi=q)
