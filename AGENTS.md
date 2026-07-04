# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## 仓库概述

这是一个 **Codex Skills（技能）** 仓库，存放自定义 skill 的定义文件和配套脚本。每个 skill 安装到 `~/.Codex/skills/` 后，由 Codex 的 FleetView harness 加载，使 Codex 能够在对话中识别并执行特定任务。

## 目录结构

```
skills/
└── <skill-name>/
    ├── SKILL.md          # skill 定义（必须，含 YAML frontmatter）
    ├── evals/
    │   └── evals.json    # 评估测试用例
    └── scripts/          # 配套脚本（可选）
        └── *.py
```

## Skill 文件格式

### SKILL.md

每个 skill 的核心文件，使用 YAML frontmatter + Markdown 正文：

```yaml
---
name: skill-name           # skill 唯一标识符，kebab-case
description: >             # 触发描述（很重要：harness 用此决定何时调用 skill）
  详细描述何时触发，包含关键词列表和边界场景
---
```

正文为 skill 的执行指令，Codex 在 skill 被触发后会遵循这些指令工作。

### evals/evals.json

```json
{
  "skill_name": "skill-name",
  "evals": [
    {
      "id": 1,
      "prompt": "测试提示词（可用 {output_dir} 占位符）",
      "expected_output": "期望输出的描述",
      "files": ["需要的文件路径列表"]
    }
  ]
}
```

## 现有 Skills

### transcript-to-article
将访谈/播客 transcript 转化为中文深度解读文章（Markdown 格式），包含 YAML frontmatter、要点速览、分节正文、编辑手记等结构。

### local-cc-digest
通过 `scripts/summarize_sessions.py` 扫描 `~/.Codex/projects/` 的 JSONL session 文件，生成工作回顾报告。

**脚本用法：**
```bash
python3 skills/local-cc-digest/scripts/summarize_sessions.py --range week --json
python3 skills/local-cc-digest/scripts/summarize_sessions.py --range today
python3 skills/local-cc-digest/scripts/summarize_sessions.py --project <keyword> --range month --json
```

## 新增 Skill 的注意事项

- `description` 字段直接影响 skill 触发准确率，需覆盖用户可能说的各种表达方式（含口语化表达）
- `evals.json` 的测试用例应覆盖 description 中提到的主要触发场景
- 配套脚本统一放在 `scripts/` 子目录，不要直接放在 skill 根目录
