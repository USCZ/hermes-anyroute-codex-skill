# Hermes AnyRoute Codex Operator

这个仓库是一份面向 VPS 运维的 Hermes 技能与排障手册，用来维护这条生产链路：

```text
Telegram
  -> Hermes Gateway
  -> Hermes Agent
  -> local codex app-server subprocess
  -> /root/.codex/config.toml
  -> AnyRoute / AnyRouter https://anyrouter.top/v1
  -> gpt-5.5
```

核心结论：**AnyRoute 的 `gpt-5.5` 应通过 Codex CLI/app-server 运行，不应通过 Hermes 直接调用普通 Chat Completions 或朴素 Responses。**

## 为什么不能直连

这台 VPS 已经实测过：

| 请求方式 | 结果 |
| --- | --- |
| `/v1/chat/completions` + `gpt-5.5` | 返回不支持模型或失败 |
| 朴素 `/v1/responses` 非流式 | `invalid codex request` 或类似错误 |
| 朴素 `/v1/responses` 流式 | 可能返回 `must be stream request` 或请求形状错误 |
| Codex CLI / Codex app-server | 可用 |

所以 `codex-anyrouter` 的关键不是“换一个 base_url”，而是强制 Hermes 把 turn 交给 Codex app-server，让 Codex 发送它自己的 Responses wire shape。

## 架构图

```mermaid
flowchart LR
    TG[Telegram user] --> GW[Hermes Gateway]
    GW --> H[Hermes Agent]
    H -->|provider: codex-anyrouter| R[Runtime resolver]
    R -->|api_mode: codex_app_server| AS[codex app-server subprocess]
    AS --> CFG[/root/.codex/config.toml]
    AS --> AUTH[/root/.codex/auth.json]
    CFG --> AR[AnyRoute / AnyRouter /v1]
    AUTH --> AR
    AR --> M[gpt-5.5]
    M --> AR --> AS --> H --> GW --> TG

    H -. must not bypass Codex .-> BAD[Direct Hermes Responses]
    BAD -. invalid codex request .-> AR
```

## Codex 配置

`/root/.codex/config.toml` 应保持这个形态：

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

`/root/.codex/auth.json` 保存 AnyRoute API key，仓库文档只写占位符：

```json
{
  "OPENAI_API_KEY": "sk-REPLACE_WITH_ANYROUTE_KEY"
}
```

配置原因：

- `approval_policy = "never"`：Telegram 里没有可靠的 Codex 审批 UI，避免 turn 卡在不可点击的 approval。
- `sandbox_mode = "danger-full-access"`：这条链路用于 GitHub push、文件写入和长任务操作。真正高风险操作应由 Hermes 在回复中说明命令并等待自然语言确认。
- `wire_api = "responses"`：AnyRoute 上的 `gpt-5.5` 依赖 Codex 使用的 Responses wire shape。

## Hermes 配置

`/root/.hermes/config.yaml` 中保留命名 provider：

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
    api_key: sk-REPLACE_WITH_ANYROUTE_KEY
    default_model: gpt-5.5
    api_mode: codex_responses
```

虽然配置里仍可写 `api_mode: codex_responses`，但运行时解析必须改写成：

```text
api_mode = codex_app_server
```

确认命令：

```bash
python3 - <<'PY'
from hermes_cli.runtime_provider import resolve_runtime_provider
res = resolve_runtime_provider(requested="codex-anyrouter")
for key in ("provider", "model", "base_url", "api_mode", "source"):
    print(f"{key}: {res.get(key)}")
PY
```

期望：

```text
provider: codex-anyrouter
model: gpt-5.5
base_url: https://anyrouter.top/v1
api_mode: codex_app_server
```

## Hermes 代码修复点

这些修复点用于判断当前 Hermes 是否仍然保留 AnyRoute/Codex 生产路径：

| 文件 | 需要保留的行为 |
| --- | --- |
| `hermes_cli/runtime_provider.py` | `codex-anyrouter` 强制解析为 `codex_app_server` |
| `agent/background_review.py` | 当 parent 是 AnyRoute `codex_app_server` 时跳过 background direct fallback |
| `agent/transports/codex_app_server_session.py` | AnyRoute API-key 模式不要提示 `codex login`；429/503/high demand 归类为上游波动 |
| `agent/codex_runtime.py` | app-server turn timeout 使用 `HERMES_AGENT_TIMEOUT`，默认可到 1800s；超时时汇总 progress；短计划回复自动续跑 |

## 安装技能

复制到 Hermes 用户技能目录：

```bash
mkdir -p ~/.hermes/skills/devops
cp -R skill/hermes-anyroute-codex-operator ~/.hermes/skills/devops/
```

## 一键自检

只读配置和源码检查：

```bash
python3 skill/hermes-anyroute-codex-operator/scripts/check_anyroute_codex_operator.py
```

live 检查会调用上游并消耗少量额度：

```bash
python3 skill/hermes-anyroute-codex-operator/scripts/check_anyroute_codex_operator.py --live
```

加入 Gateway 状态和工具联网检查：

```bash
python3 skill/hermes-anyroute-codex-operator/scripts/check_anyroute_codex_operator.py --live --gateway --tool-live
```

## 手动验证命令

基础 Hermes 链路：

```bash
hermes chat -q '只回复 APP_SERVER_PATCH_OK' \
  --provider codex-anyrouter \
  --model gpt-5.5 \
  --toolsets '' \
  --quiet
```

Codex CLI 直连 AnyRoute：

```bash
codex exec -C /tmp --skip-git-repo-check --model gpt-5.5 '只回复 PING_OK'
```

工具联网：

```bash
hermes chat -q '请用终端运行 curl -I -s https://github.com，只回复 HTTP 首行。' \
  --provider codex-anyrouter \
  --model gpt-5.5 \
  --quiet
```

## 常见错误判断

| 现象 | 判断 | 处理 |
| --- | --- | --- |
| `invalid codex request` | Hermes 可能绕过 Codex 直打 AnyRoute | 检查 `api_mode` 是否实际为 `codex_app_server` |
| `must be stream request` | 朴素 Responses 形状不兼容 | 不要改成 direct Responses |
| `high demand` / `stream disconnected` / `429` / `503` | AnyRoute 或上游波动 | 降低并发、稍后重试、临时切 provider |
| ChatGPT plugin sync 401 | Codex API-key 模式的非致命插件同步警告 | 如果模型回答成功，可忽略 |
| TG 只收到短回复但后台有请求 | app-server progress 未被充分汇总或 turn 超时 | 检查 `HERMES_AGENT_TIMEOUT`、progress summary、auto-continue |
| GitHub push 403 | token 权限不足 | 给目标仓库 `Contents: Read and write`，不要反复重试 |

## GitHub Token 要求

Fine-grained PAT 推荐设置：

```text
Repository access: only the target repository
Repository permissions:
  Contents: Read and write
  Metadata: Read-only
```

如果需要创建仓库，还需要创建仓库权限；否则先在网页创建仓库，再只授予目标仓库 contents write。

不要把 GitHub PAT 写进 README、技能文件、git remote URL 或 shell 历史。

## 产物结构

```text
skill/hermes-anyroute-codex-operator/
  SKILL.md
  agents/openai.yaml
  scripts/check_anyroute_codex_operator.py
  references/operator-runbook.md
  references/error-map.md
```
