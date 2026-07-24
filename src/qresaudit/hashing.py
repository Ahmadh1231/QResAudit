import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def run_id_for(value: Any) -> str:
    return stable_hash(value)[:32]


def write_checksums(bundle: Path) -> Path:
    paths = sorted(
        path for path in bundle.rglob("*") if path.is_file() and path.name != "checksums.sha256"
    )
    lines = [f"{sha256_file(path)}  {path.relative_to(bundle).as_posix()}" for path in paths]
    target = bundle / "checksums.sha256"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def read_checksums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        digest, separator, relative = line.partition("  ")
        if not separator or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError(f"malformed checksum line {line_number}")
        relative_path = PurePosixPath(relative)
        if (
            not relative
            or relative_path.is_absolute()
            or ".." in relative_path.parts
            or "\\" in relative
        ):
            raise ValueError(f"unsafe checksum path on line {line_number}")
        if relative in result:
            raise ValueError(f"duplicate checksum entry for {relative}")
        result[relative] = digest
    return result
