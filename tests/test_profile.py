import base64
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("profile_updater", ROOT / ".github/scripts/update_readme.py")
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


def content(value):
    return {"content": base64.b64encode(value.encode()).decode()}


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.date = "2026-01-01"
        self.archive = "archive/2026/01/2026-01-01.md"
        self.manifest = {"status": "complete", "published_date": self.date,
                         "feeds_published": 9, "feeds_expected": 9, "archive": self.archive}
        self.paths = ["STATUS.json", self.archive] + [
            f"feeds/{feed}/{self.date}.md" for feed in
            ("news", "trending", "research", "challenges", "tools", "prompts", "security", "market", "learning")]
        self.archive_body = "# Digest\n\n**Feeds:** 9/9 published\n"
        self.truncated = False
        self.calls = []

    def gh(self, path):
        self.calls.append(path)
        if path.endswith("/commits/main"):
            return {"sha": "immutable-sha"}
        if "/git/trees/" in path:
            return {"truncated": self.truncated, "tree": [
                {"path": p, "type": "blob", "size": 120} for p in self.paths]}
        if "/contents/STATUS.json" in path:
            return content(json.dumps(self.manifest))
        return content(self.archive_body)

    def render(self):
        with patch.object(updater, "gh", side_effect=self.gh):
            return updater.section_techpulse()

    def test_complete_manifest_and_archive_are_linked_at_immutable_revision(self):
        result = self.render()
        self.assertIn("9/9 feeds", result)
        self.assertIn("blob/immutable-sha/", result)
        self.assertIn("last complete publication", result)
        self.assertTrue(all("immutable-sha" in p for p in self.calls[1:]))

    def test_empty_index_archive_never_becomes_success(self):
        self.archive_body = "**Feeds:** 0/9 published\nNot yet published today."
        self.assertIn("unavailable", self.render())

    def test_missing_feed_rejects_complete_claim(self):
        self.paths.pop()
        self.assertIn("unavailable", self.render())

    def test_missing_manifest_is_explicitly_unverified(self):
        self.paths.remove("STATUS.json")
        self.assertIn("unverified", self.render())

    def test_truncated_tree_rejects_complete_claim(self):
        self.truncated = True
        self.assertIn("unavailable", self.render())

    def test_future_date_rejects_complete_claim(self):
        self.manifest["published_date"] = "2999-01-01"
        self.assertIn("unavailable", self.render())

    def test_network_failure_cannot_preserve_a_success_message(self):
        with patch.object(updater, "gh", side_effect=OSError("offline")):
            self.assertIn("unavailable", updater.section_techpulse())

    def test_main_offline_replaces_old_publication_claim_and_preserves_markers(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "README.md"
            path.write_text((ROOT / "README.md").read_text())
            with patch.object(updater, "README", path), patch.object(updater, "gh", side_effect=OSError("offline")):
                updater.main()
            rendered = path.read_text()
            self.assertIn("Publication status unavailable", rendered)
            self.assertNotIn("Last verified complete digest", rendered)
            self.assertNotIn("WAKATIME_API_KEY", rendered)
            for key in ("TECHPULSE", "LATEST_BUILDS", "ACTIVITY", "SNAPSHOT", "LANGS", "UPDATED"):
                self.assertEqual(rendered.count(f"<!-- {key}:START -->"), 1)
                self.assertEqual(rendered.count(f"<!-- {key}:END -->"), 1)


if __name__ == "__main__":
    unittest.main()
