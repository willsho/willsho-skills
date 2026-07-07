#!/usr/bin/env python3
"""Deploy a static HTML page or site directory to Vercel and return a structured result.

This script does the deterministic heavy lifting for the `deploy-html-vercel` skill:
  - normalize input (inline HTML string, an HTML file, or an existing site directory)
  - guarantee an index.html exists in the directory that gets uploaded
  - scan the content for leaked secrets and block the deploy unless --force is given
  - detect the Vercel CLI (global `vercel`, else `npx vercel`)
  - run the deploy (preview by default, production with --prod), honoring VERCEL_TOKEN
  - extract the deployment URL and classify failures into readable error codes
  - emit a single JSON object on stdout so the calling agent can parse it directly

Nothing except the final JSON is printed to stdout, so callers can json.loads() it verbatim.
Secrets (VERCEL_TOKEN, matched sensitive values) are never echoed back.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

PLATFORM = "vercel"

# Directories that should never be uploaded even if they live inside a site_dir.
# We hand Vercel a .vercelignore for these so only the intended assets ship.
DEFAULT_IGNORES = [
    "node_modules",
    ".git",
    ".env",
    ".env.*",
    "*.log",
    ".DS_Store",
]


# --------------------------------------------------------------------------- #
# Result helpers
# --------------------------------------------------------------------------- #
def emit(result):
    """Print the result as JSON on stdout and exit 0 (the JSON carries success)."""
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0)


def fail(error_code, message, raw_error=None, **extra):
    result = {
        "success": False,
        "platform": PLATFORM,
        "error_code": error_code,
        "message": message,
    }
    if raw_error is not None:
        result["raw_error"] = redact(raw_error)
    result.update(extra)
    emit(result)


# --------------------------------------------------------------------------- #
# Secret handling
# --------------------------------------------------------------------------- #
# Assignment-style leaks: `api_key = "sk-..."`, `password: 'hunter2'`, etc.
# We deliberately require an assignment + a real-looking value so that innocent
# HTML like <input type="password"> or a "Reset password" label does not trip.
_ASSIGN_KEYS = (
    r"api[_-]?key|secret|access[_-]?token|auth[_-]?token|refresh[_-]?token|"
    r"client[_-]?secret|password|passwd|private[_-]?key|bearer"
)
_ASSIGN_QUOTED = re.compile(
    r'(?i)\b(' + _ASSIGN_KEYS + r')\b["\']?\s*[:=]\s*["\']([^"\']{6,})["\']'
)
_ASSIGN_BARE = re.compile(
    r'(?i)\b(' + _ASSIGN_KEYS + r')\b\s*[:=]\s*([A-Za-z0-9\-_./+]{12,})'
)

# Known credential shapes — high-signal, matched regardless of surrounding syntax.
_KNOWN_SHAPES = [
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]

# Values that look like placeholders rather than real secrets.
_PLACEHOLDER = re.compile(
    r"(?i)^(your[_-].*|xxx+|placeholder|example|sample|test|demo|dummy|changeme|"
    r"none|null|true|false|<.*>|\{\{.*\}\}|\$\{.*\}|\.\.\.)$"
)


def _looks_like_placeholder(value):
    v = value.strip()
    return not v or _PLACEHOLDER.match(v) is not None


def _redact_value(value):
    v = value.strip()
    if len(v) <= 4:
        return "***"
    return v[:3] + "***" + v[-1:]


def scan_for_secrets(deploy_dir):
    """Return a list of {file, indicator, snippet} for likely leaked secrets.

    Only text-like assets (.html/.htm/.js/.mjs/.json/.css) are scanned, and each
    file is read up to a size cap so a huge bundle can't stall the scan.
    """
    findings = []
    seen = set()
    max_bytes = 2_000_000
    scan_exts = {".html", ".htm", ".js", ".mjs", ".json", ".css", ".txt"}

    for root, dirs, files in os.walk(deploy_dir):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".git")]
        for name in files:
            if os.path.splitext(name)[1].lower() not in scan_exts:
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, deploy_dir)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    text = fh.read(max_bytes)
            except OSError:
                continue

            for regex in (_ASSIGN_QUOTED, _ASSIGN_BARE):
                for m in regex.finditer(text):
                    indicator, value = m.group(1).lower(), m.group(2)
                    if _looks_like_placeholder(value):
                        continue
                    key = (rel, indicator, value)
                    if key in seen:
                        continue
                    seen.add(key)
                    findings.append({
                        "file": rel,
                        "indicator": indicator,
                        "snippet": f"{indicator} = {_redact_value(value)}",
                    })

            for label, regex in _KNOWN_SHAPES:
                for m in regex.finditer(text):
                    value = m.group(0)
                    key = (rel, label, value)
                    if key in seen:
                        continue
                    seen.add(key)
                    findings.append({
                        "file": rel,
                        "indicator": label,
                        "snippet": f"{label}: {_redact_value(value)}",
                    })
    return findings


def redact(text):
    """Strip the Vercel token (and anything after --token) out of any text."""
    if not text:
        return text
    token = os.environ.get("VERCEL_TOKEN")
    if token:
        text = text.replace(token, "***")
    text = re.sub(r"(--token[ =])\S+", r"\1***", text)
    return text


# --------------------------------------------------------------------------- #
# Input preparation
# --------------------------------------------------------------------------- #
def sanitize_project_name(name):
    if not name:
        return None
    slug = re.sub(r"[^a-z0-9._-]+", "-", name.strip().lower()).strip("-._")
    slug = slug[:100]
    return slug or None


def prepare_deploy_dir(args):
    """Return (deploy_dir, temp_dir_or_None, project_name).

    temp_dir is set only when we created a directory that should be cleaned up.
    """
    sources = [bool(args.html_content), bool(args.html_file), bool(args.site_dir)]
    if sum(sources) == 0:
        fail("NO_INPUT",
             "No input provided. Pass --site-dir, --html-file, or --html-content.")
    if sum(sources) > 1:
        fail("INVALID_INPUT",
             "Provide exactly one input source: --site-dir OR --html-file OR --html-content.")

    project_name = sanitize_project_name(args.project_name)

    # Case 1: an existing site directory — deploy it in place, never mutate it.
    if args.site_dir:
        site_dir = os.path.abspath(os.path.expanduser(args.site_dir))
        if not os.path.exists(site_dir):
            fail("SITE_DIR_NOT_FOUND", f"Site directory does not exist: {site_dir}")
        if not os.path.isdir(site_dir):
            fail("SITE_DIR_NOT_FOUND", f"Path is not a directory: {site_dir}")

        has_index = os.path.isfile(os.path.join(site_dir, "index.html"))
        if not has_index:
            html_files = [f for f in os.listdir(site_dir)
                          if f.lower().endswith((".html", ".htm"))
                          and os.path.isfile(os.path.join(site_dir, f))]
            if len(html_files) == 1:
                # Stage a copy so we can add index.html without touching the user's dir.
                tmp = tempfile.mkdtemp(prefix="vercel-deploy-")
                staged = os.path.join(tmp, project_name or "site")
                shutil.copytree(site_dir, staged,
                                ignore=shutil.ignore_patterns(*DEFAULT_IGNORES))
                shutil.copyfile(os.path.join(site_dir, html_files[0]),
                                os.path.join(staged, "index.html"))
                write_ignore_file(staged)
                return staged, tmp, (project_name or sanitize_project_name(
                    os.path.basename(site_dir)))
            fail("INDEX_HTML_MISSING",
                 f"No index.html found in {site_dir} and could not infer one "
                 f"(found {len(html_files)} candidate .html files). "
                 f"Add an index.html to the directory.")

        write_ignore_file(site_dir)
        return site_dir, None, (project_name or sanitize_project_name(
            os.path.basename(site_dir)))

    # Case 2/3: inline HTML string or an HTML file -> write index.html into a temp dir.
    if args.html_file:
        html_path = os.path.abspath(os.path.expanduser(args.html_file))
        if not os.path.isfile(html_path):
            fail("SITE_DIR_NOT_FOUND", f"HTML file does not exist: {html_path}")
        with open(html_path, "r", encoding="utf-8", errors="ignore") as fh:
            html = fh.read()
    else:
        html = args.html_content

    if not html or not html.strip():
        fail("INDEX_HTML_MISSING", "HTML content is empty; nothing to deploy.")

    tmp = tempfile.mkdtemp(prefix="vercel-deploy-")
    deploy_dir = os.path.join(tmp, project_name or "generated-html")
    os.makedirs(deploy_dir, exist_ok=True)
    with open(os.path.join(deploy_dir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(html)
    write_ignore_file(deploy_dir)
    return deploy_dir, tmp, (project_name or "generated-html")


def write_ignore_file(deploy_dir):
    """Drop a .vercelignore so unrelated local files never get uploaded."""
    path = os.path.join(deploy_dir, ".vercelignore")
    if os.path.exists(path):
        return
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(DEFAULT_IGNORES) + "\n")
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Vercel CLI
# --------------------------------------------------------------------------- #
def detect_cli():
    """Return the CLI invocation as a list, or None if neither vercel nor npx exists."""
    if shutil.which("vercel"):
        return ["vercel"]
    if shutil.which("npx"):
        return ["npx", "--yes", "vercel"]
    return None


def classify_error(stdout, stderr, returncode):
    """Map Vercel CLI failure output to a stable error_code + human message."""
    blob = f"{stdout}\n{stderr}".lower()
    auth_markers = [
        "no existing credentials", "not authenticated", "please log in",
        "please run `vercel login`", "you must be logged in", "credentials",
        "token is not valid", "invalid token", "the specified token is not valid",
    ]
    perm_markers = [
        "not authorized", "forbidden", "not allowed", "do not have permission",
        "you don't have access", "insufficient", "scope",
    ]
    if any(m in blob for m in auth_markers):
        return ("VERCEL_NOT_AUTHENTICATED",
                "Vercel CLI is not authenticated. Run `vercel login` or set a "
                "VERCEL_TOKEN environment variable, then retry.")
    if any(m in blob for m in perm_markers):
        return ("VERCEL_PERMISSION_DENIED",
                "The Vercel account/token lacks permission for this deployment. "
                "Check the team/scope and token privileges.")
    return ("DEPLOY_FAILED",
            f"Vercel deployment failed (exit code {returncode}). "
            f"See raw_error for details.")


_URL_RE = re.compile(r"https://[^\s\"'<>]+")


def extract_url(stdout, stderr):
    """Return the deployment URL. Prefer stdout (CLI prints the URL there)."""
    for stream in (stdout, stderr):
        urls = _URL_RE.findall(stream or "")
        # The deployment URL is the last https URL emitted; inspect URLs come first.
        preferred = [u for u in urls if ".vercel.app" in u]
        if preferred:
            return preferred[-1].rstrip(".,)")
    for stream in (stdout, stderr):
        urls = _URL_RE.findall(stream or "")
        if urls:
            return urls[-1].rstrip(".,)")
    return None


def build_command(cli, deploy_dir, production, use_token):
    cmd = list(cli) + ["--cwd", deploy_dir, "--yes"]
    if production:
        cmd.append("--prod")
    if use_token:
        cmd += ["--token", os.environ["VERCEL_TOKEN"]]
    return cmd


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(description="Deploy static HTML to Vercel.")
    src = parser.add_argument_group("input (choose one)")
    src.add_argument("--site-dir", help="Path to an existing static site directory.")
    src.add_argument("--html-file", help="Path to a single HTML file to deploy.")
    src.add_argument("--html-content", help="Inline HTML string (small snippets only).")

    parser.add_argument("--project-name", help="Desired Vercel project name.")
    parser.add_argument("--production", action="store_true",
                        help="Production deploy (default is a preview deploy).")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--no-cleanup", action="store_true",
                        help="Keep the temp deploy directory after finishing.")
    parser.add_argument("--force", action="store_true",
                        help="Deploy even if likely secrets are detected.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Prepare + validate + scan, but do not call Vercel.")
    args = parser.parse_args()

    deploy_type = "production" if args.production else "preview"
    deploy_dir, temp_dir, project_name = prepare_deploy_dir(args)

    def cleanup():
        if temp_dir and not args.no_cleanup:
            shutil.rmtree(temp_dir, ignore_errors=True)

    try:
        # ---- security scan (runs even in dry-run so leaks are caught early) ----
        findings = scan_for_secrets(deploy_dir)
        if findings and not args.force:
            cleanup()
            fail("SENSITIVE_CONTENT_DETECTED",
                 "Deployment blocked: the content appears to contain secrets "
                 f"({', '.join(sorted({f['indicator'] for f in findings}))}). "
                 "Remove them, or pass force=true to override intentionally.",
                 sensitive_findings=findings,
                 deployment_type=deploy_type,
                 project_name=project_name)

        # ---- CLI detection ----
        cli = detect_cli()
        if cli is None:
            cleanup()
            fail("VERCEL_CLI_NOT_FOUND",
                 "Vercel CLI not found. Install it with `npm install -g vercel`, "
                 "or ensure `npx` is available to run `npx vercel`.",
                 deployment_type=deploy_type,
                 project_name=project_name)

        use_token = bool(os.environ.get("VERCEL_TOKEN"))
        cmd = build_command(cli, deploy_dir, args.production, use_token)

        # ---- dry run: report what would happen, skip the network call ----
        if args.dry_run:
            result = {
                "success": True,
                "dry_run": True,
                "platform": PLATFORM,
                "deployment_type": deploy_type,
                "project_name": project_name,
                "deploy_dir": deploy_dir,
                "index_html_present": os.path.isfile(
                    os.path.join(deploy_dir, "index.html")),
                "cli": " ".join(cli),
                "would_run": redact(" ".join(cmd)),
                "using_token": use_token,
                "sensitive_findings": findings,
                "message": "Dry run: inputs validated, index.html present, secret "
                           "scan complete. No deployment performed.",
            }
            if not args.no_cleanup:
                cleanup()
            emit(result)

        # ---- real deploy ----
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=args.timeout_seconds,
                env=os.environ.copy(),
            )
        except subprocess.TimeoutExpired:
            cleanup()
            fail("DEPLOY_TIMEOUT",
                 f"Vercel deployment timed out after {args.timeout_seconds}s. "
                 "Try a larger timeout_seconds or a smaller site.",
                 deployment_type=deploy_type,
                 project_name=project_name)
        except FileNotFoundError:
            cleanup()
            fail("VERCEL_CLI_NOT_FOUND",
                 "Vercel CLI could not be executed. Install it with "
                 "`npm install -g vercel`.",
                 deployment_type=deploy_type,
                 project_name=project_name)

        stdout, stderr = proc.stdout or "", proc.stderr or ""

        if proc.returncode != 0:
            error_code, message = classify_error(stdout, stderr, proc.returncode)
            cleanup()
            fail(error_code, message,
                 raw_error=(stderr or stdout)[-2000:],
                 deployment_type=deploy_type,
                 project_name=project_name)

        url = extract_url(stdout, stderr)
        cleanup()
        if not url:
            fail("URL_NOT_FOUND",
                 "Deployment reported success but no URL could be extracted from "
                 "the CLI output.",
                 raw_error=(stdout or stderr)[-2000:],
                 deployment_type=deploy_type,
                 project_name=project_name)

        emit({
            "success": True,
            "platform": PLATFORM,
            "deployment_url": url,
            "deployment_type": deploy_type,
            "project_name": project_name,
            "message": f"HTML deployed successfully ({deploy_type}).",
        })
    except Exception as exc:  # noqa: BLE001 — always return structured JSON
        cleanup()
        fail("DEPLOY_FAILED",
             f"Unexpected error during deployment: {exc}",
             raw_error=str(exc),
             deployment_type=deploy_type,
             project_name=project_name)


if __name__ == "__main__":
    main()
