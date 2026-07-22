# willsho-skills

个人 Codex / Claude Code Skills 仓库，存放自定义 skill 的定义文件、评估用例、参考材料和配套脚本。

## Skills

| Skill | 功能 | 配套文件 |
|-------|------|----------|
| [gpt-image-gen](skills/gpt-image-gen/) | 用 apimart.ai 的 GPT-Image-2 生成图片（文生图、图生图），支持 15 种比例与 1K/2K/4K 分辨率，最多 16 张参考图 | `scripts/`, `references/` |
| [link-project-skills](skills/link-project-skills/) | 把仓库内的 skills 批量软链接到 Agents/Codex 与 Claude 的用户级技能目录 | `scripts/`, `evals/` |
| [local-cc-digest](skills/local-cc-digest/) | 扫描本地 Claude Code session，生成日报、周报或阶段回顾 | `scripts/`, `evals/` |
| [mole-cli](skills/mole-cli/) | 用 Mole (`mo`) macOS CLI 清理磁盘、卸载应用、分析存储、优化与监控系统 | - |
| [podwise-transcript](skills/podwise-transcript/) | 通过 Podwise CLI 获取 YouTube、播客或本地音视频的 transcript、summary、chapters 等内容 | - |
| [stepfun-audio-transcription](skills/stepfun-audio-transcription/) | 使用 StepFun `stepaudio-2.5-asr` 将本地音视频或公开媒体直链转成文字稿，支持标题热词、手动热词和按时长切片 | `scripts/`, `evals/` |
| [transcript-to-article](skills/transcript-to-article/) | 将访谈、播客或视频文字稿整理成中文深度解读文章 | `evals/` |
| [youtube-transcript](skills/youtube-transcript/) | 获取 YouTube 视频字幕 / transcript，并按语言优先级兜底 | `scripts/`, `evals/` |

## Skills Beta

| Skill | 功能 | 配套文件 |
|-------|------|----------|
| [consumer-brand-growth](skills/consumer-brand-growth/) | 给消费品牌做增长诊断与方案，覆盖渠道、复购、新品、护城河等问题 | `references/` |
| [deploy-html-cloudflare](skills/deploy-html-cloudflare/) | 把 HTML 页面或静态站点目录通过 Cloudflare Pages Direct Upload 部署上线，返回可访问 URL，含敏感信息扫描与结构化 JSON 结果 | `scripts/`, `evals/` |
| [deploy-html-vercel](skills/deploy-html-vercel/) | 一键把静态 HTML 页面或站点目录部署到 Vercel，返回可访问线上 URL，含 token 脱敏与密钥泄露扫描 | `scripts/`, `evals/` |
| [focus-my-energy](skills/focus-my-energy/) | 把一天 / 一周的待办对齐到精力节律，按高 / 中 / 低精力窗口安排深度工作与杂事 | `evals/` |
| [get-more-perspectives](skills/get-more-perspectives/) | 在有分量且答案不唯一的决策拍板前，先给出 3-5 个真正不同的视角，铺开选项与权衡 | `evals/` |
| [interview-coach](skills/interview-coach/) | 提供面试前准备、模拟面试、面后复盘与长期能力积累，把岗位线索和真实经历转化为针对性训练 | `references/`, `evals/` |
| [ip-flywheel](skills/ip-flywheel/) | 给 IP、角色、内容公司做飞轮诊断、商业化分析和打法方案 | `references/`, `evals/` |
| [match-my-writing-style](skills/match-my-writing-style/) | 从你的真实写作样本学习文风，存成可复用的「文风档案」并套用到新写作 | `references/`, `evals/` |
| [shangtou-changwen](skills/shangtou-changwen/) | 把平铺直叙的中文草稿改写成「上头毒舌磕学家」式网络长帖文风，可套用于追星、剧评、热点锐评、CP 分析等 | `references/` |

## 来自其他 builders 的 Skills

