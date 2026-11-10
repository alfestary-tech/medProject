import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pydicom
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter, QPen, QPixmap

import utils.bd_requests
from utils.db_path import get_db_path


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


class DicomFunctions:
    def show_ct_side_views(self):
        self.image_filter = 0
        if self.cts is not None:
            self.build_projection_views()

    def show_main_slice(self):
        self.main_window = 0
        self.move_main_window_widgets()

    def show_side_slice(self):
        self.main_window = 1
        self.move_main_window_widgets()

    def show_front_slice(self):
        self.main_window = 2
        self.move_main_window_widgets()

    def move_main_window_widgets(self):
        tab = self.page1.windowList
        front = self.page1.firstSideLabel
        side = self.page1.secondSideLabel

        self.page1.mainViewLayout.removeWidget(tab)
        self.page1.mainViewLayout.removeWidget(front)
        self.page1.mainViewLayout.removeWidget(side)
        self.page1.frontViewLayout.removeWidget(tab)
        self.page1.frontViewLayout.removeWidget(front)
        self.page1.frontViewLayout.removeWidget(side)
        self.page1.sideViewLayout.removeWidget(tab)
        self.page1.sideViewLayout.removeWidget(front)
        self.page1.sideViewLayout.removeWidget(side)

        if self.main_window == 0:
            big_widget = tab
            front_widget = front
            side_widget = side
            self.page1.mainViewHeader.setText("Основной срез")
            self.page1.frontViewHeader.setText("Вид спереди")
            self.page1.sideViewHeader.setText("Вид сбоку")
        elif self.main_window == 1:
            big_widget = side
            front_widget = tab
            side_widget = front
            self.page1.mainViewHeader.setText("Вид сбоку")
            self.page1.frontViewHeader.setText("Основной срез")
            self.page1.sideViewHeader.setText("Вид спереди")
        else:
            big_widget = front
            front_widget = tab
            side_widget = side
            self.page1.mainViewHeader.setText("Вид спереди")
            self.page1.frontViewHeader.setText("Основной срез")
            self.page1.sideViewHeader.setText("Вид сбоку")

        if big_widget == tab:
            tab.setMinimumSize(500, 500)
        else:
            tab.setMinimumSize(0, 0)

        self.page1.mainViewLayout.addWidget(big_widget)
        self.page1.frontViewLayout.addWidget(front_widget)
        self.page1.sideViewLayout.addWidget(side_widget)
        self.page1.viewersLayout.setStretch(0, 9)
        self.page1.viewersLayout.setStretch(1, 4)

        tab.show()
        front.show()
        side.show()

    def show_md_side_views(self):
        self.image_filter = 1
        if self.cts is not None:
            self.build_projection_views()

    def opened_tab(self, index):
        if index in (0, 1, 2):
            self.last_image_tab = index
        if self.image_filter == 1 and self.cts is not None:
            self.build_projection_views()

    def open_file(self, item):
        if not self.check_active_session():
            return
        index = self.page1.fileList.row(item)
        if self.page1.sliceSlider.value() == index + 1:
            self.show_dicom(index)
        else:
            self.page1.sliceSlider.setValue(index + 1)

    def slider_edit(self):
        if not self.check_active_session():
            return
        if not self.list_files:
            return
        value = self.page1.sliceSlider.value()
        self.show_dicom(value - 1)
        self.page1.sliceCounter.setText(
            f"Срез: {value} / {len(self.list_files)}"
        )
        self.update_projection_views()

    def update_slice_pixmap(self, *_):
        for pixmap, label in (
            (self.slice_pixmap, self.page1.imageLabel),
            (self.mask_pixmap, self.page1.maskLabel),
            (self.dose_pixmap, self.page1.doseLabel),
        ):
            if pixmap is None or label.size().isEmpty():
                continue
            label.setPixmap(
                pixmap.scaled(
                    label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def show_dicom(self, index):
        ct = self.cts[index]
        ct_min, ct_max = np.percentile(ct, (1, 99))
        mask = self.masks[index].any(axis=0).astype(np.uint8) * 255

        self.slice_pixmap = QPixmap.fromImage(
            self.array_to_image(ct, ct_min, ct_max)
        )
        self.mask_pixmap = QPixmap.fromImage(self.pixels_to_image(mask))
        self.dose_pixmap = QPixmap.fromImage(
            self.array_to_image(self.doses[index], 0, self.dose_max)
        )
        self.update_slice_pixmap()
        self.update_last_date()

    def build_projection_views(self):
        volume = self.cts
        if self.image_filter == 1:
            if self.last_image_tab == 1:
                volume = self.masks.any(axis=1)
            elif self.last_image_tab == 2:
                volume = self.doses

        front_pixels = volume[:, volume.shape[1] // 2, :]
        side_pixels = volume[:, :, volume.shape[2] // 2]

        if self.image_filter == 1 and self.last_image_tab == 1:
            self.front_image = self.pixels_to_image(
                front_pixels.astype(np.uint8) * 255
            )
            self.side_image = self.pixels_to_image(
                side_pixels.astype(np.uint8) * 255
            )
        elif self.image_filter == 1 and self.last_image_tab == 2:
            self.front_image = self.array_to_image(
                front_pixels, 0, self.dose_max
            )
            self.side_image = self.array_to_image(
                side_pixels, 0, self.dose_max
            )
        else:
            front_min, front_max = np.percentile(front_pixels, (1, 99))
            side_min, side_max = np.percentile(side_pixels, (1, 99))
            self.front_image = self.array_to_image(
                front_pixels, front_min, front_max
            )
            self.side_image = self.array_to_image(
                side_pixels, side_min, side_max
            )
        self.update_projection_views()

    def update_projection_views(self):
        if not self.list_files:
            return
        for image, label in (
            (self.front_image, self.page1.firstSideLabel),
            (self.side_image, self.page1.secondSideLabel),
        ):
            if image is None:
                continue
            pixmap = QPixmap.fromImage(image).scaled(
                label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            y = round(
                (self.page1.sliceSlider.value() - 0.5)
                * pixmap.height()
                / len(self.list_files)
            )
            painter = QPainter(pixmap)
            painter.setPen(QPen(Qt.GlobalColor.white, 2))
            painter.drawLine(0, y, pixmap.width() - 1, y)
            painter.end()
            label.setPixmap(pixmap)

    def clear_projection_views(self):
        self.front_image = None
        self.side_image = None
        self.page1.firstSideLabel.clear()
        self.page1.secondSideLabel.clear()

    def show_patient_data(self, ds):
        if ds is None:
            self.page1.patientName.setText("—")
            self.page1.patientID.setText("—")
            self.page1.patientBD.setText("—")
            self.page1.modality.setText("—")
            return
        self.page1.patientName.setText(str(ds.get("PatientName") or "—"))
        self.page1.patientID.setText(str(ds.get("PatientID") or "—"))
        birth_date = str(ds.get("PatientBirthDate") or "")
        if len(birth_date) == 8 and birth_date.isdigit():
            self.page1.patientBD.setText(
                f"{birth_date[6:8]}.{birth_date[4:6]}.{birth_date[:4]}"
            )
        else:
            self.page1.patientBD.setText("—")
        self.page1.modality.setText(str(ds.get("Modality") or "—"))

    def update_last_date(self):
        today = datetime.now(ZoneInfo("Europe/Moscow"))
        date = f"{today.day}.{today.month}.{today.year}"
        con = sqlite3.connect(get_db_path())
        try:
            con.execute(utils.bd_requests.add_date_, (date,))
            con.commit()
        finally:
            con.close()

    def pixels_to_image(self, pixels):
        height, width = pixels.shape
        return QImage(
            pixels.tobytes(),
            width,
            height,
            width,
            QImage.Format.Format_Grayscale8,
        ).copy()

    def array_to_image(self, pixels, minimum, maximum):
        if maximum > minimum:
            pixels = np.clip(pixels, minimum, maximum)
            pixels = (pixels - minimum) * 255 / (maximum - minimum)
        else:
            pixels = np.zeros_like(pixels)
        return self.pixels_to_image(pixels.astype(np.uint8))
