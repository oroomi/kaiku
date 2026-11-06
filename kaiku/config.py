"""Settings. Loads /root/hack/kaiku/.env; never prints values."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


class Settings:
    ROOT = ROOT
    PORT = int(os.getenv("PORT", "8210"))
    DB_PATH = Path(os.getenv("KAIKU_DB", str(ROOT / "data" / "kaiku.sqlite")))
    DATA_DIR = ROOT / "data"
    BROKER_URL = os.getenv("KAIKU_BROKER_URL") or os.getenv("BROKER_URL", "http://127.0.0.1:1026")
    PUBLIC_URL = os.getenv("PUBLIC_URL", f"http://127.0.0.1:{PORT}")
    OWNER_WHATSAPP = os.getenv("OWNER_WHATSAPP", "")
    STUB_DECIDE = os.getenv("KAIKU_STUB_DECIDE", "auto")  # "wait" holds the stub decide step
    YEXT_ENTITY_ID = os.getenv("YEXT_ENTITY_ID", "SinceAI07")
    DEMO_TODAY = os.getenv("KAIKU_DEMO_TODAY", "2026-12-17")
    STEP_GAP = float(os.getenv("KAIKU_STEP_GAP", "1.0"))


settings = Settings()
