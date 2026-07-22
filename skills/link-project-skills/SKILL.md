---
name: link-project-skills
description: >-
  Symlink skills from a skills repository (`skills/*/SKILL.md`) into both
  `~/.agents/skills` and `~/.claude/skills`, so Codex/Agents and Claude use the
  same source directories. Use this whenever the user asks to install,
  register, expose, batch-link, sync, 软链接, or 符号链接 a project's skills to
  Agents/Codex and Claude skill directories, even if they only say “同步这个项目的
  skills” without naming the destination paths.
compatibility: Requires Python 3 and a filesystem that supports symbolic links.
---

# Link Project Skills

Use the bundled `scripts/link_skills.py` script instead of assembling many
individual link commands. The script discovers valid skills by looking for
`skills/<name>/SKILL.md`, creates the destination directories when needed, and
prints a result for every link. In the examples below, resolve
`<skill-directory>` to the directory containing this `SKILL.md`; do not pass
the placeholder literally.

## Workflow

1. Identify the source repository.
   - When this skill belongs to the repository being linked, run the script
     without `--repo`; it resolves the repository from its own real path.
   - When the user names a different repository, pass its root with `--repo`.
2. Run the script. A request to install, link, or sync the skills authorizes
   creating the links, so a preview is unnecessary unless the user asks for
   one.
3. Read the summary and report how many links were created, already correct,
   repaired, or blocked by conflicts.
4. If a destination contains a real file/directory or a symlink to another
   source, preserve it and explain the conflict. Use `--repair` only when the
   user explicitly wants incorrect symlinks replaced; `--repair` still never
   overwrites real files or directories.

## Commands

Link every valid skill in this repository to both default destinations:

```bash
python3 <skill-directory>/scripts/link_skills.py
```

Link skills from another repository:

```bash
python3 <skill-directory>/scripts/link_skills.py --repo /path/to/repository
```

Link only selected skills:

```bash
python3 <skill-directory>/scripts/link_skills.py --skill first-skill --skill second-skill
```

Preview without changing the filesystem:

```bash
python3 <skill-directory>/scripts/link_skills.py --dry-run
```

For isolated testing or a custom installation, repeat `--target` as needed. If
any `--target` is supplied, it replaces the two default destinations.

## Safety behavior

- Treat an existing link to the same source as success, making repeated runs
  idempotent.
- Never delete or modify a source skill.
- Never replace a destination that is a real file or directory.
- Do not treat every directory under `skills/` as a skill; require `SKILL.md`.
- Return a non-zero status when requested skills are missing, the repository is
  invalid, or unresolved conflicts remain, so callers do not mistake a partial
  installation for full success.
