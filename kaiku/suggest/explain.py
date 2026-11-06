"""Finnish and English copy. Dates '24.12.', times '9-13', no em dashes."""
from __future__ import annotations

from datetime import date

WD_ESS = ["maanantaina", "tiistaina", "keskiviikkona", "torstaina", "perjantaina", "lauantaina", "sunnuntaina"]
WD_GEN = ["maanantain", "tiistain", "keskiviikon", "torstain", "perjantain", "lauantain", "sunnuntain"]
WD_PLUR = ["maanantaisin", "tiistaisin", "keskiviikkoisin", "torstaisin", "perjantaisin", "lauantaisin", "sunnuntaisin"]
WD_FI_IDX = {"maanantai": 0, "tiistai": 1, "keskiviikko": 2, "torstai": 3, "perjantai": 4, "lauantai": 5, "sunnuntai": 6}
WD_FI_NOM = ["maanantai", "tiistai", "keskiviikko", "torstai", "perjantai", "lauantai", "sunnuntai"]
WD_ABBR = ["ma", "ti", "ke", "to", "pe", "la", "su"]
WD_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WD_ABBR_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
# holiday (lower-case nominative) -> essive ("auki jouluaattona")
ESSIVE = {
    "jouluaatto": "jouluaattona", "joulupäivä": "joulupäivänä", "tapaninpäivä": "tapaninpäivänä",
    "uudenvuodenaatto": "uudenvuodenaattona", "uudenvuodenpäivä": "uudenvuodenpäivänä", "loppiainen": "loppiaisena",
    "isänpäivä": "isänpäivänä", "äitienpäivä": "äitienpäivänä", "vappu": "vappuna", "juhannusaatto": "juhannusaattona",
    "juhannuspäivä": "juhannuspäivänä", "pyhäinpäivä": "pyhäinpäivänä", "itsenäisyyspäivä": "itsenäisyyspäivänä",
    "pitkäperjantai": "pitkänäperjantaina", "pääsiäispäivä": "pääsiäispäivänä",
    "toinen pääsiäispäivä": "toisena pääsiäispäivänä", "helatorstai": "helatorstaina", "helluntaipäivä": "helluntaipäivänä",
}


def d_fi(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day}.{d.month}."


def _t(s: str) -> str:
    h, m = s.split(":")
    return f"{int(h)}" if m == "00" else f"{int(h)}.{m}"


def hours_fi(hours) -> str:
    if hours == "closed" or not hours:
        return "suljettu"
    return ", ".join(f"{_t(x['start'])}-{_t(x['end'])}" for x in hours)


def hours_en(hours) -> str:
    if hours == "closed" or not hours:
        return "closed"
    return ", ".join(f"{x['start']}-{x['end']}" for x in hours)


def hours_key(hours) -> str:
    """Canonical form for equality checks."""
    if hours == "closed" or not hours:
        return "closed"
    return "|".join(f"{x['start']}-{x['end']}" for x in hours)


def cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def ask_fi(name_fi: str, iso: str) -> str:
    ess = ESSIVE.get(name_fi.lower(), f"päivänä {d_fi(iso)}")
    return f"Oletteko auki {ess} {d_fi(iso)}? Vastaa esimerkiksi 9-13 tai suljettu."


def ask_en(name_en: str, iso: str) -> str:
    return f"Are you open on {name_en} {d_fi(iso)}? Reply for example 9-13 or closed."


def proposal_fi(iso: str, hours) -> str:
    d = date.fromisoformat(iso)
    ab = WD_ABBR[d.weekday()]
    if hours == "closed" or not hours:
        return f"{ab} {d_fi(iso)} suljettu."
    return f"{ab} {d_fi(iso)} klo {hours_fi(hours)}."


def proposal_en(iso: str, hours) -> str:
    d = date.fromisoformat(iso)
    ab = WD_ABBR_EN[d.weekday()]
    if hours == "closed" or not hours:
        return f"{ab} {d_fi(iso)} closed."
    return f"{ab} {d_fi(iso)} {hours_en(hours)}."


def shows_now(det, wd: int):
    """What we may say about the published hours, only from verified state.
    Returns (fi, en) clauses without a leading 'joten'/'so'. Google is named only when Serper verified it."""
    reg = det.signals["regular_that_day"]["hours"]
    g = det.signals.get("google_now") or {}
    if g.get("status") == "shows_hours":
        if g.get("hours") is not None and hours_key(g["hours"]) == hours_key(reg):
            return (f"Google näyttää nyt tavalliset {WD_GEN[wd]} aukioloajat ({hours_fi(reg)})",
                    f"Google now shows your regular {WD_EN[wd]} hours ({hours_en(reg)})")
        return (f"Google näyttää nyt tämän päivän aukioloajoiksi \"{g.get('text')}\"",
                f"Google now shows \"{g.get('text')}\" for that day")
    return (f"Fonecta Connect näyttää nyt tavalliset {WD_GEN[wd]} aukioloajat ({hours_fi(reg)})",
            f"Fonecta Connect now shows your regular {WD_EN[wd]} hours ({hours_en(reg)})")


