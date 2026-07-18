from __future__ import annotations

import ast
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
REQUIRED_PRECACHE_PATHS = {
    "/",
    "/digital/",
    "/privacy",
    "/TOS",
    "/sitemap.xml",
    "/manifest.json",
    "/apple-touch-icon.png",
    "/android-chrome-192x192.png",
    "/android-chrome-512x512.png",
    "/og-image.png",
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


def strip_jsonc_comments(source: str) -> str:
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(source):
        character = source[index]
        if in_string:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            output.append(character)
            index += 1
            continue
        if source.startswith("//", index):
            newline = source.find("\n", index + 2)
            if newline == -1:
                break
            output.append("\n")
            index = newline + 1
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            assert end != -1, "wrangler.jsonc contains an unterminated comment"
            output.extend("\n" for character in source[index : end + 2] if character == "\n")
            index = end + 2
            continue
        output.append(character)
        index += 1
    return "".join(output)


def remove_jsonc_trailing_commas(source: str) -> str:
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(source):
        character = source[index]
        if in_string:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            output.append(character)
            index += 1
            continue
        if character == ",":
            next_index = index + 1
            while next_index < len(source) and source[next_index].isspace():
                next_index += 1
            if next_index < len(source) and source[next_index] in "}]":
                index += 1
                continue
        output.append(character)
        index += 1
    return "".join(output)


def load_wrangler_config() -> dict[str, Any]:
    config_path = REPOSITORY_ROOT / "wrangler.jsonc"
    source = strip_jsonc_comments(config_path.read_text(encoding="utf-8"))
    config = json.loads(remove_jsonc_trailing_commas(source))
    assert isinstance(config, dict), "wrangler.jsonc must contain a JSON object"
    return config


def extract_service_worker_assets(source: str) -> list[str]:
    matches = re.findall(r"\bconst\s+ASSETS\s*=\s*(\[.*?\])\s*;", source, re.DOTALL)
    assert len(matches) == 1, "public/sw.js must define exactly one static ASSETS array"
    assets = ast.literal_eval(matches[0])
    assert isinstance(assets, list), "The service worker ASSETS value must be a list"
    assert assets, "The service worker ASSETS array must not be empty"
    assert all(isinstance(asset, str) for asset in assets), (
        "Every service worker precache entry must be a literal string"
    )
    return assets


def deployment_asset_root() -> tuple[Path, str]:
    config = load_wrangler_config()
    assets_config = config.get("assets")
    assert isinstance(assets_config, dict), "wrangler.jsonc must define an assets object"
    directory = assets_config.get("directory")
    html_handling = assets_config.get("html_handling")
    assert isinstance(directory, str) and directory, (
        "wrangler.jsonc assets.directory must be a non-empty string"
    )
    assert html_handling == "auto-trailing-slash", (
        "Static route resolution assumes Wrangler html_handling=auto-trailing-slash"
    )
    root = (REPOSITORY_ROOT / directory).resolve()
    assert root == PUBLIC_ROOT.resolve(), (
        "Wrangler must deploy the public directory that contains the service worker"
    )
    return root, html_handling


def resolve_deployment_path(route: str, root: Path, html_handling: str) -> Path | None:
    parsed = urlsplit(route)
    assert not parsed.scheme and not parsed.netloc, (
        f"Precache route must be same-origin and root-relative: {route!r}"
    )
    assert not parsed.query and not parsed.fragment, (
        f"Precache route must not contain a query or fragment: {route!r}"
    )
    assert parsed.path.startswith("/"), (
        f"Precache route must start with a slash: {route!r}"
    )
    decoded_path = unquote(parsed.path)
    parts = decoded_path.lstrip("/").split("/")
    assert ".." not in parts and "." not in parts, (
        f"Precache route must not traverse the asset directory: {route!r}"
    )
    relative = decoded_path.lstrip("/")
    candidates: list[Path] = []
    if not relative:
        candidates.append(root / "index.html")
    else:
        candidates.append(root / relative)
        if decoded_path.endswith("/"):
            candidates.append(root / relative / "index.html")
        elif html_handling == "auto-trailing-slash":
            candidates.append(root / (relative + ".html"))
            candidates.append(root / relative / "index.html")
    resolved_root = root.resolve()
    for candidate in candidates:
        resolved_candidate = candidate.resolve()
        try:
            resolved_candidate.relative_to(resolved_root)
        except ValueError:
            continue
        if resolved_candidate.is_file():
            return resolved_candidate
    return None


def manifest_icon_path(src: str) -> Path:
    icon_url = urlsplit(urljoin(SITE_ORIGIN + "/manifest.json", src))
    assert icon_url.scheme == "https" and icon_url.netloc == "clocksimulator.com", (
        f"Manifest icon must use the clocksimulator.com origin: {src!r}"
    )
    assert not icon_url.query and not icon_url.fragment, (
        f"Manifest icon must not contain a query or fragment: {src!r}"
    )
    root, html_handling = deployment_asset_root()
    resolved = resolve_deployment_path(icon_url.path, root, html_handling)
    assert resolved is not None, f"Manifest icon does not resolve to an asset: {src!r}"
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
    root, html_handling = deployment_asset_root()
    resolved = resolve_deployment_path(parsed.path, root, html_handling)
    assert resolved == page_path.resolve(), (
        f"{relative_path} canonical route does not resolve back to that deployed page"
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


def test_service_worker_precache_paths_resolve_to_deployed_assets() -> None:
    service_worker = (PUBLIC_ROOT / "sw.js").read_text(encoding="utf-8")
    precache_paths = extract_service_worker_assets(service_worker)
    assert len(precache_paths) == len(set(precache_paths)), (
        "The service worker ASSETS array contains duplicate paths"
    )
    assert REQUIRED_PRECACHE_PATHS <= set(precache_paths), (
        "The service worker must precache the clocks, legal pages, manifest, sitemap, and icons"
    )
    assert "/privacy.html" not in precache_paths and "/TOS.html" not in precache_paths, (
        "Legal pages must be precached under their extensionless public routes"
    )
    root, html_handling = deployment_asset_root()
    unresolved = [
        route
        for route in precache_paths
        if resolve_deployment_path(route, root, html_handling) is None
    ]
    assert not unresolved, (
        "Service worker precache paths do not resolve under the Wrangler deployment contract: "
        + repr(unresolved)
    )
