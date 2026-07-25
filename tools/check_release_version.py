"""Reject release tags that do not match the package version."""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path


def normalize_release_tag(tag: str) -> str:
    normalized = tag.strip()
    if normalized.startswith("refs/tags/"):
        normalized = normalized.removeprefix("refs/tags/")
    if normalized.startswith("v"):
        normalized = normalized[1:]
    if not normalized:
        raise ValueError("release tag is empty")
    return normalized


def package_version(pyproject: Path) -> str:
    with pyproject.open("rb") as handle:
        raw = tomllib.load(handle)
    version = raw.get("project", {}).get("version")
    if not isinstance(version, str) or not version:
        raise ValueError(f"project.version is missing from {pyproject}")
    return version


def check_release_version(tag: str, pyproject: Path) -> str:
    tag_version = normalize_release_tag(tag)
    configured_version = package_version(pyproject)
    if tag_version != configured_version:
        raise ValueError(
            f"release tag version {tag_version!r} does not match "
            f"project version {configured_version!r}"
        )
    return configured_version


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True, help="GitHub release tag, such as v2.0.0")
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    args = parser.parse_args()
    version = check_release_version(args.tag, args.pyproject)
    print(f"release tag matches package version {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
