"""Kaiku's chat brain: Anthropic claude-sonnet-5-5 with three tools, and a deterministic fallback that never needs the API."""
from __future__ import annotations

import json
import logging
import os
import re

from . import actions as A
from . import feed as F
from . import parser as P
from .util import hours_text, is_pending

log = logging.getLogger("kaiku.chat.brain")
MODEL = "claude-sonnet-5-5"
MAX_WORDS = 40
MAX_STEPS = 5

SYSTEM = """You are Kaiku, the assistant of Fonecta Connect, chatting with the owner of {name}. Connect publishes the business's opening hours to Google, Apple Maps, Bing and directories. You suggest, the owner decides.

Rules:
- Reply in {lang}. HARD LIMIT {max_words} words per reply, one to three short plain sentences, no lists, no markdown, no emoji, no dashes as punctuation. Write hours as 9-13 and dates as 24.12.
- Never invent hours, dates or facts. Use only the suggestions below and tool results. Never claim what Google shows beyond the suggestion text.
- The owner always has the last word. Never approve, edit or decline on your own. Act only on what the owner just said.
- "yes", "I agree", "approve", "ok", "do it": call decide(approve) for the suggestion under discussion. "no", "no thanks": decide(decline). A time range such as "make it 10-14", "9 to 1" (means 9-13), or "closed": decide(edit) with edited_hours as [{{"start":"10:00","end":"14:00"}}] or "closed". "Change the hours" with no hours: ask which hours.
- After decide returns ok with a follow_up_question, say in one short sentence what was saved, then ask the follow_up_question word for word. That is the ONE follow-up.
- If a follow-up is awaiting an answer: "yes" calls set_standing_permission(enabled true), "no" calls it with enabled false and you say you will ask again each time. Then name the next waiting item in a few words.
- If decide returns an error, say so plainly and nothing was changed.
- Items of kind no_change need nothing. Mention one only if asked, in one line: nothing to change and why.
- If the owner asks something the data does not answer, say you do not know. Stay on opening hours.

Business: {name}, {address}. Today in the demo clock: {today}.
Suggestions (id | kind | title | proposed | last year | status | reason):
{feed}
Under discussion: {focus}
Follow-up awaiting an answer for: {followup}"""

FI = {
    "again": "En ymmärtänyt. Sano kyllä, ei tai tunnit, esimerkiksi 10-14.",
    "which": "Mitkä tunnit? Esimerkiksi 10-14 tai suljettu.",
    "nothing": "Ei ole mitään päätettävää juuri nyt.",
    "saved": "Valmista, {what} on tallennettu.",
    "declined": "Selvä, jätän ennalleen.",
    "perm_yes": "Selvä, teen tämän jatkossa itse.",
    "perm_no": "Selvä, kysyn aina erikseen.",
    "error": "Se ei onnistunut, mitään ei muutettu.",
}
EN = {
    "again": "I did not catch that. Say yes, no, or hours such as 10-14.",
    "which": "Which hours? For example 10-14, or say closed.",
    "nothing": "Nothing is waiting for a decision right now.",
    "saved": "Done, {what} is saved.",
    "declined": "Okay, I will leave it as it is.",
    "perm_yes": "Done, I will do this by myself from now on.",
    "perm_no": "Fine, I will ask you each time.",
    "error": "That did not work, nothing was changed.",
}


def trim_words(text: str, limit: int = MAX_WORDS) -> str:
    text = text.replace("—", ",").replace("–", "-").strip()
    if len(text.split()) <= limit:
        return text
    sents = re.split(r"(?<=[.!?])\s+", text)
    out, n = [], 0
    for s in sents:
        w = len(s.split())
        if out and n + w > limit:
            break
        out.append(s)
        n += w
    return " ".join(out)


def pending_items(items):
    return [i for i in items if i["kind"] != "no_change" and is_pending(i)]


