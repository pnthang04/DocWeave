"""Check the installed packages and resources after relocating BabelDOC."""

import importlib.metadata
import unittest
from pathlib import Path

import babeldoc

import docweave


class RepositoryLayoutTest(unittest.TestCase):
    def test_editable_packages_and_bundled_resources(self):
        root = Path(__file__).resolve().parents[1]
        vendor = root / "third_party" / "BabelDOC"
        package = vendor / "babeldoc"
        self.assertEqual(Path(babeldoc.__file__).resolve().parent, package)
        self.assertEqual(
            Path(docweave.__file__).resolve().parent, root / "src" / "docweave"
        )
        self.assertTrue((package / "format/pdf/document_il/il_version_1.xsd").is_file())
        self.assertTrue(
            (
                package / "format/pdf/new_parser/runtime/data/cmap/78-H.pickle.gz"
            ).is_file()
        )
        self.assertTrue((vendor / "examples/ci/test.pdf").is_file())
        self.assertTrue((vendor / "LICENSE").is_file())
        self.assertFalse((vendor / "README.md").exists())
        entry_points = importlib.metadata.distribution("BabelDOC").entry_points
        self.assertTrue(
            any(
                entry.name == "babeldoc"
                and entry.group == "console_scripts"
                and entry.value == "babeldoc.main:cli"
                for entry in entry_points
            )
        )
