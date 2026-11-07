"""The owner conversation, v4: Accept and Suggest a change hand over to Kaiku, who proposes in plain words; the owner's
"yes" applies (through actions.decide), Kaiku's confirmation is the receipt, and nothing is claimed that the apply result
does not say. Session keys (kaiku.chat.router.session): focus (suggestion id), stage, pending (the owner's own value
waiting for a yes), followup (the recurring question waits for an answer).

stage: None | "proposed" (Kaiku asked 'shall I?', yes applies the card) | "ask_new" (Kaiku asked 'what should it be?')
       | "confirm" (the owner gave a value, Kaiku asked 'shall I save it?').
With no stage a yes still applies the focus (the WhatsApp opening is itself the proposal); the web page never sets focus
without proposing first."""
from __future__ import annotations

import re
from datetime import date as _date

from .. import store
from . import feed as F
from . import parser as P
from .util import d_short, hours_text, is_pending

WHERE = "Google, Fonecta Finder and 020202"
RECURRING_Q = "You changed this last year as well. Do you want to make it recurring, this time of the year?"
LEAVE = "Okay, I leave it as it is."
TEXT_KINDS = ("description", "review")
_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_TERMINAL = ("approved", "edited", "applied", "declined")


# ---------- small helpers ----------
def _biz(bid):
    return store.get_business(bid)


def _spans(h):
    if h in (None, "closed"):
        return h
    return [x.model_dump() if hasattr(x, "model_dump") else x for x in h]


def regular_that_day(bid: str, iso: str) -> str:
    b = _biz(bid)
    if b is None or not iso:
        return ""
    wd = _DAYS[_date.fromisoformat(iso).weekday()]
    return hours_text(_spans(b.regular_hours.get(wd))) or "closed"


def season(item: dict) -> str:
    iso = item.get("holiday_date") or ""
    md = iso[5:]
    if md >= "12-24" or md <= "01-06":
        return "Christmas" if iso else (item.get("holiday_name_en") or "This day")
    return item.get("holiday_name_en") or "This day"


def holiday_name(item: dict) -> str:
    if item.get("holiday_name_en"):
        return item["holiday_name_en"]
    t = item.get("title_en") or "this holiday"
    return re.sub(r"\s*\d{1,2}\.\d{1,2}\.?.*$", "", t).strip() or t


def period_name(item: dict) -> str:
    return (item.get("title_en") or "Christmas period").split(":")[0].strip()


def is_missing_description(item: dict) -> bool:
    return item["kind"] == "description" and not item.get("typos")


def member_item(bid: str, item: dict, m: dict) -> dict:
    """A period's per-date member as its own holiday item. The id is the one the single-date card has, so a date that was
    already decided on its own card is the same decision."""
    iso = m["date"]
    prop = m.get("proposed")
    return {"id": f"feed-{bid}-holiday_hours-{iso}", "kind": "holiday_hours", "holiday_date": iso, "holiday_name_en": m.get("name_en"),
            "title_en": f"{m.get('name_en') or iso} {d_short(iso)}", "text_en": "", "proposed": prop,
            "confidence": m.get("confidence") or item.get("confidence") or 0.5, "reasons": item.get("reasons", [])[:2], "status": "proposed"}


def period_members(bid: str, item: dict) -> list[dict]:
    prop = item.get("proposed")
    if not (isinstance(prop, list) and prop and isinstance(prop[0], dict) and "date" in prop[0]):
        return []
    return [member_item(bid, item, m) for m in prop]


def undecided_members(bid: str, item: dict) -> list[dict]:
    stored = []
    try:
        stored = store.list_suggestions(bid, 300)
    except Exception:
        pass
    done_dates = {s.holiday_date for s in stored if s.status in _TERMINAL}
    done_ids = {s.id for s in stored if s.status in _TERMINAL}
    return [m for m in period_members(bid, item) if m["id"] not in done_ids and m["holiday_date"] not in done_dates]


