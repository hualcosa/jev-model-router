#!/usr/bin/env python3
"""Check the public entrypoint's local links, provenance and asset contracts.

Offline/stdlib only. This complements legacy advisory parity, not visual QA or
proof of native execution. Run from any directory; paths resolve from this script.
"""
from html.parser import HTMLParser
from pathlib import Path
import json
import re
import struct
import sys
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DOCS = ("README.md", "CONTRIBUTING.md", "SECURITY.md", "docs/installation.md",
        "docs/configuration.md", "docs/routing-rationale.md", "docs/demo.md")
PRIVATE_ROOTS = ("specs", "docs/slides")
ASSETS = ("assets/public/routing-overview.svg", "assets/public/routing-flow.svg",
          "assets/public/routing-overview-mobile.svg", "assets/public/routing-flow-mobile.svg",
          "assets/public/social-preview.png", "assets/public/demo.png")


class HTMLLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.missing_alt = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "img" and not (values.get("alt") or "").strip():
            self.missing_alt = True
        for key, value in attrs:
            if key in ("href", "src") and value:
                self.links.append(value)
            elif key == "srcset" and value:
                self.links.extend(item.strip().split()[0] for item in value.split(",") if item.strip())


def anchors(text):
    """GitHub-style anchors for the simple ATX headings in these documents."""
    result, counts = set(), {}
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", text, re.M):
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        n = counts.get(slug, 0)
        counts[slug] = n + 1
        result.add(slug + ("-" + str(n) if n else ""))
    return result


def local_link_errors(root, relative, text):
    errors = []
    # Ignore fenced command blocks, which may contain shell/JSON syntax.
    prose = re.sub(r"```[^\n]*\n.*?```", "", text, flags=re.S)
    links = re.findall(r"!?\[[^\]]*\]\(([^\s)]+)(?:\s+\"[^\"]*\")?\)", prose)
    parser = HTMLLinks()
    parser.feed(prose)
    links += parser.links
    if parser.missing_alt:
        errors.append(f"{relative}: HTML image needs text alternative")
    for link in links:
        url = urlsplit(link)
        if url.scheme or url.netloc:
            if url.scheme not in ("https", "http", "mailto") and not url.netloc:
                errors.append(f"{relative}: unexpected URL scheme: {link}")
            continue
        path = (root / relative).parent / unquote(url.path) if url.path else root / relative
        path = path.resolve()
        if not path.is_relative_to(root.resolve()):
            errors.append(f"{relative}: escaping link: {link}")
            continue
        target = path.relative_to(root.resolve()).as_posix()
        if any(target == p or target.startswith(p + "/") for p in PRIVATE_ROOTS):
            errors.append(f"{relative}: private development link: {link}")
        if not path.exists():
            errors.append(f"{relative}: missing link: {link}")
        elif url.fragment and path.suffix == ".md":
            if unquote(url.fragment) not in anchors(path.read_text(encoding="utf-8")):
                errors.append(f"{relative}: missing anchor: {link}")
    return errors


def png_size(path):
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("invalid PNG")
    return struct.unpack(">II", data[16:24])


def check(root=ROOT):
    root = Path(root).resolve()
    errors = []
    for rel in DOCS:
        path = root / rel
        if not path.is_file():
            errors.append(f"missing public document: {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        errors += local_link_errors(root, rel, text)
        if re.search(r"/(?:Users|home)/[^\s/]+/|native_session_id|raw_evidence", text):
            errors.append(f"{rel}: private path or raw evidence field")
        for alt, _ in re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", text):
            if not alt.strip():
                errors.append(f"{rel}: image needs text alternative")
    for rel in ASSETS:
        path = root / rel
        if not path.is_file():
            errors.append(f"missing public asset: {rel}")
            continue
        try:
            if path.suffix == ".svg":
                svg = ET.fromstring(path.read_bytes())
                ns = "{http://www.w3.org/2000/svg}"
                if not svg.get("viewBox") or svg.find(ns + "title") is None or svg.find(ns + "desc") is None:
                    errors.append(f"{rel}: SVG needs viewBox/title/desc")
                for element in svg.iter():
                    if element.tag.endswith("script") or any(k.lower().startswith("on") for k in element.attrib):
                        errors.append(f"{rel}: executable SVG content")
                    if any(k.endswith("href") and not v.startswith("#") for k, v in element.attrib.items()):
                        errors.append(f"{rel}: external SVG dependency")
            else:
                size = png_size(path)
                wanted = (1280, 640) if "social-preview" in rel else (1120, 720)
                if size != wanted:
                    errors.append(f"{rel}: expected dimensions {wanted}, got {size}")
                if path.stat().st_size >= 1_000_000:
                    errors.append(f"{rel}: expected less than 1 MB")
        except (ValueError, ET.ParseError, struct.error):
            errors.append(f"{rel}: invalid image")
    for rel in PRIVATE_ROOTS:
        if (root / rel).exists():
            errors.append(f"internal material still in public tree: {rel}")
    if (root / ".github/workflows/deploy-slides.yml").exists():
        errors.append("removed legacy slides still have a deployment workflow")
    evidence = root / "assets/public/demo-evidence.json"
    try:
        data = json.loads(evidence.read_text(encoding="utf-8"))
        if data["kind"] != "historical-native-evidence-summary" or len(data["workers"]) != 2:
            raise ValueError()
        if not re.fullmatch(r"[a-f0-9]{64}", data["source_sha256"]):
            raise ValueError()
        raw = evidence.read_text(encoding="utf-8")
        if re.search(r"native_session_id|agent_id|raw_evidence|/Users/", raw):
            errors.append("demo evidence contains private identifiers")
    except (OSError, ValueError, KeyError, TypeError):
        errors.append("missing or invalid public demo evidence summary")
    return errors


def main():
    errors = check()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Public docs OK: {len(DOCS)} documents, local links, provenance and {len(ASSETS)} assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
