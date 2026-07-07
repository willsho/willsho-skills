---
name: deploy-html-vercel
description: >
  一键把静态 HTML 页面或静态站点目录部署到 Vercel，返回可直接访问的线上 URL。当你（或上游
  Agent）刚生成了一个 HTML 页面——产品介绍页、原型页、报告页、数据可视化页、落地页、单页小工具、
  demo、slides、看板——并且用户想「看看效果」「发出来」「给个链接」「部署一下」「上线」「分享给别人」
  时，立即使用本 skill。也适用于用户给出一个本地静态站点目录（含 index.html + CSS/JS/图片资源）
  要发布的场景。触发词：部署、上线、发布、deploy、publish、host、放到网上、生成链接、可访问的
  URL、Vercel、preview、production、把这个页面发出来、帮我托管。即使用户没有明说「Vercel」，
  只要意图是「把刚做好的 HTML/静态页面变成一个能点开的网址」，都应触发本 skill。
  不适用于：需要后端/数据库/服务端渲染的动态应用、非静态的框架构建产物（除非已 build 成静态目录）、
  部署到 Vercel 以外的指定平台。
---

# Deploy HTML via Vercel

把一个静态 HTML 页面或静态站点目录部署到 Vercel，拿回一个可直接访问的 URL。

所有确定性的工作——整理部署目录、扫描敏感信息、检测 CLI、执行部署、提取 URL、清理临时文件、
输出结构化 JSON——都由 `scripts/deploy_vercel.py` 完成。你的职责是：判断输入形态、把参数正确
地传给脚本、读懂它返回的 JSON，然后把结果清楚地讲给用户。**不要自己手写部署命令或重新实现这套
逻辑**，脚本已经处理了 token 脱敏、错误分类、目录隔离等一系列容易出错的细节。

## 何时以及如何调用

典型场景是：你刚在对话里生成了一段 HTML，用户说「部署一下 / 发出来 / 给个链接」。这时你手上
已经有 HTML 内容，只需要把它交给脚本。

**核心原则：先把内容落到磁盘，再让脚本部署。** 命令行直接传超长 HTML 字符串很容易因为引号、
反引号、特殊字符而出错，所以除了极短的片段，都应先用 Write 工具把内容写到文件，再传路径。

根据输入形态选择参数：

| 你手上的东西 | 怎么做 |
|---|---|
| 一段刚生成的完整 HTML | 用 Write 写到某个临时文件如 `/tmp/deploy-src/index.html`，然后传 `--site-dir /tmp/deploy-src`（或直接 `--html-file /tmp/deploy-src/index.html`） |
| 一个已有的本地站点目录（含 index.html、CSS、JS、图片） | 直接传 `--site-dir <目录路径>` |
| 极短的 HTML 片段（几行以内） | 可以直接 `--html-content '<...>'` |

调用示例：

```bash
python3 <skill_dir>/scripts/deploy_vercel.py --site-dir /tmp/deploy-src --project-name "product-landing"
```

脚本会打印一个 JSON 对象到 stdout（且只有这个 JSON），你 `json.loads` 之后据此回复用户即可。

## 参数速查

- `--site-dir <path>`：本地静态站点目录（推荐）。原地部署，不会改动用户目录。
- `--html-file <path>`：单个 HTML 文件，脚本会把它作为 index.html。
- `--html-content '<html>'`：内联 HTML 字符串，仅用于很短的片段。
  （以上三选一，多传会报 `INVALID_INPUT`。）
- `--project-name <name>`：期望的 Vercel 项目名（会被规范化为合法 slug）。
- `--production`：正式发布。**默认是 preview（预览）部署**，只有用户明确说「正式发布 / 上生产 /
  production / 发到正式环境」时才加这个参数。
- `--timeout-seconds <int>`：部署超时，默认 120。站点较大或网络慢时可调大。
- `--force`：即使检测到疑似敏感信息也强制部署（见下）。
- `--no-cleanup`：保留临时部署目录（调试用；默认部署后自动清理）。
- `--dry-run`：只做输入校验、目录整理和敏感信息扫描，**不真正部署**。用于自检。

