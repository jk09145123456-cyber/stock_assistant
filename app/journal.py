"""16장 행동 기록 - 시스템 판단 vs 사용자의 실제 행동을 기록해 나중에 비교."""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

JOURNAL_PATH = Path(__file__).resolve().parent.parent / "data" / "action_journal.csv"
FIELDS = ["date", "symbol", "name", "system_decision", "user_action", "user_note", "price_at_entry"]


def append_entry(symbol: str, name: str, system_decision: str, user_action: str, user_note: str, price: float | None) -> None:
    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    is_new = not JOURNAL_PATH.exists()
    with open(JOURNAL_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow({
            "date": dt.date.today().isoformat(),
            "symbol": symbol,
            "name": name,
            "system_decision": system_decision,
            "user_action": user_action,
            "user_note": user_note,
            "price_at_entry": price if price is not None else "",
        })


def load_entries() -> list[dict]:
    if not JOURNAL_PATH.exists():
        return []
    with open(JOURNAL_PATH, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
