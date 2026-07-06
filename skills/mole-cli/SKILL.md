---
name: mole-cli
description: >-
  How to use the Mole (`mo`) macOS CLI to clean, uninstall, analyze, optimize,
  and monitor a Mac. Use this whenever the user wants to free up disk space,
  find what's eating storage, uninstall an app and its leftovers, clean caches /
  build artifacts, check CPU/memory/disk/GPU health, or mentions "mole" / "mo" /
  清理 Mac / 卸载应用 / 磁盘分析 / 系统监控 / 释放空间. Also use it before running
  any `mo ...` command so you pick the agent-safe, non-interactive path instead
  of launching a TUI that will hang the session.
---

# Mole (`mo`) CLI

Mole is a macOS all-in-one maintenance CLI (clean, uninstall, disk analysis, optimize, system monitor). The installed binary is **`mo`** (the Homebrew package is `mole`). It is **macOS only**.

## The one thing to get right: interactive vs. scriptable

Most `mo` commands open a **full-screen TUI** (arrow keys / Vim `h j k l`). As an agent you cannot drive these — running one will block until it's killed. Before running anything, sort the command into one of these buckets:

| Bucket | Commands | How to run as an agent |
|---|---|---|
| **Scriptable (safe)** | `mo analyze --json`, `mo status --json`, `mo history`, `mo --version`, `mo --help` | Run directly, capture stdout, parse. |
| **Preview-only** | any destructive command with `--dry-run` | Run to *report* what would change. Never run the real (non-dry) version yourself. |
| **Interactive / destructive** | `mo` (menu), `mo clean`, `mo uninstall`, `mo optimize`, `mo purge`, `mo installer`, `mo remove`, `mo touchid` | Do **not** launch these yourself — they need a human at the TUI and confirm destructive deletes. Give the user the exact command to run in their own terminal. |

Rule of thumb: if you're *reading* system state, use the `--json` commands. If you're *changing* the system, produce a `--dry-run` report and hand the real command to the user.

## Reading system state (do this yourself)

`mo status` auto-switches to JSON when its output is piped, but pass `--json` explicitly to be safe:

```bash
mo status --json                 # health_score, cpu, memory, disks, uptime, host
mo status --json | jq '.health_score'
```

`mo analyze` explores disk usage. Give it a path so it doesn't scan everything:

```bash
mo analyze --json ~/Documents    # {path, overview, entries[], large_files[], total_size, total_files}
mo analyze --json /Volumes       # external drives (skipped by default otherwise)
```

Each `entries[]`/`large_files[]` item has `name`, `path`, `size` (and `is_dir` for entries) — use these to point the user at the biggest space hogs.

`mo history` shows past operations (add `--json` for machine-readable):

```bash
mo history --json
```

## Changing the system (report, then hand off)

These delete files or modify the system, so they confirm interactively. Preview with `--dry-run` (add `--debug` for detail), summarize the result, then give the user the real command to run themselves.

```bash
mo clean --dry-run --debug   # caches, logs, leftovers of uninstalled apps
mo uninstall --dry-run       # remove an app + its hidden leftovers
mo purge --dry-run           # project build artifacts (node_modules, target, etc.)
mo installer --dry-run       # find & remove leftover installer files
mo optimize --dry-run        # refresh caches & services
```

`--dry-run` is supported by `clean`, `uninstall`, `purge`, `optimize`, `installer`, `remove`, `completion`, and `touchid enable`.

Safety notes worth relaying to the user:
- Mole is safety-first: it validates paths, protects system directories, and skips/refuses when uncertain rather than widening the delete scope.
- `mo purge` leaves projects modified in the last 7 days unselected by default.
- `mo analyze` moves files to Trash via Finder (recoverable), not a hard delete.

## Configuration & environment

- `MO_NO_OPLOG=1` — disable the operation log at `~/Library/Logs/mole/operations.log`.
- `MO_LAUNCHER_APP=<name>` — override terminal auto-detection (iTerm2 has known issues).
- `mo clean --whitelist`, `mo optimize --whitelist` — manage protected rules.
- `mo purge --paths` — configure scan dirs (also `~/.config/mole/purge_paths`; defaults `~/Projects`, `~/GitHub`, `~/dev`). Install `fd` (`brew install fd`) for best purge results.
- `mo status --proc-cpu-alerts=false` (also `--proc-cpu-threshold`, `--proc-cpu-window`) — tune process CPU alerts.

## Install / update / remove

```bash
brew install mole                                                    # macOS 14+
curl -fsSL https://raw.githubusercontent.com/tw93/mole/main/install.sh | bash
mo update            # update (add --nightly for latest main, script-install only)
mo remove            # uninstall Mole itself
```

If `mo` isn't found, check it's installed (`command -v mo`) and confirm the platform is macOS — Mole doesn't run on Linux/Windows (an experimental Windows branch aside).
