#!/usr/bin/env python3
"""Redacted diagnostics for Hermes -> Codex -> AnyRouter routing."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request

SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{8})[A-Za-z0-9_-]+|"
    r"(github_pat_[A-Za-z0-9_]+)|"
    r"((?:api[_-]?key|token|secret|password|authorization)(?:\"?\s*[:=]\s*\"?))([^\"'\s,]+)",
    re.IGNORECASE,
)


def redact(value: object) -> str:
    text = str(value)

    def repl(match: re.Match[str]) -> str:
        if match.group(1):
            return f"{match.group(1)}...<redacted>"
        if match.group(2):
            return "github_pat_<redacted>"
        return f"{match.group(3)}<redacted>"

    return SECRET_RE.sub(repl, text)


def load_toml(path: Path) -> dict:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        return {}
    except Exception as exc:
        return {"_error": f"{type(exc).__name__}: {exc}"}


def load_yaml(path: Path) -> dict:
    try:
        import yaml  # type: ignore
    except Exception:
        return {"_error": "PyYAML is not installed; cannot parse Hermes config."}
    try:
        return yaml.safe_load(path.read_text()) or {}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        return {"_error": f"{type(exc).__name__}: {exc}"}


def print_section(title: str) -> None:
    print(f"\n## {title}")


def print_kv(key: str, value: object) -> None:
    print(f"{key}: {redact(value)}")


def summarize_config() -> tuple[str, str]:
    codex_home = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
    hermes_home = Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()

    codex_cfg = load_toml(codex_home / "config.toml")
    hermes_cfg = load_yaml(hermes_home / "config.yaml")

    print_section("Codex config")
    print_kv("path", codex_home / "config.toml")
    if "_error" in codex_cfg:
        print_kv("error", codex_cfg["_error"])
    model = codex_cfg.get("model", "")
    provider_name = codex_cfg.get("model_provider", "")
    preferred_auth = codex_cfg.get("preferred_auth_method", "")
    providers = codex_cfg.get("model_providers", {}) or {}
    provider_cfg = providers.get(provider_name, {}) if isinstance(providers, dict) else {}
    base_url = str(provider_cfg.get("base_url", "")).rstrip("/")
    wire_api = provider_cfg.get("wire_api", "")
    print_kv("model", model)
    print_kv("model_provider", provider_name)
    print_kv("preferred_auth_method", preferred_auth)
    print_kv("provider.base_url", base_url)
    print_kv("provider.wire_api", wire_api)
    print_kv(
        "looks_like_anyrouter_apikey",
        provider_name == "anyrouter"
        and "anyrouter" in base_url.lower()
        and str(preferred_auth).lower() == "apikey",
    )

    print_section("Hermes config")
    print_kv("path", hermes_home / "config.yaml")
    if "_error" in hermes_cfg:
        print_kv("error", hermes_cfg["_error"])
    model_cfg = hermes_cfg.get("model", {}) if isinstance(hermes_cfg, dict) else {}
    provider = model_cfg.get("provider", "")
    hermes_model = model_cfg.get("default", "")
    print_kv("model.default", hermes_model)
    print_kv("model.provider", provider)
    print_kv("model.api_mode", model_cfg.get("api_mode", ""))
    print_kv("model.openai_runtime", model_cfg.get("openai_runtime", ""))
    named = (hermes_cfg.get("providers", {}) or {}).get(provider, {}) if isinstance(hermes_cfg, dict) else {}
    if named:
        print_kv("providers.<provider>.base_url", named.get("base_url", ""))
        print_kv("providers.<provider>.api_mode", named.get("api_mode", ""))
        print_kv("providers.<provider>.default_model", named.get("default_model", ""))

    print_section("Expected runtime")
    if str(provider).lower() == "codex-anyrouter":
        print("Hermes provider `codex-anyrouter` should resolve to `codex_app_server`.")
    else:
        print("Hermes main provider is not `codex-anyrouter`; verify whether this is intentional.")

    return base_url or "https://anyrouter.top/v1", str(model or hermes_model or "gpt-5.5")


def read_codex_api_key() -> str:
    auth_path = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser() / "auth.json"
    try:
        data = json.loads(auth_path.read_text())
    except Exception:
        return ""
    return str(data.get("OPENAI_API_KEY") or "")


def probe_models(base_url: str, model: str, timeout: int) -> None:
    print_section("Live AnyRouter /models")
    api_key = read_codex_api_key()
    if not api_key:
        print("SKIP: no OPENAI_API_KEY found in Codex auth.")
        return
    req = urllib.request.Request(
        base_url.rstrip("/") + "/models",
        headers={"Authorization": "Bearer " + api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            data = json.loads(body)
            ids = [item.get("id") for item in data.get("data", []) if isinstance(item, dict)]
            print_kv("status", resp.status)
            print_kv("models_count", len(ids))
            print_kv(f"has_{model}", model in ids)
            print_kv("gpt_models", [item for item in ids if "gpt" in str(item).lower()])
    except urllib.error.HTTPError as exc:
        print_kv("status", exc.code)
        print(redact(exc.read(1000).decode("utf-8", "replace")))
    except Exception as exc:
        print_kv("error", f"{type(exc).__name__}: {exc}")


def run_probe(label: str, command: list[str], timeout: int) -> None:
    print_section(label)
    print_kv("command", " ".join(command))
    try:
        proc = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        print("SKIP: command not found.")
        return
    except subprocess.TimeoutExpired:
        print_kv("result", f"timeout after {timeout}s")
        return
    output = redact(proc.stdout.strip())
    print_kv("exit_code", proc.returncode)
    print_kv("contains_OK", "OK" in output)
    if len(output) > 2400:
        output = "...<output truncated>...\n" + output[-2400:]
    print("output_excerpt:")
    print(output or "<no output>")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Run live probes that call upstream services.")
    parser.add_argument("--timeout", type=int, default=240, help="Timeout for live command probes.")
    args = parser.parse_args()

    base_url, model = summarize_config()

    if not args.live:
        print("\nRun with --live to call AnyRouter, Codex CLI, and Hermes CLI.")
        return 0

    probe_models(base_url, model, min(args.timeout, 60))
    run_probe(
        "Live Codex CLI",
        [
            "codex",
            "exec",
            "-C",
            "/tmp",
            "--skip-git-repo-check",
            "--ephemeral",
            "--model",
            model,
            "只回复 OK，不要解释。",
        ],
        args.timeout,
    )
    run_probe(
        "Live Hermes CLI via codex-anyrouter",
        [
            "hermes",
            "chat",
            "-q",
            "只回复 OK，不要解释。",
            "--provider",
            "codex-anyrouter",
            "-m",
            model,
            "-t",
            "",
            "-Q",
            "--max-turns",
            "1",
            "--source",
            "tool",
        ],
        args.timeout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
