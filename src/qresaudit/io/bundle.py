import json
import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from qresaudit.models.manifest import HFSSRunManifest


def safe_bundle_path(bundle: Path, relative: str) -> Path:
    candidate = (bundle / relative).resolve()
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
    output: Path, *, force: bool = False, keep_failed: bool = False
) -> Iterator[Path]:
    staging = output.with_name(output.name + ".partial")
    if output.exists() and not force:
        raise FileExistsError(f"destination exists: {output}; use --force")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    prepare_bundle_directories(staging)
    try:
        yield staging
        if output.exists():
            if output.is_dir():
                shutil.rmtree(output)
            else:
                output.unlink()
        os.replace(staging, output)
    except Exception:
        if not keep_failed and staging.exists():
            shutil.rmtree(staging)
        raise
