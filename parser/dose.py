import pydicom
import numpy as np
from scipy.ndimage import map_coordinates

from utils.errors import ReferenceUIDError


def open_dose_dicom(filename: str, expected_frame_uid=None) -> tuple[np.array, dict]:
    dcm = pydicom.dcmread(filename, force=True)

    info = {"dose": {"units": dcm.DoseUnits,
                     "type": dcm.DoseType,
                     "sum_type": dcm.DoseSummationType},
            "pixel_spacing": list(dcm.PixelSpacing),
            "patient_pos": np.asarray(dcm.ImagePositionPatient, dtype=float),
            "orientation": list(dcm.ImageOrientationPatient),
            "offset":  np.asarray(dcm.GridFrameOffsetVector, dtype=float), 
            "frame_uid": str(dcm.FrameOfReferenceUID),
            "plan_uid": dcm.ReferencedRTPlanSequence[0].ReferencedSOPInstanceUID,
            "struct_uid": dcm.ReferencedStructureSetSequence[0].ReferencedSOPInstanceUID,
            "DVH": {}}

    if expected_frame_uid is not None:
        if expected_frame_uid != info["frame_uid"]:
            raise ReferenceUIDError("Wrong UID!")

    pixel_array = dcm.pixel_array * float(dcm.DoseGridScaling)

    for dvh_seq in dcm.DVHSequence:
        seq = dvh_seq.DVHReferencedROISequence[0]
        info["DVH"][seq.ReferencedROINumber] = {}
        info["DVH"][seq.ReferencedROINumber]["contribution_type"] = seq.DVHROIContributionType
        info["DVH"][seq.ReferencedROINumber]["units"] = dvh_seq.DoseUnits
        info["DVH"][seq.ReferencedROINumber]["type"] = dvh_seq.DoseType
        info["DVH"][seq.ReferencedROINumber]["scaling"] = dvh_seq.DVHDoseScaling
        info["DVH"][seq.ReferencedROINumber]["volume_units"] = dvh_seq.DVHVolumeUnits
        info["DVH"][seq.ReferencedROINumber]["bins"] = dvh_seq.DVHNumberOfBins
        info["DVH"][seq.ReferencedROINumber]["data"] = list(dvh_seq.DVHData)
        info["DVH"][seq.ReferencedROINumber]["min_dose"] = float(dvh_seq.DVHMinimumDose)
        info["DVH"][seq.ReferencedROINumber]["max_dose"] = float(dvh_seq.DVHMaximumDose)

    return pixel_array, info


def resize(cts, info_ct, dose_map, info_dose):
    if len(cts) != len(dose_map):
        raise ValueError("Число срезов КТ и дозы не совпадает")

    dose_on_ct = np.zeros(cts.shape, dtype=np.float32)
    valid_mask = np.zeros(cts.shape, dtype=bool)

    dose_rows, dose_cols = dose_map.shape[1:]
    dose_pos = info_dose["patient_pos"]
    dose_spacing = info_dose["pixel_spacing"]

    rows, cols = np.indices(cts.shape[1:], dtype=float)

    for k, info in enumerate(info_ct):
        ct_pos = info["patient_pos"]
        ct_spacing = info["pixel_spacing"]

        x = ct_pos[0] + cols * ct_spacing[1]
        y = ct_pos[1] + rows * ct_spacing[0]

        dose_col = (x - dose_pos[0]) / dose_spacing[1]
        dose_row = (y - dose_pos[1]) / dose_spacing[0]

        valid = (
            (dose_row >= 0) & (dose_row <= dose_rows - 1)
            & (dose_col >= 0) & (dose_col <= dose_cols - 1)
        )
        valid_mask[k] = valid

        map_coordinates(
            np.asarray(dose_map[k], dtype=np.float32),
            [dose_row, dose_col],
            output=dose_on_ct[k],
            order=1,
            mode="constant",
            cval=0.0,
            prefilter=False,
        )
        dose_on_ct[k][~valid] = 0

    return dose_on_ct, valid_mask
