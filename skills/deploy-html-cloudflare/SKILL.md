---
name: deploy-html-cloudflare
description: >-
  把生成好的 HTML 页面或静态站点目录，通过 Cloudflare Pages Direct Upload 快速部署上线，
  返回一个可直接访问的 URL。当用户（或上游 Agent）说"把这个页面部署一下 / 发布上线 / 生成一个
  可访问的链接 / 帮我托管这个 HTML / 上线这个 landing page / demo / 报告页 / 数据可视化页 /
  内部预览页"，或提到 Cloudflare Pages、pages.dev、Wrangler、Direct Upload、静态站点部署、
  deploy HTML、publish page、host static site、share a link 时，使用本 skill。生成完
  HTML 后想拿到一个别人能点开的网址，就用它。仅面向直接上传部署，不负责 Git 仓库驱动的自动部署。
---

# Deploy HTML via Cloudflare Pages

把单个 HTML 文件内容、或一个本地静态站点目录，用 Wrangler CLI 的 **Cloudflare Pages
Direct Upload** 部署上线，并返回可访问的 `*.pages.dev` URL。

所有繁琐步骤（定位 wrangler、认证检查、整理目录、敏感信息扫描、项目名规范化、自动建项目、
解析部署 URL）都封装在 `scripts/deploy_cloudflare_pages.py` 里。**直接调用脚本，不要手写
wrangler 命令重新实现这套逻辑。** 脚本永远向 stdout 打印一行 JSON 结果，供你解析后展示给用户。

## 何时用本 skill

- 上游生成了一个 HTML 页面（landing page、交互式 demo、报告页、数据可视化、内部预览页），
  需要一个能直接点开的线上链接。
- 有一个本地静态站点目录（含 index.html + CSS/JS/图片），想整目录部署上线。

**不适用**：Git 仓库驱动的自动部署（push 触发构建）。本 skill 只做 Direct Upload 直接上传；
如果用户要的是「连 GitHub 仓库、每次 push 自动部署」，那是 Cloudflare Pages 的 Git integration
工作流，不归本 skill。

## 前置条件

1. **Node.js**（提供 `npx`）或已全局安装的 Wrangler。脚本优先用全局 `wrangler`，否则回退
   `npx --yes wrangler`。都没有时返回 `WRANGLER_NOT_INSTALLED`，提示 `npm install -g wrangler`。
2. **Cloudflare 认证**，二选一：
   - 交互式登录：`wrangler login`（一次性）。
   - 非交互式（推荐给 Agent / CI）：设置环境变量
     `CLOUDFLARE_API_TOKEN`（需含 **Cloudflare Pages: Edit** 权限）和 `CLOUDFLARE_ACCOUNT_ID`。

如果两者都没配好，脚本会返回 `CLOUDFLARE_NOT_AUTHENTICATED`，把登录/配置指引转达给用户即可。

## 使用方式

### 输入是「一段 HTML 内容」

上游 Agent 生成的 HTML 通常较大且含引号，**不要**塞进命令行 `--html-content`。推荐先用
Write 工具把 HTML 写到一个临时文件，再用 `--html-file`；或通过 stdin 传入：

```bash
# 方式一：写到文件后部署（推荐）
python3 ~/.claude/skills/deploy-html-cloudflare/scripts/deploy_cloudflare_pages.py \
  --html-file /tmp/page.html \
  --project-name my-landing-demo

# 方式二：stdin 管道
cat /tmp/page.html | python3 .../deploy_cloudflare_pages.py --html-stdin --project-name my-demo

# 方式三：短小片段可直接传字符串
python3 .../deploy_cloudflare_pages.py --html-content '<html><body>Hello</body></html>' --project-name hello
```

脚本会创建临时目录、写入 `index.html`、部署，然后（默认）清理临时目录。

### 输入是「一个静态站点目录」

```bash
python3 ~/.claude/skills/deploy-html-cloudflare/scripts/deploy_cloudflare_pages.py \
  --site-dir ./dist \
  --project-name my-site
```

脚本会校验目录存在且包含 `index.html`，然后整目录上传（CSS/JS/图片等资源一并部署）。
**site_dir 是用户的目录，脚本不会删除它**（`--cleanup-after-deploy` 只影响脚本自建的临时目录）。

## 参数

