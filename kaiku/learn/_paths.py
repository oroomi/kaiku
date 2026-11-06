"""Data dir rule shared by timetravel and prefs: env KAIKU_DATA_DIR, default <repo>/data."""
import json
import os
import tempfile
from pathlib import Path


def data_dir() -> Path:
    d = os.environ.get("KAIKU_DATA_DIR")
    p = Path(d) if d else Path(__file__).resolve().parents[2] / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json_atomic(path: Path, obj) -> None:
    """Write to a temp file in the same dir, then rename: readers never see a half file."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
