#!/usr/bin/env python3
"""Redacted diagnostics for Hermes -> Codex -> AnyRouter routing."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
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
    r"(github_pat_[A-Za-z0-9_]+)|"
    r"(sk-[A-Za-z0-9_-]{8})[A-Za-z0-9_-]+|"
    r"((?:api[_-]?key|token|secret|password|authorization|access_token|refresh_token|id_token|jwt|bearer)"
    r"(?:\"?\s*[:=]\s*\"?))([^\"'\s,}]+)",
    re.IGNORECASE,
)

NOISE_PATTERNS = (
    "state db discrepancy during find_thread_path_by_id_str_in_subdir",
    "failed to unwatch",
    "codex_file_watcher",
)


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""


CHECKS: list[Check] = []


def redact(value: object) -> str:
    text = str(value)

    def repl(match: re.Match[str]) -> str:
        if match.group(1):
            return "github_pat_<redacted>"
        if match.group(2):
            return f"{match.group(2)}...<redacted>"
        return f"{match.group(3)}<redacted>"

    text = SECRET_RE.sub(repl, text)
    text = re.sub(r"(?i)(authorization:\s*bearer\s+)[^\s]+", r"\1<redacted>", text)
    return text


def record(name: str, status: str, detail: object = "") -> None:
    CHECKS.append(Check(name=name, status=status, detail=redact(detail)))


def print_section(title: str) -> None:
    print(f"\n## {title}")


def print_kv(key: str, value: object) -> None:
    print(f"{key}: {redact(value)}")


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


def hermes_repo_path() -> Path | None:
    candidates = [
        Path.cwd(),
        Path("/usr/local/lib/hermes-agent"),
        Path.home() / "hermes-agent",
    ]
    for path in candidates:
        if (path / "hermes_cli" / "runtime_provider.py").exists():
            return path
    return None


def summarize_config(args: argparse.Namespace) -> tuple[str, str, str]:
    codex_home = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
    hermes_home = Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()

    codex_cfg = load_toml(codex_home / "config.toml")
    hermes_cfg = load_yaml(hermes_home / "config.yaml")

    print_section("Codex config")
    print_kv("path", codex_home / "config.toml")
    if "_error" in codex_cfg:
        print_kv("error", codex_cfg["_error"])
        record("Codex config parse", "FAIL", codex_cfg["_error"])

    codex_model = str(codex_cfg.get("model", "") or "")
    provider_name = str(codex_cfg.get("model_provider", "") or "")
    preferred_auth = str(codex_cfg.get("preferred_auth_method", "") or "")
    providers = codex_cfg.get("model_providers", {}) or {}
    provider_cfg = providers.get(provider_name, {}) if isinstance(providers, dict) else {}
    base_url = str(provider_cfg.get("base_url", "") or "").rstrip("/")
    wire_api = str(provider_cfg.get("wire_api", "") or "")
    looks_like_anyrouter = (
        provider_name.lower() == "anyrouter"
        and "anyrouter" in base_url.lower()
        and preferred_auth.lower() == "apikey"
    )

    print_kv("model", codex_model)
    print_kv("model_provider", provider_name)
    print_kv("preferred_auth_method", preferred_auth)
    print_kv("provider.base_url", base_url)
    print_kv("provider.wire_api", wire_api)
    print_kv("looks_like_anyrouter_apikey", looks_like_anyrouter)
    record(
        "Codex config uses AnyRouter API-key mode",
        "PASS" if looks_like_anyrouter else "FAIL",
        f"model_provider={provider_name}, base_url={base_url}, preferred_auth_method={preferred_auth}",
    )
    record(
        "Codex provider wire_api is responses",
        "PASS" if wire_api.lower() == "responses" else "WARN",
        wire_api or "missing",
    )

    print_section("Hermes config")
    print_kv("path", hermes_home / "config.yaml")
    if "_error" in hermes_cfg:
        print_kv("error", hermes_cfg["_error"])
        record("Hermes config parse", "FAIL", hermes_cfg["_error"])

    model_cfg = hermes_cfg.get("model", {}) if isinstance(hermes_cfg, dict) else {}
    hermes_provider = str(model_cfg.get("provider", "") or "")
    hermes_model = str(model_cfg.get("default", "") or model_cfg.get("model", "") or "")
    print_kv("model.default", hermes_model)
    print_kv("model.provider", hermes_provider)
    print_kv("model.api_mode", model_cfg.get("api_mode", ""))
    print_kv("model.openai_runtime", model_cfg.get("openai_runtime", ""))

    named = {}
    if isinstance(hermes_cfg, dict):
        providers_cfg = hermes_cfg.get("providers", {}) or {}
        if isinstance(providers_cfg, dict):
            named = providers_cfg.get(hermes_provider, {}) or {}
    if named:
        print_kv("providers.<provider>.base_url", named.get("base_url", ""))
        print_kv("providers.<provider>.api_mode", named.get("api_mode", ""))
        print_kv("providers.<provider>.default_model", named.get("default_model", ""))

    expected_provider = args.provider
    record(
        f"Hermes provider is {expected_provider}",
        "PASS" if hermes_provider.lower() == expected_provider.lower() else "WARN",
        hermes_provider or "missing",
    )

    model = args.model or codex_model or hermes_model or "gpt-5.5"
    resolved_base_url = args.base_url or base_url or str(named.get("base_url", "") or "") or "https://anyrouter.top/v1"
    return resolved_base_url.rstrip("/"), model, expected_provider


def check_runtime_resolution(provider: str) -> None:
    print_section("Hermes runtime resolution")
    repo = hermes_repo_path()
    if repo and str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    try:
        from hermes_cli.runtime_provider import resolve_runtime_provider

        result = resolve_runtime_provider(requested=provider)
    except Exception as exc:
        print_kv("error", f"{type(exc).__name__}: {exc}")
        record("Runtime resolver import/execution", "WARN", exc)
        return

    for key in ("provider", "model", "base_url", "api_mode", "source", "credential_source"):
        print_kv(key, result.get(key))
    api_mode = result.get("api_mode")
    record(
        "Runtime resolves to codex_app_server",
        "PASS" if api_mode == "codex_app_server" else "FAIL",
        api_mode or "missing",
    )


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
        record("AnyRouter /models contains target model", "SKIP", "missing Codex OPENAI_API_KEY")
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
            has_model = model in ids
            print_kv("status", resp.status)
            print_kv("models_count", len(ids))
            print_kv(f"has_{model}", has_model)
            print_kv("gpt_models", [item for item in ids if "gpt" in str(item).lower()])
            record(
                f"AnyRouter /models contains {model}",
                "PASS" if resp.status == 200 and has_model else "FAIL",
                f"status={resp.status}, models_count={len(ids)}",
            )
    except urllib.error.HTTPError as exc:
        body = exc.read(1000).decode("utf-8", "replace")
        print_kv("status", exc.code)
        print(redact(body))
        record(f"AnyRouter /models contains {model}", "FAIL", f"HTTP {exc.code}: {body}")
    except Exception as exc:
        print_kv("error", f"{type(exc).__name__}: {exc}")
        record(f"AnyRouter /models contains {model}", "FAIL", exc)


def clean_output(output: str) -> str:
    lines = []
    for line in output.splitlines():
        if any(pattern in line for pattern in NOISE_PATTERNS):
            continue
        lines.append(line.rstrip())
    text = "\n".join(line for line in lines if line.strip())
    if len(text) > 2400:
        text = "...<output truncated>...\n" + text[-2400:]
    return text or "<no output>"


def run_probe(label: str, command: list[str], timeout: int, success_needle: str = "OK") -> None:
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
        record(label, "SKIP", "command not found")
        return
    except subprocess.TimeoutExpired:
        print_kv("result", f"timeout after {timeout}s")
        record(label, "FAIL", f"timeout after {timeout}s")
        return

    output = clean_output(redact(proc.stdout.strip()))
    contains = success_needle in output
    print_kv("exit_code", proc.returncode)
    print_kv(f"contains_{success_needle}", contains)
    print("output_excerpt:")
    print(output)
    record(
        label,
        "PASS" if proc.returncode == 0 and contains else "FAIL",
        f"exit_code={proc.returncode}, contains_{success_needle}={contains}",
    )


def read_gateway_state() -> None:
    print_section("Gateway status")
    active = run_simple(["systemctl", "is-active", "hermes-gateway.service"])
    show = run_simple(
        [
            "systemctl",
            "show",
            "hermes-gateway.service",
            "-p",
            "ActiveState",
            "-p",
            "SubState",
            "-p",
            "ExecMainPID",
            "--no-pager",
        ]
    )
    if active is not None:
        print_kv("systemctl.is-active", active.strip())
    if show is not None:
        print(show.strip())

    gateway_path = Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser() / "gateway_state.json"
    if gateway_path.exists():
        try:
            data = json.loads(gateway_path.read_text())
            platforms = data.get("platforms", {})
            compact = {
                "gateway_state": data.get("gateway_state"),
                "pid": data.get("pid"),
                "platforms": {
                    name: {
                        "state": details.get("state"),
                        "error_code": details.get("error_code"),
                        "error_message": details.get("error_message"),
                        "updated_at": details.get("updated_at"),
                    }
                    for name, details in platforms.items()
                    if isinstance(details, dict)
                },
                "updated_at": data.get("updated_at"),
            }
            print_kv("gateway_state_path", gateway_path)
            print(json.dumps(compact, ensure_ascii=False, indent=2))
            telegram_state = compact["platforms"].get("telegram", {}).get("state")
            record(
                "Gateway Telegram connected",
                "PASS" if telegram_state == "connected" else "WARN",
                telegram_state or "missing",
            )
        except Exception as exc:
            print_kv("gateway_state_error", f"{type(exc).__name__}: {exc}")
            record("Gateway state readable", "WARN", exc)
    else:
        print_kv("gateway_state_path", f"{gateway_path} missing")
        record("Gateway state readable", "WARN", "missing gateway_state.json")

    if active is not None:
        record(
            "hermes-gateway.service active",
            "PASS" if active.strip() == "active" else "WARN",
            active.strip(),
        )


def run_simple(command: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=10,
            check=False,
        )
    except Exception:
        return None
    return redact(proc.stdout)


def print_summary() -> int:
    print_section("Summary")
    rank = {"FAIL": 3, "WARN": 2, "SKIP": 1, "PASS": 0}
    for check in sorted(CHECKS, key=lambda item: rank.get(item.status, 9), reverse=True):
        detail = f" - {check.detail}" if check.detail else ""
        print(f"{check.status:<5} {check.name}{detail}")
    return 1 if any(check.status == "FAIL" for check in CHECKS) else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Run live probes that call upstream services.")
    parser.add_argument("--gateway", action="store_true", help="Read gateway service and state status.")
    parser.add_argument("--timeout", type=int, default=240, help="Timeout for live command probes.")
    parser.add_argument("--provider", default="codex-anyrouter", help="Hermes provider to validate.")
    parser.add_argument("--model", default="", help="Model to validate. Defaults to Codex/Hermes config.")
    parser.add_argument("--base-url", default="", help="AnyRouter base URL. Defaults to config.")
    parser.add_argument("--skip-models", action="store_true", help="Skip live /models probe.")
    parser.add_argument("--skip-codex", action="store_true", help="Skip live Codex CLI probe.")
    parser.add_argument("--skip-hermes", action="store_true", help="Skip live Hermes CLI probe.")
    args = parser.parse_args()

    base_url, model, provider = summarize_config(args)
    check_runtime_resolution(provider)

    if args.live:
        if not args.skip_models:
            probe_models(base_url, model, min(args.timeout, 60))
        if not args.skip_codex:
            run_probe(
                "Codex CLI returned OK",
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
        if not args.skip_hermes:
            run_probe(
                "Hermes returned OK via codex-anyrouter",
                [
                    "hermes",
                    "chat",
                    "-q",
                    "只回复 OK，不要解释。",
                    "--provider",
                    provider,
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
    else:
        print("\nRun with --live to call AnyRouter, Codex CLI, and Hermes CLI.")

    if args.gateway:
        read_gateway_state()

    return print_summary()


if __name__ == "__main__":
    raise SystemExit(main())
