"""Shared standard-library helpers for the teaching examples."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def report(status: str, checks: list[dict[str, Any]], reasons: list[str], evidence: dict[str, Any], provenance: dict[str, Any], limitations: list[str] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "integrity-report-v1",
        "status": status,
        "checks": checks,
        "reasons": reasons,
        "evidence": evidence,
        "provenance": provenance,
        "limitations": limitations or [],
    }


def check(name: str, status: str, evidence: dict[str, Any] | None = None, reason: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"name": name, "status": status, "evidence": evidence or {}}
    if reason:
        item["reason"] = reason
    return item


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_expected(result: dict[str, Any], expected: dict[str, Any]) -> None:
    for key, value in expected.items():
        if key == "integrity":
            assert result["integrity"]["status"] == value["status"]
            assert result["integrity"]["reasons"] == value["reasons"]
        else:
            assert result[key] == value, (key, result[key], value)
