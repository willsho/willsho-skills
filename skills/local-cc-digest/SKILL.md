---
name: local-cc-digest
description: 生成 Claude Code 工作回顾报告。当用户问"这周做了什么"、"帮我回顾一下"、"工作日报"、"工作周报"、"最近在忙什么"、"总结一下这段时间"、"claude 帮我干了哪些事"、"session 摘要"等，都应触发此 skill。即使用户只是随口问"上周都做了啥"、"这个月的工作"，只要语境与回顾 Claude 协作内容有关，都应触发。
---

# Local Claude Code Work Digest

从本地 `~/.claude/projects/` 目录解析 session JSONL 文件，提取完整对话（用户消息 + Claude 回复），生成一份详实的工作回顾报告。

## 为什么需要这个 skill

Claude Code 的每次对话都存储在本地 JSONL 文件中，但没有内置的方式来回顾"这段时间里我和 Claude 都做了什么"。这个 skill 解决了这个问题：

- 写日报/周报时快速回忆工作内容
- 回顾某个项目的推进历史
- 了解自己在哪些方向花了最多时间

## 数据来源

与 `local-cc-cost` 使用相同的数据源：

```
~/.claude/projects/
└── <project-path>/
    └── <session-uuid>.jsonl
```

脚本同时提取两类消息：
- `type: "user"` — 用户发出的指令，代表"我让 Claude 做什么"
- `type: "assistant"` — Claude 的文字回复，代表"Claude 实际做了什么、得出了什么结论"

工具调用（tool_use）和工具结果（tool_result）会被过滤，只保留有信息量的文字内容。

## 使用方式

**第一步：运行脚本提取原始数据**

```bash
python3 ~/.claude/skills/local-cc-digest/scripts/summarize_sessions.py [OPTIONS]
```

### 常用参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--range today` | 今天 | |
| `--range week` | 本周（周一起） | |
| `--range month` | 本月 | |
| `--range YYYY-MM-DD` | 指定某天 | `--range 2026-04-01` |
| `--range YYYY-MM-DD:YYYY-MM-DD` | 日期范围 | `--range 2026-03-25:2026-04-07` |
| `--project <keyword>` | 按项目名筛选 | `--project blindbox` |
| `--json` | 输出 JSON 格式（推荐，便于后续处理） | |
| `--max-turns <n>` | 每个 session 最多提取 n 轮对话（user+assistant 各算1轮，默认 30） | |

### 典型场景

**用户问"这周做了什么"：**
```bash
python3 ~/.claude/skills/local-cc-digest/scripts/summarize_sessions.py --range week --json
```

**用户问"blindbox 项目最近的进展"：**
```bash
python3 ~/.claude/skills/local-cc-digest/scripts/summarize_sessions.py --project blindbox --range month --json
```

**用户问"今天帮我干了哪些事"：**
```bash
python3 ~/.claude/skills/local-cc-digest/scripts/summarize_sessions.py --range today --json
```

**第二步：对脚本输出做智能摘要**

拿到 JSON 数据后，同时阅读 `turns` 中的 user 和 assistant 消息，理解每个 session 的完整工作内容，生成工作回顾报告。

## 报告生成要求

### 核心原则

- **从对话中提炼结果**：user 消息告诉你"我想做什么"，assistant 消息告诉你"实际做了什么、得出了什么结论"。两者结合才能写出有实质内容的报告
- **写结果，不写过程**：不是"讨论了 XX"，而是"确定了 XX 方案"、"实现了 XX 功能"、"发现了 XX 问题"
- **保留有价值的细节**：代码改动（文件名、行数）、关键数据（指标、测试结果）、重要结论（产品决策、技术方案）都应保留，这些是报告有价值的地方
- **按项目分组，重要 session 可展开**：跨多个项目时按项目分组；同一项目内工作量大的 session 可以有二级结构（如"代码调研"、"方案设计"、"代码实现"）
- **语言简洁**：中文，动词开头，信息密度高

### 报告结构

根据内容量灵活选择：

**简单场景**（session 少、工作内容单一）：
```
## 工作回顾 — [时间范围]

### 📁 [项目名]（共 N 个 session）

**[日期]**
- [动词短语 + 关键细节]
- [动词短语 + 关键细节]

### 📊 汇总
- 总 session 数：N / 涉及项目：A、B / 主要方向：...
```

**复杂场景**（session 多、工作内容丰富）：
```
## 工作回顾 — [时间范围]

### 📁 [项目名]（共 N 个 session）

#### [子方向/阶段名]（日期）
[2-4 句话描述这个子方向做了什么，包含关键细节]

#### [子方向/阶段名]（日期）
...

### 📁 [另一个项目]
...

### 📊 汇总
- 总 session 数：N
- 涉及项目：A、B、C
- 本期亮点：[1-2 条最重要的成果]
```

## 注意事项

- 脚本只读取**主 session 文件**，不包含 subagent 子会话（避免噪音）
- 每个 session 默认最多提取 30 轮对话；超长 session 可用 `--max-turns` 调整
- 短小的填充消息（"继续"、"好的"等）已在脚本层过滤，无需处理
- 如果某个 session 的内容很少（如只有 1-2 条消息），可以合并到同日其他 session 中简短描述