| Skill | 功能 | 配套文件 |
|-------|------|----------|
| [explain-diff-html](skills/explain-diff-html/) | 将代码变更 / diff / 分支 / PR 生成富交互的 HTML 讲解（背景、直觉、代码走读、测验） | - |
| [khazix-writer](skills/khazix-writer/) | 以「数字生命卡兹克」的文风撰写、续写或扩写公众号长文 | `references/` |

> **来源：** `explain-diff-html` 改编自 Geoffrey Litt 的 [gist](https://gist.github.com/geoffreylitt/a29df1b5f9865506e8952488eac3d524)。延伸阅读：[Understanding is the new bottleneck](https://www.geoffreylitt.com/2026/07/02/understanding-is-the-new-bottleneck.html)。

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

## 安装与同步 Skills

仓库内置了 [`link-project-skills`](skills/link-project-skills/)：它会扫描
`skills/*/SKILL.md`，并用符号链接让 Codex / Agents 与 Claude 共用仓库里的同一份源码。
修改源 skill 后，不需要重复复制文件。

把仓库内的全部 skills 安装到用户级目录 `~/.agents/skills` 和
`~/.claude/skills`：

```bash
python3 skills/link-project-skills/scripts/link_skills.py
```

只把引导技能安装到当前项目的 `.agents/skills` 和 `.claude/skills`：

```bash
python3 skills/link-project-skills/scripts/link_skills.py \
  --skill link-project-skills \
  --target .agents/skills \
  --target .claude/skills
```

常用选项：

- `--dry-run`：只预览，不修改文件系统；
- `--skill <name>`：只同步指定 skill，可重复传入；
- `--repo <path>`：从另一个 skill 仓库读取；
- `--repair`：替换指向错误来源的旧符号链接，但仍不会覆盖真实文件或目录。

脚本可安全重复执行：正确的现有链接会标记为 `UNCHANGED`；遇到同名真实内容时会保留原内容、报告冲突并返回非零状态。

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

## StepFun 音频转写

`stepfun-audio-transcription` 使用 StepFun `stepaudio-2.5-asr` 转写本地音频、本地视频或无需登录即可下载的媒体直链。运行前需要：

- Python 3
- `ffmpeg`
- 环境变量 `STEPFUN_API_KEY`

```bash
export STEPFUN_API_KEY="<your-key>"

python3 skills/stepfun-audio-transcription/scripts/transcribe_audio.py \
  "/path/to/interview.m4a" \
  --output "/path/to/interview.txt" \
  --title "访谈标题" \
  --hotword "专有名词"
```

脚本会在一次 ffmpeg 处理中把媒体转成 16 kHz、单声道、32 kbps MP3，并直接按时长分片：

- 默认每片最多 600 秒（10 分钟）；
- 不足 600 秒的媒体只生成一片；
- 使用 `--segment-seconds 300` 可改为每片最多 5 分钟；
- 各片依次调用 StepFun，成功后按原顺序合并为纯文字稿。

公开媒体直链也可以直接作为输入：

```bash
python3 skills/stepfun-audio-transcription/scripts/transcribe_audio.py \
  "https://example.com/episode.m4a" \
  --output "./episode.txt"
```

小宇宙单集页面不是音频直链，当前需要先从页面解析出 `media.xyzcdn.net` 的 `.m4a` / `.mp3` 地址，再传给脚本。API Key 只通过环境变量提供，不要写入命令、配置文件或仓库。

## 常用命令

```bash
# 查看所有 skill
find skills -maxdepth 2 -name SKILL.md | sort

# 快速检查仓库状态
git status --short

# 运行 local-cc-digest 示例
python3 skills/local-cc-digest/scripts/summarize_sessions.py --range week --json

# 测试 skills 符号链接脚本
python3 skills/link-project-skills/scripts/test_link_skills.py

# 运行 StepFun 音频转写的离线测试
python3 skills/stepfun-audio-transcription/scripts/test_transcribe_audio.py
```
