#!/usr/bin/env python3
"""Link skills from a repository into Agents and Claude skill directories."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_TARGETS = (Path("~/.agents/skills"), Path("~/.claude/skills"))


@dataclass
class Counts:
    created: int = 0
    unchanged: int = 0
    repaired: int = 0
    conflicts: int = 0


def default_repo_root() -> Path:
    # resolve() follows the installed skill symlink back to this repository.
    return Path(__file__).resolve().parents[3]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Link skills/<name> directories into ~/.agents/skills and "
            "~/.claude/skills."
        )
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=default_repo_root(),
        help="repository root containing skills/ (defaults to this skill's repository)",
    )
    parser.add_argument(
        "--skill",
        action="append",
        default=[],
        help="link only this skill name; repeat to select multiple skills",
    )
    parser.add_argument(
        "--target",
        action="append",
        type=Path,
        default=[],
        help="destination skill directory; repeat as needed (replaces defaults)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show planned changes without modifying the filesystem",
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        help="replace symlinks that point elsewhere; never replaces real paths",
    )
    return parser.parse_args()


def discover_skills(repo_root: Path, selected: Iterable[str]) -> list[Path]:
    skills_root = repo_root.expanduser().resolve() / "skills"
    if not skills_root.is_dir():
        raise ValueError(f"repository has no skills directory: {skills_root}")

    discovered = {
        candidate.name: candidate.resolve()
        for candidate in skills_root.iterdir()
        if candidate.is_dir() and (candidate / "SKILL.md").is_file()
    }
    if not discovered:
        raise ValueError(f"no skills containing SKILL.md found in: {skills_root}")

    requested = list(dict.fromkeys(selected))
    if requested:
        missing = [name for name in requested if name not in discovered]
        if missing:
            raise ValueError("requested skills not found: " + ", ".join(missing))
        return [discovered[name] for name in requested]

    return [discovered[name] for name in sorted(discovered)]


def paths_match(link: Path, source: Path) -> bool:
    raw_target = Path(os.readlink(link))
    resolved_target = raw_target if raw_target.is_absolute() else link.parent / raw_target
    return resolved_target.resolve(strict=False) == source.resolve()


def ensure_target_dir(target: Path, dry_run: bool) -> bool:
    if os.path.lexists(target):
        if target.is_dir():
            return True
        print(f"ERROR target is not a directory: {target}", file=sys.stderr)
        return False

    if dry_run:
        print(f"WOULD_CREATE_DIRECTORY {target}")
    else:
        target.mkdir(parents=True, exist_ok=True)
        print(f"CREATED_DIRECTORY {target}")
    return True


def link_one(
    source: Path,
    destination: Path,
    *,
    dry_run: bool,
    repair: bool,
    counts: Counts,
) -> None:
    if destination.is_symlink():
        if paths_match(destination, source):
            print(f"UNCHANGED {destination} -> {source}")
            counts.unchanged += 1
            return

        current = os.readlink(destination)
        if not repair:
            print(
                f"CONFLICT {destination} is a symlink to {current}; "
                "rerun with --repair to replace it",
                file=sys.stderr,
            )
            counts.conflicts += 1
            return

        if dry_run:
            print(f"WOULD_REPAIR {destination} -> {source}")
        else:
            destination.unlink()
            destination.symlink_to(source, target_is_directory=True)
            print(f"REPAIRED {destination} -> {source}")
        counts.repaired += 1
        return

    if os.path.lexists(destination):
        print(
            f"CONFLICT {destination} already exists and is not a symlink; preserved",
            file=sys.stderr,
        )
        counts.conflicts += 1
        return

    if dry_run:
        print(f"WOULD_CREATE {destination} -> {source}")
    else:
        destination.symlink_to(source, target_is_directory=True)
        print(f"CREATED {destination} -> {source}")
    counts.created += 1


def main() -> int:
    args = parse_args()
    try:
        sources = discover_skills(args.repo, args.skill)
    except ValueError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2

    raw_targets = args.target or list(DEFAULT_TARGETS)
    # Keep the destination path itself unresolved so a broken target symlink is
    # reported as invalid instead of accidentally creating its dangling target.
    targets = list(
        dict.fromkeys(Path(os.path.abspath(target.expanduser())) for target in raw_targets)
    )
    counts = Counts()

    usable_targets: list[Path] = []
    for target in targets:
        if ensure_target_dir(target, args.dry_run):
            usable_targets.append(target)
        else:
            counts.conflicts += len(sources)

    for target in usable_targets:
        for source in sources:
            link_one(
                source,
                target / source.name,
                dry_run=args.dry_run,
                repair=args.repair,
                counts=counts,
            )

    print(
        "SUMMARY "
        f"skills={len(sources)} targets={len(targets)} "
        f"created={counts.created} unchanged={counts.unchanged} "
        f"repaired={counts.repaired} conflicts={counts.conflicts} "
        f"dry_run={str(args.dry_run).lower()}"
    )
    return 1 if counts.conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
