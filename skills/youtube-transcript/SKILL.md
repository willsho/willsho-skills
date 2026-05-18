---
name: youtube-transcript
description: 获取 YouTube 视频字幕/转录文本的工具。当用户提供 YouTube 链接、视频 ID，或说"帮我获取这个视频的字幕"、"获取 transcript"、"提取 YouTube 文字"、"转录视频"时，主动使用此 skill。即使用户只是想"总结视频内容"、"分析视频"，也应该先用这个 skill 获取字幕，再进行后续处理。支持自动语言优先级（英文 > 简体中文 > 繁体中文）。
---

# YouTube Transcript Skill

直接通过 Python 获取 YouTube 视频字幕，无需外部服务。优先使用 `youtube-transcript-api`，失败后自动用 `yt-dlp` 兜底。

## 依赖安装

首次使用前确认已安装依赖：

```bash
pip install youtube-transcript-api yt-dlp
```

## 获取字幕的步骤

### 第一步：提取视频 ID

从用户输入中提取视频 ID（6–20 位字母数字和 `-_`）：

- 完整 URL：`https://www.youtube.com/watch?v=VIDEO_ID`
- 短链接：`https://youtu.be/VIDEO_ID`
- 纯 ID：直接使用

### 第二步：运行脚本

```bash
python3 ~/.claude/skills/youtube-transcript/scripts/fetch_transcript.py VIDEO_ID [LANG]
```

- `VIDEO_ID`：视频 ID（必填）
- `LANG`：语言代码，可选，例如 `en`、`zh-CN`；不填则自动按优先级尝试 `en` → `zh-CN` → `zh-TW`

### 第三步：处理返回结果

**成功时**，脚本输出 JSON：

```json
{
  "video_id": "dQw4w9WgXcQ",
  "lang": "en",
  "source": "youtube-transcript-api",
  "title": "视频标题（yt-dlp 时有值，youtube-transcript-api 时为 null）",
  "plain_text": "完整字幕文本...",
  "items": [
    {"text": "第一句话", "start": 0.0, "duration": 2.5}
  ]
}
```

将 `plain_text` 字段（完整文本）呈现给用户；`title` 非空时一并展示。

**失败时**，输出：

```json
{"error": "Both methods failed. primary=...; fallback=..."}
```

常见原因：
- 视频无字幕或字幕被禁用
- 指定语言不存在（尝试不指定语言，让脚本自动选择）
- 网络问题（检查网络或稍后重试）

## 输出格式

```
[视频 ID: VIDEO_ID | 语言: en | 来源: youtube-transcript-api]

完整字幕文本内容...
```

有标题时：

```
[VIDEO_ID | 视频标题 | en]

完整字幕文本内容...
```

如果用户后续要做总结/分析，直接基于这段文本继续处理即可。
