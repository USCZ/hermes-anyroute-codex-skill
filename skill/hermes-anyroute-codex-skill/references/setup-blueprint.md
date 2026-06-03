# Setup Blueprint

This reference explains the intended VPS routing model for Hermes Agent using AnyRoute/AnyRouter through Codex.

## Mental Model

```text
User on Telegram / Hermes CLI
  -> Hermes Gateway or `hermes chat`
  -> Hermes provider `codex-anyrouter`
  -> Hermes runtime resolution rewrites to `codex_app_server`
  -> Codex app-server subprocess
  -> local Codex CLI config and auth
  -> AnyRouter `https://anyrouter.top/v1`
  -> model such as `gpt-5.5`
```

The important design point is that Hermes should not send the AnyRouter key directly in this path. Hermes delegates the turn to Codex, and Codex uses its own config and auth files.

## Expected Files

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
  "OPENAI_API_KEY": "sk-..."
}
```

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
    api_key: sk-...
    default_model: gpt-5.5
    api_mode: codex_responses
```

In the patched Hermes runtime resolver, the named provider `codex-anyrouter` is a special case: even when `openai_runtime` is `auto`, it resolves to `api_mode=codex_app_server` so the request follows local Codex.

## Validation Order

1. Direct provider visibility:

```bash
python3 skill/hermes-anyroute-codex-skill/scripts/check_anyroute_codex.py
```

2. Live endpoint and runtime checks:

```bash
python3 skill/hermes-anyroute-codex-skill/scripts/check_anyroute_codex.py --live
```

3. Manual Codex check:

```bash
codex exec -C /tmp --skip-git-repo-check --ephemeral --model gpt-5.5 '只回复 OK，不要解释。'
```

4. Manual Hermes check:

```bash
hermes chat -q '只回复 OK，不要解释。' --provider codex-anyrouter -m gpt-5.5 -t '' -Q --max-turns 1 --source tool
```

5. Gateway read-only status:

```bash
systemctl is-active hermes-gateway.service
systemctl show hermes-gateway.service -p ActiveState -p SubState -p ExecMainPID --no-pager
python3 - <<'PY'
import json, pathlib
p = pathlib.Path('~/.hermes/gateway_state.json').expanduser()
print(json.dumps(json.loads(p.read_text()), ensure_ascii=False, indent=2))
PY
```

Only send a Telegram message if the user explicitly wants a Telegram end-to-end smoke test.

## Known Good Outcome

- AnyRouter `/models` returns HTTP 200 and includes `gpt-5.5`.
- `codex exec` returns `OK`.
- `hermes chat --provider codex-anyrouter` returns `OK`.
- `gateway_state.json` says Telegram and api_server are connected.

That proves the active chain is usable:

```text
Hermes -> Codex app-server -> local Codex AnyRouter config -> AnyRouter
```

It does not prove direct Hermes `POST /responses` to AnyRouter is compatible. Keep those two routes separate.
