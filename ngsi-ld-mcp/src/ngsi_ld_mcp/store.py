"""Proposal state in one small JSON file (atomic writes), so approval state survives restarts."""
from __future__ import annotations

import json
import os
import tempfile
import threading


class ProposalStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()

    def _read(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as e:
            raise RuntimeError(f"proposal file {self.path} is corrupt: {e}") from e

    def _write(self, data: dict) -> None:
        d = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        os.replace(tmp, self.path)

    def all(self) -> dict:
        with self._lock:
            return self._read()

    def get(self, pid: str) -> dict | None:
        return self.all().get(pid)

    def put(self, rec: dict) -> None:
        with self._lock:
            data = self._read()
            data[rec["proposal_id"]] = rec
            self._write(data)
