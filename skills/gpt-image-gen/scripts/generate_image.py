#!/usr/bin/env python3
"""
GPT-Image-2 图像生成脚本 (apimart.ai)

封装完整的异步工作流：
  1. POST /v1/images/generations  -> 拿到 task_id
  2. 轮询 GET /v1/tasks/{task_id} -> 等待 completed
  3. 下载结果图片到本地

支持文生图与图生图（参考图可传 URL 或本地文件，本地文件自动转 base64）。

仅依赖 Python 标准库（urllib），无需 pip install。
"""

import argparse
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

API_BASE = "https://api.apimart.ai"
GEN_ENDPOINT = f"{API_BASE}/v1/images/generations"
TASK_ENDPOINT = f"{API_BASE}/v1/tasks"

VALID_SIZES = {
    "auto", "1:1", "3:2", "2:3", "4:3", "3:4", "5:4", "4:5",
    "16:9", "9:16", "2:1", "1:2", "3:1", "1:3", "21:9", "9:21",
}
VALID_RESOLUTIONS = {"1k", "2k", "4k"}


# --------------------------------------------------------------------------- #
# API key 解析：环境变量优先，再回退到配置文件
# --------------------------------------------------------------------------- #
def resolve_api_key(cli_key=None):
    """
    优先级:
      1. --api-key 命令行参数
      2. 环境变量 APIMART_API_KEY
      3. 配置文件 (JSON, 字段 "api_key"):
           ~/.config/apimart/config.json
           <skill 目录>/config.json
    """
    if cli_key:
        return cli_key.strip()

    env_key = os.environ.get("APIMART_API_KEY")
    if env_key:
        return env_key.strip()

    candidates = [
        os.path.expanduser("~/.config/apimart/config.json"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                key = (data.get("api_key") or "").strip()
                if key:
                    return key
            except (json.JSONDecodeError, OSError):
                continue

    sys.exit(
        "错误：未找到 API Key。\n"
        "请任选一种方式提供：\n"
        "  1) export APIMART_API_KEY=sk-xxxx\n"
        "  2) 在 ~/.config/apimart/config.json 写入 {\"api_key\": \"sk-xxxx\"}\n"
        "  3) 传入 --api-key sk-xxxx\n"
        "获取 Key: https://apimart.ai/keys"
    )


# --------------------------------------------------------------------------- #
# HTTP 工具
# --------------------------------------------------------------------------- #
def http_request(url, api_key, method="GET", payload=None, timeout=60):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            err = json.loads(body)
            msg = err.get("error", {}).get("message", body)
        except json.JSONDecodeError:
            msg = body
        sys.exit(f"API 错误 (HTTP {e.code}): {msg}")
    except urllib.error.URLError as e:
        sys.exit(f"网络错误：{e.reason}")


# --------------------------------------------------------------------------- #
# 参考图处理：本地文件 -> base64 data URI；URL/data URI 原样透传
# --------------------------------------------------------------------------- #
def to_image_ref(item):
    if item.startswith(("http://", "https://", "data:")):
        return item
    if os.path.isfile(item):
        mime, _ = mimetypes.guess_type(item)
        mime = mime or "image/png"
        with open(item, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{b64}"
    sys.exit(f"错误：参考图 '{item}' 既不是 URL 也不是存在的本地文件")


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def submit_task(api_key, prompt, size, resolution, image_refs, official_fallback):
    payload = {
        "model": "gpt-image-2",
        "prompt": prompt,
        "n": 1,
    }
    if size:
        payload["size"] = size
    if resolution:
        payload["resolution"] = resolution
    if image_refs:
        payload["image_urls"] = [to_image_ref(x) for x in image_refs]
    if official_fallback:
        payload["official_fallback"] = True

    print(f"提交任务… (size={size or 'default'}, resolution={resolution or 'default'}, "
          f"参考图={len(image_refs)} 张)", file=sys.stderr)
    resp = http_request(GEN_ENDPOINT, api_key, method="POST", payload=payload)

    data = resp.get("data") or []
    if not data or not data[0].get("task_id"):
        sys.exit(f"提交失败，响应异常：{json.dumps(resp, ensure_ascii=False)}")
    task_id = data[0]["task_id"]
    print(f"已提交，task_id = {task_id}", file=sys.stderr)
    return task_id


def poll_task(api_key, task_id, first_delay=12, interval=4, max_wait=300):
    """轮询直到 completed/failed 或超时。返回任务对象。"""
    print(f"等待 {first_delay}s 后开始查询…", file=sys.stderr)
    time.sleep(first_delay)

    deadline = time.time() + max_wait
    while time.time() < deadline:
        resp = http_request(f"{TASK_ENDPOINT}/{task_id}", api_key, method="GET")
        task = resp.get("data") or {}
        status = task.get("status")
        progress = task.get("progress", 0)

        if status == "completed":
            print(f"完成 (耗时 {task.get('actual_time', '?')}s, "
                  f"花费 {task.get('cost', '?')})", file=sys.stderr)
            return task
        if status == "failed":
            err = task.get("error", {}).get("message", "未知错误")
            sys.exit(f"任务失败：{err}")

        print(f"  状态={status} 进度={progress}% …", file=sys.stderr)
        time.sleep(interval)

    sys.exit(f"超时：等待 {max_wait}s 后任务仍未完成 (task_id={task_id})")


def extract_urls(task):
    images = (task.get("result") or {}).get("images") or []
    urls = []
    for img in images:
        u = img.get("url")
        if isinstance(u, list):
            urls.extend(u)
        elif isinstance(u, str):
            urls.append(u)
    if not urls:
        sys.exit(f"任务已完成但未找到图片 URL：{json.dumps(task, ensure_ascii=False)}")
    return urls


def download(url, out_path):
    # 结果图托管在 CDN，对不带 User-Agent 的裸请求会返回 403，故显式带上浏览器 UA。
    req = urllib.request.Request(url)
    req.add_header(
        "User-Agent",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            content = resp.read()
    except urllib.error.URLError as e:
        sys.exit(f"下载失败 {url}: {e}")
    with open(out_path, "wb") as f:
        f.write(content)
    return out_path


def resolve_output_paths(output, url_count):
    """
    output 可能是：
      - None             -> 当前目录，自动命名
      - 已存在的目录      -> 目录内自动命名
      - 以 / 结尾的目录    -> 创建并自动命名
      - 具体文件名        -> 直接用（多图时追加序号）
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    def auto_name(dir_path):
        os.makedirs(dir_path, exist_ok=True)
        if url_count == 1:
            return [os.path.join(dir_path, f"gpt-image_{ts}.png")]
        return [os.path.join(dir_path, f"gpt-image_{ts}_{i}.png") for i in range(url_count)]

    if not output:
        return auto_name(os.getcwd())
    if output.endswith(os.sep) or os.path.isdir(output):
        return auto_name(output)

    # 具体文件路径
    parent = os.path.dirname(output) or "."
    os.makedirs(parent, exist_ok=True)
    if url_count == 1:
        return [output]
    root, ext = os.path.splitext(output)
    ext = ext or ".png"
    return [f"{root}_{i}{ext}" for i in range(url_count)]


def main():
    p = argparse.ArgumentParser(
        description="GPT-Image-2 图像生成 (apimart.ai)。提交 -> 轮询 -> 下载。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  文生图:   generate_image.py \"水彩风格的橘猫看夕阳\" --size 16:9 --resolution 2k\n"
            "  4K 输出:  generate_image.py \"星空下的古堡\" --size 16:9 --resolution 4k\n"
            "  图生图:   generate_image.py \"变成水彩画\" --image ./photo.jpg\n"
            "  多参考图: generate_image.py \"融合成海报\" --image a.jpg --image-url https://x/b.jpg\n"
        ),
    )
    p.add_argument("prompt", help="图像描述文本（中英文均可，建议详细）")
    p.add_argument("--size", default="1:1",
                   help="比例: 1:1,3:2,2:3,4:3,3:4,5:4,4:5,16:9,9:16,2:1,1:2,3:1,1:3,21:9,9:21,auto；"
                        "或像素如 1881x836。默认 1:1")
    p.add_argument("--resolution", default="1k", choices=sorted(VALID_RESOLUTIONS),
                   help="分辨率档位 1k/2k/4k，默认 1k")
    p.add_argument("--image", action="append", default=[], metavar="PATH",
                   help="本地参考图文件（自动转 base64），可重复；触发图生图模式")
    p.add_argument("--image-url", action="append", default=[], metavar="URL",
                   help="参考图 URL 或 data URI，可重复；触发图生图模式")
    p.add_argument("-o", "--output", default=None,
                   help="输出文件或目录；默认当前目录自动命名")
    p.add_argument("--official-fallback", action="store_true",
                   help="使用官方渠道兜底")
    p.add_argument("--api-key", default=None, help="直接传入 API Key（优先级最高）")
    p.add_argument("--first-delay", type=int, default=12, help="首次查询前等待秒数，默认 12")
    p.add_argument("--interval", type=int, default=4, help="轮询间隔秒数，默认 4")
    p.add_argument("--max-wait", type=int, default=300, help="最大等待秒数，默认 300")
    args = p.parse_args()

    # 基本校验（比例可为像素，故仅在含 ':' 时校验枚举）
    if ":" in args.size and args.size not in VALID_SIZES:
        sys.exit(f"错误：size '{args.size}' 不合法。合法比例: {', '.join(sorted(VALID_SIZES))}，"
                 f"或传像素如 1024x1024")

    image_refs = list(args.image) + list(args.image_url)
    if len(image_refs) > 16:
        sys.exit(f"错误：参考图最多 16 张，当前 {len(image_refs)} 张")

    api_key = resolve_api_key(args.api_key)

    task_id = submit_task(api_key, args.prompt, args.size, args.resolution,
                          image_refs, args.official_fallback)
    task = poll_task(api_key, task_id, args.first_delay, args.interval, args.max_wait)
    urls = extract_urls(task)
    out_paths = resolve_output_paths(args.output, len(urls))

    saved = []
    for url, path in zip(urls, out_paths):
        saved.append(download(url, path))

    print("\n已保存:")
    for s in saved:
        print(f"  {os.path.abspath(s)}")


if __name__ == "__main__":
    main()
