# Hermes AnyRoute Codex Operator

这个仓库是一份 **AI 优先使用的 Hermes 技能**。

你可以把这个仓库地址直接发给能安装技能的 AI，让它学习并帮你维护 VPS 上这条链路：

```text
Telegram 用户
    |
    v
Hermes Gateway
    |
    v
Hermes Agent
    |
    v
codex-anyrouter provider
    |
    v
Codex app-server subprocess
    |
    v
/root/.codex/config.toml + /root/.codex/auth.json
    |
    v
AnyRoute / AnyRouter: https://anyrouter.top/v1
    |
    v
gpt-5.5
```

核心原则只有一句：**AnyRoute 的 `gpt-5.5` 要让 Codex CLI/app-server 去调用，不要让 Hermes 直接用普通 Chat Completions 或普通 Responses 去直连。**

## 先给 AI 用

把下面这段话直接发给小龙虾、爱马仕、Codex 或其他能安装/读取技能的 AI：

```text
请安装并使用这个技能：
https://github.com/USCZ/hermes-anyroute-codex-skill

技能目录是：
skill/hermes-anyroute-codex-operator

安装后请先读取 SKILL.md，再按 references/operator-runbook.md 和 references/error-map.md
检查我的 VPS 上 Hermes -> Codex app-server -> AnyRoute / AnyRouter -> gpt-5.5 链路。

注意：不要把这个问题修成 Hermes 直连 AnyRoute。codex-anyrouter 必须解析到 codex_app_server。
```

如果这个 AI 能在 VPS 上执行命令，可以再把下面这段也发给它：

```bash
cd /tmp
rm -rf hermes-anyroute-codex-skill
git clone https://github.com/USCZ/hermes-anyroute-codex-skill.git

mkdir -p ~/.hermes/skills/devops
rm -rf ~/.hermes/skills/devops/hermes-anyroute-codex-operator
cp -R /tmp/hermes-anyroute-codex-skill/skill/hermes-anyroute-codex-operator \
  ~/.hermes/skills/devops/
```

这一步的意思很简单：把仓库里的技能目录复制到 Hermes 的用户技能目录里。之后 AI 就可以按技能里的规则诊断和修复这条链路。

## 再给人看

下面是人手动操作时的教程。你可以一段一段复制到 VPS 里执行。

### 1. 登录 VPS

在自己电脑的终端里连接 VPS：

```bash
ssh root@你的VPS_IP
```

如果你的 VPS 用户不是 `root`，把 `root` 换成实际用户名。

### 2. 安装这个技能

```bash
cd /tmp
rm -rf hermes-anyroute-codex-skill
git clone https://github.com/USCZ/hermes-anyroute-codex-skill.git

mkdir -p ~/.hermes/skills/devops
rm -rf ~/.hermes/skills/devops/hermes-anyroute-codex-operator
cp -R /tmp/hermes-anyroute-codex-skill/skill/hermes-anyroute-codex-operator \
  ~/.hermes/skills/devops/
```

检查是否复制成功：

```bash
ls ~/.hermes/skills/devops/hermes-anyroute-codex-operator
```

正常会看到：

```text
SKILL.md  agents  references  scripts
```

### 3. 检查 Codex 配置

打开或创建 Codex 配置文件：

```bash
mkdir -p /root/.codex
nano /root/.codex/config.toml
```

内容应该长这样：

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

再检查 AnyRoute API key 文件：

```bash
nano /root/.codex/auth.json
```

格式如下，把占位符换成你的 AnyRoute key：

```json
{
  "OPENAI_API_KEY": "sk-REPLACE_WITH_ANYROUTE_KEY"
}
```

不要把真实 key 发到聊天窗口、README、GitHub、日志或截图里。

### 4. 检查 Hermes 配置

打开 Hermes 配置：

```bash
mkdir -p /root/.hermes
nano /root/.hermes/config.yaml
```

关键部分应该是：

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

这里看起来写的是 `api_mode: codex_responses`，但最终运行时必须被 Hermes 代码改写成：

```text
api_mode = codex_app_server
```

这是这套方案的关键。如果没有改写，Hermes 就可能绕过 Codex，直接打到 AnyRoute，然后出现 `invalid codex request`、`must be stream request` 等错误。

### 5. 先跑只读自检

这个命令不会主动请求模型，主要检查配置和源码补丁是否在：

```bash
python3 ~/.hermes/skills/devops/hermes-anyroute-codex-operator/scripts/check_anyroute_codex_operator.py
```

如果最后 Summary 里有 `FAIL`，优先看失败项。`WARN` 不一定是坏事，通常表示需要人工确认。

### 6. 再跑 live 检查

这个命令会请求 AnyRoute / Codex / Hermes，会消耗一点额度：

```bash
python3 ~/.hermes/skills/devops/hermes-anyroute-codex-operator/scripts/check_anyroute_codex_operator.py --live
```

如果你还想检查 gateway 状态：

```bash
python3 ~/.hermes/skills/devops/hermes-anyroute-codex-operator/scripts/check_anyroute_codex_operator.py --live --gateway
```

如果你还想检查 Hermes 工具联网能力：

```bash
python3 ~/.hermes/skills/devops/hermes-anyroute-codex-operator/scripts/check_anyroute_codex_operator.py --live --gateway --tool-live
```

### 7. 手动验证三条链路

Codex 直连 AnyRoute：

```bash
codex exec -C /tmp --skip-git-repo-check --model gpt-5.5 '只回复 PING_OK'
```

Hermes 通过 `codex-anyrouter`：

```bash
hermes chat -q '只回复 APP_SERVER_PATCH_OK' \
  --provider codex-anyrouter \
  --model gpt-5.5 \
  --toolsets '' \
  --quiet
```

Hermes 工具联网：

```bash
hermes chat -q '请用终端运行 curl -I -s https://github.com，只回复 HTTP 首行。' \
  --provider codex-anyrouter \
  --model gpt-5.5 \
  --quiet
```

## 看报错怎么判断

| 看到的现象 | 通常代表什么 | 先怎么处理 |
| --- | --- | --- |
| `invalid codex request` | Hermes 可能绕过 Codex 直连 AnyRoute | 检查 `codex-anyrouter` 是否解析成 `codex_app_server` |
| `must be stream request` | 请求形状不是 Codex 需要的形状 | 不要改成普通 direct Responses |
| `high demand`、`429`、`503` | AnyRoute 或上游拥堵 | 降低并发，稍后重试 |
| ChatGPT plugin sync 401 | Codex API-key 模式下的插件同步噪声 | 如果模型回答成功，可以先忽略 |
| Telegram 只收到一句计划 | app-server 可能超时或没有汇总进度 | 查 `HERMES_AGENT_TIMEOUT`、progress summary、auto-continue |
| GitHub push 403 | GitHub token 没有目标仓库写权限 | 给 token 开 `Contents: Read and write` |

## 仓库内容

最终仓库只保留技能需要的文件：

```text
.gitignore
README.md
skill/hermes-anyroute-codex-operator/
  SKILL.md
  agents/openai.yaml
  references/error-map.md
  references/operator-runbook.md
  scripts/check_anyroute_codex_operator.py
```

之前临时加入过的 Hermes 源码快照不属于可安装技能，已经移除，避免以后和真正的 Hermes 代码版本不一致。

## 安全提醒

- 不要把 AnyRoute key、GitHub token、Telegram token 写进 GitHub。
- 不要把 token 放进 `git remote` URL。
- 需要推送 GitHub 时，fine-grained PAT 至少要有目标仓库 `Contents: Read and write`。
- 如果 token 已经发到聊天里，最好立刻撤销并重新生成。