def has_last_year(bid: str, item: dict) -> bool:
    """True only when there is real last-year data for this holiday: the suggestion's own last_year, or an exception
    the business set on the same day last year."""
    if item.get("last_year"):
        return True
    b = _biz(bid)
    if b is None:
        return False
    dates = [item.get("holiday_date")] if item["kind"] != "period" else [m["date"] for m in (item.get("proposed") or []) if isinstance(m, dict)]
    last = {e.date[5:] for e in b.last_year_exceptions}
    return any(d and d[5:] in last for d in dates)


def _plain_reason(item: dict) -> str:
    rs = item.get("reasons") or []
    t = (rs[0].get("text_en") if rs else None) or item.get("text_en") or "that is what the data says"
    t = re.sub(r"\s*\([^)]*\)", "", t).strip().rstrip(".")
    t = re.sub(r"\b0?(\d{1,2}):00\b", r"\1", t)
    t = re.sub(r"\b0?(\d{1,2}):(\d\d)\b", r"\1:\2", t)
    t = re.sub(r"(\d)–(\d)", r"\1-\2", t)
    return t[:1].lower() + t[1:]


# ---------- Kaiku's pre-written texts ----------
def proposal(bid: str, item: dict) -> str:
    k = item["kind"]
    if k == "period":
        ms = undecided_members(bid, item) or period_members(bid, item)
        lst = "; ".join(f"{d_short(m['holiday_date'])} " + ("closed" if m["proposed"] in (None, "closed", []) else hours_text(m["proposed"])) for m in ms)
        return f"The {period_name(item)} is coming: {lst}. Shall I set all of them?"
    if k == "description":
        if is_missing_description(item):
            return f"Your listing has no description. Shall I publish this one? {item.get('proposed') or ''}".strip()
        ty = item.get("typos") or []
        fix = " and ".join(f"\"{t['wrong']}\" to \"{t['right']}\"" for t in ty[:2]) + (f" and {len(ty) - 2} more" if len(ty) > 2 else "")
        return f"Shall I correct {fix} in your description?"
    if k == "review":
        n = item.get("rating")
        star = f"{int(n) if float(n) == int(n) else n}-star review" if n else "review"
        return f"Shall I post this reply to the {star}? \"{item.get('proposed') or ''}\""
    name, date = holiday_name(item), d_short(item["holiday_date"]) if item.get("holiday_date") else ""
    what = f"{name} {date}".strip()
    prop = item.get("proposed")
    if not prop:
        return f"I have no ready hours for {what}. What should they be?"
    reg = regular_that_day(bid, item.get("holiday_date") or "")
    still = f"still says {reg}" if reg and reg != "closed" else "still says you are closed"
    if prop == "closed":
        return f"{season(item)} is coming. Do you want to mark {what} as closed? Everywhere Connect publishes {still}."
    return (f"{season(item)} is coming. Do you want to change your hours on {what} to {hours_text(prop)}? "
            f"Everywhere Connect publishes {still}.")


def change_prompt(item: dict) -> str:
    k = item["kind"]
    title = item.get("title_en") or "this"
    if k == "description":
        if is_missing_description(item):
            return "You want to change the description draft. Tell me the text you want instead, and I will check it with you before I save it."
        t = (item.get("typos") or [{}])[0]
        return (f"You want to change the description fix. I suggested \"{t.get('right', 'the correction')}\" instead of \"{t.get('wrong', 'the typo')}\". "
                "What should the description say?")
    if k == "review":
        return "You want to change the reply. I drafted it because this review has no reply yet. What should the reply say?"
    if k == "period":
        return (f"You want to change the {period_name(item)}. I suggested {hours_text(item.get('proposed'))} because {_plain_reason(item)}. "
                "Tell me one set of hours for all of these dates, or say closed.")
    prop = item.get("proposed")
    sug = f"I suggested {hours_text(prop)}" if prop else "I had no ready hours"
    return f"You want to change {title}. {sug} because {_plain_reason(item)}. What should it be?"


