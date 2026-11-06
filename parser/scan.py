import os
import pydicom
import numpy as np


def prepeare_CT_images(patient_dir: str) -> tuple[np.array, list]:
    # Получаем путь до файла и читаем
    info = [pydicom.dcmread(os.path.join(*(patient_dir, dcm)))
            for dcm in os.listdir(patient_dir)]

    info.sort(key=lambda x: x.ImagePositionPatient[-1])

    # ДУБЛИКАТЫ В ТЕСТОВОМ ДАТАСЕТЕ!
    unique = {}
    for ds in info:
        unique.setdefault(str(ds.SOPInstanceUID), ds)

    info = sorted(
        unique.values(),
        key=lambda ds: float(ds.ImagePositionPatient[-1])
    )

    # Собираем снимки
    cts = np.stack([dcm.pixel_array * dcm.RescaleSlope +
                    dcm.RescaleIntercept for dcm in info], axis=0)
    # Собираем информацию по снимку
    plus_info = [{
        "slice_thickness": float(dcm.SliceThickness),
        "pixel_spacing": np.asarray(dcm.PixelSpacing, dtype=float),
        "positions": np.asarray(
            [dcm.ImagePositionPatient for dcm in info], dtype=float
        ),
        "orientation": np.asarray(dcm.ImageOrientationPatient, dtype=float),
        "series_uid": dcm.SeriesInstanceUID,
        "frame_uid": dcm.FrameOfReferenceUID,
        "sop_uid": dcm.SOPInstanceUID,
        "countors": [],
        "patient_pos": dcm.ImagePositionPatient
    } for dcm in info]
    return cts, plus_info