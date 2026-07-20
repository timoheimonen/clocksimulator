from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit
import xml.etree.ElementTree as ET

from PIL import Image
import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROOT = REPOSITORY_ROOT / "public"
SITE_ORIGIN = "https://clocksimulator.com"
SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"
SITEMAP_PAGE_CANONICALS = {
    PUBLIC_ROOT / "index.html": SITE_ORIGIN + "/",
    PUBLIC_ROOT / "digital" / "index.html": SITE_ORIGIN + "/digital/",
    PUBLIC_ROOT / "privacy.html": SITE_ORIGIN + "/privacy",
    PUBLIC_ROOT / "TOS.html": SITE_ORIGIN + "/TOS",
}
PAGE_CANONICALS = {
    **SITEMAP_PAGE_CANONICALS,
    PUBLIC_ROOT / "extension" / "privacy.html": SITE_ORIGIN + "/extension/privacy",
    PUBLIC_ROOT / "extension" / "TOS.html": SITE_ORIGIN + "/extension/TOS",
}
EXPECTED_LEGAL_LINKS = {
    PUBLIC_ROOT / "index.html": {"/privacy", "/TOS"},
    PUBLIC_ROOT / "digital" / "index.html": {"/privacy", "/TOS"},
    PUBLIC_ROOT / "TOS.html": {"/privacy"},
    PUBLIC_ROOT / "extension" / "TOS.html": {
        "/extension/privacy",
        "/extension/TOS",
    },
}
REQUIRED_MANIFEST_ICON_SIZES = {(192, 192), (512, 512)}


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


class AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.casefold() != "a":
            return
        href = dict(attrs).get("href")
        if href is not None:
            self.hrefs.append(href)


def parse_head_metadata(path: Path) -> HeadMetadataParser:
    parser = HeadMetadataParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser


def parse_anchor_hrefs(path: Path) -> list[str]:
    parser = AnchorParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser.hrefs


def load_manifest() -> dict[str, Any]:
    manifest_path = PUBLIC_ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert isinstance(manifest, dict), "manifest.json must contain a JSON object"
    return manifest


def manifest_icon_path(src: str) -> Path:
    icon_url = urlsplit(urljoin(SITE_ORIGIN + "/manifest.json", src))
    assert icon_url.scheme == "https" and icon_url.netloc == "clocksimulator.com", (
        f"Manifest icon must use the clocksimulator.com origin: {src!r}"
    )
    assert not icon_url.query and not icon_url.fragment, (
        f"Manifest icon must not contain a query or fragment: {src!r}"
    )
    decoded_path = unquote(icon_url.path)
    assert decoded_path.startswith("/"), (
        f"Manifest icon must use a root-relative path: {src!r}"
    )
    parts = decoded_path.lstrip("/").split("/")
    assert ".." not in parts and "." not in parts, (
        f"Manifest icon path must stay inside the public directory: {src!r}"
    )
    resolved = (PUBLIC_ROOT / decoded_path.lstrip("/")).resolve()
    try:
        resolved.relative_to(PUBLIC_ROOT.resolve())
    except ValueError:
        pytest.fail(f"Manifest icon path must stay inside the public directory: {src!r}")
    assert resolved.is_file(), f"Manifest icon does not resolve to an asset: {src!r}"
    return resolved


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


def test_manifest_is_valid_and_has_required_application_fields() -> None:
    manifest = load_manifest()
    for field in ("name", "short_name", "lang"):
        value = manifest.get(field)
        assert isinstance(value, str) and value.strip(), (
            f"manifest.json field {field!r} must be a non-empty string"
        )
    assert manifest.get("id") == "/"
    assert manifest.get("start_url") == "/"
    assert manifest.get("display") in {
        "browser",
        "fullscreen",
        "minimal-ui",
        "standalone",
        "window-controls-overlay",
    }
    for field in ("background_color", "theme_color"):
        value = manifest.get(field)
        assert isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value), (
            f"manifest.json field {field!r} must be a six-digit hex color"
        )
    icons = manifest.get("icons")
    assert isinstance(icons, list) and icons, "manifest.json must declare at least one icon"


