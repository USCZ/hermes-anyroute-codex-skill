# Error Map

Use this map to classify failures by layer.

## Direct AnyRoute Request Shape

Symptoms:

```text
invalid codex request
invalid_responses_request
must be stream request
当前 API 不支持所选模型 gpt-5.5
model not found
```

Likely cause: Hermes or another client is bypassing Codex and sending ordinary Chat Completions or naive Responses to AnyRoute.

Action: restore `codex-anyrouter -> codex_app_server`. Do not switch to sub2api, ordinary OpenAI-compatible direct mode, or non-Codex Responses as the first fix.

## AnyRoute Upstream Instability

Symptoms:

```text
high demand
stream disconnected
retrying sampling request
bad response status code 429
bad response status code 503
too many requests
service unavailable
bad gateway
upstream
overloaded
```

Likely cause: AnyRoute or its upstream route is overloaded.

Action: retry later, reduce concurrency, or temporarily switch the main provider. Do not tell the user to run `codex login` for this API-key setup.

## Codex API-Key Mode Plugin Warnings

Symptoms:

```text
chatgpt authentication required to sync remote plugins; api key auth is not supported
failed to warm featured plugin ids cache ... 401 Unauthorized
remote plugin catalog ... 401 Unauthorized
```

Likely cause: Codex attempted ChatGPT plugin catalog sync while using API-key auth.

Action: if the model answer succeeds, treat this as non-fatal noise.

## Hermes Runtime Misrouting

Symptoms:

```text
resolve_runtime_provider(...).api_mode = codex_responses
Codex direct probe returns PING_OK
Hermes bridge probe fails
```

Likely cause: `codex-anyrouter` is not being rewritten to `codex_app_server`.

Action: inspect `hermes_cli/runtime_provider.py`, especially `_maybe_apply_codex_app_server_runtime()` and named custom provider resolution.

## Background Review Direct Fallback

Symptoms:

```text
Main prompt works
AnyRoute backend shows odd non-streaming/direct failed requests
Logs mention background review, skill review, or auxiliary direct Responses
```

Likely cause: background review bypassed app-server and used direct Responses.

Action: confirm `agent/background_review.py` skips background review when parent runtime is AnyRoute `codex_app_server`.

## Telegram Short Reply / Hidden Progress

Symptoms:

```text
Telegram receives one short sentence
AnyRoute dashboard shows many successful requests
Files were modified but user saw only a plan/status
turn timed out after 600.0s
```

Likely cause: app-server performed tool work, but Hermes only sent final response or timed out before summarizing progress.

Action: confirm `agent/codex_runtime.py` uses long timeout, progress summary, and auto-continue for plan-only finals.

## GitHub Upload

Symptoms:

```text
403 Resource not accessible by personal access token
Permission denied to OWNER/REPO.git
could not read Username for 'https://github.com'
```

Likely cause: token lacks repo access or `Contents: Read and write`.

Action: use a fine-grained PAT scoped to the target repo with `Contents: Read and write`; use `GIT_ASKPASS` or credential prompt, not token-in-remote URLs.
