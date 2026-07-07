#!/usr/bin/env python3
"""
Cloudflare Pages Direct Upload 部署脚本

把一段 HTML 或一个静态站点目录，通过 Wrangler CLI 的 Pages Direct Upload
部署到 Cloudflare Pages，返回结构化 JSON 结果（含访问 URL）。

流程：
  1. 定位 wrangler（全局命令 or `npx wrangler`）
  2. 检查认证（CLOUDFLARE_API_TOKEN 环境变量 / `wrangler whoami`）
  3. 整理部署目录（html_content -> 临时目录 index.html；或校验 site_dir）
  4. 扫描疑似敏感信息（除非 --force）
  5. 规范化 / 生成项目名
  6. 需要时自动创建 Pages 项目
  7. `wrangler pages deploy <dir> --project-name=<name> --branch=<branch>`
  8. 从输出解析 *.pages.dev URL

关键约定：
  - **最终结果永远是 stdout 上的一行 JSON**（成功与失败都是），供上游 Agent 解析。
  - 诊断 / 进度信息走 stderr。
  - 成功 exit 0，失败 exit 1。

仅依赖 Python 标准库，无需 pip install。
面向 Direct Upload（直接上传），不处理 Git 仓库驱动的自动部署。
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

PLATFORM = "cloudflare_pages"

# Cloudflare Pages 项目名规则：小写字母/数字/连字符，首尾为字母数字，长度 <= 58
MAX_PROJECT_NAME_LEN = 58

# 结果 URL 匹配：<hash>.<project>.pages.dev 或 <project>.pages.dev
PAGES_URL_RE = re.compile(r"https://[A-Za-z0-9._-]+\.pages\.dev\b")


# --------------------------------------------------------------------------- #
# 结构化输出
# --------------------------------------------------------------------------- #
def emit(result, exit_code):
    """把结果作为一行 JSON 打到 stdout，并以给定 code 退出。"""
    result.setdefault("platform", PLATFORM)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(exit_code)


def fail(error_code, message, raw_error=""):
    emit(
        {
            "success": False,
            "error_code": error_code,
            "message": message,
            "raw_error": (raw_error or "")[:4000],
        },
        1,
    )


def log(msg):
    print(msg, file=sys.stderr)


# --------------------------------------------------------------------------- #
# 子进程
# --------------------------------------------------------------------------- #
def run(cmd, timeout, cwd=None):
    """运行命令，返回 (returncode, stdout, stderr)。超时抛 TimeoutExpired。"""
    env = dict(os.environ)
    env.setdefault("NO_COLOR", "1")  # 去掉 ANSI 颜色，便于解析
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,  # 无 TTY，避免任何交互式 prompt 挂起
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        text=True,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def resolve_wrangler():
    """
    返回 wrangler 命令前缀（list）。优先全局 wrangler，其次 `npx wrangler`。
    都不可用返回 None。
    """
    if shutil.which("wrangler"):
        return ["wrangler"]
    if shutil.which("npx"):
        # --yes 避免首次运行 npx 时的交互式确认
        return ["npx", "--yes", "wrangler"]
    return None


# --------------------------------------------------------------------------- #
# 错误分类：从 wrangler 输出粗粒度识别失败类型
# --------------------------------------------------------------------------- #
def classify_error(text):
    t = (text or "").lower()

    def has(*needles):
        return any(n in t for n in needles)

    # 账号缺失 / 多账号需指定（放在 auth 之前，措辞更具体）
    if has(
        "more than one account",
        "multiple accounts",
        "cloudflare_account_id",
        "supply the account",
        "specify an account",
        "select an account",
    ):
        return "MISSING_ACCOUNT_ID"

    # 未认证 / token 无效
    if has(
        "not authenticated",
        "you are not logged in",
        "not logged in",
        "wrangler login",
        "authentication error",
        "unable to authenticate",
        "invalid request headers",
        "please run `wrangler login`",
        "no account id found",
    ):
        return "CLOUDFLARE_NOT_AUTHENTICATED"

    # 权限不足
    if has(
        "not authorized",
        "unauthorized",
        "forbidden",
        "insufficient",
        "does not have permission",
        "permission",
        "authentication error [code: 10000]",
    ):
        return "PERMISSION_DENIED"

    # 项目不存在
    if has("project not found", "does not exist", "no project", "8000007"):
        return "PROJECT_NOT_FOUND"

    return "DEPLOY_FAILED"


AUTH_HINTS = {
    "CLOUDFLARE_NOT_AUTHENTICATED": (
        "Wrangler is not authenticated. Run `wrangler login`, or set the "
        "CLOUDFLARE_API_TOKEN (and CLOUDFLARE_ACCOUNT_ID) environment variables."
    ),
    "MISSING_ACCOUNT_ID": (
        "Cloudflare account could not be determined. Set the CLOUDFLARE_ACCOUNT_ID "
        "environment variable to the target account id."
    ),
    "PERMISSION_DENIED": (
        "The current Cloudflare credentials lack permission for Pages. The API token "
        "needs the 'Cloudflare Pages: Edit' permission."
    ),
    "PROJECT_NOT_FOUND": (
        "The Cloudflare Pages project does not exist and could not be created "
        "automatically. Create it first with "
        "`wrangler pages project create <name> --production-branch=<branch>`, "
        "or pass an existing project name."
    ),
    "DEPLOY_FAILED": "Cloudflare Pages deployment failed.",
}


# --------------------------------------------------------------------------- #
# 项目名处理
# --------------------------------------------------------------------------- #
def normalize_project_name(name):
    """规范化为合法的 Pages 项目名（小写字母/数字/连字符，首尾字母数字，<=58）。"""
    name = (name or "").strip().lower()
    name = re.sub(r"[^a-z0-9-]+", "-", name)  # 非法字符 -> 连字符
    name = re.sub(r"-{2,}", "-", name)         # 折叠连续连字符
    name = name.strip("-")
    if len(name) > MAX_PROJECT_NAME_LEN:
        name = name[:MAX_PROJECT_NAME_LEN].strip("-")
    return name


def generate_project_name():
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"agent-html-{ts}"


def title_from_html(html):
    m = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()
    return ""


# --------------------------------------------------------------------------- #
# 敏感信息扫描
# --------------------------------------------------------------------------- #
# 明显的密钥格式
SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "OpenAI-style secret key (sk-...)"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "GitHub token"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "Slack token"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "Google API key"),
]

# 形如  api_key = "xxxxx" / "secret": "xxxxx" / password: 'xxxxx'
KV_KEY_RE = re.compile(
    r"""(?ix)
    \b(api[_-]?key|apikey|secret|secret[_-]?key|access[_-]?token|
       client[_-]?secret|private[_-]?key|password|passwd|pwd|token|
       auth[_-]?token|bearer)\b
    \s*[:=]\s*
    ['"]([^'"]{8,})['"]
    """
)

# 占位符：命中这些的赋值不算敏感
PLACEHOLDER_RE = re.compile(
    r"^(x{3,}|\*{3,}|\.{3,}|<[^>]+>|\{\{?[^}]*\}?\}|"
    r"your[_-].*|my[_-].*|example.*|placeholder.*|changeme.*|todo.*|"
    r"none|null|undefined|test|demo|sample|dummy|value|string)$",
    re.IGNORECASE,
)


def scan_sensitive(samples):
    """
    samples: [(label, text), ...]
    返回命中列表 [{"where":..., "kind":..., "snippet":...}, ...]
    """
    findings = []
    for label, text in samples:
        if not text:
            continue
        for rx, kind in SECRET_PATTERNS:
            for m in rx.finditer(text):
                findings.append(
                    {"where": label, "kind": kind, "snippet": redact(m.group(0))}
                )
        for m in KV_KEY_RE.finditer(text):
            key, val = m.group(1), m.group(2)
            if PLACEHOLDER_RE.match(val.strip()):
                continue
            findings.append(
                {
                    "where": label,
                    "kind": f"hardcoded credential ({key.lower()})",
                    "snippet": redact(f'{key}="{val}"'),
                }
            )
    # 去重
    seen, uniq = set(), []
    for f in findings:
        k = (f["where"], f["kind"], f["snippet"])
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    return uniq[:20]


def redact(s):
    """截断并部分打码，避免把完整密钥回显到结果里。"""
    s = s.strip().replace("\n", " ")
    if len(s) <= 12:
        return s[:4] + "…"
    return s[:8] + "…" + s[-4:]


TEXT_EXTS = {".html", ".htm", ".js", ".mjs", ".cjs", ".css", ".json",
             ".txt", ".md", ".xml", ".svg", ".yaml", ".yml", ".env", ".ts"}
MAX_SCAN_BYTES = 512 * 1024  # 单文件最多扫 512KB


def collect_dir_samples(root):
    samples = []
    for dirpath, dirnames, filenames in os.walk(root):
        # 跳过依赖 / 版本控制目录
        dirnames[:] = [d for d in dirnames if d not in
                       (".git", "node_modules", ".wrangler", "__pycache__")]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext and ext not in TEXT_EXTS:
                continue
            path = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(path) > MAX_SCAN_BYTES:
                    continue
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    txt = f.read()
            except OSError:
                continue
            rel = os.path.relpath(path, root)
            samples.append((rel, txt))
    return samples


# --------------------------------------------------------------------------- #
# 部署目录整理
# --------------------------------------------------------------------------- #
def read_html_input(args):
    """按优先级读取 HTML 内容：stdin > html_file > html_content。返回字符串或 None。"""
    if args.html_stdin:
        return sys.stdin.read()
    if args.html_file:
        if not os.path.isfile(args.html_file):
            fail("HTML_FILE_MISSING",
                 f"--html-file not found: {args.html_file}")
        with open(args.html_file, "r", encoding="utf-8") as f:
            return f.read()
    if args.html_content is not None:
        return args.html_content
    return None


def prepare_deploy_dir(args):
    """
    返回 (deploy_dir, is_temp, samples, html_for_title)
    samples 用于敏感信息扫描；html_for_title 用于自动项目名。
    """
    html = read_html_input(args)

    if html is not None:
        if not html.strip():
            fail("HTML_FILE_MISSING", "Provided HTML content is empty.")
        tmp = tempfile.mkdtemp(prefix="cf-pages-")
        index_path = os.path.join(tmp, "index.html")
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(html)
        log(f"已将 HTML 写入临时目录 index.html：{index_path}")
        return tmp, True, [("index.html", html)], html

    if args.site_dir:
        site = os.path.abspath(os.path.expanduser(args.site_dir))
        if not os.path.isdir(site):
            fail("DIRECTORY_NOT_FOUND",
                 f"Site directory does not exist: {args.site_dir}")
        if not os.path.isfile(os.path.join(site, "index.html")):
            fail("HTML_FILE_MISSING",
                 f"No index.html found in site directory: {args.site_dir}")
        samples = collect_dir_samples(site)
        html_title_src = ""
        idx = os.path.join(site, "index.html")
        try:
            with open(idx, "r", encoding="utf-8", errors="ignore") as f:
                html_title_src = f.read()
        except OSError:
            pass
        return site, False, samples, html_title_src

    fail("MISSING_INPUT",
         "No input provided. Pass one of --html-content / --html-file / "
         "--html-stdin / --site-dir.")


# --------------------------------------------------------------------------- #
# 认证预检
# --------------------------------------------------------------------------- #
def preflight_auth(wrangler_cmd, timeout):
    """
    尽早给出干净的未认证错误。
    - 若设置了 CLOUDFLARE_API_TOKEN，视为 token 模式，直接通过。
    - 否则尝试 `wrangler whoami`，明确未登录才失败；其它异常放行，交给部署阶段分类。
    """
    if os.environ.get("CLOUDFLARE_API_TOKEN"):
        log("检测到 CLOUDFLARE_API_TOKEN，使用非交互式 token 认证。")
        return
    try:
        code, out, err = run(wrangler_cmd + ["whoami"], timeout=min(timeout, 90))
    except subprocess.TimeoutExpired:
        log("whoami 预检超时，跳过（交由部署阶段判定）。")
        return
    except FileNotFoundError:
        return
    combined = f"{out}\n{err}"
    low = combined.lower()
    if code != 0 and ("not authenticated" in low or "not logged in" in low
                      or "wrangler login" in low):
        fail("CLOUDFLARE_NOT_AUTHENTICATED",
             AUTH_HINTS["CLOUDFLARE_NOT_AUTHENTICATED"], combined)
    if code == 0:
        log("Cloudflare 认证检查通过。")


# --------------------------------------------------------------------------- #
# 项目创建（幂等）
# --------------------------------------------------------------------------- #
def ensure_project(wrangler_cmd, project, branch, timeout):
    """尝试创建项目；已存在则视为成功；认证/权限类错误直接上报。"""
    cmd = wrangler_cmd + [
        "pages", "project", "create", project,
        "--production-branch", branch,
    ]
    log(f"确保 Pages 项目存在：{project}")
    try:
        code, out, err = run(cmd, timeout=timeout)
    except subprocess.TimeoutExpired:
        fail("DEPLOY_TIMEOUT",
             f"Timed out creating project after {timeout}s.", "")
    combined = f"{out}\n{err}"
    low = combined.lower()
    if code == 0:
        log("项目已创建。")
        return
    if any(s in low for s in ("already exists", "already have", "duplicate")):
        log("项目已存在，跳过创建。")
        return
    # 分类：认证 / 权限 / 账号 类错误应立刻上报，其余（含未知）也上报
    ec = classify_error(combined)
    if ec == "PROJECT_NOT_FOUND":
        # create 阶段出现 not found 不合逻辑，降级为通用失败
        ec = "DEPLOY_FAILED"
    fail(ec, AUTH_HINTS.get(ec, "Failed to create Cloudflare Pages project."),
         combined)


# --------------------------------------------------------------------------- #
# 部署
# --------------------------------------------------------------------------- #
def deploy(wrangler_cmd, deploy_dir, project, branch, timeout):
    cmd = wrangler_cmd + [
        "pages", "deploy", deploy_dir,
        "--project-name", project,
        "--branch", branch,
        "--commit-dirty=true",  # 避免 site_dir 位于脏 git 仓库时的交互确认
    ]
    log("开始部署：" + " ".join(cmd))
    try:
        # 以 deploy_dir 为 cwd，避免误连上层 git 仓库上下文
        code, out, err = run(cmd, timeout=timeout, cwd=deploy_dir)
    except subprocess.TimeoutExpired:
        fail("DEPLOY_TIMEOUT",
             f"Deployment timed out after {timeout}s.", "")
    combined = f"{out}\n{err}"
    if code != 0:
        ec = classify_error(combined)
        fail(ec, AUTH_HINTS.get(ec, "Cloudflare Pages deployment failed."),
             combined)
    return combined


def extract_url(output, project):
    urls = PAGES_URL_RE.findall(output or "")
    if urls:
        # 优先带 hash 子域的本次部署 URL（形如 <hash>.<project>.pages.dev）
        hashed = [u for u in urls if u.count(".") >= 3]
        return (hashed[-1] if hashed else urls[-1]), sorted(set(urls))
    # 兜底：项目生产别名
    return f"https://{project}.pages.dev", []


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main():
    p = argparse.ArgumentParser(
        description="Deploy an HTML page or static site to Cloudflare Pages "
                    "via Wrangler Direct Upload. Prints a JSON result to stdout.",
    )
    # 输入（四选一，按优先级 stdin > html-file > html-content > site-dir）
    p.add_argument("--html-content", default=None,
                   help="HTML 内容字符串（小片段用；大文件请用 --html-file/--html-stdin）")
    p.add_argument("--html-file", default=None,
                   help="包含 HTML 内容的文件路径，将作为 index.html 部署")
    p.add_argument("--html-stdin", action="store_true",
                   help="从 stdin 读取 HTML 内容")
    p.add_argument("--site-dir", default=None,
                   help="本地静态站点目录（须含 index.html）")

    p.add_argument("--project-name", default=None,
                   help="Cloudflare Pages 项目名；缺省自动生成，非法字符自动规范化")
    p.add_argument("--branch", default="main", help="部署分支，默认 main")
    p.add_argument("--timeout-seconds", type=int, default=120,
                   help="单步命令超时秒数，默认 120")
    p.add_argument("--cleanup-after-deploy", dest="cleanup", default="true",
                   choices=["true", "false"],
                   help="部署后是否清理临时目录（仅影响脚本创建的临时目录），默认 true")
    p.add_argument("--force", action="store_true",
                   help="发现疑似敏感信息时仍继续部署，默认否")
    p.add_argument("--no-auto-create", action="store_true",
                   help="不自动创建缺失的 Pages 项目")
    args = p.parse_args()

    cleanup = args.cleanup == "true"

    # 1) 定位 wrangler
    wrangler_cmd = resolve_wrangler()
    if not wrangler_cmd:
        fail("WRANGLER_NOT_INSTALLED",
             "Wrangler CLI not found and npx is unavailable. Install it with "
             "`npm install -g wrangler` (requires Node.js).")

    # 2) 整理部署目录（在敏感扫描 / 认证前，以便优先给出输入错误）
    deploy_dir, is_temp, samples, html_title_src = prepare_deploy_dir(args)

    try:
        # 3) 敏感信息扫描
        if not args.force:
            findings = scan_sensitive(samples)
            if findings:
                emit({
                    "success": False,
                    "error_code": "SENSITIVE_CONTENT_DETECTED",
                    "message": ("Potential secrets detected in the content. "
                                "Deployment blocked. Remove them, or re-run with "
                                "force=true to override."),
                    "findings": findings,
                }, 1)

        # 4) 项目名
        raw_name = args.project_name
        if raw_name:
            project = normalize_project_name(raw_name)
            if not project:
                fail("INVALID_PROJECT_NAME",
                     f"Project name '{raw_name}' could not be normalized into a "
                     "valid Cloudflare Pages name (lowercase letters, digits, "
                     "hyphens).")
            normalized = project != raw_name
        else:
            base = title_from_html(html_title_src)
            project = normalize_project_name(base) if base else ""
            if not project:
                project = generate_project_name()
            else:
                project = normalize_project_name(f"{project}-{datetime.now():%Y%m%d-%H%M%S}")
            normalized = False
            log(f"未指定项目名，自动生成：{project}")

        # 5) 认证预检
        preflight_auth(wrangler_cmd, args.timeout_seconds)

        # 6) 确保项目存在
        if not args.no_auto_create:
            ensure_project(wrangler_cmd, project, args.branch, args.timeout_seconds)

        # 7) 部署
        output = deploy(wrangler_cmd, deploy_dir, project, args.branch,
                        args.timeout_seconds)

        # 8) 解析 URL
        url, all_urls = extract_url(output, project)

        msg = "HTML deployed successfully."
        if raw_name and normalized:
            msg += f" (project name normalized to '{project}')"

        result = {
            "success": True,
            "deployment_url": url,
            "project_name": project,
            "branch": args.branch,
            "message": msg,
        }
        if all_urls:
            result["all_urls"] = all_urls
        emit(result, 0)

    finally:
        if is_temp and cleanup and os.path.isdir(deploy_dir):
            shutil.rmtree(deploy_dir, ignore_errors=True)
            log(f"已清理临时目录：{deploy_dir}")


if __name__ == "__main__":
    main()