def test_manifest_icons_exist_and_match_declared_dimensions() -> None:
    icons = load_manifest().get("icons")
    assert isinstance(icons, list) and icons, "manifest.json must declare at least one icon"
    observed_sizes: set[tuple[int, int]] = set()
    observed_sources: set[str] = set()
    for icon in icons:
        assert isinstance(icon, dict), "Every manifest icon must be an object"
        src = icon.get("src")
        sizes = icon.get("sizes")
        media_type = icon.get("type")
        assert isinstance(src, str) and src, "Every manifest icon must have a src"
        assert src not in observed_sources, f"Duplicate manifest icon src: {src!r}"
        observed_sources.add(src)
        assert isinstance(sizes, str) and sizes, (
            f"Manifest icon {src!r} must declare its sizes"
        )
        declared_sizes = {
            (int(match.group("width")), int(match.group("height")))
            for token in sizes.split()
            if (
                match := re.fullmatch(
                    r"(?P<width>[1-9]\d*)x(?P<height>[1-9]\d*)", token
                )
            )
        }
        assert len(declared_sizes) == len(sizes.split()), (
            f"Manifest icon {src!r} has an invalid sizes value: {sizes!r}"
        )
        assert media_type == "image/png", (
            f"Manifest icon {src!r} must declare type image/png"
        )
        icon_path = manifest_icon_path(src)
        with Image.open(icon_path) as image:
            actual_size = image.size
            actual_format = image.format
            image.verify()
        assert actual_format == "PNG", f"Manifest icon {src!r} is not a valid PNG"
        assert actual_size in declared_sizes, (
            f"Manifest icon {src!r} is {actual_size}, declared as {sizes!r}"
        )
        observed_sizes.add(actual_size)
    assert REQUIRED_MANIFEST_ICON_SIZES <= observed_sizes, (
        "Manifest must include valid 192x192 and 512x512 icons; observed "
        + repr(sorted(observed_sizes))
    )


def test_sitemap_uses_the_canonical_public_urls() -> None:
    sitemap_path = PUBLIC_ROOT / "sitemap.xml"
    root = ET.parse(sitemap_path).getroot()
    assert root.tag == "{" + SITEMAP_NAMESPACE + "}urlset"
    locations = [
        element.text.strip()
        for element in root.findall(
            "sitemap:url/sitemap:loc", {"sitemap": SITEMAP_NAMESPACE}
        )
        if element.text and element.text.strip()
    ]
    expected_locations = set(SITEMAP_PAGE_CANONICALS.values())
    assert len(locations) == len(expected_locations), (
        "sitemap.xml must contain each public canonical URL exactly once"
    )
    assert len(locations) == len(set(locations)), "sitemap.xml contains duplicate URLs"
    assert set(locations) == expected_locations, (
        "sitemap.xml does not match the public canonical URLs: " + repr(locations)
    )



def test_robots_points_to_the_canonical_sitemap() -> None:
    robots_lines = (PUBLIC_ROOT / "robots.txt").read_text(encoding="utf-8").splitlines()
    directives = [
        (name.strip().casefold(), value.strip())
        for line in robots_lines
        if (content := line.split("#", 1)[0].strip()) and ":" in content
        for name, value in [content.split(":", 1)]
    ]
    assert ("user-agent", "*") in directives
    assert ("allow", "/") in directives
    sitemap_directives = [value for name, value in directives if name == "sitemap"]
    assert sitemap_directives == [SITE_ORIGIN + "/sitemap.xml"], (
        "robots.txt must point to the canonical sitemap URL exactly once"
    )


@pytest.mark.parametrize(
    ("page_path", "expected_canonical"),
    list(PAGE_CANONICALS.items()),
    ids=[path.relative_to(PUBLIC_ROOT).as_posix() for path in PAGE_CANONICALS],
)
def test_public_page_has_exactly_one_correct_canonical_link(
    page_path: Path, expected_canonical: str
) -> None:
    metadata = parse_head_metadata(page_path)
    relative_path = page_path.relative_to(REPOSITORY_ROOT)
    assert metadata.misplaced_canonical_urls == [], (
        f"{relative_path} has canonical links outside head"
    )
    assert len(metadata.canonical_urls) == 1, (
        f"{relative_path} must have exactly one canonical link"
    )
    canonical = metadata.canonical_urls[0]
    parsed = urlsplit(canonical)
    assert parsed.scheme == "https" and parsed.netloc == "clocksimulator.com", (
        f"{relative_path} canonical must use the clocksimulator.com HTTPS origin"
    )
    assert not parsed.query and not parsed.fragment, (
        f"{relative_path} canonical must not contain a query or fragment"
    )
    assert canonical == expected_canonical, (
        f"{relative_path} canonical is {canonical!r}, expected {expected_canonical!r}"
    )


@pytest.mark.parametrize(
    ("page_path", "expected_paths"),
    list(EXPECTED_LEGAL_LINKS.items()),
    ids=[path.relative_to(PUBLIC_ROOT).as_posix() for path in EXPECTED_LEGAL_LINKS],
)
def test_internal_legal_links_use_canonical_public_routes(
    page_path: Path, expected_paths: set[str]
) -> None:
    observed_paths = {
        parsed.path
        for href in parse_anchor_hrefs(page_path)
        for parsed in [urlsplit(urljoin(SITE_ORIGIN + "/", href))]
        if parsed.scheme == "https" and parsed.netloc == "clocksimulator.com"
    }
    assert expected_paths <= observed_paths
    assert not ({"/privacy.html", "/TOS.html", "/extension/tos"} & observed_paths)
