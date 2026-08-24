"""YAML 설정 로더. config/*.yaml -> dict."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load(name: str) -> dict:
    path = CONFIG_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass
class Settings:
    portfolio: dict
    risk: dict
    strategy: dict
    backtest: dict

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            portfolio=_load("portfolio.yaml"),
            risk=_load("risk_rules.yaml"),
            strategy=_load("strategy_rules.yaml"),
            backtest=_load("backtest.yaml"),
        )


def get_settings() -> Settings:
    return Settings.load()
