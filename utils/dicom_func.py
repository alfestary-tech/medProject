import os

import pydicom


def get_dicom_files(folder):
    files = []
    for file in os.listdir(folder):
        if file.upper() in {"RS.DCM", "RP.DCM", "RD.DCM"}:
            continue
        if file.startswith("."):
            continue
        path = os.path.join(folder, file)
        if not os.path.isfile(path):
            continue
        ds = pydicom.dcmread(path, stop_before_pixels=True)
        z = float(ds.ImagePositionPatient[-1])
        files.append((z, str(ds.SOPInstanceUID), file))

    files.sort(key=lambda item: item[0])
    unique = {}
    for z, uid, file in files:
        unique.setdefault(uid, (z, file))
    return sorted(unique.values(), key=lambda item: item[0])
