# willsho-skills

个人 Codex / Claude Code Skills 仓库，存放自定义 skill 的定义文件、评估用例、参考材料和配套脚本。

## Skills

| Skill | 功能 | 配套文件 |
|-------|------|----------|
| [consumer-brand-growth](skills/consumer-brand-growth/) | 给消费品牌做增长诊断与方案，覆盖渠道、复购、新品、护城河等问题 | `references/` |
| [explain-diff-html](skills/explain-diff-html/) | 将代码变更 / diff / 分支 / PR 生成富交互的 HTML 讲解（背景、直觉、代码走读、测验） | - |
| [ip-flywheel](skills/ip-flywheel/) | 给 IP、角色、内容公司做飞轮诊断、商业化分析和打法方案 | `references/`, `evals/` |
| [local-cc-digest](skills/local-cc-digest/) | 扫描本地 Claude Code session，生成日报、周报或阶段回顾 | `scripts/`, `evals/` |
| [mole-cli](skills/mole-cli/) | 用 Mole (`mo`) macOS CLI 清理磁盘、卸载应用、分析存储、优化与监控系统 | - |
| [podwise-transcript](skills/podwise-transcript/) | 通过 Podwise CLI 获取 YouTube、播客或本地音视频的 transcript、summary、chapters 等内容 | - |
| [transcript-to-article](skills/transcript-to-article/) | 将访谈、播客或视频文字稿整理成中文深度解读文章 | `evals/` |
| [youtube-transcript](skills/youtube-transcript/) | 获取 YouTube 视频字幕 / transcript，并按语言优先级兜底 | `scripts/`, `evals/` |

## 目录结构

```text
skills/
└── <skill-name>/
    ├── SKILL.md          # skill 定义，必须包含 YAML frontmatter
    ├── evals/
    │   └── evals.json    # 评估测试用例，可选
    ├── references/       # 长参考材料或案例库，可选
    └── scripts/          # 配套脚本，可选
```

## SKILL.md 格式

每个 skill 的入口文件是 `SKILL.md`，格式为 YAML frontmatter 加 Markdown 正文：

```markdown
---
name: skill-name
description: >
  说明什么时候应该触发这个 skill。这里应覆盖用户可能使用的关键词、
  口语化表达、适用边界和不适用场景。
---

# Skill 标题

具体执行步骤、输出格式、注意事项和示例。
```

`description` 会直接影响触发准确率。新增或修改 skill 时，优先把触发场景写清楚，再补充正文工作流。

## 评估用例

有评估需求的 skill 可以放置 `evals/evals.json`：

```json
{
  "skill_name": "skill-name",
  "evals": [
    {
      "id": 1,
      "prompt": "测试提示词",
      "expected_output": "期望输出描述",
      "files": []
    }
  ]
}
```

评估用例应覆盖 `description` 里最重要的触发场景，尤其是容易误触发或漏触发的表达。

## 脚本与配置

- 脚本统一放在 skill 目录下的 `scripts/`，不要直接放在 skill 根目录。
- 长案例、框架、示例文章等材料统一放在 `references/`。
- 需要密钥或本地配置时，只提交 `*.example.*` 示例文件；不要提交真实 token、API key 或个人配置。
- 已包含 `config.json` 的本地目录在提交前要额外检查，避免把密钥写入 git 历史。

## 常用命令

```bash
# 查看所有 skill
find skills -maxdepth 2 -name SKILL.md | sort

# 快速检查仓库状态
git status --short

# 运行 local-cc-digest 示例
python3 skills/local-cc-digest/scripts/summarize_sessions.py --range week --json
```
