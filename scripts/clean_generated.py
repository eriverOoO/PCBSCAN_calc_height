from __future__ import annotations

import argparse
import os
import shutil
import stat
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DIRECT_TARGETS = (
    ".venv",
    "processed",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
)

DIR_GLOBS = (
    "tmp_debug*",
    "aruco_markers*",
    "markers",
)

FILE_GLOBS = (
    "*.pyc",
    "*.pyo",
)

LOOSE_ARRAY_GLOBS = (
    "*.npy",
    "*.ply",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Remove generated decoder/build/debug artifacts from the workspace."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete files. Without this flag the command only prints a dry-run.",
    )
    parser.add_argument(
        "--include-loose-arrays",
        action="store_true",
        help="Also delete generated-looking .npy/.ply files outside known output folders.",
    )
    parser.add_argument(
        "--include-dist",
        action="store_true",
        help="Also delete built executables under dist/. This is disabled by default.",
    )
    args = parser.parse_args(argv)

    targets = list(
        _dedupe(
            _iter_targets(
                ROOT,
                include_loose_arrays=args.include_loose_arrays,
                include_dist=args.include_dist,
            )
        )
    )
    rows = [(path, _path_size(path)) for path in targets if path.exists()]
    rows.sort(key=lambda item: item[1], reverse=True)

    total = sum(size for _, size in rows)
    action = "DELETE" if args.execute else "DRY-RUN"
    print(f"{action}: {len(rows)} generated target(s), {_format_bytes(total)} total")
    for path, size in rows:
        print(f"{_format_bytes(size):>10}  {path.relative_to(ROOT)}")

    if not args.execute:
        print("\nRun again with --execute to delete these generated artifacts.")
        return 0

    failures: list[tuple[Path, str]] = []
    for path, _ in rows:
        try:
            _remove_path(path)
        except Exception as exc:  # pragma: no cover - platform/permission dependent
            failures.append((path, str(exc)))

    if failures:
        print("\nFailed to delete:")
        for path, reason in failures:
            print(f"- {path.relative_to(ROOT)}: {reason}")
        return 1
    return 0


def _iter_targets(root: Path, *, include_loose_arrays: bool, include_dist: bool):
    for relative in DIRECT_TARGETS:
        path = root / relative
        if path.exists():
            yield path

    if include_dist:
        dist_dir = root / "dist"
        if dist_dir.exists():
            yield dist_dir

    build_dir = root / "build"
    if build_dir.is_dir():
        for child in build_dir.iterdir():
            if child.name == "reference":
                continue
            yield child

    for pattern in DIR_GLOBS:
        for path in root.glob(pattern):
            if path.exists():
                yield path

    for cache_dir in root.rglob("__pycache__"):
        if _inside_nested_repo(cache_dir, root) or _is_inside_dist(cache_dir, root):
            continue
        yield cache_dir

    for pattern in FILE_GLOBS:
        for path in root.rglob(pattern):
            if _inside_nested_repo(path, root) or _is_inside_dist(path, root):
                continue
            yield path

    if include_loose_arrays:
        for pattern in LOOSE_ARRAY_GLOBS:
            for path in root.rglob(pattern):
                if _inside_nested_repo(path, root):
                    continue
                yield path


def _dedupe(paths):
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if not _is_relative_to(resolved, ROOT):
            continue
        if _inside_nested_repo(resolved, ROOT):
            continue
        if resolved in seen:
            continue
        if any(parent in seen for parent in resolved.parents):
            continue
        seen.add(resolved)
        yield resolved


def _inside_nested_repo(path: Path, root: Path) -> bool:
    current = path if path.is_dir() else path.parent
    while _is_relative_to(current, root):
        if current != root and (current / ".git").exists():
            return True
        if current == root:
            return False
        current = current.parent
    return True


def _is_inside_dist(path: Path, root: Path) -> bool:
    return _is_relative_to(path, root / "dist")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _path_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError:
                pass
    return total


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, onerror=_make_writable_and_retry)
    else:
        path.unlink()


def _make_writable_and_retry(func, path, exc_info) -> None:
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0 or unit == "GB":
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{value:.2f} GB"


if __name__ == "__main__":
    raise SystemExit(main())
