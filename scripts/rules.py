"""Validate public domain overrides and build client-specific artifacts."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
KINDS = ("reject", "direct", "residential", "proxy")
POLICIES = dict(reject="reject", direct="direct", residential="RESIDENTIAL", proxy="PROXY")
DOMAIN = re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def parse(text):
    rules = []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith(("#", "//", ";")):
            continue
        parts = line.split(",")
        if len(parts) != 2 or parts[0] not in ("DOMAIN", "DOMAIN-SUFFIX"):
            raise ValueError("Line %d: expected DOMAIN or DOMAIN-SUFFIX without policy" % number)
        if not DOMAIN.fullmatch(parts[1]):
            raise ValueError("Line %d: expected a lowercase ASCII domain" % number)
        rule = tuple(parts)
        if rule in rules:
            raise ValueError("Duplicate rule: " + line)
        rules.append(rule)
    if not rules:
        raise ValueError("Empty ruleset: retain an .invalid placeholder")
    return rules


def overlaps(a, b):
    if a[1] == b[1]:
        return True
    return ((a[0] == "DOMAIN-SUFFIX" and b[1].endswith("." + a[1])) or
            (b[0] == "DOMAIN-SUFFIX" and a[1].endswith("." + b[1])))


def validate(texts):
    parsed = {kind: parse(texts[kind]) for kind in KINDS}
    for index, kind in enumerate(KINDS):
        for other in KINDS[index + 1:]:
            for a in parsed[kind]:
                for b in parsed[other]:
                    if overlaps(a, b):
                        raise ValueError("Cross-list overlap: %s %s / %s %s" % (kind, a, other, b))
    return parsed


def read_sources(root=ROOT):
    return {kind: (root / "rules" / (kind + ".list")).read_text(encoding="utf-8") for kind in KINDS}


def artifacts(texts):
    parsed = validate(texts)
    files = {}
    for kind in KINDS:
        qx = ["# Generated; edit rules/%s.list instead." % kind]
        for rule_type, domain in parsed[kind]:
            mapped = {"DOMAIN": "host", "DOMAIN-SUFFIX": "host-suffix"}[rule_type]
            qx.append(",".join((mapped, domain, POLICIES[kind])))
        files["dist/quantumult-x/" + kind + ".list"] = "\n".join(qx) + "\n"
    manifest = {"schema": 1, "rules": {
        kind: {"path": "rules/" + kind + ".list", "count": len(parsed[kind]),
               "sha256": hashlib.sha256(texts[kind].encode()).hexdigest()}
        for kind in KINDS}}
    files["manifest.json"] = json.dumps(manifest, indent=2) + "\n"
    return files


def build(check=False):
    files = artifacts(read_sources())
    for name, text in files.items():
        path = ROOT / name
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                raise ValueError("Stale generated artifact: " + name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")


def set_domain(kind, value, suffix=False):
    url = urlsplit(value if "://" in value else "https://" + value)
    if url.username or url.password or not url.hostname:
        raise ValueError("Supply a public domain or URL without credentials")
    domain = url.hostname.encode("idna").decode("ascii").lower()
    if not DOMAIN.fullmatch(domain):
        raise ValueError("Invalid domain")
    marker = ("DOMAIN-SUFFIX" if suffix else "DOMAIN") + "," + domain
    original = read_sources()
    updated = {}
    for category, text in original.items():
        lines = [line for line in text.splitlines() if line.strip() != marker]
        if category == kind:
            lines.append(marker)
        updated[category] = "\n".join(lines) + "\n"
    validate(updated)
    for category, text in updated.items():
        if text != original[category]:
            (ROOT / "rules" / (category + ".list")).write_text(text, encoding="utf-8")
    build()
    print("Set %s -> %s" % (domain, kind))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    sub.add_parser("build")
    command = sub.add_parser("set")
    command.add_argument("category", choices=KINDS)
    command.add_argument("domain_or_url")
    command.add_argument("--suffix", action="store_true")
    args = parser.parse_args()
    if args.command == "set":
        set_domain(args.category, args.domain_or_url, args.suffix)
    else:
        build(check=args.command == "check")
        print("Rules and generated artifacts are valid")


if __name__ == "__main__":
    main()