def confirm_text(item: dict, value) -> str:
    k = item["kind"]
    if k == "description":
        return f"Shall I save this as your description? \"{value}\""
    if k == "review":
        return f"Shall I post this as your reply? \"{value}\""
    h = hours_text(value)
    if k == "period":
        return f"{h[:1].upper() + h[1:]} on all of these dates, shall I save it?"
    d = d_short(item["holiday_date"]) if item.get("holiday_date") else "that day"
    return f"{h[:1].upper() + h[1:]} on {d}, shall I save it?"


def discard_text(item: dict) -> str:
    k = item["kind"]
    if k == "description":
        return "Okay, I leave your description as it is."
    if k == "review":
        return "Okay, I leave the review without a reply."
    if k == "period":
        return f"Okay, I leave the {period_name(item)} as it is."
    return f"Okay, I leave {item.get('title_en') or 'it'} as it is."


def receipt(bid: str, item: dict, r: dict) -> str:
    """What happened, said only as far as the apply result says it. r = actions.decide's result."""
    k = item["kind"]
    if not r.get("ok"):
        return ""
    if k == "review":
        if r.get("posted"):
            return "Done. Your reply is posted on the review." + (" I read it back to check." if r.get("verified") else "")
        if r.get("yext") == "ok":
            return "Your reply is stored. The sandbox key cannot post review comments, so it is not on the review yet."
    elif r.get("yext") == "ok":
        if k == "description":
            return f"Done. Your description is saved and shows on {WHERE} within the hour."
        if k == "period":
            n = r.get("count")
            return f"Done. {'All ' + str(n) + ' dates are' if n and n > 1 else 'The dates are'} saved and show on {WHERE} within the hour."
        final = r.get("final_hours") or ""
        return f"Done. {d_short(item['holiday_date']) if item.get('holiday_date') else holiday_name(item)} {final} is saved and shows on {WHERE} within the hour."
    if r.get("yext") is None:
        return "I have your answer, but the write to Yext has not finished, so I will not say it is saved yet."
    return "I could not save it: the write to Yext did not go through, so nothing has changed on your listing."


def handoff_text(bid: str, sess: dict, exclude: set[str]) -> str:
    """Move the focus to the next pending card and propose it. '' when nothing else is waiting."""
    items = F.get_feed(bid).get("suggestions", [])
    for i in items:
        if i["kind"] == "no_change" or not is_pending(i) or i["id"] in exclude:
            continue
        if i["kind"] == "period" and not undecided_members(bid, i):
            continue
        sess["focus"] = i["id"]
        sess["stage"] = "ask_new" if (i["kind"] == "holiday_hours" and not i.get("proposed")) else "proposed"
        sess["pending"] = None
        return f"Next: {i.get('title_en')}. {proposal(bid, i)}"
    sess["focus"], sess["stage"], sess["pending"] = None, None, None
    return ""


def reset(sess: dict) -> None:
    sess["focus"], sess["stage"], sess["pending"], sess["followup"] = None, None, None, None


# ---------- entry points the routes call ----------
def start_proposal(bid: str, sess: dict, item: dict) -> str:
    sess["focus"], sess["followup"], sess["pending"] = item["id"], None, None
    t = proposal(bid, item)
    sess["stage"] = "ask_new" if (item["kind"] == "holiday_hours" and not item.get("proposed")) else "proposed"
    return t


def start_change(sess: dict, item: dict) -> str:
    sess["focus"], sess["followup"], sess["pending"], sess["stage"] = item["id"], None, None, "ask_new"
    return change_prompt(item)


# ---------- the deterministic part of a turn ----------
def _focus_item(bid: str, sess: dict) -> dict | None:
    fid = sess.get("focus")
    if not fid:
        return None
    for i in F.get_feed(bid).get("suggestions", []):
        if i["id"] == fid and i["kind"] != "no_change" and is_pending(i):
            return i
    return None


