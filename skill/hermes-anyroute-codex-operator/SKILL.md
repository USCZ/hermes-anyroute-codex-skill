---
name: hermes-anyroute-codex-operator
description: 维护 Hermes 经 Codex 连接 AnyRouter 的运行链路。
---

# Hermes AnyRoute Codex Operator

Use this skill when the user wants to install, verify, diagnose, or repair the VPS path where Hermes reaches AnyRoute/AnyRouter `gpt-5.5` through local Codex app-server.

## Core Rule

The intended production path is:

```text
Telegram -> Hermes Gateway -> Hermes Agent -> codex-anyrouter
  -> codex_app_server -> local codex app-server
  -> /root/.codex/config.toml + /root/.codex/auth.json
  -> https://anyrouter.top/v1 -> gpt-5.5
```

Do not "fix" this by switching Hermes to direct Chat Completions or naive Responses against AnyRoute. On this VPS, `gpt-5.5` works through Codex CLI/app-server's request shape.

## Install The Skill

If the skill is not installed yet, use `terminal` to copy it from the repository:

```bash
cd /tmp
rm -rf hermes-anyroute-codex-skill
git clone https://github.com/USCZ/hermes-anyroute-codex-skill.git
mkdir -p ~/.hermes/skills/devops
rm -rf ~/.hermes/skills/devops/hermes-anyroute-codex-operator
cp -R /tmp/hermes-anyroute-codex-skill/skill/hermes-anyroute-codex-operator ~/.hermes/skills/devops/
```

## First Checks

Run the bundled static checker with `terminal`:

```bash
python3 ~/.hermes/skills/devops/hermes-anyroute-codex-operator/scripts/check_anyroute_codex_operator.py
```

Use live checks only when the user accepts that they call AnyRoute/Codex/Hermes and may consume quota:

```bash
python3 ~/.hermes/skills/devops/hermes-anyroute-codex-operator/scripts/check_anyroute_codex_operator.py --live
```

For gateway and tool-network validation:

```bash
python3 ~/.hermes/skills/devops/hermes-anyroute-codex-operator/scripts/check_anyroute_codex_operator.py --live --gateway --tool-live
```

Healthy signals:

- Codex CLI version is at least `0.136.0`.
- `/root/.codex/config.toml` uses provider `anyrouter`, `preferred_auth_method = "apikey"`, `wire_api = "responses"`, `approval_policy = "never"`, and `sandbox_mode = "danger-full-access"`.
- `/root/.hermes/config.yaml` uses provider `codex-anyrouter`.
- Runtime resolution returns `api_mode = "codex_app_server"`.
- Live Codex and Hermes probes return the expected sentinel text.

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

## What To Preserve In Hermes

Before editing config, audit these installed Hermes files:

```text
/usr/local/lib/hermes-agent/hermes_cli/runtime_provider.py
/usr/local/lib/hermes-agent/agent/background_review.py
/usr/local/lib/hermes-agent/agent/transports/codex_app_server_session.py
/usr/local/lib/hermes-agent/agent/codex_runtime.py
```

Expected behavior:

- `runtime_provider.py`: `codex-anyrouter` always rewrites to `codex_app_server`, including named custom provider resolution.
- `background_review.py`: AnyRoute `codex_app_server` parents skip background review direct fallback.
- `codex_app_server_session.py`: AnyRoute API-key mode does not suggest `codex login`; 429/503/high-demand/stream-disconnected errors are classified as upstream instability; ChatGPT plugin sync 401 is non-fatal.
- `codex_runtime.py`: app-server turn timeout follows `HERMES_AGENT_TIMEOUT`; timeout responses include assistant progress; short plan-only finals auto-continue for autonomous long tasks.

## References

- Read `references/operator-runbook.md` for the full repair sequence.
- Read `references/error-map.md` when classifying failures.

## Safety

- Never print, commit, or paste API keys, GitHub tokens, Telegram tokens, cookies, or raw `Authorization` headers.
- Back up `~/.hermes/config.yaml` and `~/.codex/config.toml` before edits.
- For high-risk shell operations, explain the command and wait for natural-language confirmation.
