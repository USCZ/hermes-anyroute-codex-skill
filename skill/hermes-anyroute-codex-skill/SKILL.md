---
name: hermes-anyroute-codex-skill
description: 诊断 Hermes 经 Codex 使用 AnyRouter 的链路.
---

# Hermes AnyRoute Codex Skill

Use this skill when the user wants Hermes Agent on a VPS to call AnyRoute/AnyRouter through the local Codex CLI or Codex app-server runtime, especially when Telegram, Hermes CLI, Codex CLI, and direct AnyRouter probes disagree.

## Core Chain

Treat this as the target chain unless the user proves a different bridge exists:

```text
Telegram or Hermes CLI
  -> Hermes Agent provider `codex-anyrouter`
  -> Hermes `codex_app_server` runtime
  -> local `codex` CLI using `~/.codex/config.toml`
  -> AnyRouter `/v1` with model `gpt-5.5`
```

Do not describe the chain as working until a live Hermes smoke test succeeds through `codex-anyrouter` or the exact runtime/provider the user will use.

## Fast Triage

1. Use `terminal` to inspect configs with secret redaction.
   - Codex: `~/.codex/config.toml` should show `model_provider = "anyrouter"`, an AnyRouter base URL, and `wire_api = "responses"`.
   - Hermes: `~/.hermes/config.yaml` should use provider `codex-anyrouter` for the main model.
2. Confirm Hermes runtime resolution.
   - In this Hermes build, `codex-anyrouter` must resolve to `api_mode=codex_app_server`.
   - If it resolves to direct `codex_responses`, Hermes may hit AnyRouter with an incompatible request shape.
3. Probe in order:
   - AnyRouter `/models` contains the intended model.
   - `codex exec -C /tmp --skip-git-repo-check --model gpt-5.5 '只回复 OK'` returns `OK`.
   - `hermes chat -q '只回复 OK' --provider codex-anyrouter -m gpt-5.5 -t '' -Q --max-turns 1` returns `OK`.
4. Check gateway state without sending a message unless the user explicitly asked for a Telegram smoke test.
   - Read systemd status, `~/.hermes/gateway_state.json`, and recent logs.
   - Sending Telegram messages is an external side effect; avoid it unless requested.

## Helper Script

Run the bundled checker from the repository root or skill folder:

```bash
python3 skill/hermes-anyroute-codex-skill/scripts/check_anyroute_codex.py
python3 skill/hermes-anyroute-codex-skill/scripts/check_anyroute_codex.py --live
```

The default mode is read-only and prints a redacted config summary. `--live` performs the direct `/models`, Codex CLI, and Hermes CLI smoke tests, which can consume upstream quota.

## Reference Files

- Read `references/setup-blueprint.md` when explaining or rebuilding the setup.
- Read `references/error-map.md` when classifying failures from logs or tool output.

## Safety Rules

- Never print API keys, GitHub tokens, Codex auth tokens, Telegram tokens, or raw `Authorization` headers.
- Do not leave a failed Hermes config hypothesis active. If a runtime switch fails, restore the previous config before ending.
- Treat ChatGPT plugin sync warnings from Codex API-key mode as non-fatal unless the model request itself fails.
- Keep auxiliary model failures separate from the main AnyRouter path; title generation, compression, or review forks can fail even when the main prompt succeeds.
