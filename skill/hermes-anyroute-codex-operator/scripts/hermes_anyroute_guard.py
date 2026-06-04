#!/usr/bin/env python3
"""Fail-fast guard for Hermes AnyRoute -> Codex app-server routing.

This script is intentionally narrow: it protects only the local
``codex-anyrouter`` alias. Other Hermes providers must remain switchable.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys


AGENT_ROOT = Path(os.environ.get("HERMES_AGENT_ROOT") or "/usr/local/lib/hermes-agent")
HERMES_HOME = Path(os.environ.get("HERMES_HOME") or "/root/.hermes")
CODEX_HOME = Path(os.environ.get("CODEX_HOME") or "/root/.codex")
HERMES_CONFIG = HERMES_HOME / "config.yaml"
CODEX_CONFIG = CODEX_HOME / "config.toml"
CODEX_AUTH = CODEX_HOME / "auth.json"
EXPECTED_BASE_URL = "https://anyrouter.top/v1"
EXPECTED_MODEL = "gpt-5.5"

sys.path.insert(0, str(AGENT_ROOT))


def fail(message: str) -> None:
    print(f"[hermes-anyroute-guard] FAIL: {message}", file=sys.stderr)
    sys.exit(75)


def require_text(path: Path, needles: list[str]) -> str:
    if not path.exists():
        fail(f"missing {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    lowered = text.lower()
    for needle in needles:
        if needle.lower() not in lowered:
            fail(f"{path} missing required marker: {needle}")
    return text


def main() -> None:
    require_text(
        HERMES_CONFIG,
        [
            "provider: codex-anyrouter",
            "codex-anyrouter:",
            f"base_url: {EXPECTED_BASE_URL}",
            "api_mode: codex_app_server",
        ],
    )
    require_text(
        CODEX_CONFIG,
        [
            'model_provider = "anyrouter"',
            'preferred_auth_method = "apikey"',
            f'base_url = "{EXPECTED_BASE_URL}"',
            'wire_api = "responses"',
        ],
    )
    if not CODEX_AUTH.exists():
        fail(f"missing {CODEX_AUTH}")
    try:
        auth = json.loads(CODEX_AUTH.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"{CODEX_AUTH} is not valid json: {exc}")
    key = str(auth.get("OPENAI_API_KEY") or "").strip()
    if not key.startswith("sk-"):
        fail(f"{CODEX_AUTH} does not contain an AnyRoute-style OPENAI_API_KEY")

    try:
        from hermes_cli.runtime_provider import resolve_runtime_provider
    except Exception as exc:
        fail(f"cannot import runtime resolver: {exc}")

    try:
        runtime = resolve_runtime_provider(
            requested="codex-anyrouter",
            target_model=EXPECTED_MODEL,
        )
    except Exception as exc:
        fail(f"cannot resolve codex-anyrouter runtime: {exc}")

    provider = str(runtime.get("provider") or "")
    api_mode = str(runtime.get("api_mode") or "")
    base_url = str(runtime.get("base_url") or "").rstrip("/")
    model = str(runtime.get("model") or EXPECTED_MODEL)
    if provider != "codex-anyrouter":
        fail(f"codex-anyrouter resolved to provider={provider!r}")
    if api_mode != "codex_app_server":
        fail(f"codex-anyrouter resolved to api_mode={api_mode!r}; expected codex_app_server")
    if base_url != EXPECTED_BASE_URL:
        fail(f"codex-anyrouter resolved to base_url={base_url!r}")
    if model and model != EXPECTED_MODEL:
        fail(f"codex-anyrouter resolved to model={model!r}; expected {EXPECTED_MODEL}")

    print("[hermes-anyroute-guard] OK: codex-anyrouter is bound to Codex app-server")


if __name__ == "__main__":
    main()
