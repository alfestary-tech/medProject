import os

import numpy as np
import pydicom
from pydicom.pixels import apply_modality_lut, apply_voi_lut


def get_dicom_files(folder):
    files = []
    for file in os.listdir(folder):
        path = os.path.join(folder, file)
        if not os.path.isfile(path):
            continue
        try:
            ds = pydicom.dcmread(path, stop_before_pixels=True)
        except Exception:
            continue
        if "InstanceNumber" not in ds:
            continue
        files.append((int(ds.InstanceNumber), file))
    files.sort(key=lambda item: item[0])
    return files


def _read_pixels(path):
    ds = pydicom.dcmread(path)
    pixels = apply_modality_lut(ds.pixel_array, ds)
    has_voi = "VOILUTSequence" in ds or (
        "WindowCenter" in ds and "WindowWidth" in ds
    )
    if has_voi:
        pixels = apply_voi_lut(pixels, ds)
    return ds, pixels.astype("float32"), has_voi


def _normalize_pixels(pixels, min_val, max_val, inverted):
    pixels = np.clip(pixels, min_val, max_val)
    if max_val > min_val:
        pixels = (pixels - min_val) * 255 / (max_val - min_val)
    else:
        pixels = np.zeros_like(pixels)
    pixels = pixels.astype("uint8")
    if inverted:
        pixels = 255 - pixels
    return pixels


def get_slice(folder, files, slice_index):
    path = os.path.join(folder, files[slice_index][1])
    ds, pixels, has_voi = _read_pixels(path)
    if has_voi:
        min_val = pixels.min()
        max_val = pixels.max()
    else:
        min_val = np.percentile(pixels, 1)
        max_val = np.percentile(pixels, 99)
    inverted = ds.get("PhotometricInterpretation") == "MONOCHROME1"
    return ds, _normalize_pixels(pixels, min_val, max_val, inverted)


def build_projection_views(folder, files):
    front_lines = []
    side_lines = []
    shape = None
    inverted = False

    for number, file in files:
        path = os.path.join(folder, file)
        ds, pixels, _ = _read_pixels(path)
        if shape is None:
            shape = pixels.shape
            inverted = ds.get("PhotometricInterpretation") == "MONOCHROME1"
        elif pixels.shape != shape:
            raise ValueError("Размеры срезов различаются")

        front_lines.append(pixels[pixels.shape[0] // 2, :])
        side_lines.append(pixels[:, pixels.shape[1] // 2])

    front_pixels = np.stack(front_lines)
    side_pixels = np.stack(side_lines)
    front_pixels = _normalize_pixels(
        front_pixels,
        np.percentile(front_pixels, 1),
        np.percentile(front_pixels, 99),
        inverted,
    )
    side_pixels = _normalize_pixels(
        side_pixels,
        np.percentile(side_pixels, 1),
        np.percentile(side_pixels, 99),
        inverted,
    )
    return front_pixels, side_pixels
