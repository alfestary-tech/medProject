import os
import shutil
import sys
from pathlib import Path


def get_db_path():
    if not getattr(sys, "frozen", False):
        return Path("data/main.db")

    folder = Path(os.environ["LOCALAPPDATA"]) / "DicomViewer"
    folder.mkdir(parents=True, exist_ok=True)
    database = folder / "main.db"

    if not database.exists():
        source = Path(sys._MEIPASS) / "data" / "main.db"
        shutil.copyfile(source, database)

    return database
