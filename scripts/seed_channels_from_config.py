"""
One-time seed: copy channel list from config.json into the channels table.
Run from project root (with venv activated):
  PYTHONPATH=. python -m scripts.seed_channels_from_config
Only inserts if the channels table is empty (idempotent for fresh DB).
"""

import json
import sys
from pathlib import Path

# Project root on PYTHONPATH
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from app.core.database import SessionLocal
from app.models import Channel


def main() -> None:
    config_path = root / "config.json"
    if not config_path.exists():
        print("config.json not found; skipping seed")
        return
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    usernames = data.get("channels", [])
    if not usernames:
        print("No 'channels' in config.json; skipping seed")
        return
    message_limit = int(data.get("message_limit_per_channel", 10))
    only_unread = bool(data.get("only_unread", False))

    db = SessionLocal()
    try:
        existing = db.query(Channel).count()
        if existing > 0:
            print(f"Channels table already has {existing} row(s); skipping seed")
            return
        for idx, username in enumerate(usernames):
            ch = Channel(
                username=username.strip(),
                display_name=None,
                message_limit=message_limit,
                only_unread=only_unread,
                sort_order=idx,
            )
            db.add(ch)
        db.commit()
        print(f"Seeded {len(usernames)} channels from config.json")
    finally:
        db.close()


if __name__ == "__main__":
    main()
