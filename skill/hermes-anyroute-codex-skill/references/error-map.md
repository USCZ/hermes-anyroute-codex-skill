# Error Map

Use this map to avoid fixing the wrong layer.

## Codex API-Key Mode Warnings

These can appear during `codex exec` or Codex app-server startup:

```text
chatgpt authentication required to sync remote plugins; api key auth is not supported
failed to warm featured plugin ids cache ... 401 Unauthorized
```

Meaning: Codex tried to sync ChatGPT remote plugins while running in API-key mode. If the model response succeeds, this is not the root cause.

## AnyRouter Upstream Failures

Typical text:

```text
high demand
stream disconnected
bad response status code 429
bad response status code 503
rate limit
service unavailable
upstream
overloaded
```

Meaning: the local Codex config was loaded, but AnyRouter or its upstream route was unavailable. Do not tell the user to run `codex login` for this API-key setup. Retry later, reduce concurrency, or temporarily switch Hermes to a non-AnyRouter provider.

## Direct Hermes Responses Incompatibility

Typical text:

```text
invalid codex request
invalid_responses_request
Panic detected ... new-api
```

Meaning: Hermes sent a direct Responses-style request to AnyRouter that AnyRouter/new-api did not accept. Use the `codex-anyrouter` provider path that resolves to `codex_app_server`, or update Hermes' request shape before trying direct Responses again.

## Chat Completions Model Mismatch

Typical text:

```text
当前 API 不支持所选模型 gpt-5.5
model not found
404
```

Meaning: the endpoint is reachable, but the selected model may only be exposed through a different wire API or under a different model name. Probe `/models` before editing Hermes config.

## Hermes Auxiliary Failures

Typical text:

```text
provider=openai-codex base_url=https://chatgpt.com/backend-api/codex
HTTP 500
Auxiliary auto-detect: no provider available
Compression, summarization, and memory flush will not work
```

Meaning: title generation, compression, skill review, or memory review can fail independently of the main AnyRouter path. Report this separately. The main chat path can be healthy while auxiliary tasks need a cheaper normal chat-completions provider.

## Gateway vs Model Path

Gateway connected means Telegram/API server transport is alive. It does not prove model routing.

Model smoke success means Hermes can answer one prompt. It does not prove Telegram delivery unless a Telegram message is sent or recent gateway logs show delivery.

Report these separately:

```text
Gateway: active/running, Telegram connected.
Codex CLI: minimal prompt succeeded/failed.
Hermes codex-anyrouter: minimal prompt succeeded/failed.
Telegram delivery: observed in recent logs / not tested to avoid side effect.
```
