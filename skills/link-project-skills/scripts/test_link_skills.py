#!/usr/bin/env python3
"""Regression tests for link_skills.py."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("link_skills.py")


class LinkSkillsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.repo = self.root / "repo"
        self.targets = [self.root / "agents", self.root / "claude"]
        for name in ("alpha", "beta"):
            skill = self.repo / "skills" / name
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(f"---\nname: {name}\n---\n")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_script(self, *extra: str) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, str(SCRIPT), "--repo", str(self.repo)]
        for target in self.targets:
            command.extend(("--target", str(target)))
        command.extend(extra)
        return subprocess.run(command, text=True, capture_output=True, check=False)

    def assert_link(self, target: Path, name: str) -> None:
        link = target / name
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), (self.repo / "skills" / name).resolve())

    def test_links_all_skills_to_both_targets(self) -> None:
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        for target in self.targets:
            self.assert_link(target, "alpha")
            self.assert_link(target, "beta")
        self.assertIn("created=4", result.stdout)

    def test_repeated_run_is_idempotent(self) -> None:
        self.assertEqual(self.run_script().returncode, 0)
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("created=0", result.stdout)
        self.assertIn("unchanged=4", result.stdout)

    def test_real_path_conflict_is_preserved(self) -> None:
        conflict = self.targets[0] / "alpha"
        conflict.mkdir(parents=True)
        marker = conflict / "keep.txt"
        marker.write_text("keep")

        result = self.run_script()

        self.assertEqual(result.returncode, 1)
        self.assertEqual(marker.read_text(), "keep")
        self.assertFalse(conflict.is_symlink())
        self.assert_link(self.targets[0], "beta")
        self.assert_link(self.targets[1], "alpha")
        self.assert_link(self.targets[1], "beta")
        self.assertIn("conflicts=1", result.stdout)

    def test_repair_replaces_only_wrong_symlink(self) -> None:
        wrong_source = self.root / "wrong-alpha"
        wrong_source.mkdir()
        self.targets[0].mkdir()
        (self.targets[0] / "alpha").symlink_to(wrong_source)

        result = self.run_script("--repair", "--skill", "alpha")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_link(self.targets[0], "alpha")
        self.assert_link(self.targets[1], "alpha")
        self.assertIn("repaired=1", result.stdout)
        self.assertIn("created=1", result.stdout)

    def test_broken_target_symlink_is_rejected(self) -> None:
        broken_target = self.root / "broken-target"
        dangling_destination = self.root / "must-not-be-created"
        broken_target.symlink_to(dangling_destination)
        self.targets = [broken_target]

        result = self.run_script()

        self.assertEqual(result.returncode, 1)
        self.assertTrue(broken_target.is_symlink())
        self.assertFalse(dangling_destination.exists())
        self.assertIn("target is not a directory", result.stderr)


if __name__ == "__main__":
    unittest.main()
