# willsho-skills

个人 Claude Code Skills 仓库，存放自定义 skill 的定义文件和配套脚本。

## Skills

| Skill | 功能 |
|-------|------|
| [transcript-to-article](skills/transcript-to-article/) | 将访谈/播客 transcript 转化为中文深度解读文章 |
| [local-cc-digest](skills/local-cc-digest/) | 扫描本地 Claude Code session，生成工作回顾报告 |

## 目录结构

```
skills/
└── <skill-name>/
    ├── SKILL.md          # skill 定义（含 YAML frontmatter）
    ├── evals/
    │   └── evals.json    # 评估测试用例
    └── scripts/          # 配套脚本（可选）
```
