---
name: stepfun-audio-transcription
description: 使用 StepFun 阶跃星辰 StepAudio ASR 将本地音频、本地视频或公开音频直链转成文字稿。用户提到“声音转文字”“音频转文字”“录音转写”“语音识别”“ASR”“把 mp3/m4a/wav/mp4 转成文字”“转写播客/访谈/会议录音”，或提供媒体文件并要求提取其中讲话内容时，应主动使用此 skill。支持中文标题自动提取人名/品牌/术语热词，也支持用户指定热词。若输入是已有字幕的 YouTube 链接，优先使用专门的 YouTube 字幕 skill；本 skill 适合本地文件和可直接下载的媒体 URL。
compatibility: 需要 Python 3、ffmpeg、网络访问，以及环境变量 STEPFUN_API_KEY。
---

# StepFun Audio Transcription

使用随 skill 附带的 `scripts/transcribe_audio.py`，通过 StepFun `stepaudio-2.5-asr` 把音频或视频中的语音转成纯文字。

## 工作原则

- 先确认输入是存在的本地媒体文件，或无需登录即可下载的音视频直链。
- 使用脚本完成真实转写，不要根据文件名、标题或上下文猜测内容。
- API Key 只从 `STEPFUN_API_KEY` 环境变量读取；不要把 Key 写进命令、代码、日志或输出文件。
- ASR 只返回识别到的文字。不要自行补充说话人标签、时间戳、未听清内容或润色后的句子。
- 用户若还需要摘要、纪要或文章，先保留原始转写文件，再基于原文生成派生内容，避免覆盖原稿。

## 前置检查

检查依赖：

```bash
command -v ffmpeg
test -n "$STEPFUN_API_KEY"
```

如果 `ffmpeg` 缺失，说明需要先安装 ffmpeg。如果环境变量缺失，请用户在自己的终端设置：

```bash
export STEPFUN_API_KEY="<your-key>"
```

不要要求用户把真实 Key 发送到对话中。

## 转写步骤

1. 确定本 skill 的实际目录，然后调用其中的脚本；不要假设它固定安装在 `~/.claude` 或 `~/.codex`。
2. 为输出选择一个明确的 `.txt` 路径。默认放在源文件旁边；如果工作区或用户指定了输出目录，则遵从该位置。
3. 有节目名、会议主题或文件标题时传入 `--title`，脚本会从中提取可能的人名、品牌与术语作为热词。
4. 用户明确给出的专有名词用重复的 `--hotword` 传入。手动热词会与标题热词去重合并。
5. 运行脚本并检查退出码与输出文件。脚本会在转码时直接按时长分片：默认每片最多 600 秒，不足 600 秒的音频只有一片；各片逐一转写后按顺序合并。

基本用法：

```bash
python3 <skill-dir>/scripts/transcribe_audio.py \
  "/path/to/interview.m4a" \
  --output "/path/to/interview.txt"
```

带标题和热词：

```bash
python3 <skill-dir>/scripts/transcribe_audio.py \
  "/path/to/episode.mp3" \
  --output "/path/to/episode.txt" \
  --title "对话 Yuri：StepFun 与多模态 Agent" \
  --hotword "阶跃星辰" \
  --hotword "StepAudio"
```

公开媒体直链：

```bash
python3 <skill-dir>/scripts/transcribe_audio.py \
  "https://example.com/audio/episode.mp3" \
  --output "/path/to/episode.txt" \
  --title "节目标题"
```

需要更短的分片时可调整时长，例如每片 5 分钟：

```bash
python3 <skill-dir>/scripts/transcribe_audio.py \
  "/path/to/long-meeting.m4a" \
  --output "/path/to/long-meeting.txt" \
  --segment-seconds 300
```

如果用户明确要求非中文识别，可用 `--language` 传入相应语言代码；未指定时保留默认值 `zh`。

## 输出与交付

成功时，脚本把纯文字稿写入 `--output`，进度信息写入标准错误流。向用户交付：

- 可点击的文字稿文件路径；
- 使用的输入来源和输出位置；
- 如果用户要求，再附简短摘要或后续处理结果。

不要在回复里粘贴超长全文，除非用户明确要求。不要删除原始媒体文件或中间以外的用户文件；脚本创建的临时转码和切片会自动清理。

## 常见失败

- `STEPFUN_API_KEY is not set`：请用户在本机环境设置 Key 后重试。
- `ffmpeg not found`：安装 ffmpeg，并确认命令在 `PATH` 中。
- `input does not exist`：核对附件落盘路径或用户给出的路径。
- `download failed`：URL 不是公开媒体直链、已过期或需要登录；请用户提供本地文件或新的直链。
- `StepFun HTTP 401/403`：Key 无效或权限不足。
- `StepFun HTTP 429`：脚本会自动重试；持续失败时稍后再试。
- `StepFun returned an empty transcript`：确认媒体中有清晰、可听见的语音，并检查 `--language` 是否匹配。
- 某个分片失败：保留错误信息，不把部分结果冒充完整文字稿。
