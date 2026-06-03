#!/usr/bin/env python3
"""Operator diagnostics for Hermes -> Codex app-server -> AnyRoute."""

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

UPSTREAM_HINTS = (
    "high demand",
    "stream disconnected",
    "bad response status code 429",
    "bad response status code 503",
    "status code 429",
    "status code 503",
    "rate limit",
    "too many requests",
    "service unavailable",
    "bad gateway",
    "upstream",
    "overloaded",
)

DIRECT_SHAPE_HINTS = (
    "invalid codex request",
    "invalid_responses_request",
    "must be stream request",
    "model not found",
    "不支持所选模型",
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
        return {"_error": "PyYAML is not installed"}
    try:
        return yaml.safe_load(path.read_text()) or {}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        return {"_error": f"{type(exc).__name__}: {exc}"}


def version_tuple(text: str) -> tuple[int, ...]:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    if not match:
        return ()
    return tuple(int(part) for part in match.groups())


def run_simple(command: list[str], timeout: int = 20) -> tuple[int, str]:
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
        return 127, "command not found"
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s"
    return proc.returncode, redact(proc.stdout.strip())


def clean_output(output: str) -> str:
    lines: list[str] = []
    for line in output.splitlines():
        if any(pattern in line for pattern in NOISE_PATTERNS):
            continue
        lines.append(line.rstrip())
    text = "\n".join(line for line in lines if line.strip())
    if len(text) > 3000:
        text = "...<output truncated>...\n" + text[-3000:]
    return text or "<no output>"


def classify_live_failure(output: str) -> tuple[str, str]:
    lower = output.lower()
    if any(hint in lower for hint in UPSTREAM_HINTS):
        return "WARN", "AnyRoute/upstream instability"
    if any(hint in lower for hint in DIRECT_SHAPE_HINTS):
        return "FAIL", "direct/non-Codex request shape suspected"
    return "FAIL", "probe failed"


def inspect_codex_config(codex_home: Path) -> tuple[str, str]:
    print_section("Codex config")
    config_path = codex_home / "config.toml"
    cfg = load_toml(config_path)
    print_kv("path", config_path)
    if "_error" in cfg:
        print_kv("error", cfg["_error"])
        record("Codex config parse", "FAIL", cfg["_error"])

    model = str(cfg.get("model") or "")
    provider = str(cfg.get("model_provider") or "")
    auth_method = str(cfg.get("preferred_auth_method") or "")
    approval_policy = str(cfg.get("approval_policy") or "")
    sandbox_mode = str(cfg.get("sandbox_mode") or "")
    providers = cfg.get("model_providers", {}) or {}
    provider_cfg = providers.get(provider, {}) if isinstance(providers, dict) else {}
    base_url = str(provider_cfg.get("base_url") or "").rstrip("/")
    wire_api = str(provider_cfg.get("wire_api") or "")
    sandbox_workspace = cfg.get("sandbox_workspace_write", {}) or {}
    network_access = sandbox_workspace.get("network_access")

    for key, value in (
        ("model", model),
        ("model_provider", provider),
        ("preferred_auth_method", auth_method),
        ("approval_policy", approval_policy),
        ("sandbox_mode", sandbox_mode),
        ("sandbox_workspace_write.network_access", network_access),
        ("provider.base_url", base_url),
        ("provider.wire_api", wire_api),
    ):
        print_kv(key, value)

    record(
        "Codex uses AnyRouter API-key provider",
        "PASS" if provider == "anyrouter" and auth_method == "apikey" and "anyrouter" in base_url else "FAIL",
        f"provider={provider}, auth={auth_method}, base_url={base_url}",
    )
    record(
        "Codex wire_api is responses",
        "PASS" if wire_api == "responses" else "FAIL",
        wire_api or "missing",
    )
    record(
        "Codex approval policy is never",
        "PASS" if approval_policy == "never" else "WARN",
        approval_policy or "missing",
    )
    record(
        "Codex sandbox is danger-full-access",
        "PASS" if sandbox_mode == "danger-full-access" else "WARN",
        sandbox_mode or "missing",
    )
    record(
        "Codex workspace network access enabled",
        "PASS" if network_access is True else "WARN",
        network_access,
    )
    return base_url or "https://anyrouter.top/v1", model or "gpt-5.5"


def inspect_hermes_config(hermes_home: Path) -> tuple[str, str]:
    print_section("Hermes config")
    config_path = hermes_home / "config.yaml"
    cfg = load_yaml(config_path)
    print_kv("path", config_path)
    if "_error" in cfg:
        print_kv("error", cfg["_error"])
        record("Hermes config parse", "FAIL", cfg["_error"])

    model_cfg = cfg.get("model", {}) if isinstance(cfg, dict) else {}
    provider = str(model_cfg.get("provider") or "")
    model = str(model_cfg.get("default") or model_cfg.get("model") or "")
    context_length = model_cfg.get("context_length")
    openai_runtime = str(model_cfg.get("openai_runtime") or "")
    api_mode = str(model_cfg.get("api_mode") or "")
    providers = cfg.get("providers", {}) if isinstance(cfg, dict) else {}
    named = providers.get(provider, {}) if isinstance(providers, dict) else {}

    for key, value in (
        ("model.default", model),
        ("model.provider", provider),
        ("model.context_length", context_length),
        ("model.openai_runtime", openai_runtime),
        ("model.api_mode", api_mode),
        ("providers.<provider>.base_url", named.get("base_url", "")),
        ("providers.<provider>.api_mode", named.get("api_mode", "")),
        ("providers.<provider>.default_model", named.get("default_model", "")),
    ):
        print_kv(key, value)

    record(
        "Hermes provider is codex-anyrouter",
        "PASS" if provider == "codex-anyrouter" else "FAIL",
        provider or "missing",
    )
    record(
        "Hermes context length configured for long tasks",
        "PASS" if isinstance(context_length, int) and context_length >= 200000 else "WARN",
        context_length,
    )
    return provider or "codex-anyrouter", model or "gpt-5.5"


def inspect_codex_version() -> None:
    print_section("Codex binary")
    code, output = run_simple(["codex", "--version"], timeout=20)
    print_kv("codex --version", output)
    parsed = version_tuple(output)
    if code != 0 or not parsed:
        record("Codex CLI version readable", "FAIL", output)
        return
    record(
        "Codex CLI version >= 0.136.0",
        "PASS" if parsed >= (0, 136, 0) else "WARN",
        output,
    )


def inspect_runtime_resolution(hermes_root: Path, provider: str) -> None:
    print_section("Hermes runtime resolution")
    if str(hermes_root) not in sys.path:
        sys.path.insert(0, str(hermes_root))
    try:
        from hermes_cli.runtime_provider import resolve_runtime_provider

        result = resolve_runtime_provider(requested=provider)
    except Exception as exc:
        print_kv("error", f"{type(exc).__name__}: {exc}")
        record("Runtime resolver execution", "FAIL", exc)
        return
    for key in ("provider", "model", "base_url", "api_mode", "source"):
        print_kv(key, result.get(key))
    record(
        "Runtime resolves codex-anyrouter to codex_app_server",
        "PASS" if result.get("api_mode") == "codex_app_server" else "FAIL",
        result.get("api_mode") or "missing",
    )


def file_contains(path: Path, needles: tuple[str, ...]) -> bool:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return False
    return all(needle in text for needle in needles)


def inspect_source_fixes(hermes_root: Path) -> None:
    print_section("Hermes source fix audit")
    checks = [
        (
            "runtime_provider codex-anyrouter app-server rewrite",
            hermes_root / "hermes_cli" / "runtime_provider.py",
            ('provider_norm == "codex-anyrouter"', 'return "codex_app_server"', '":codex_app_server"'),
        ),
        (
            "background_review skips AnyRouter app-server review",
            hermes_root / "agent" / "background_review.py",
            ('_parent_api_mode == "codex_app_server"', '"codex-anyrouter"', "Skipping background review"),
        ),
        (
            "app-server session classifies AnyRouter API-key failures",
            hermes_root / "agent" / "transports" / "codex_app_server_session.py",
            ("_codex_config_uses_anyrouter_apikey", "_classify_anyrouter_provider_failure", "AnyRouter key", "right fix"),
        ),
        (
            "app-server session treats ChatGPT plugin sync separately",
            hermes_root / "agent" / "transports" / "codex_app_server_session.py",
            ("chatgpt.com/backend-api/plugins/featured", "AnyRouter key", "401 unauthorized"),
        ),
        (
            "codex_runtime uses long app-server timeout",
            hermes_root / "agent" / "codex_runtime.py",
            ("HERMES_CODEX_APPSERVER_TURN_TIMEOUT", "HERMES_AGENT_TIMEOUT", "1800"),
        ),
        (
            "codex_runtime summarizes progress on timeout",
            hermes_root / "agent" / "codex_runtime.py",
            ("_build_app_server_progress_response", "assistant progress", "未完全收尾"),
        ),
        (
            "codex_runtime auto-continues short plan finals",
            hermes_root / "agent" / "codex_runtime.py",
            ("_looks_like_incomplete_app_server_final", "_build_app_server_autocontinue_prompt", "auto-continue"),
        ),
    ]
    for name, path, needles in checks:
        ok = file_contains(path, needles)
        print_kv(name, "PASS" if ok else f"missing in {path}")
        record(name, "PASS" if ok else "FAIL", path)


def read_codex_api_key(codex_home: Path) -> str:
    try:
        data = json.loads((codex_home / "auth.json").read_text())
    except Exception:
        return ""
    return str(data.get("OPENAI_API_KEY") or "")


def probe_models(base_url: str, model: str, codex_home: Path, timeout: int) -> None:
    print_section("Live AnyRoute /models")
    api_key = read_codex_api_key(codex_home)
    if not api_key:
        print("SKIP: no OPENAI_API_KEY in Codex auth.")
        record("AnyRoute /models contains target model", "SKIP", "missing Codex auth key")
        return
    req = urllib.request.Request(
        base_url.rstrip("/") + "/models",
        headers={"Authorization": "Bearer " + api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
            ids = [item.get("id") for item in data.get("data", []) if isinstance(item, dict)]
            print_kv("status", resp.status)
            print_kv("models_count", len(ids))
            print_kv(f"has_{model}", model in ids)
            print_kv("gpt_models", [item for item in ids if "gpt" in str(item).lower()])
            record(
                f"AnyRoute /models contains {model}",
                "PASS" if resp.status == 200 and model in ids else "FAIL",
                f"status={resp.status}, models_count={len(ids)}",
            )
    except urllib.error.HTTPError as exc:
        body = exc.read(1000).decode("utf-8", "replace")
        print_kv("status", exc.code)
        print(redact(body))
        status, reason = classify_live_failure(body)
        record(f"AnyRoute /models contains {model}", status, f"HTTP {exc.code}: {reason}")
    except Exception as exc:
        print_kv("error", f"{type(exc).__name__}: {exc}")
        record(f"AnyRoute /models contains {model}", "WARN", exc)


def run_probe(label: str, command: list[str], sentinel: str, timeout: int) -> None:
    print_section(label)
    print_kv("command", " ".join(command))
    code, output = run_simple(command, timeout=timeout)
    output = clean_output(output)
    contains = sentinel in output
    print_kv("exit_code", code)
    print_kv(f"contains_{sentinel}", contains)
    print("output_excerpt:")
    print(output)
    if code == 0 and contains:
        record(label, "PASS", f"exit_code={code}")
        return
    status, reason = classify_live_failure(output)
    record(label, status, f"{reason}; exit_code={code}; contains_{sentinel}={contains}")


def inspect_gateway(hermes_home: Path) -> None:
    print_section("Gateway status")
    code, active = run_simple(["systemctl", "is-active", "hermes-gateway.service"], timeout=10)
    print_kv("systemctl.is-active", active)
    record("hermes-gateway.service active", "PASS" if code == 0 and active == "active" else "WARN", active)
    code, show = run_simple(
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
        ],
        timeout=10,
    )
    if show:
        print(show)
    state_path = hermes_home / "gateway_state.json"
    try:
        data = json.loads(state_path.read_text())
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
        print(json.dumps(compact, ensure_ascii=False, indent=2))
        telegram = compact["platforms"].get("telegram", {}).get("state")
        record("Gateway Telegram connected", "PASS" if telegram == "connected" else "WARN", telegram or "missing")
    except Exception as exc:
        print_kv("gateway_state_error", f"{type(exc).__name__}: {exc}")
        record("Gateway state readable", "WARN", exc)


def print_summary() -> int:
    print_section("Summary")
    rank = {"FAIL": 3, "WARN": 2, "SKIP": 1, "PASS": 0}
    for check in sorted(CHECKS, key=lambda item: rank.get(item.status, 9), reverse=True):
        detail = f" - {check.detail}" if check.detail else ""
        print(f"{check.status:<5} {check.name}{detail}")
    return 1 if any(check.status == "FAIL" for check in CHECKS) else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Run live AnyRoute/Codex/Hermes probes.")
    parser.add_argument("--gateway", action="store_true", help="Read gateway service and state.")
    parser.add_argument("--tool-live", action="store_true", help="Run live Hermes terminal/network probe.")
    parser.add_argument("--timeout", type=int, default=240, help="Timeout for live command probes.")
    parser.add_argument("--hermes-root", default="/usr/local/lib/hermes-agent")
    parser.add_argument("--hermes-home", default=os.environ.get("HERMES_HOME", "~/.hermes"))
    parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME", "~/.codex"))
    parser.add_argument("--model", default="")
    args = parser.parse_args()

    hermes_root = Path(args.hermes_root).expanduser()
    hermes_home = Path(args.hermes_home).expanduser()
    codex_home = Path(args.codex_home).expanduser()

    base_url, codex_model = inspect_codex_config(codex_home)
    provider, hermes_model = inspect_hermes_config(hermes_home)
    model = args.model or codex_model or hermes_model or "gpt-5.5"
    inspect_codex_version()
    inspect_runtime_resolution(hermes_root, provider)
    inspect_source_fixes(hermes_root)

    if args.live:
        probe_models(base_url, model, codex_home, timeout=min(args.timeout, 60))
        run_probe(
            "Codex CLI direct AnyRoute probe",
            [
                "codex",
                "exec",
                "-C",
                "/tmp",
                "--skip-git-repo-check",
                "--model",
                model,
                "只回复 PING_OK",
            ],
            "PING_OK",
            args.timeout,
        )
        run_probe(
            "Hermes codex-anyrouter bridge probe",
            [
                "hermes",
                "chat",
                "-q",
                "只回复 APP_SERVER_PATCH_OK",
                "--provider",
                "codex-anyrouter",
                "--model",
                model,
                "--toolsets",
                "",
                "--quiet",
            ],
            "APP_SERVER_PATCH_OK",
            args.timeout,
        )
    else:
        print("\nRun with --live to call AnyRoute, Codex CLI, and Hermes CLI.")

    if args.tool_live:
        run_probe(
            "Hermes tool/network probe",
            [
                "hermes",
                "chat",
                "-q",
                "请用终端运行 curl -I -s https://github.com，只回复 HTTP 首行。",
                "--provider",
                "codex-anyrouter",
                "--model",
                model,
                "--quiet",
            ],
            "HTTP/",
            args.timeout,
        )

    if args.gateway:
        inspect_gateway(hermes_home)

    return print_summary()


if __name__ == "__main__":
    raise SystemExit(main())
