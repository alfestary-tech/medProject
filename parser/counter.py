import pydicom
import numpy as np
from skimage.draw import polygon
import cv2

from utils.errors import SeriesUIDError

def open_conture_dicom(filename: str, ct_info: dict[str: any]) -> None:
    data = pydicom.dcmread(filename, force=True)
    series_uid = data.ReferencedFrameOfReferenceSequence[0].RTReferencedStudySequence[0]
    series_uid = series_uid.RTReferencedSeriesSequence[0].SeriesInstanceUID
    if ct_info[0]["series_uid"] != str(series_uid):
        raise SeriesUIDError("Wrong UID!")

    # Подготовка словаря: Номер ROI -> Информация о ROI
    roi_struct = {int(el.ROINumber): {"name": str(el.ROIName)}
                  for el in data.StructureSetROISequence}
    roi = data.ROIContourSequence
    for info in ct_info:
        sop_uid = info["sop_uid"]
        for el in roi:
            roi_struct[int(el.ReferencedROINumber)]["color"] = list(
                el.ROIDisplayColor)
            info["countors"].append(
                {int(el.ReferencedROINumber): roi_struct[int(el.ReferencedROINumber)].copy()})
            info["countors"][-1]["arrays"] = []
            info["countors"][-1]["types"] = []
            for seq in el.ContourSequence:
                if str(seq.ContourImageSequence[0].ReferencedSOPInstanceUID) == sop_uid:
                    info["countors"][-1]["arrays"].append(
                        np.array(seq.ContourData))
                    info["countors"][-1]["types"].append(
                        str(seq.ContourGeometricType))
            info["countors"][-1][int(el.ReferencedROINumber)]["arrays"] = []
            info["countors"][-1][int(el.ReferencedROINumber)]["types"] = []
            for seq in el.ContourSequence:
                if str(seq.ContourImageSequence[0].ReferencedSOPInstanceUID) == sop_uid:
                    info["countors"][-1][int(el.ReferencedROINumber)
                                         ]["arrays"].append(np.array(seq.ContourData))
                    info["countors"][-1][int(el.ReferencedROINumber)
                                         ]["types"].append(str(seq.ContourGeometricType))


def prepare_mask_skimage(shape, countor, slice_info, roi_number):
    mask = np.zeros(shape, dtype=bool)
    roi = countor[roi_number]

    position = np.asarray(slice_info["patient_pos"], dtype=float)
    orientation = np.asarray(slice_info["orientation"], dtype=float)
    spacing = np.asarray(slice_info["pixel_spacing"], dtype=float)

    for data in roi["arrays"]:
        points = np.asarray(data, dtype=float).reshape(-1, 3)
        if len(points) < 3:  # например, ISOCENTER имеет тип POINT
            continue

        delta = points - position
        cols = (delta @ orientation[:3]) / spacing[1]
        rows = (delta @ orientation[3:]) / spacing[0]

        rr, cc = polygon(rows, cols, shape=shape)
        mask[rr, cc] = True

    return mask


def prepare_mask_cv(shape, countor, slice_info, roi_number):
    mask = np.zeros(shape, dtype=np.uint8)
    roi = countor[roi_number]

    position = np.asarray(slice_info["patient_pos"], dtype=float)
    orientation = np.asarray(slice_info["orientation"], dtype=float)
    spacing = np.asarray(slice_info["pixel_spacing"], dtype=float)

    for data in roi["arrays"]:
        points = np.asarray(data, dtype=float).reshape(-1, 3)
        if len(points) < 3:  # например, ISOCENTER имеет тип POINT
            continue

        delta = points - position
        cols = (delta @ orientation[:3]) / spacing[1]
        rows = (delta @ orientation[3:]) / spacing[0]

        vertices = np.rint(
            np.column_stack((cols, rows)) * 16
        ).astype(np.int32)

        cv2.fillPoly(mask, [vertices], color=1, shift=4)

    return mask.astype(bool)


def collect_masks(cts, info):
    n_roi = len(info[0]["countors"])
    masks = np.zeros((len(cts), n_roi, *cts.shape[1:]), dtype=bool)

    for j in range(len(cts)):
        for roi_number, countor in enumerate(info[j]["countors"], start=1):
            masks[j, roi_number - 1] = prepare_mask_cv(
                cts[j].shape, countor, info[j], roi_number
            )
        info[j]["masks"] = masks[j]

    return masks
