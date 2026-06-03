---
name: hermes-anyroute-codex-operator
description: 维护 Hermes 经 Codex 连接 AnyRouter 的运行链路。
---

# Hermes AnyRoute Codex Operator

Use this skill when maintaining, diagnosing, or repairing the VPS production path where Hermes Agent on Telegram uses local Codex app-server to reach AnyRoute/AnyRouter `gpt-5.5`.

## Production Chain

The intended path is:

```text
Telegram
  -> Hermes Gateway
  -> Hermes Agent
  -> provider `codex-anyrouter`
  -> runtime `codex_app_server`
  -> local `codex app-server`
  -> /root/.codex/config.toml
  -> AnyRoute / AnyRouter https://anyrouter.top/v1
  -> gpt-5.5
```

Do not "fix" this by switching to direct Hermes Chat Completions or naive Responses. On this VPS, AnyRoute `gpt-5.5` is usable through Codex CLI/app-server's special Responses wire shape, not ordinary OpenAI-compatible requests.

## First Checks

Run the bundled checker with `terminal`:

```bash
python3 skill/hermes-anyroute-codex-operator/scripts/check_anyroute_codex_operator.py
```

For live probes:

```bash
python3 skill/hermes-anyroute-codex-operator/scripts/check_anyroute_codex_operator.py --live --gateway
```

Only run the tool-network live probe when the user wants a fuller validation:

```bash
python3 skill/hermes-anyroute-codex-operator/scripts/check_anyroute_codex_operator.py --live --gateway --tool-live
```

Required healthy signals:
- Codex CLI version is at least `0.136.0`.
- `/root/.codex/config.toml` has `model_provider = "anyrouter"`, `preferred_auth_method = "apikey"`, `wire_api = "responses"`, `approval_policy = "never"`, and `sandbox_mode = "danger-full-access"`.
- Hermes provider is `codex-anyrouter`.
- Runtime resolution returns `api_mode = "codex_app_server"`.
- Hermes source still contains the AnyRoute app-server fixes listed below.
- Live `codex exec` and `hermes chat --provider codex-anyrouter` return the expected sentinel text.

## Code Fixes To Preserve

Check these files before changing config:

```text
/usr/local/lib/hermes-agent/hermes_cli/runtime_provider.py
/usr/local/lib/hermes-agent/agent/background_review.py
/usr/local/lib/hermes-agent/agent/transports/codex_app_server_session.py
/usr/local/lib/hermes-agent/agent/codex_runtime.py
```

Expected behavior:
- `runtime_provider.py`: `codex-anyrouter` always rewrites to `codex_app_server`, including named custom provider resolution.
- `background_review.py`: AnyRoute `codex_app_server` parents skip background review direct fallback, so Hermes does not send non-streaming direct Responses to AnyRoute.
- `codex_app_server_session.py`: AnyRoute API-key mode does not suggest `codex login`; 429/503/high-demand/stream-disconnected errors are classified as AnyRoute upstream instability; ChatGPT plugin sync 401 is non-fatal.
- `codex_runtime.py`: app-server turn timeout follows `HERMES_AGENT_TIMEOUT` with a long default; timeout responses include assistant progress; short "I will/next/preparing" finals auto-continue for autonomous long tasks.

## Manual Probes

Codex direct:

```bash
codex exec -C /tmp --skip-git-repo-check --model gpt-5.5 '只回复 PING_OK'
```

Hermes bridge:

```bash
hermes chat -q '只回复 APP_SERVER_PATCH_OK' \
  --provider codex-anyrouter \
  --model gpt-5.5 \
  --toolsets '' \
  --quiet
```

Tool/network path:

```bash
hermes chat -q '请用终端运行 curl -I -s https://github.com，只回复 HTTP 首行。' \
  --provider codex-anyrouter \
  --model gpt-5.5 \
  --quiet
```

## Failure Routing

Read `references/error-map.md` for details. Fast rules:
- `invalid codex request` or `must be stream request`: suspect direct Hermes -> AnyRoute request shape. Restore Codex app-server routing.
- `429`, `503`, `high demand`, `stream disconnected`: AnyRoute/upstream instability. Do not switch to sub2api or plain OpenAI direct as a first fix.
- ChatGPT plugin sync 401 with successful model output: harmless Codex API-key-mode warning.
- Telegram receives only a plan/short status: inspect app-server timeout, progress summary, and auto-continue logic.
- GitHub push 403: token lacks contents write or repo access. Do not retry blindly.

## Safety Rules

- Never print or commit API keys, GitHub tokens, Telegram tokens, cookies, or raw `Authorization` headers.
- Back up `~/.hermes/config.yaml` and `~/.codex/config.toml` before edits.
- Avoid restart/service changes unless the user asks or the repair requires it.
- For high-risk shell operations, explain the command and wait for natural-language confirmation; do not rely on Codex approval UI inside Telegram.