认证走环境变量：如果设置了 `VERCEL_TOKEN`，脚本会自动以非交互方式部署；否则依赖本机
`vercel login` 的登录态。你不需要、也不应该把 token 写进命令行——脚本会从环境读取并做脱敏。

## 安全：部署前的敏感信息检查

脚本会在部署前扫描内容里是否有疑似泄露的密钥（`api_key`、`secret`、`access_token`、
`password`、`private_key`，以及 `sk-`、`AKIA`、GitHub/Slack token、私钥块等已知格式）。
一旦命中，**默认阻止部署**并返回 `SENSITIVE_CONTENT_DETECTED`，里面的 `sensitive_findings`
会列出命中的文件和脱敏片段（不会回显完整密钥）。

这是为了防止把用户的密钥推到公网。遇到这种情况：

1. **先把命中项如实告诉用户**——哪个文件、哪类字段。
2. 如果确实是误报（比如只是一个登录表单的 "Password" 文案，或占位符），或者用户明确知情并坚持
   要发，再带上 `--force` 重新部署。**不要在没跟用户确认的情况下擅自加 `--force`。**
3. 更好的做法通常是：帮用户把密钥从 HTML 里挪走（比如改成运行时从后端获取），而不是硬发。

其他安全约束脚本已内建：结果里绝不暴露 `VERCEL_TOKEN`；只上传指定目录（自动写 `.vercelignore`
排除 `node_modules`、`.git`、`.env` 等）；临时目录默认部署后清理。

## 读懂返回结果并回复用户

**成功：**

```json
{
  "success": true,
  "platform": "vercel",
  "deployment_url": "https://product-landing-xxxx.vercel.app",
  "deployment_type": "preview",
  "project_name": "product-landing",
  "message": "HTML deployed successfully (preview)."
}
```

拿到后，直接把可点击的 `deployment_url` 给用户，并说明这是 preview 还是 production。比如：
「已部署好了 ✅ 预览地址：<url>（这是预览部署；如果要正式发布，告诉我一声，我用 production 重发）」。

**失败：** `success` 为 `false`，用 `error_code` 判断原因，用 `message` 里的可读说明回复用户。
常见错误码与应对：

| error_code | 含义 | 你该怎么回复 |
|---|---|---|
| `VERCEL_CLI_NOT_FOUND` | 本机没有 vercel 也没有 npx | 提示安装：`npm install -g vercel` |
| `VERCEL_NOT_AUTHENTICATED` | 未登录 / token 无效 | 提示用户 `vercel login` 或配置 `VERCEL_TOKEN` |
| `VERCEL_PERMISSION_DENIED` | 账号/token 无权限或 scope 不对 | 提示检查团队/scope 和 token 权限 |
| `SENSITIVE_CONTENT_DETECTED` | 内容含疑似密钥 | 见上一节，先告知再决定是否 `--force` |
| `SITE_DIR_NOT_FOUND` | 目录不存在 | 确认路径是否正确 |
| `INDEX_HTML_MISSING` | 目录里没有 index.html | 提示补一个 index.html，或改用 `--html-file` 指定入口 |
| `DEPLOY_TIMEOUT` | 部署超时 | 建议调大 `timeout_seconds` 或精简站点 |
| `DEPLOY_FAILED` / `URL_NOT_FOUND` | 其他失败 | 参考 `raw_error`（已脱敏）如实转述关键信息 |

回复时保持诚实：成功就干脆地给链接；失败就说清楚卡在哪、下一步怎么办，不要假装部署成功了。

## 一个完整的心智模型

1. 用户让你做一个页面 → 你生成 HTML。
2. 用户说「发出来 / 部署一下 / 给个链接」→ 触发本 skill。
3. 把 HTML 写到 `/tmp/deploy-src/index.html`（多文件就整个目录），确认资源引用是相对路径。
4. 跑 `deploy_vercel.py --site-dir /tmp/deploy-src [--project-name ...] [--production]`。
5. 解析 JSON：成功给 URL，失败按错误码引导用户。

不确定用户要 preview 还是 production 时，默认用 preview（更安全、可反复重发），并在回复里
说明「这是预览，要正式发布随时说」。
