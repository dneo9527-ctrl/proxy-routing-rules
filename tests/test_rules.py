import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rules import artifacts, overlaps, parse, read_sources, validate


class RuleTests(unittest.TestCase):
    def test_cross_list_parent_overlap(self):
        texts = read_sources()
        texts["reject"] += "DOMAIN-SUFFIX,qudad.icu\n"
        with self.assertRaisesRegex(ValueError, "Cross-list overlap"):
            validate(texts)

    def test_distinct_exact_domains_do_not_overlap(self):
        self.assertFalse(overlaps(("DOMAIN", "qudad.icu"), ("DOMAIN", "key.qudad.icu")))
        self.assertFalse(overlaps(("DOMAIN-SUFFIX", "qudad.icu"), ("DOMAIN", "notqudad.icu")))

    def test_bad_syntax_and_secrets_are_rejected(self):
        for value in ("DOMAIN,key.qudad.icu,DIRECT", "DOMAIN,https://key.qudad.icu/",
                      "DOMAIN,key.qudad.icu?token=example", "DOMAIN-SUFFIX,*.qudad.icu"):
            with self.assertRaises(ValueError):
                parse(value)

    def test_duplicate_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            parse("DOMAIN,example.com\nDOMAIN,example.com\n")

    def test_qx_mapping(self):
        built = artifacts(read_sources())
        self.assertIn("host,key.qudad.icu,direct\n", built["dist/quantumult-x/direct.list"])
        self.assertIn("host-suffix,claude.ai,RESIDENTIAL\n", built["dist/quantumult-x/residential.list"])


if __name__ == "__main__":
    unittest.main()
