import json
import os
import shutil
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from qresaudit.models.manifest import HFSSRunManifest


def safe_bundle_path(bundle: Path, relative: str) -> Path:
    relative_path = PurePosixPath(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts or "\\" in relative:
        raise ValueError(f"path escapes bundle: {relative}")
    lexical = bundle.joinpath(*relative_path.parts)
    current = bundle
    for part in relative_path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"symlink path component is forbidden: {relative}")
    candidate = lexical.resolve()
    root = bundle.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"path escapes bundle: {relative}")
    return candidate


def load_manifest(path: Path) -> HFSSRunManifest:
    return HFSSRunManifest.model_validate_json(path.read_text(encoding="utf-8"))


def write_manifest(path: Path, manifest: HFSSRunManifest) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def prepare_bundle_directories(root: Path) -> None:
    for relative in (
        "network",
        "modes",
        "convergence",
        "reports",
        "fields/raw",
        "fields/hdf5",
        "mesh",
        "logs",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)


@contextmanager
def atomic_staging(
    output: Path,
    *,
    force: bool = False,
    keep_failed: bool = False,
    validate_final: Callable[[Path], None] | None = None,
) -> Iterator[Path]:
    staging = output.with_name(output.name + ".partial")
    backup = output.with_name(output.name + ".backup")
    if output.exists() and not force:
        raise FileExistsError(f"destination exists: {output}; use --force")
    if backup.exists():
        raise FileExistsError(f"stale backup exists: {backup}; inspect or restore it first")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    prepare_bundle_directories(staging)
    try:
        yield staging
        if output.exists():
            os.replace(output, backup)
        try:
            os.replace(staging, output)
            if validate_final is not None:
                validate_final(output)
        except Exception:
            if output.exists():
                if output.is_dir():
                    shutil.rmtree(output)
                else:
                    output.unlink()
            if backup.exists():
                os.replace(backup, output)
            raise
        if backup.exists():
            if backup.is_dir():
                shutil.rmtree(backup)
            else:
                backup.unlink()
    except Exception:
        if not keep_failed and staging.exists():
            shutil.rmtree(staging)
        raise
