---
name: gpt-image-gen
description: >-
  使用 apimart.ai 的 GPT-Image-2 模型生成图片（文生图与图生图）。当用户想要"生成/画/出一张图"、
  "做一张海报/插画/头像/壁纸/封面"、"把这张照片改成 XX 风格"、"根据参考图融合/重绘"、或提到
  gpt-image、apimart、文生图、图生图、AI 画图、出图、4K 大图等需求时，使用本 skill。支持 15 种
  比例与 1K/2K/4K 分辨率，最多 16 张参考图。即使用户没明说"用 apimart 或 gpt-image-2"，只要是
  让你生成一张全新图片或基于参考图改图，都应优先使用本 skill 而不是其它方式。
---

# GPT-Image-2 图像生成

通过 apimart.ai 的 GPT-Image-2 接口生成图片。接口是**异步**的：提交后返回 `task_id`，
需要轮询任务状态，完成后再下载图片。这些步骤已经封装在 `scripts/generate_image.py` 里，
直接调用脚本即可，不要手写 curl 重新实现整套轮询逻辑。

## 何时用本 skill

- 文生图：根据一句话描述生成全新图片（插画、海报、头像、壁纸、概念图等）
- 图生图：基于一张或多张参考图（本地文件或 URL）重绘 / 改风格 / 融合
- 需要指定比例（横图 / 竖图 / 方图）或高分辨率（2K / 4K）输出

## 前置条件：API Key

脚本按以下顺序查找密钥，任选其一配置即可：

1. 命令行 `--api-key`（优先级最高）
2. 环境变量 `APIMART_API_KEY`
3. 配置文件（JSON，字段 `api_key`）：`~/.config/apimart/config.json` 或本 skill 目录下的 `config.json`

如果运行时报"未找到 API Key"，先告诉用户去 https://apimart.ai/keys 获取，然后建议其
`export APIMART_API_KEY=sk-xxxx`，或写入配置文件。不要把密钥打印到聊天里。

## 基本用法

脚本只依赖 Python 标准库，直接运行：

```bash
python3 ~/.claude/skills/gpt-image-gen/scripts/generate_image.py "<提示词>" [选项]
```

常用选项：

| 选项 | 说明 | 默认 |
| --- | --- | --- |
| `--size` | 比例（见下表）或像素如 `1881x836`；`auto` 由服务端决定 | `1:1` |
| `--resolution` | `1k` / `2k` / `4k` | `1k` |
| `--image PATH` | 本地参考图，自动转 base64，可重复 → 触发图生图 | 无 |
| `--image-url URL` | 参考图 URL 或 data URI，可重复 → 触发图生图 | 无 |
| `-o, --output` | 输出文件或目录；默认当前目录自动命名 | 当前目录 |
| `--official-fallback` | 使用官方渠道兜底 | 关闭 |

生成的图片默认保存到**当前工作目录**，文件名形如 `gpt-image_20260607_153000.png`，
脚本结束时会打印保存的绝对路径。

## 示例

**文生图（指定比例 + 2K）**
```bash
python3 ~/.claude/skills/gpt-image-gen/scripts/generate_image.py \
  "一只橘猫坐在窗台上看夕阳，水彩画风格" --size 16:9 --resolution 2k
```

**4K 输出**
```bash
python3 ~/.claude/skills/gpt-image-gen/scripts/generate_image.py \
  "星空下的古老城堡，电影感" --size 16:9 --resolution 4k
```

**图生图（本地照片改风格）**
```bash
python3 ~/.claude/skills/gpt-image-gen/scripts/generate_image.py \
  "把这张照片变成水彩画风格" --image ./photo.jpg
```

**多参考图融合（本地 + URL 混用）**
```bash
python3 ~/.claude/skills/gpt-image-gen/scripts/generate_image.py \
  "把这两张照片融合成一张海报" --size 4:3 --resolution 2k \
  --image ./a.jpg --image-url https://example.com/b.jpg
```

## 比例速查

横图 `3:2 4:3 5:4 16:9 2:1 3:1 21:9`，竖图 `2:3 3:4 4:5 9:16 1:2 1:3 9:21`，
方图 `1:1`，外加 `auto`。完整的 `size × resolution → 实际像素`对照表见
`references/sizes.md`——当用户对成图像素有明确要求（比如"我要 3840×2160"）时再去查。

## 撰写提示词的建议

- 提示词支持中英文，越具体越好：主体、风格、光线、构图、氛围都可以写进去。
- **比例只通过 `--size` 传，不要在提示词里重复写"16:9 / 横图"**，避免与参数冲突。
- 帮用户生成时，可以把用户简短的描述适当扩写得更具画面感，但保留其核心意图。

## 注意事项

- **异步耗时**：单张图通常 30~60 秒。脚本默认提交后等 12 秒再开始查询，每 4 秒轮询一次，
  最多等 300 秒；网络较慢或 4K 大图可用 `--max-wait` 调大。
- **内容审核**：提示词会经过平台敏感词/安全审核，命中违规会直接报错且不计费。
- **结果链接时效**：返回 URL 约 24 小时后过期；脚本已即时下载到本地，无需担心。
- **参考图上限 16 张**，URL 与本地文件可混用。
- **计费**：按 1K/2K/4K 档位计费，失败和审核未过不扣费。生成 4K / 多次出图时注意成本。
- `n` 固定为 1（接口限制），一次调用出一张图；要多张就多次调用。
