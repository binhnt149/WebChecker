from pathlib import Path
import hashlib
import tempfile
import unittest

from scripts.stage_release import filenames, PLATFORMS, stage, verify
from scripts.validate_release import app_version, validate_ref


class ReleaseToolsTests(unittest.TestCase):
    def test_tag_must_match_version(self) -> None:
        version = app_version()
        validate_ref(f"refs/tags/v{version}", version)
        validate_ref("refs/heads/main", version)
        for ref in ["refs/tags/v0.0.0", "refs/tags/v1.1.0;echo hacked", "refs/tags/v1.1.0-beta"]:
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                validate_ref(ref, version)

    def test_stage_and_verify_all_packages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "dist", Path(directory) / "release"
            source.mkdir()
            for name in ["SiteSentry Desktop.exe", "SiteSentry-Desktop-Windows.zip", "SiteSentry-Desktop-macOS.dmg"]:
                (source / name).write_bytes(b"package fixture")
            for platform in PLATFORMS:
                stage(platform, source, output, "1.1.0")
            verify(output, "1.1.0")
            expected = sorted(name for platform in PLATFORMS for name in filenames("1.1.0", platform))
            lines = (output / "SHA256SUMS.txt").read_text().splitlines()
            self.assertEqual(len(lines), 4)
            for line, name in zip(lines, expected):
                self.assertEqual(line, f"{hashlib.sha256(b'package fixture').hexdigest()}  {name}")
            verify(output, "1.1.0")
            (output / expected[0]).unlink()
            with self.assertRaises(ValueError):
                verify(output, "1.1.0")

    def test_missing_or_empty_artifacts_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "dist", Path(directory) / "release"
            source.mkdir()
            with self.assertRaises(ValueError):
                stage("Windows-x64", source, output, "1.1.0")
            (source / "SiteSentry-Desktop-macOS.dmg").touch()
            with self.assertRaises(ValueError):
                stage("macOS-arm64", source, output, "1.1.0")
            with self.assertRaises(ValueError):
                filenames("1.1.0", "other")
