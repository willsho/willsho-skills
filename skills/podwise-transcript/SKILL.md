---
name: podwise-transcript
description: 通过 podwise CLI 获取 YouTube 视频或播客的 transcript（文字稿）、summary、chapters 等内容。当用户提供 YouTube URL、播客 URL 或 Podwise episode URL，想要获取 transcript、字幕、文字稿、summary、摘要、章节、Q&A、mind map、highlights 时，立即使用此 skill。即使用户只说"帮我拿一下这个视频的文字"、"获取 transcript"、"这个播客有没有文字稿"，只要涉及 podwise、YouTube 或播客内容提取，都应触发此 skill。
---

# Podwise Transcript Skill

使用 podwise CLI 将 YouTube 视频或播客 URL 转为 transcript 及其他 AI 分析内容。

## 支持的输入格式

- YouTube：`https://www.youtube.com/watch?v=<id>` 或 `https://youtu.be/<id>`
- 小宇宙：`https://www.xiaoyuzhoufm.com/episode/<id>`
- Podwise episode：`https://podwise.ai/dashboard/episodes/<id>`
- 本地音视频文件：`.mp3 .wav .m4a .mp4 .m4v .mov .webm`

## 工作流程

### 第一步：提交处理

```bash
podwise process "<url>"
```

命令会自动轮询直到处理完成（最多 30 分钟）。输出中会包含 episode URL，格式为：
```
Imported: "<标题>" → episode: https://podwise.ai/dashboard/episodes/<id>
```

如果 URL 已经是 Podwise episode URL，可以跳过此步骤，直接进入第二步。

### 第二步：获取内容

使用从第一步输出中提取的 episode URL：

```bash
# 获取完整 transcript（带时间戳和说话人标签）
podwise get transcript https://podwise.ai/dashboard/episodes/<id>

# 其他可用内容
podwise get summary    <episode_url>   # AI 摘要和关键要点
podwise get chapters   <episode_url>   # 章节目录（带时间戳）
podwise get qa         <episode_url>   # AI 提取的 Q&A 对
podwise get mindmap    <episode_url>   # Markdown 格式思维导图
podwise get highlights <episode_url>   # 精彩片段（带时间戳）
podwise get keywords   <episode_url>   # 主题关键词
```

**语言选项**：使用 `--lang` 获取翻译版本：
```bash
podwise get transcript <episode_url> --lang Chinese
# 可选：Chinese, Traditional-Chinese, English, Japanese, Korean
```

## 常见场景

**用户只要 transcript**：执行 process + get transcript，输出完整文字稿。

**用户要 transcript 并翻译成中文**：执行 process + `get transcript --lang Chinese`。

**用户要摘要**：执行 process + get summary。

**用户要多种内容**（如 transcript + summary）：process 只需跑一次，然后分别调用 get。

**本地文件**：
```bash
podwise process ./audio.mp3 --title "我的访谈"
```

## 注意事项

- `podwise process` 会消耗账户 credits，处理前可告知用户
- transcript 输出通常较大（数十 KB），会自动保存到本地文件
- 如果 episode 已处理过，`podwise get` 会直接从缓存返回，无需重复 process
- 不要使用 `--pretty` 或 `--pretty-no-pager` 参数（这些是给人类用的，不适合 AI agent）
