import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from pivoki_studio import rules


class FolderRules(unittest.TestCase):
    def test_explicit_enable_stability_deduplication_and_persistence(self):
        with TemporaryDirectory() as temp, patch.dict(os.environ, PIVOKI_DATA_DIR=temp):
            root = Path(temp, "in")
            out = Path(temp, "out")
            root.mkdir()
            out.mkdir()
            Path(root, "old.png").touch()
            key = rules.enable(root, out, "png", "pkg", 1, "skip", False)
            new = root / "new.png"
            new.touch()
            seen = []
            def dispatch(req):
                seen.append(req)
                return {"status": "planned" if req["action"] == "plan" else "success"}

            rules.tick(lambda: 0, dispatch)
            new.write_bytes(b"second chunk")
            rules.tick(lambda: 5, dispatch)
            rules.tick(lambda: 9, dispatch)
            self.assertFalse(seen)
            rules.tick(lambda: 12, dispatch)
            rules.tick(lambda: 100, dispatch)
            self.assertEqual([r["action"] for r in seen], ["plan", "run"])
            self.assertEqual(seen[0]["inputs"], [str(new.resolve())])
            self.assertEqual(seen[0]["planId"], seen[1]["planId"])
            rules.change(key, "pause")
            self.assertFalse(rules.definitions()[0]["enabled"])
            rules.change(key, "remove")
            self.assertTrue(new.is_file())