def focus_of(items, sess) -> dict | None:
    pend = pending_items(items)
    f = next((i for i in pend if i["id"] == sess.get("focus")), None)
    return f or (pend[0] if pend else None)


def _feed_lines(items) -> str:
    rows = []
    for i in items:
        rows.append(f"{i['id']} | {i['kind']} | {i['title_en']} | {hours_text(i.get('proposed')) or '-'} | "
                    f"{hours_text(i.get('last_year')) or '-'} | {i.get('status', 'proposed')} | {i.get('text_en', '')}")
    return "\n".join(rows) or "(none)"


def build_system(biz, items, sess, lang: str) -> str:
    from ..learn import timetravel
    f = focus_of(items, sess)
    fu = next((i for i in items if i["id"] == sess.get("followup")), None)
    return SYSTEM.format(name=biz.name, address=biz.address, lang="Finnish" if lang == "fi" else "English", max_words=MAX_WORDS,
                         today=timetravel.today().isoformat(), feed=_feed_lines(items),
                         focus=f"{f['id']} ({f['title_en']})" if f else "nothing",
                         followup=f"{fu['id']} ({fu['title_en']})" if fu else "none")


TOOLS = [
    {"name": "get_feed", "description": "Get the current suggestions for the business with their status.",
     "input_schema": {"type": "object", "properties": {"business_id": {"type": "string"}}, "required": ["business_id"]}},
    {"name": "decide", "description": "Record the owner's decision on one suggestion and run the chain (broker, Yext, learn). Only after the owner said so.",
     "input_schema": {"type": "object", "properties": {
         "suggestion_id": {"type": "string"}, "action": {"type": "string", "enum": ["approve", "edit", "decline"]},
         "edited_hours": {"description": "for edit: the string closed, or a list of {start,end} as HH:MM", "anyOf": [
             {"type": "string", "enum": ["closed"]},
             {"type": "array", "items": {"type": "object", "properties": {"start": {"type": "string"}, "end": {"type": "string"}}, "required": ["start", "end"]}}]}},
         "required": ["suggestion_id", "action"]}},
    {"name": "set_standing_permission", "description": "Remember that the owner wants this change made every year (true) or not (false).",
     "input_schema": {"type": "object", "properties": {"suggestion_id": {"type": "string"}, "enabled": {"type": "boolean"}},
                      "required": ["suggestion_id", "enabled"]}},
]


class Turn:
    """Collects what the tools did during one chat turn."""
    def __init__(self, bid, sess):
        self.bid, self.sess, self.actions, self.last_decide = bid, sess, [], None

    async def run(self, name, args):
        if name == "get_feed":
            return {"suggestions": [{k: i.get(k) for k in ("id", "kind", "title_en", "text_en", "proposed", "last_year", "status")}
                                    for i in F.get_feed(self.bid).get("suggestions", [])]}
        if name == "decide":
            r = await A.decide(self.bid, str(args.get("suggestion_id", "")), str(args.get("action", "")), args.get("edited_hours"))
            if r.get("ok"):
                self.last_decide = r
                self.actions.append({"type": "decided", "suggestion_id": r["suggestion_id"], "action": r["action"], "status": r.get("status")})
                self.sess["followup"] = r["suggestion_id"] if r.get("follow_up_question") else None
                self.sess["focus"] = None
            return r
        if name == "set_standing_permission":
            sid = str(args.get("suggestion_id", "")) or self.sess.get("followup") or ""
            r = await A.set_standing_permission(self.bid, sid, bool(args.get("enabled")))
            if r.get("ok"):
                self.actions.append({"type": "standing", "suggestion_id": sid, "enabled": bool(args.get("enabled"))})
                self.sess["followup"] = None
            return r
        return {"ok": False, "error": "unknown tool"}


async def _create(client, **kw):
    try:
        return await client.messages.create(**kw, thinking={"type": "between_tools"}, output_config={"effort": "low"})
    except Exception as e:  # noqa: BLE001
        if type(e).__name__ not in ("BadRequestError", "TypeError"):
            raise
        return await client.messages.create(**kw)


