# config_store.py
from __future__ import annotations

import base64
import json
import os
import sys
import zlib
from pathlib import Path


APP_CONFIG_NAME = "wxReader.cfg"
_OBFUSCATION_KEY = b"wxrdrcfg"


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def config_path() -> Path:
    return app_dir() / APP_CONFIG_NAME


def _xor_bytes(data: bytes, key: bytes) -> bytes:
    if not key:
        return data
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def encode_payload(obj: dict) -> str:
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    raw = zlib.compress(raw, level=9)
    raw = _xor_bytes(raw, _OBFUSCATION_KEY)
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_payload(text: str) -> dict:
    raw = base64.urlsafe_b64decode(text.encode("ascii"))
    raw = _xor_bytes(raw, _OBFUSCATION_KEY)
    raw = zlib.decompress(raw)
    return json.loads(raw.decode("utf-8"))


def load_config() -> dict:
    p = config_path()
    if not p.exists():
        return {}

    try:
        content = p.read_text("utf-8").strip()
        if not content:
            return {}
        lines = [ln.strip() for ln in content.splitlines() if ln.strip() and not ln.startswith("#")]
        if not lines:
            return {}
        return decode_payload(lines[-1])
    except Exception:
        return {}


def save_config(data: dict) -> bool:
    # False if app directory isn't writable

    p = config_path()
    tmp = p.with_suffix(p.suffix + ".tmp")

    try:
        payload = encode_payload(data)
        tmp.write_text("### This is wxReader config ###\n" + payload + "\n", encoding="utf-8")
        os.replace(tmp, p)
        return True
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return False


def update_recent(recent_list: list[str], new_path: str, limit: int = 12) -> list[str]:
    new_path = str(Path(new_path).resolve())
    items = [new_path] + [p for p in recent_list if p and p != new_path]
    items = [p for p in items if Path(p).exists()]
    return items[:limit]
