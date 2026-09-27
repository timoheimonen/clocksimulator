from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from PIL import Image


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROOT = REPOSITORY_ROOT / "public"
SITE_ORIGIN = "https://clocksimulator.com"
SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"
PAGE_CANONICALS = {
    PUBLIC_ROOT / "index.html": SITE_ORIGIN + "/",
    PUBLIC_ROOT / "digital" / "index.html": SITE_ORIGIN + "/digital/",
    PUBLIC_ROOT / "privacy.html": SITE_ORIGIN + "/privacy",
    PUBLIC_ROOT / "TOS.html": SITE_ORIGIN + "/TOS",
}


class HeadMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_head = False
        self.canonical_urls: list[str] = []
        self.versions: list[str] = []
        self.misplaced_canonical_urls: list[str] = []
        self.misplaced_versions: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.casefold() == "head":
            self.in_head = True
            return
        attributes = dict(attrs)
        if tag.casefold() == "link":
            rel = attributes.get("rel") or ""
            if "canonical" in {token.casefold() for token in rel.split()}:
                href = attributes.get("href")
                if href is not None:
                    target = (
                        self.canonical_urls
                        if self.in_head
                        else self.misplaced_canonical_urls
                    )
                    target.append(href)
        if tag.casefold() == "meta":
            name = attributes.get("name") or ""
            if name.casefold() == "version":
                content = attributes.get("content")
                if content is not None:
                    target = self.versions if self.in_head else self.misplaced_versions
                    target.append(content)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "head":
            self.in_head = False


def parse_head_metadata(path: Path) -> HeadMetadataParser:
    parser = HeadMetadataParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser


def test_release_versions_are_synchronized() -> None:
    changelog = (REPOSITORY_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    changelog_match = re.search(
        r"^##\s+(?P<version>\d+\.\d+\.\d+)(?:\s|$)", changelog, re.MULTILINE
    )
    assert changelog_match is not None, "CHANGELOG.md has no semantic-version heading"
    latest_version = changelog_match.group("version")

    page_versions: dict[str, str] = {}
    for page_path in (PUBLIC_ROOT / "index.html", PUBLIC_ROOT / "digital" / "index.html"):
        metadata = parse_head_metadata(page_path)
        assert metadata.misplaced_versions == []
        assert len(metadata.versions) == 1, (
            f"{page_path.relative_to(REPOSITORY_ROOT)} must have exactly one meta version"
        )
        page_versions[str(page_path.relative_to(REPOSITORY_ROOT))] = metadata.versions[0]

    service_worker = (PUBLIC_ROOT / "sw.js").read_text(encoding="utf-8")
    cache_names = re.findall(
        r"\bconst\s+CACHE_NAME\s*=\s*(['\"])([^'\"]+)\1\s*;", service_worker
    )
    assert len(cache_names) == 1, "public/sw.js must define exactly one CACHE_NAME"
    cache_version_match = re.fullmatch(
        r"clocksimulator-v(?P<version>\d+\.\d+\.\d+)", cache_names[0][1]
    )
    assert cache_version_match is not None, (
        "The service worker cache name must be clocksimulator-v<semantic-version>"
    )

    observed_versions = {
        "CHANGELOG.md": latest_version,
        **page_versions,
        "public/sw.js CACHE_NAME": cache_version_match.group("version"),
    }
    assert set(observed_versions.values()) == {latest_version}, (
        "Release versions are not synchronized: " + repr(observed_versions)
    )


def test_manifest_icons_exist_and_match_declared_dimensions() -> None:
    manifest = json.loads((PUBLIC_ROOT / "manifest.json").read_text(encoding="utf-8"))
    icons = manifest.get("icons")
    assert isinstance(icons, list) and icons, "manifest.json must declare at least one icon"
    for icon in icons:
        src = icon["src"]
        icon_path = PUBLIC_ROOT / src.lstrip("/")
        assert icon_path.is_file(), f"Manifest icon does not exist: {src!r}"
        with Image.open(icon_path) as image:
            assert image.format == "PNG", f"Manifest icon {src!r} is not a PNG"
            actual_size = "%dx%d" % image.size
        assert actual_size in icon["sizes"].split(), (
            f"Manifest icon {src!r} is {actual_size}, declared as {icon['sizes']!r}"
        )


def test_canonical_sitemap_and_robots_are_consistent() -> None:
    for page_path, expected_canonical in PAGE_CANONICALS.items():
        metadata = parse_head_metadata(page_path)
        relative_path = page_path.relative_to(REPOSITORY_ROOT)
        assert metadata.misplaced_canonical_urls == [], (
            f"{relative_path} has canonical links outside head"
        )
        assert metadata.canonical_urls == [expected_canonical], (
            f"{relative_path} must have exactly one canonical link {expected_canonical!r}, "
            f"got {metadata.canonical_urls!r}"
        )

    root = ET.parse(PUBLIC_ROOT / "sitemap.xml").getroot()
    assert root.tag == "{" + SITEMAP_NAMESPACE + "}urlset"
    locations = [
        element.text.strip()
        for element in root.findall(
            "sitemap:url/sitemap:loc", {"sitemap": SITEMAP_NAMESPACE}
        )
        if element.text and element.text.strip()
    ]
    assert len(locations) == len(set(locations)), "sitemap.xml contains duplicate URLs"
    assert set(locations) == set(PAGE_CANONICALS.values()), (
        "sitemap.xml does not match the public canonical URLs: " + repr(locations)
    )

    robots_lines = (PUBLIC_ROOT / "robots.txt").read_text(encoding="utf-8").splitlines()
    sitemap_directives = [
        value.strip()
        for line in robots_lines
        if (content := line.split("#", 1)[0].strip()) and ":" in content
        for name, value in [content.split(":", 1)]
        if name.strip().casefold() == "sitemap"
    ]
    assert sitemap_directives == [SITE_ORIGIN + "/sitemap.xml"], (
        "robots.txt must point to the canonical sitemap URL exactly once"
    )
