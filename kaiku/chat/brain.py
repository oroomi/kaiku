"""Kaiku's chat brain: Anthropic claude-sonnet-5-5 with three tools, and a deterministic fallback that never needs the API."""
from __future__ import annotations

import json
import logging
import os
import re

from . import actions as A
from . import feed as F
from . import flow
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
- Every suggestion you make carries its reason in the same breath (last year, the website, peers, the typo itself, the unanswered review), taken only from the suggestion's reason column. Never a bare "shall I change it?".
- The owner always has the last word. Never approve, edit or decline on your own. Act only on what the owner just said.
- "yes", "I agree", "approve", "ok", "do it": call decide(approve) for the suggestion under discussion. "no", "no thanks": decide(decline). A time range such as "make it 10-14", "9 to 1" (means 9-13), or "closed": decide(edit) with edited_hours as [{{"start":"10:00","end":"14:00"}}] or "closed". "Change the hours" with no hours: ask which hours.
- After decide returns ok with a follow_up_question, say in one short sentence what was saved, then ask the follow_up_question word for word. That is the ONE follow-up.
- If a follow-up is awaiting an answer: "yes" calls set_standing_permission(enabled true), "no" calls it with enabled false and you say you will ask again each time. Then name the next waiting item in a few words.
- If decide returns an error, say so plainly and nothing was changed.
- A suggestion whose status is approved, edited or applied IS saved in Connect. Never say it is not saved and never "correct" an earlier receipt; if asked, confirm what was saved.
- Items of kind no_change need nothing. Mention one only if asked, in one line: nothing to change and why.
- Items of kind description (typo fix or a drafted description) and review (a drafted reply to a review) work the same way: "yes" calls decide(approve) and the drafted text in the item is saved. If the owner suggests a change, call decide(edit) with edited_text set to the owner's exact wording (never your own rewrite). "no": decide(decline). Never say a review reply was posted unless the decide result says posted true; if it says stored, say it is stored for now.
- If the owner asks something the data does not answer, say you do not know. Stay on the business listing: opening hours, the description and review replies.

Business: {name}, {address}. Today in the demo clock: {today}.
Suggestions (id | kind | title | proposed | last year | status | reason):
{feed}
Under discussion: {focus}
Stage: {stage}
Follow-up awaiting an answer for: {followup}

Stages: "proposed" = Kaiku already showed the owner a proposal for the card under discussion; a yes applies it. "ask_new" = Kaiku asked what the value should be. "confirm" = the owner gave a value and Kaiku asked 'shall I save it?'. none = nothing was proposed yet: a bare yes decides nothing, ask which card they mean.
After a decide call returns ok, answer with the single word Done: the system adds the confirmation, the recurring question and the next card itself. Never write that something is saved, posted or live yourself."""

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
    """The card under discussion. Only an explicit focus counts (Accept, Suggest a change, a hand-off, the WhatsApp opening);
    a bare 'yes' on a chat that proposed nothing never approves a card nobody mentioned. WhatsApp sessions may fall back to
    the first waiting card because their opening listed it."""
    pend = pending_items(items)
    f = next((i for i in pend if i["id"] == sess.get("focus")), None)
    if f or sess.get("via") != "whatsapp":
        return f
    return pend[0] if pend else None


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
                         followup=f"{fu['id']} ({fu['title_en']})" if fu else "none", stage=sess.get("stage") or "none")


TOOLS = [
    {"name": "get_feed", "description": "Get the current suggestions for the business with their status.",
     "input_schema": {"type": "object", "properties": {"business_id": {"type": "string"}}, "required": ["business_id"]}},
    {"name": "decide", "description": "Record the owner's decision on one suggestion and run the chain (broker, Yext, learn). Only after the owner said so.",
     "input_schema": {"type": "object", "properties": {
         "suggestion_id": {"type": "string"}, "action": {"type": "string", "enum": ["approve", "edit", "decline"]},
         "edited_text": {"type": "string", "description": "for edit of a description or review reply: the owner's own exact text"},
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
        self.bid, self.sess, self.actions, self.last_decide, self.last_item = bid, sess, [], None, None

    async def run(self, name, args):
        if name == "get_feed":
            return {"suggestions": [{k: i.get(k) for k in ("id", "kind", "title_en", "text_en", "proposed", "last_year", "status")}
                                    for i in F.get_feed(self.bid).get("suggestions", [])]}
        if name == "decide":
            r = await A.decide(self.bid, str(args.get("suggestion_id", "")), str(args.get("action", "")), args.get("edited_hours"),
                               self.sess.get("via", "web"), edited_text=args.get("edited_text"))
            if r.get("ok"):
                self.last_decide = r
                self.last_item = F.find(self.bid, str(args.get("suggestion_id", "")))
                self.actions.append({"type": "decided", "suggestion_id": r["suggestion_id"], "action": r["action"], "status": r.get("status")})
                self.sess["followup"] = r["suggestion_id"] if r.get("follow_up_question") and r.get("yext") == "ok" else None
                self.sess["focus"] = None
            return r
        if name == "set_standing_permission":
            sid = str(args.get("suggestion_id", "")) or self.sess.get("followup") or ""
            r = await A.set_standing_permission(self.bid, sid, bool(args.get("enabled")), self.sess.get("via", "web"))
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
    """No key (or the API failed): yes / no / hours / the owner's own text against the explicit focus."""
    M = FI if lang == "fi" else EN
    p = P.parse(message)
    f = focus_of(items, sess)
    if f is not None and f["kind"] in ("description", "review") and (p is None or p["action"] in ("change", "edit")) and len(message.split()) >= 3:
        return await flow.apply_and_say(turn, turn.bid, sess, f, "edit", edited_text=message.strip())
    if p is None:
        return M["again"]
    if p["action"] == "change":
        return flow.start_change(sess, f) if f else M["which"]
    if f is None:
        return "I have not proposed anything yet. Accept a suggestion above and I will talk you through it." if lang != "fi" else M["nothing"]
    if p["action"] == "edit" and f["kind"] in ("description", "review"):
        return M["again"]
    return await flow.apply_and_say(turn, turn.bid, sess, f, p["action"], edited_hours=p.get("edited"))


async def respond(bid: str, sess: dict, message: str) -> tuple[str, list]:
    from .. import store
    biz = store.get_business(bid)
    lang = "fi" if biz and getattr(biz, "owner_language", "en") == "fi" else "en"
    items = F.get_feed(bid).get("suggestions", [])
    turn = Turn(bid, sess)
    det = await flow.handle(turn, sess, message) if lang != "fi" else None
    if det is not None:
        return det, turn.actions
    reply = None
    if os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("KAIKU_CHAT_NO_LLM"):
        try:
            reply = await llm_reply(biz, items, sess, message, lang, turn)
        except Exception as exc:
            log.warning("chat LLM failed (%s), using the fallback parser", type(exc).__name__)
            reply = None
            if turn.actions:  # the LLM already acted: never repeat a decision, just report it
                reply = "Done."
    if turn.last_decide is not None and turn.last_item is not None:   # the words after a decision are the apply result's, not the model's
        a = turn.actions[-1]["action"] if turn.actions else "approve"
        return flow.finish(bid, sess, turn.last_item, a, turn.last_decide), turn.actions
    if reply is None:
        reply = await fallback_reply(items, sess, message, lang, turn)
        if turn.last_decide is not None:
            return reply, turn.actions
    return trim_words(reply), turn.actions
