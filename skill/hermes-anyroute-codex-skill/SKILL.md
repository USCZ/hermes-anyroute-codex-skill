---
name: hermes-anyroute-codex-skill
description: 诊断 Hermes 经 Codex 使用 AnyRouter 的链路。
---

# Hermes AnyRoute Codex

Use this skill when the user needs to set up, verify, or debug a VPS chain where Hermes Agent uses local Codex CLI/app-server to reach AnyRoute/AnyRouter.

## Target Chain

Treat this as the intended architecture unless the user explicitly says otherwise:

```text
Telegram or Hermes CLI
  -> Hermes Agent
  -> provider `codex-anyrouter`
  -> runtime `codex_app_server`
  -> local `codex app-server`
  -> ~/.codex/config.toml + ~/.codex/auth.json
  -> AnyRouter /v1
  -> gpt-5.5
```

The important distinction: Hermes should delegate the turn to Codex. Do not call the setup healthy if Hermes is still sending direct Responses requests to AnyRouter.

## Required Checks

Run checks in this order with `terminal`; redact secrets in any pasted output.

1. Read-only configuration check:

```bash
python3 skill/hermes-anyroute-codex-skill/scripts/check_anyroute_codex.py
```

Expected:
- Codex has `model_provider = "anyrouter"`.
- Codex provider base URL is `https://anyrouter.top/v1`.
- Codex `wire_api` is `responses`.
- Hermes main provider is `codex-anyrouter`.
- Hermes runtime resolution reports `api_mode: codex_app_server`.

2. Live smoke test:

```bash
python3 skill/hermes-anyroute-codex-skill/scripts/check_anyroute_codex.py --live
```

Do not claim end-to-end model health until these pass:
- AnyRouter `/models` returns HTTP 200 and contains the model.
- `codex exec ... '只回复 OK'` returns OK.
- `hermes chat --provider codex-anyrouter ...` returns OK.

3. Gateway status, if the user cares about Telegram/API delivery:

```bash
python3 skill/hermes-anyroute-codex-skill/scripts/check_anyroute_codex.py --gateway
```

Gateway connected only proves transport status. It does not prove the model path. Sending a Telegram message is an external side effect; only do it when the user asked for that live delivery test.

## Manual Probes

Codex layer:

```bash
codex exec -C /tmp --skip-git-repo-check --ephemeral --model gpt-5.5 '只回复 OK，不要解释。'
```

Hermes bridge layer:

```bash
hermes chat -q '只回复 OK，不要解释。' \
  --provider codex-anyrouter \
  -m gpt-5.5 \
  -t '' \
  -Q \
  --max-turns 1 \
  --source tool
```

Runtime resolver:

```bash
python3 - <<'PY'
from hermes_cli.runtime_provider import resolve_runtime_provider
res = resolve_runtime_provider(requested="codex-anyrouter")
for key in ("provider", "model", "base_url", "api_mode", "source"):
    print(f"{key}: {res.get(key)}")
PY
```

## Failure Routing

Use `references/error-map.md` when classifying logs. Common decisions:

- Codex succeeds but Hermes fails: inspect runtime resolution first.
- Hermes says `invalid codex request` or `invalid_responses_request`: likely direct Hermes -> AnyRouter Responses path, not the Codex bridge.
- `429`, `503`, `high demand`, or `stream disconnected`: AnyRouter/upstream congestion, not a Codex login failure.
- ChatGPT plugin sync 401 while the model answer succeeds: non-fatal Codex API-key mode warning.
- Auxiliary `openai-codex` errors: title/compression/memory/review path; keep separate from the main `codex-anyrouter` path.

## Setup Reference

Read `references/setup-blueprint.md` when rebuilding or explaining the architecture. Keep the user-facing README in the repository root for installation and diagrams; keep this SKILL.md focused on execution.

## Safety Rules

- Never print API keys, GitHub tokens, Telegram tokens, OAuth tokens, cookies, or raw `Authorization` headers.
- Do not edit `~/.hermes/config.yaml` without first making a timestamped backup.
- If a runtime switch fails, restore the previous config before ending.
- Do not push secrets into GitHub. Use placeholders in docs and examples.
