# Setup Blueprint

This reference explains the intended VPS routing model for Hermes Agent using AnyRoute/AnyRouter through local Codex.

## Mental Model

```text
User on Telegram / Hermes CLI
  -> Hermes Gateway or `hermes chat`
  -> Hermes provider `codex-anyrouter`
  -> runtime resolver rewrites to `codex_app_server`
  -> Codex app-server subprocess
  -> local Codex CLI config and auth
  -> AnyRouter `https://anyrouter.top/v1`
  -> model such as `gpt-5.5`
```

Hermes is the shell and session owner. Codex is the model transport owner. AnyRouter credentials belong in Codex's private local state, not in public docs or repositories.

## Expected Codex Files

`~/.codex/config.toml`:

```toml
model = "gpt-5.5"
model_provider = "anyrouter"
preferred_auth_method = "apikey"

[model_providers.anyrouter]
name = "Any Router"
base_url = "https://anyrouter.top/v1"
wire_api = "responses"
```

`~/.codex/auth.json`:

```json
{
  "OPENAI_API_KEY": "sk-REPLACE_WITH_ANYROUTER_KEY"
}
```

## Expected Hermes Files

`~/.hermes/config.yaml`:

```yaml
model:
  default: gpt-5.5
  provider: codex-anyrouter
  api_mode: codex_responses
  openai_runtime: auto

providers:
  codex-anyrouter:
    name: Codex AnyRouter
    base_url: https://anyrouter.top/v1
    api_key: sk-REPLACE_WITH_ANYROUTER_KEY
    default_model: gpt-5.5
    api_mode: codex_responses
```

In the patched Hermes runtime resolver, `codex-anyrouter` is a special provider alias: even when the persisted config says `api_mode: codex_responses`, the effective runtime becomes `codex_app_server`. That is the whole point of the bridge.

Confirm with:

```bash
python3 - <<'PY'
from hermes_cli.runtime_provider import resolve_runtime_provider
res = resolve_runtime_provider(requested="codex-anyrouter")
for key in ("provider", "model", "base_url", "api_mode", "source"):
    print(f"{key}: {res.get(key)}")
PY
```

## Validation Order

1. Read-only redacted config and runtime check:

```bash
python3 skill/hermes-anyroute-codex-skill/scripts/check_anyroute_codex.py
```

2. Live endpoint and runtime checks:

```bash
python3 skill/hermes-anyroute-codex-skill/scripts/check_anyroute_codex.py --live
```

3. Optional gateway read-only status:

```bash
python3 skill/hermes-anyroute-codex-skill/scripts/check_anyroute_codex.py --gateway
```

4. Manual Codex check:

```bash
codex exec -C /tmp --skip-git-repo-check --ephemeral --model gpt-5.5 '只回复 OK，不要解释。'
```

5. Manual Hermes check:

```bash
hermes chat -q '只回复 OK，不要解释。' --provider codex-anyrouter -m gpt-5.5 -t '' -Q --max-turns 1 --source tool
```

Only send a Telegram message if the user explicitly wants Telegram delivery tested.

## Known Good Outcome

- AnyRouter `/models` returns HTTP 200 and includes `gpt-5.5`.
- `codex exec` returns `OK`.
- `hermes chat --provider codex-anyrouter` returns `OK`.
- Runtime resolver reports `api_mode: codex_app_server`.
- Gateway state says Telegram connected if messaging is in scope.

That proves this active chain:

```text
Hermes -> Codex app-server -> local Codex AnyRouter config -> AnyRouter
```

It does not prove direct Hermes `POST /responses` to AnyRouter is compatible.
