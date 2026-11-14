import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pydicom
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QTreeWidgetItem

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

    def show_md_side_views(self):
        self.image_filter = 1
        if self.cts is not None:
            self.build_projection_views()

    def show_main_slice(self):
        self.main_window = 0
        self.move_image_labels()

    def show_side_slice(self):
        self.main_window = 1
        self.move_image_labels()

    def show_front_slice(self):
        self.main_window = 2
        self.move_image_labels()

    def move_image_labels(self):
        tab = self.page1.windowList
        image = self.page1.imageLabel
        mask = self.page1.maskLabel
        dose = self.page1.doseLabel
        front = self.page1.firstSideLabel
        side = self.page1.secondSideLabel

        image_layout = self.page1.imageSliceLayout
        mask_layout = self.page1.maskSliceLayout
        dose_layout = self.page1.doseSliceLayout
        front_layout = self.page1.frontViewLayout
        side_layout = self.page1.sideViewLayout

        layouts = (
            self.page1.mainViewLayout,
            image_layout,
            mask_layout,
            dose_layout,
            front_layout,
            side_layout,
        )

        for widget in (tab, image, mask, dose, front, side):
            for layout in layouts:
                layout.removeWidget(widget)

        self.page1.mainViewLayout.addWidget(tab)
        image_layout.addWidget(image)
        mask_layout.addWidget(mask)
        dose_layout.addWidget(dose)
        front_layout.addWidget(front)
        side_layout.addWidget(side)

        tab.setMinimumSize(500, 500)
        index = tab.currentIndex()

        if index in (0, 1, 2):
            main_labels = (image, mask, dose)
            tab_layouts = (image_layout, mask_layout, dose_layout)
            main_label = main_labels[index]
            tab_layout = tab_layouts[index]

            if self.main_window == 0:
                self.page1.mainViewHeader.setText("Основной срез")
                self.page1.frontViewHeader.setText("Вид спереди")
                self.page1.sideViewHeader.setText("Вид сбоку")
            elif self.main_window == 1:
                tab_layout.removeWidget(main_label)
                front_layout.removeWidget(front)
                side_layout.removeWidget(side)

                tab_layout.addWidget(side)
                front_layout.addWidget(main_label)
                side_layout.addWidget(front)

                self.page1.mainViewHeader.setText("Вид сбоку")
                self.page1.frontViewHeader.setText("Основной срез")
                self.page1.sideViewHeader.setText("Вид спереди")
            elif self.main_window == 2:
                tab_layout.removeWidget(main_label)
                front_layout.removeWidget(front)
                side_layout.removeWidget(side)

                tab_layout.addWidget(front)
                front_layout.addWidget(main_label)
                side_layout.addWidget(side)

                self.page1.mainViewHeader.setText("Вид спереди")
                self.page1.frontViewHeader.setText("Основной срез")
                self.page1.sideViewHeader.setText("Вид сбоку")

        for widget in (tab, image, mask, dose, front, side):
            widget.show()

        self.update_slice_pixmap()
        self.update_projection_views()

    def opened_tab(self, index):
        if index in (0, 1, 2):
            self.last_image_tab = index
        self.move_image_labels()
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
        if self.contour_index is None:
            mask = self.masks[index].any(axis=0)
        else:
            mask = self.masks[index, self.contour_index]
        mask = mask.astype(np.uint8) * 255

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
                if self.contour_index is None:
                    volume = self.masks.any(axis=1)
                else:
                    volume = self.masks[:, self.contour_index]
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
            self.patient_data = {
                "Имя пациента": "—",
                "ID пациента": "—",
                "Дата рождения": "—",
                "Модальность": "—",
            }
            return

        birth_date = str(ds.get("PatientBirthDate") or "")
        if len(birth_date) == 8 and birth_date.isdigit():
            birth_date = (
                f"{birth_date[6:8]}.{birth_date[4:6]}.{birth_date[:4]}"
            )
        else:
            birth_date = "—"

        self.patient_data = {
            "Имя пациента": str(ds.get("PatientName") or "—"),
            "ID пациента": str(ds.get("PatientID") or "—"),
            "Дата рождения": birth_date,
            "Модальность": str(ds.get("Modality") or "—"),
        }

    def show_study_data(self, info):
        self.study_info = info
        tree = self.page1.studyTree
        tree.clear()
        tree.setColumnWidth(0, 260)

        patient = QTreeWidgetItem(tree, ["Данные пациента"])
        for name, value in self.patient_data.items():
            QTreeWidgetItem(patient, [name, value])
        patient.setExpanded(True)

        sections = (
            ("КТ", "ct"),
            ("Контуры", "roi_channels"),
            ("Доза", "dose"),
            ("План", "plan"),
        )
        for title, key in sections:
            section = QTreeWidgetItem(tree, [title])
            if info is None:
                continue
            if key == "roi_channels":
                for contour in info[key].values():
                    number = contour["roi_number"]
                    name = contour["name"]
                    QTreeWidgetItem(section, [f"{number} — {name}"])
            else:
                for name, value in info[key].items():
                    self.add_data_row(section, name, value)

    def add_data_row(self, parent, name, value):
        names = {
            "frame_uid": "Идентификатор системы координат",
            "series_uid": "Идентификатор серии",
            "positions": "Позиции срезов",
            "pixel_spacing": "Размер пикселя",
            "patient_pos": "Положение пациента",
            "orientation": "Ориентация изображения",
            "offset": "Смещения срезов",
            "dose": "Доза",
            "DVH": "Гистограммы доза–объём",
            "dose_reference": "Дозовые ориентиры",
            "fraction_group": "Группы фракций",
            "beam_sequence": "Пучки",
            "control_points": "Контрольные точки",
            "units": "Единицы измерения",
            "type": "Тип",
            "sum_type": "Способ суммирования",
            "plan_uid": "Идентификатор плана",
            "struct_uid": "Идентификатор контуров",
            "structure_uid": "Идентификатор контуров",
            "sop": "Идентификатор плана",
            "contribution_type": "Тип вклада контура",
            "scaling": "Масштаб дозы",
            "volume_units": "Единицы объёма",
            "bins": "Число интервалов",
            "data": "Значения",
            "min_dose": "Минимальная доза",
            "max_dose": "Максимальная доза",
            "dose_struct_type": "Тип дозового ориентира",
            "dose_type": "Тип дозы",
            "delivery_max_dose": "Максимальная подведённая доза",
            "target_prescription_dose": "Предписанная доза",
            "target_max_dose": "Максимальная доза для цели",
            "point_coords": "Координаты точки",
            "num_fracts": "Число фракций",
            "num_beans": "Число пучков",
            "beams": "Пучки",
            "meterset": "Показание счётчика",
            "beam_type": "Тип пучка",
            "rad_type": "Тип излучения",
            "delivary_type": "Способ облучения",
            "beam_num": "Номер пучка",
            "reg_imgs": "Связанные изображения",
            "meterset_weight": "Доля показания счётчика",
            "isocenter_pos": "Положение изоцентра",
            "dose_ref": "Дозовые ориентиры",
            "gantry": "Гантри",
            "patient_sup": "Опора пациента",
            "table": "Стол",
            "top": "Столешница",
            "eccentric": "Эксцентрическое вращение",
            "vertical": "Вертикальное положение",
            "longitudinal": "Продольное положение",
            "lateral": "Поперечное положение",
            "pitch": "Наклон",
            "angle": "Угол",
            "direction": "Направление",
            "pos": "Положение",
        }
        title = names.get(str(name), str(name))
        if isinstance(value, (dict, list, tuple, np.ndarray)):
            item = QTreeWidgetItem(parent, [title, f"Элементов: {len(value)}"])
            if len(value):
                item.setData(0, Qt.ItemDataRole.UserRole, value)
                QTreeWidgetItem(item, [""])
        else:
            text = "—" if value is None else str(value)
            item = QTreeWidgetItem(parent, [title, text])
            item.setToolTip(1, text)

    def open_data_row(self, item):
        value = item.data(0, Qt.ItemDataRole.UserRole)
        if value is None:
            return
        item.takeChildren()
        if isinstance(value, dict):
            for name, child in value.items():
                self.add_data_row(item, name, child)
        else:
            for index, child in enumerate(value, start=1):
                self.add_data_row(item, index, child)
        item.setData(0, Qt.ItemDataRole.UserRole, None)

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
