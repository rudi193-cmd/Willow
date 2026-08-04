"""Gates for the doc-integrity gate.

Each check gets a case that should pass and a mutated case that should fail —
"a gate that cannot fail is not a gate."

Two distinct jobs here:

  1. The **body-hash pin** on the vendored `check_docs.py`. That catches a local
     edit to the vendored copy. It cannot catch the canonical advancing while
     this copy stays behind — that is the CI `vendor-sync` diff's job, and
     neither substitutes for the other. This is the failure that left
     `friction_floor` running a known-defective detector (box-scan A8).

  2. The **registry** in doc_gate, which must fail on a new break AND on a
     registered break that no longer fires.
"""
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import check_docs  # noqa: E402
import doc_gate  # noqa: E402

# sha256 of tools/check_docs.py as vendored from willow-grove on 2026-08-04.
# If this fails, the vendored copy was edited locally. Do not update the pin to
# make it pass — revert the edit, or land the change upstream in willow-grove
# and re-vendor.
CHECK_DOCS_SHA256 = "64742bd28f35067d5ccdfe77fb91847a7a778185ae737a789f8a156edbcffa65"


class VendorPin(unittest.TestCase):
    def test_vendored_checker_is_unmodified(self):
        body = (TOOLS / "check_docs.py").read_bytes()
        self.assertEqual(
            hashlib.sha256(body).hexdigest(),
            CHECK_DOCS_SHA256,
            "tools/check_docs.py differs from the vendored canonical. Revert the local "
            "edit, or change it in willow-grove and re-vendor — do not repin.",
        )


def _repo(tmp: Path, docs: dict[str, str]) -> Path:
    for name, text in docs.items():
        p = tmp / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return tmp


class CheckerBehaviour(unittest.TestCase):
    """The vendored checker, exercised directly — the gate is only as good as this."""

    def setUp(self):
        import tempfile
        self._d = tempfile.TemporaryDirectory()
        self.tmp = Path(self._d.name)

    def tearDown(self):
        self._d.cleanup()

    def test_clean_repo_reports_nothing(self):
        _repo(self.tmp, {"a.md": "# Title\n\n[ok](b.md)\n", "b.md": "# B\n"})
        self.assertEqual(check_docs.check(self.tmp), [])

    def test_missing_link_target_is_caught(self):
        _repo(self.tmp, {"a.md": "# Title\n\n[gone](nope.md)\n"})
        errs = check_docs.check(self.tmp)
        self.assertEqual(len(errs), 1)
        self.assertIn("nope.md", errs[0])

    def test_bad_anchor_is_caught(self):
        _repo(self.tmp, {"a.md": "# Title\n\n[x](#no-such-heading)\n"})
        self.assertIn("anchor", check_docs.check(self.tmp)[0])

    def test_good_anchor_passes(self):
        _repo(self.tmp, {"a.md": "# Real Heading\n\n[x](#real-heading)\n"})
        self.assertEqual(check_docs.check(self.tmp), [])

    def test_external_links_are_not_checked(self):
        _repo(self.tmp, {"a.md": "# T\n\n[x](https://example.invalid/nope)\n"})
        self.assertEqual(check_docs.check(self.tmp), [])


class Registry(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = tempfile.TemporaryDirectory()
        self.tmp = Path(self._d.name)
        self._saved = dict(doc_gate.KNOWN_BROKEN)

    def tearDown(self):
        doc_gate.KNOWN_BROKEN.clear()
        doc_gate.KNOWN_BROKEN.update(self._saved)
        self._d.cleanup()

    def test_a_registered_break_is_tolerated(self):
        _repo(self.tmp, {"a.md": "# T\n\n[gone](nope.md)\n"})
        msg = check_docs.check(self.tmp)[0]
        doc_gate.KNOWN_BROKEN.clear()
        doc_gate.KNOWN_BROKEN[msg] = "test fixture"
        new, stale = doc_gate.evaluate(self.tmp)
        self.assertEqual((new, stale), ([], []))

    def test_a_new_break_fails(self):
        _repo(self.tmp, {"a.md": "# T\n\n[gone](nope.md)\n"})
        doc_gate.KNOWN_BROKEN.clear()
        new, stale = doc_gate.evaluate(self.tmp)
        self.assertEqual(len(new), 1)
        self.assertEqual(stale, [])

    def test_a_fixed_break_still_registered_fails(self):
        """The direction that keeps the registry honest."""
        _repo(self.tmp, {"a.md": "# T\n", "b.md": "# B\n"})
        doc_gate.KNOWN_BROKEN.clear()
        doc_gate.KNOWN_BROKEN["a.md: link target 'gone.md' does not exist"] = "fixture"
        new, stale = doc_gate.evaluate(self.tmp)
        self.assertEqual(new, [])
        self.assertEqual(len(stale), 1)

    def test_the_live_registry_matches_the_live_repo(self):
        """Against the real charter repo: no new breaks, no stale entries."""
        new, stale = doc_gate.evaluate(doc_gate.ROOT)
        self.assertEqual(new, [], f"new broken reference(s): {new}")
        self.assertEqual(stale, [], f"KNOWN_BROKEN entries that no longer fire: {stale}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