| 参数 | 说明 | 默认 |
| --- | --- | --- |
| `--html-content STR` | 直接传 HTML 字符串（仅限小片段） | 无 |
| `--html-file PATH` | 读取该文件作为 index.html 部署（大页面首选） | 无 |
| `--html-stdin` | 从 stdin 读取 HTML | 关闭 |
| `--site-dir PATH` | 本地静态站点目录（须含 index.html） | 无 |
| `--project-name NAME` | Pages 项目名；缺省自动生成，非法字符自动规范化 | 自动生成 |
| `--branch NAME` | 部署分支 | `main` |
| `--timeout-seconds N` | 单步命令超时秒数 | `120` |
| `--cleanup-after-deploy true\|false` | 部署后是否清理**临时**目录 | `true` |
| `--force` | 发现疑似敏感信息时仍继续部署 | 关闭 |
| `--no-auto-create` | 不自动创建缺失的 Pages 项目 | 关闭 |

输入优先级：`--html-stdin` > `--html-file` > `--html-content` > `--site-dir`。四者需至少提供其一。

**项目名规则**：只允许小写字母、数字、连字符，首尾为字母数字，长度 ≤ 58。传入的非法名会被
自动规范化（如 `My Demo!!` → `my-demo`），并在返回 `message` 里说明。未传项目名时，脚本基于
`<title>` 或时间戳生成形如 `agent-html-20260707-113000` 的合法名。

## 输出格式

**成功**（exit 0）：

```json
{
  "success": true,
  "platform": "cloudflare_pages",
  "deployment_url": "https://a1b2c3d4.my-demo.pages.dev",
  "project_name": "my-demo",
  "branch": "main",
  "message": "HTML deployed successfully.",
  "all_urls": ["https://a1b2c3d4.my-demo.pages.dev"]
}
```

**失败**（exit 1）：

```json
{
  "success": false,
  "platform": "cloudflare_pages",
  "error_code": "CLOUDFLARE_NOT_AUTHENTICATED",
  "message": "Wrangler is not authenticated. Please run `wrangler login` or configure Cloudflare API credentials.",
  "raw_error": "..."
}
```

拿到结果后，成功就把 `deployment_url` 作为可点击链接呈现给用户；失败就把 `message` 的可读原因
和处置建议转达给用户（必要时附上 `raw_error` 的关键片段）。

### 错误码

| error_code | 含义 | 处置 |
| --- | --- | --- |
| `MISSING_INPUT` | 没提供任何输入 | 提供 html 或 site_dir |
| `WRANGLER_NOT_INSTALLED` | 找不到 wrangler，也没有 npx | `npm install -g wrangler`（需 Node.js） |
| `CLOUDFLARE_NOT_AUTHENTICATED` | 未登录且无 API Token | `wrangler login` 或配置 `CLOUDFLARE_API_TOKEN` |
| `MISSING_ACCOUNT_ID` | 无法确定 Cloudflare 账号 | 设置 `CLOUDFLARE_ACCOUNT_ID` |
| `PERMISSION_DENIED` | 凭证缺少 Pages 权限 | Token 需含 Cloudflare Pages: Edit |
| `PROJECT_NOT_FOUND` | 项目不存在且未能自动创建 | 先建项目或换一个已存在的项目名 |
| `DIRECTORY_NOT_FOUND` | site_dir 不存在 | 检查目录路径 |
| `HTML_FILE_MISSING` | 缺 index.html 或 HTML 为空 | 确保有非空 index.html |
| `INVALID_PROJECT_NAME` | 项目名无法规范化为合法名 | 换一个含字母/数字的名字 |
| `SENSITIVE_CONTENT_DETECTED` | 内容里有疑似密钥 | 移除密钥，或经用户确认后加 `--force` |
| `DEPLOY_TIMEOUT` | 部署超时 | 调大 `--timeout-seconds` 后重试 |
| `DEPLOY_FAILED` | 其它部署失败 | 看 `raw_error` |

## 安全要求

1. **不要**把 API Key、token、用户隐私数据写进 HTML。
2. 部署前脚本会扫描 HTML / 站点文本文件中疑似敏感信息（`api_key`、`secret`、`token`、
   `password`、私钥块、AWS/GitHub/Google 等密钥格式）。命中即返回 `SENSITIVE_CONTENT_DETECTED`
   并**默认停止部署**。确认是误报或确需部署时，再由用户明确同意后加 `--force`。
3. 脚本不会在结果里回显 `CLOUDFLARE_API_TOKEN`；命中的敏感片段也会打码截断。
4. 只上传指定的 HTML / 目录，不会把本地无关文件带上去；临时目录默认部署后清理。

## 注意事项

- **Direct Upload ≠ Git integration**：本 skill 是直接上传部署。如果这个项目之后又接了 Git
  自动部署，两种来源的部署会并存/互相覆盖，需提醒用户注意工作流差异。
- 首次用 `npx wrangler` 会下载 Wrangler，可能耗时几十秒；全局安装可避免。
- `deployment_url` 是本次部署的带 hash 子域链接，立即可访问；项目生产别名为
  `https://<project_name>.pages.dev`（指向生产分支的最新部署）。