async def apply_and_say(turn, bid: str, sess: dict, item: dict, action: str, edited_hours=None, edited_text=None) -> str:
    """decide(...) through the Turn (so actions and the follow-up bookkeeping stay in one place), then the receipt, the
    recurring question when there is last-year data, and the hand-off to the next card."""
    args = {"suggestion_id": item["id"], "action": action}
    if edited_hours is not None:
        args["edited_hours"] = edited_hours
    if edited_text is not None:
        args["edited_text"] = edited_text
    r = await turn.run("decide", args)
    return finish(bid, sess, item, action, r)


def finish(bid: str, sess: dict, item: dict, action: str, r: dict) -> str:
    """Kaiku's words after a decide(...) result: the receipt (only as far as the apply result says), the recurring
    question when there is last-year data, else the hand-off to the next card."""
    sess["stage"], sess["pending"] = None, None
    if not r.get("ok"):
        if r.get("needs_hours") or r.get("needs_text"):
            sess["focus"], sess["stage"] = item["id"], "ask_new"
            return "I have no ready value for that one. What should it be?"
        sess["focus"] = None
        return "That one is already decided." if str(r.get("error", "")).startswith("already") else "That did not work, nothing was changed."
    if action == "decline":
        sess["focus"] = None
        return LEAVE
    say = receipt(bid, item, r)
    if r.get("follow_up_question") and r.get("yext") == "ok":
        return f"{say} {r['follow_up_question']}".strip()
    sess["followup"] = None
    nxt = handoff_text(bid, sess, {item["id"]})
    return f"{say} {nxt}".strip()


async def recurring_answer(turn, bid: str, sess: dict, yes: bool) -> str:
    sid = sess.get("followup")
    item = F.find(bid, sid) if sid else None
    r = await turn.run("set_standing_permission", {"suggestion_id": sid, "enabled": yes})
    sess["followup"] = None
    if yes and r.get("ok") and item is not None:
        name = period_name(item) if item["kind"] == "period" else holiday_name(item)
        say = f"Every {name} from now on, unless you tell me otherwise."
    elif yes:
        say = "I could not store that, so I will ask you again next time."
    else:
        say = "Okay, I will ask you each time."
    nxt = handoff_text(bid, sess, {sid} if sid else set())
    return f"{say} {nxt}".strip()


async def handle(turn, sess: dict, message: str) -> str | None:
    """A reply when the conversation is in a stage this module owns and the message is yes / no / a value; None = let the
    brain (or the legacy fallback) take it."""
    bid = turn.bid
    p = P.parse(message)
    yn = p["action"] if p and p["action"] in ("approve", "decline") else None
    if sess.get("followup"):
        if yn:
            return await recurring_answer(turn, bid, sess, yn == "approve")
        sess["followup"] = None            # the question lapses: a later 'yes' must not answer it
    stage = sess.get("stage")
    if not stage:
        return None
    item = _focus_item(bid, sess)
    if item is None:
        reset(sess)
        return None
    text_kind = item["kind"] in TEXT_KINDS
    words = len(message.split())
    if yn == "decline":
        return await apply_and_say(turn, bid, sess, item, "decline")
    own_text = text_kind and (p is None or p["action"] in ("change", "edit")) and words >= 3
    own_hours = (not text_kind) and p is not None and p["action"] == "edit"
    if stage == "proposed":
        if yn == "approve":
            return await apply_and_say(turn, bid, sess, item, "approve")
        if p and p["action"] == "change":
            return start_change(sess, item)
    elif stage == "ask_new":
        if yn == "approve":
            return "Tell me what it should be, or say no to leave it as it is."
        if p and p["action"] == "change":
            return change_prompt(item)
    elif stage == "confirm":
        if yn == "approve" and sess.get("pending") is not None:
            v = sess["pending"]
            if text_kind:
                return await apply_and_say(turn, bid, sess, item, "edit", edited_text=v)
            return await apply_and_say(turn, bid, sess, item, "edit", edited_hours=v)
    if own_hours or own_text:
        v = p["edited"] if own_hours else message.strip()
        sess["pending"], sess["stage"] = v, "confirm"
        return confirm_text(item, v)
    return None