def past_fi(iso: str) -> str:
    return f"Päivä {d_fi(iso)} on jo mennyt, joten aukioloaikoihin ei ehdoteta muutosta."


def past_en(iso: str) -> str:
    return f"{d_fi(iso)} has already passed, so no change to the opening hours is suggested."


def build_messages(business, det, kind: str, proposed, primary: str) -> tuple[str, str]:
    """primary: lastyear|website|peers|regular|already|ask"""
    iso = det.holiday_date
    d = date.fromisoformat(iso)
    h = det.holiday or {}
    nfi, nen = h.get("name_fi") or "Poikkeuspäivä", h.get("name_en") or "The day"
    wd = d.weekday()
    reg = det.signals["regular_that_day"]["hours"]
    hi = f"Hei {business.name}! {cap(nfi)} on {WD_ESS[wd]} {d_fi(iso)}"
    hi_en = f"Hi {business.name}! {nen} is on {WD_EN[wd]} {d_fi(iso)}"
    if kind == "ask":
        q = ask_fi(nfi, iso)
        return f"{hi} Meillä ei ole varmaa tietoa aukioloajoistanne. {q}", \
            f"{hi_en} We do not have reliable data on your hours. {ask_en(nen, iso)}"
    if kind == "no_change":
        if primary == "already":
            return f"{hi} Poikkeusaukioloajat ovat jo lisätty, joten mitään ei tarvitse tehdä.", \
                f"{hi_en} Exception hours are already set, nothing to do."
        if not reg and h.get("public_holiday"):
            return (f"{cap(nfi)} {d_fi(iso)} on {WD_FI_NOM[wd]} ja olette silloin kiinni, joten muutosta ei tarvita."), \
                (f"{nen} {d_fi(iso)} is on a {WD_EN[wd]} and you are closed then, so no change is needed.")
        if not reg:
            return (f"{hi} Olette {WD_PLUR[wd]} normaalisti suljettu, eikä {nfi.lower()} ole arkipyhä, "
                    f"joten aukioloaikoihin ei tarvita muutosta."), \
                (f"{hi_en} You are normally closed on {WD_EN[wd]}s and this is not a public holiday, "
                 f"so no change is needed.")
        return (f"{hi} Tavalliset {WD_GEN[wd]} aukioloajat ({hours_fi(reg)}) pätevät myös silloin, "
                f"joten aukioloaikoihin ei tarvita muutosta."), \
            (f"{hi_en} Your regular {WD_EN[wd]} hours ({hours_en(reg)}) apply, so no change is needed.")
    sfi, sen = shows_now(det, wd)
    google_fi, google_en = f"joten {sfi}", f"so {sen}"
    prop_fi, prop_en = proposal_fi(iso, proposed), proposal_en(iso, proposed)
    ly = det.signals["last_year"]
    if primary == "lastyear":
        then_fi = "auki " + hours_fi(ly["hours"]) if ly["hours"] != "closed" else "suljettuna"
        then_en = "open " + hours_en(ly["hours"]) if ly["hours"] != "closed" else "closed"
        return (f"{hi} Viime vuonna olitte {then_fi}, mutta tälle vuodelle ei ole lisätty poikkeusaukioloaikoja, "
                f"{google_fi}. Ehdotus: {prop_fi}"), \
            (f"{hi_en} Last year you were {then_en} that day, but no exception hours have been added this year, "
             f"{google_en}. We suggest: {prop_en}")
    if primary == "website":
        q = det.signals["website"]["quote"]
        return (f"{hi} Verkkosivullanne lukee \"{q}\", mutta tälle vuodelle ei ole lisätty poikkeusaukioloaikoja, "
                f"{google_fi}. Ehdotus: {prop_fi}"), \
            (f"{hi_en} Your website says \"{q}\", but no exception hours have been added this year, "
             f"{google_en}. We suggest: {prop_en}")
    # peers
    return (f"{hi} Tälle vuodelle ei ole lisätty poikkeusaukioloaikoja, {google_fi}. "
            f"Saman alan yritykset ovat yleensä {'kiinni' if proposed == 'closed' else 'auki ' + hours_fi(proposed)} "
            f"tänä päivänä. Ehdotus: {prop_fi}"), \
        (f"{hi_en} No exception hours have been added this year, {google_en}. Similar businesses are usually "
         f"{'closed' if proposed == 'closed' else 'open ' + hours_en(proposed)} that day. We suggest: {prop_en}")