async def llm_reply(biz, items, sess, message, lang, turn: Turn) -> str:
    import anthropic
    client = anthropic.AsyncAnthropic(max_retries=1, timeout=30.0)
    msgs = [{"role": r, "content": t} for r, t in sess["hist"][-12:]] + [{"role": "user", "content": message}]
    system = build_system(biz, items, sess, lang)
    text = ""
    for _ in range(MAX_STEPS):
        resp = await _create(client, model=MODEL, max_tokens=500, system=system, tools=TOOLS, messages=msgs)
        calls = [b for b in resp.content if b.type == "tool_use"]
        text = "".join(b.text for b in resp.content if b.type == "text").strip() or text
        if not calls:
            break
        msgs.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) if hasattr(b, "model_dump") else b for b in resp.content]})
        res = []
        for c in calls:
            out = await turn.run(c.name, dict(c.input or {}))
            res.append({"type": "tool_result", "tool_use_id": c.id, "content": json.dumps(out, ensure_ascii=False)})
        msgs.append({"role": "user", "content": res})
    if not text:
        raise RuntimeError("empty reply")
    return text


async def fallback_reply(items, sess, message, lang, turn: Turn) -> str:
    M = FI if lang == "fi" else EN
    p = P.parse(message)
    fu = sess.get("followup")
    if fu and p and p["action"] in ("approve", "decline"):
        yes = p["action"] == "approve"
        await turn.run("set_standing_permission", {"suggestion_id": fu, "enabled": yes})
        nxt = focus_of(F.get_feed(turn.bid)["suggestions"], sess)
        return M["perm_yes" if yes else "perm_no"] + (f" Next: {nxt['title_en']}." if nxt and lang != "fi" else "")
    f = focus_of(items, sess)
    if p is None:
        return M["again"]
    if p["action"] == "change":
        return M["which"]
    if f is None:
        return M["nothing"]
    args = {"suggestion_id": f["id"], "action": p["action"], "edited_hours": p.get("edited")}
    r = await turn.run("decide", args)
    if not r.get("ok"):
        return M["error"]
    if p["action"] == "decline":
        return M["declined"]
    what = f"{f.get('holiday_name_en') or f['title_en']} {r.get('final_hours')}"
    return (M["saved"].format(what=what) + " " + (r.get("follow_up_question") or "")).strip()


async def respond(bid: str, sess: dict, message: str) -> tuple[str, list]:
    from .. import store
    biz = store.get_business(bid)
    lang = "fi" if biz and getattr(biz, "owner_language", "en") == "fi" else "en"
    items = F.get_feed(bid).get("suggestions", [])
    turn = Turn(bid, sess)
    reply = None
    if os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("KAIKU_CHAT_NO_LLM"):
        try:
            reply = await llm_reply(biz, items, sess, message, lang, turn)
            if turn.last_decide and turn.last_decide.get("follow_up_question") and turn.last_decide["follow_up_question"] not in reply:
                reply = reply.rstrip() + " " + turn.last_decide["follow_up_question"]
        except Exception as exc:
            log.warning("chat LLM failed (%s), using the fallback parser", type(exc).__name__)
            reply = None
            if turn.actions:  # the LLM already acted: never repeat a decision, just report it
                reply = EN["saved"].format(what="that") + " " + ((turn.last_decide or {}).get("follow_up_question") or "")
    if reply is None:
        reply = await fallback_reply(items, sess, message, lang, turn)
    q = (turn.last_decide or {}).get("follow_up_question")
    if q and q in reply:  # the one follow-up is never trimmed away
        body = trim_words(reply.replace(q, "").strip(), max(8, MAX_WORDS - len(q.split())))
        return (body + " " + q).strip(), turn.actions
    return trim_words(reply), turn.actions
