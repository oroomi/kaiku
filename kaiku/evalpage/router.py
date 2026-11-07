"""/eval: judge-facing quality page. Upload a CSV/JSON dataset, see what Kaiku would suggest, row by row.
Uploads are parsed in memory only; the network is never used; nothing is sent to anyone."""
from __future__ import annotations

import asyncio
import json
import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from kaiku.evalpage import loader, runner

router = APIRouter()
_sem = asyncio.Semaphore(2)


def _err(msg, headers=None, mapping=None, status=400):
    return JSONResponse({"ok": False, "error": msg, "headers": headers or [], "mapping": mapping or {},
                         "fields": loader.FIELD_HELP}, status_code=status)


@router.get("/eval", response_class=HTMLResponse)
def eval_page(request: Request):
    from kaiku.app import render
    sample = runner.sample_result()
    return render(request, "eval.html", sample_json=json.dumps(sample, ensure_ascii=False).replace("</", "<\\/"),
                  always_answer=os.environ.get("KAIKU_EVAL_ALWAYS_ANSWER") == "1", ask_below=runner.ASK_BELOW,
                  fields=loader.FIELD_HELP)


@router.get("/api/eval/sample")
def eval_sample():
    return runner.sample_result()


@router.post("/api/eval/run")
async def eval_run(request: Request):
    try:
        ctype = request.headers.get("content-type", "")
        if "multipart/form-data" not in ctype:
            return _err("Send the dataset as a multipart upload with the field name 'file'.")
        try:
            declared = int(request.headers.get("content-length") or 0)
        except ValueError:
            declared = 0
        if declared > loader.MAX_BYTES + 64 * 1024:
            return _err("The file is larger than 2 MB. Send a smaller sample (500 rows at most).")
        form = await request.form()
        up = form.get("file")
        if up is None or not hasattr(up, "read"):
            return _err("No file in the upload. Choose a CSV or JSON file.")
        raw = await up.read(loader.MAX_BYTES + 1)
        override = None
        if form.get("mapping"):
            try:
                override = json.loads(str(form.get("mapping")))
                if not isinstance(override, dict):
                    raise ValueError
            except ValueError:
                return _err("The column mapping was not valid JSON.")
        try:
            cases, info = loader.parse(raw, getattr(up, "filename", "") or "", override)
        except loader.LoadError as e:
            return _err(str(e), e.headers, e.mapping)
        async with _sem:
            try:
                rows, summary = await asyncio.to_thread(runner.run_cases, cases)
            except runner.TooSlow as e:
                return _err(str(e))
        return {"ok": True, "rows": rows, "summary": summary, "kind": info["kind"], "headers": info.get("headers", []),
                "mapping": info.get("mapping", {}), "fields": loader.FIELD_HELP, "note": info.get("note"),
                "label": f"Your file: {getattr(up, 'filename', '') or 'upload'} (parsed in memory, not stored)."}
    except Exception as e:  # noqa: BLE001  the page never answers 500
        return _err(f"Something unexpected went wrong reading this file ({type(e).__name__}). Check it is plain CSV or JSON.")
