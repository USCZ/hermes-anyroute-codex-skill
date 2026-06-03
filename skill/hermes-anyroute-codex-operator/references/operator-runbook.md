# Operator Runbook

This runbook captures the VPS-specific repair knowledge for Hermes using AnyRoute/AnyRouter through Codex app-server.

## Non-Negotiable Routing Rule

AnyRoute `gpt-5.5` on this VPS is operated through Codex CLI/app-server:

```text
Hermes -> codex app-server -> Codex AnyRouter provider -> AnyRoute /v1 -> gpt-5.5
```

Do not replace this with:

```text
Hermes -> /v1/chat/completions -> AnyRoute
Hermes -> naive /v1/responses -> AnyRoute
```

Those paths were tested and failed with model unsupported, `invalid codex request`, or stream-shape errors.

## Expected Local Config

`/root/.codex/config.toml`:

```toml
model = "gpt-5.5"
model_provider = "anyrouter"
preferred_auth_method = "apikey"
approval_policy = "never"
sandbox_mode = "danger-full-access"

[sandbox_workspace_write]
network_access = true

[model_providers.anyrouter]
name = "Any Router"
base_url = "https://anyrouter.top/v1"
wire_api = "responses"
```

`/root/.hermes/config.yaml`:

```yaml
model:
  default: gpt-5.5
  provider: codex-anyrouter
  context_length: 200000
  openai_runtime: auto

providers:
  codex-anyrouter:
    name: Codex AnyRouter
    base_url: https://anyrouter.top/v1
    api_key: <YOUR_ANYROUTE_API_KEY>
    default_model: gpt-5.5
    api_mode: codex_responses
```

The persisted provider mode can remain `codex_responses`; the effective runtime must be `codex_app_server`.

## Static Code Audit

### Runtime resolver

File:

```text
/usr/local/lib/hermes-agent/hermes_cli/runtime_provider.py
```

Required behavior:

```python
if provider_norm == "codex-anyrouter":
    return "codex_app_server"
```

Named custom provider resolution must also return:

```python
api_mode = "codex_app_server"
```

### Background review

File:

```text
/usr/local/lib/hermes-agent/agent/background_review.py
```

Required behavior: when the parent runtime is `codex_app_server` and provider/base_url is AnyRoute/AnyRouter, skip background review. The background review fork otherwise downgrades to direct Responses and can pollute AnyRoute with incompatible non-streaming requests.

### Error classification

File:

```text
/usr/local/lib/hermes-agent/agent/transports/codex_app_server_session.py
```

Required behavior:

- AnyRouter API-key setup is detected from local Codex config.
- 429/503/high-demand/stream-disconnected errors produce AnyRoute upstream guidance.
- OAuth/login hints are suppressed for AnyRoute API-key mode.
- ChatGPT plugin sync 401 is treated as non-fatal if the model request succeeds.

### App-server long task handling

File:

```text
/usr/local/lib/hermes-agent/agent/codex_runtime.py
```

Required behavior:

- Turn timeout reads `HERMES_CODEX_APPSERVER_TURN_TIMEOUT` or `HERMES_AGENT_TIMEOUT`.
- Effective timeout is long enough for Telegram tasks, typically 1800 seconds.
- Timeout/retire responses include assistant progress messages already produced by app-server.
- Short plan-only finals auto-continue when the user asked for complete autonomous work, GitHub upload, or no short answers.

## Live Validation Ladder

1. Runtime:

```bash
python3 - <<'PY'
from hermes_cli.runtime_provider import resolve_runtime_provider
print(resolve_runtime_provider(requested="codex-anyrouter"))
PY
```

2. Codex:

```bash
codex exec -C /tmp --skip-git-repo-check --model gpt-5.5 '只回复 PING_OK'
```

3. Hermes:

```bash
hermes chat -q '只回复 APP_SERVER_PATCH_OK' --provider codex-anyrouter --model gpt-5.5 --toolsets '' --quiet
```

4. Tool/network path:

```bash
hermes chat -q '请用终端运行 curl -I -s https://github.com，只回复 HTTP 首行。' --provider codex-anyrouter --model gpt-5.5 --quiet
```

5. Gateway:

```bash
systemctl is-active hermes-gateway.service
systemctl show hermes-gateway.service -p ActiveState -p SubState -p ExecMainPID --no-pager
```

Gateway connected proves transport status only; it does not prove the model path.

## Recovery Flow

1. If Codex direct fails, inspect `/root/.codex/config.toml`, `/root/.codex/auth.json`, Codex version, and AnyRoute status.
2. If Codex direct passes but Hermes fails, inspect runtime resolver and named provider resolution.
3. If Hermes passes but Telegram only gets short progress, inspect app-server timeout, progress summary, and auto-continue.
4. If GitHub upload fails with 403, replace the token with one that has target repo `Contents: Read and write`.
5. If AnyRoute returns high-demand or 429/503, classify as upstream instability and retry later rather than changing the architecture.
