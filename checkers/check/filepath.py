import os

def check_filenames(*filenames):
    for filename in filenames:
        if not os.path.exists(filename):
            raise FileExistsError("No File!")
        if os.path.isfile(filename):
            if not filename.endswith("dcm"):
                raise FileNotFoundError("File is not DICOM!")