from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path

import numpy as np

from .io import save_float01_png, save_uint8_image


def _prepare_matplotlib() -> None:
    cache_dir = Path(tempfile.gettempdir()) / "pcb_fpp_decoder_mpl"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))
    import matplotlib

    matplotlib.use("Agg", force=True)


def finite_percentiles(
    image: np.ndarray, low: float = 1.0, high: float = 99.0
) -> tuple[float, float]:
    values = np.asarray(image)[np.isfinite(image)]
    if values.size == 0:
        return 0.0, 1.0
    lo, hi = np.percentile(values, [low, high])
    if not np.isfinite(lo) or not np.isfinite(hi) or abs(hi - lo) < 1e-9:
        center = float(np.nanmedian(values))
        return center - 0.5, center + 0.5
    return float(lo), float(hi)


def normalize_for_preview(
    image: np.ndarray,
    mask: np.ndarray | None = None,
    low: float = 1.0,
    high: float = 99.0,
) -> np.ndarray:
    work = np.asarray(image, dtype=np.float32)
    if mask is not None:
        work = np.where(mask, work, np.nan)
    lo, hi = finite_percentiles(work, low=low, high=high)
    preview = (work - lo) / (hi - lo)
    preview = np.where(np.isfinite(preview), preview, 0.0)
    return np.clip(preview, 0.0, 1.0).astype(np.float32)


def save_mask(path: Path, mask: np.ndarray) -> None:
    save_uint8_image(path, np.where(mask, 255, 0).astype(np.uint8))


def save_preview_gray(path: Path, image: np.ndarray, mask: np.ndarray | None = None) -> None:
    save_float01_png(path, normalize_for_preview(image, mask=mask))


def save_colormap(
    path: Path,
    image: np.ndarray,
    mask: np.ndarray | None = None,
    cmap: str = "viridis",
    with_colorbar: bool = False,
    title: str | None = None,
) -> None:
    _prepare_matplotlib()
    import matplotlib.pyplot as plt

    display = np.asarray(image, dtype=np.float32)
    if mask is not None:
        display = np.where(mask, display, np.nan)
    lo, hi = finite_percentiles(display)

    path.parent.mkdir(parents=True, exist_ok=True)
    if with_colorbar:
        fig, ax = plt.subplots(figsize=(7.0, 5.0), dpi=150)
        im = ax.imshow(display, cmap=cmap, vmin=lo, vmax=hi)
        ax.axis("off")
        if title:
            ax.set_title(title)
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        fig.tight_layout()
        fig.savefig(path, bbox_inches="tight", pad_inches=0.05)
        plt.close(fig)
    else:
        norm = np.clip((display - lo) / (hi - lo), 0.0, 1.0)
        norm = np.where(np.isfinite(norm), norm, 0.0)
        cmap_obj = plt.get_cmap(cmap)
        rgba = cmap_obj(norm)
        if mask is not None:
            rgba[..., :3] = np.where(mask[..., None], rgba[..., :3], 0.0)
        save_uint8_image(path, (rgba[..., :3] * 255.0).astype(np.uint8))


def save_wrapped_phase_preview(path: Path, wrapped_phase: np.ndarray, mask: np.ndarray | None) -> None:
    phase_0_1 = (np.asarray(wrapped_phase) + math.pi) / (2.0 * math.pi)
    phase_0_1 = np.mod(phase_0_1, 1.0)
    if mask is not None:
        phase_0_1 = np.where(mask, phase_0_1, 0.0)

    _prepare_matplotlib()
    import matplotlib.pyplot as plt

    rgba = plt.get_cmap("twilight")(phase_0_1)
    save_uint8_image(path, (rgba[..., :3] * 255.0).astype(np.uint8))


def write_ascii_ply(
    path: Path,
    z: np.ndarray,
    mask: np.ndarray,
    max_points: int = 300_000,
    scale_xy: float = 1.0,
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    valid = np.isfinite(z) & mask
    rows, cols = np.nonzero(valid)
    if rows.size == 0:
        points = np.empty((0, 3), dtype=np.float32)
    else:
        step = max(1, int(math.ceil(rows.size / max_points)))
        rows = rows[::step]
        cols = cols[::step]
        points = np.column_stack((cols * scale_xy, rows * scale_xy, z[rows, cols]))

    with path.open("w", encoding="ascii") as f:
        f.write("ply\n")
        f.write("format ascii 1.0\n")
        f.write(f"element vertex {points.shape[0]}\n")
        f.write("property float x\n")
        f.write("property float y\n")
        f.write("property float z\n")
        f.write("end_header\n")
        for x, y, value in points:
            f.write(f"{float(x):.6f} {float(y):.6f} {float(value):.6f}\n")
    return int(points.shape[0])


def save_point_cloud_preview(
    path: Path,
    z: np.ndarray,
    mask: np.ndarray,
    max_points: int = 50_000,
) -> None:
    _prepare_matplotlib()
    import matplotlib.pyplot as plt

    valid = np.isfinite(z) & mask
    rows, cols = np.nonzero(valid)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(7.0, 5.0), dpi=150)
    ax = fig.add_subplot(111, projection="3d")
    if rows.size:
        step = max(1, int(math.ceil(rows.size / max_points)))
        rows = rows[::step]
        cols = cols[::step]
        values = z[rows, cols]
        ax.scatter(cols, rows, values, c=values, cmap="viridis", s=0.25, linewidths=0)
    ax.set_xlabel("u")
    ax.set_ylabel("v")
    ax.set_zlabel("z")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
