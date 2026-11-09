import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

import numpy as np
import pydicom
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from PyQt6 import uic
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QStackedWidget,
)

import utils.bd_requests
import utils.dicom_func
from parser.parser import prepare_all_data


class DicomReader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.stack = QStackedWidget()
        ui_dir = Path(__file__).resolve().parent / "ui"
        self.page1 = uic.loadUi(str(ui_dir / "main.ui"))
        self.page2 = uic.loadUi(str(ui_dir / "log.ui"))
        self.page3 = uic.loadUi(str(ui_dir / "reg.ui"))
        style_path = Path(__file__).resolve().parent / "styles" / "style.qss"
        self.setStyleSheet(style_path.read_text(encoding="utf-8"))
        self.stack.addWidget(self.page1)
        self.stack.addWidget(self.page2)
        self.stack.addWidget(self.page3)
        self.setCentralWidget(self.stack)
        self.resize(1360, 820)
        self.folder = ""
        self.list_files = []
        self.cts = None
        self.masks = None
        self.doses = None
        self.dose_max = 0.0
        self.slice_pixmap = None
        self.mask_pixmap = None
        self.dose_pixmap = None
        self.front_image = None
        self.side_image = None
        self.image_filter = 0
        self.last_image_tab = 0
        self.page1.imageLabel.installEventFilter(self)
        self.page1.maskLabel.installEventFilter(self)
        self.page1.doseLabel.installEventFilter(self)
        self.page1.firstSideLabel.installEventFilter(self)
        self.page1.secondSideLabel.installEventFilter(self)
        self.page1.windowList.currentChanged.connect(self.update_slice_pixmap)
        self.page1.windowList.currentChanged.connect(self.opened_tab)
        self.page1.actionOpenFolder.triggered.connect(self.load_folder)
        self.page1.actionConstantView.triggered.connect(
            self.show_ct_side_views
        )
        self.page1.actionRepeatView.triggered.connect(
            self.show_md_side_views
        )
        self.page1.sliceSlider.setMinimum(1)
        self.page1.sliceSlider.setMaximum(1)
        self.page1.sliceCounter.setText("Срез: 0 / 0")
        self.page1.sliceSlider.valueChanged.connect(self.slider_edit)
        self.page2.loginButton.clicked.connect(self.log_in)
        self.page2.registerButton.clicked.connect(self.show_register_page)
        self.page3.registerButton.clicked.connect(self.register)
        self.page3.backButton.clicked.connect(self.show_login_page)
        self.page1.logOutButton.clicked.connect(self.log_out)
        self.page1.fileList.itemClicked.connect(self.open_file)
        self.page1.folderButton.clicked.connect(self.show_folder_path)
        self.ph = PasswordHasher()
        self.check_active_session()
        con = sqlite3.connect("data/main.db")
        cur = con.cursor()
        result = cur.execute(utils.bd_requests.login_request).fetchone()
        con.close()
        if result:
            self.stack.setCurrentIndex(0)
        else:
            self.stack.setCurrentIndex(1)

    def log_in(self):
        login = self.page2.loginLineEdit.text()
        password = self.page2.passwordLineEdit.text()
        if not login or not password:
            self.statusBar().showMessage(
                "Введите логин и пароль", 5000
            )
            return
        con = sqlite3.connect("data/main.db")
        try:
            cur = con.cursor()
            result = cur.execute(
                utils.bd_requests.log_in_, (login,)
            ).fetchone()
            if result is None:
                self.statusBar().showMessage(
                    "Неверный логин или пароль", 5000
                )
                return
            stored_password_hash = result[0]
            try:
                self.ph.verify(stored_password_hash, password)
                cur.execute(utils.bd_requests.logout_request)
                cur.execute(utils.bd_requests.check_login_, (login,))
                con.commit()
                today = datetime.now(ZoneInfo("Europe/Moscow"))
                date = f"{today.day}.{today.month}.{today.year}"
                cur.execute(utils.bd_requests.add_date_, (date,))
                con.commit()
                self.statusBar().showMessage("Успешный вход", 5000)
                self.stack.setCurrentIndex(0)
                self.page2.loginLineEdit.clear()
                self.page2.passwordLineEdit.clear()
            except (VerificationError, InvalidHashError):
                self.statusBar().showMessage(
                    "Неверный логин или пароль", 5000
                )
        finally:
            con.close()

    def log_out(self):
        self.clear_session_view()
        con = sqlite3.connect("data/main.db")
        cur = con.cursor()
        cur.execute(utils.bd_requests.logout_request)
        con.commit()
        con.close()

    def show_login_page(self):
        self.stack.setCurrentIndex(1)
        self.page2.loginLineEdit.clear()
        self.page2.passwordLineEdit.clear()

    def show_register_page(self):
        self.stack.setCurrentIndex(2)
        self.page3.loginLineEdit.clear()
        self.page3.passwordLineEdit.clear()

    def register(self):
        login = self.page3.loginLineEdit.text()
        password = self.page3.passwordLineEdit.text()
        if not login or not password:
            self.statusBar().showMessage(
                "Заполните все поля", 5000
            )
            return
        con = sqlite3.connect("data/main.db")
        cur = con.cursor()
        result = cur.execute(utils.bd_requests.reg_in_, (login,)).fetchone()
        if result:
            self.statusBar().showMessage(
                "Пользователь с таким логином "
                "уже существует",
                5000,
            )
            con.close()
            return
        password_hash = self.ph.hash(password)
        cur.execute(utils.bd_requests.check_password_, (login, password_hash))
        con.commit()
        con.close()
        self.statusBar().showMessage(
            "Пользователь успешно "
            "зарегистрирован",
            5000,
        )
        self.stack.setCurrentIndex(1)

    def check_active_session(self):
        con = sqlite3.connect("data/main.db")
        cur = con.cursor()
        date = cur.execute(utils.bd_requests.check_date_).fetchone()
        last_date = None
        if date and date[0]:
            try:
                last_date = datetime.strptime(date[0], "%d.%m.%Y").date()
            except ValueError:
                last_date = None
        today = datetime.now(ZoneInfo("Europe/Moscow")).date()
        active = last_date is not None and (today - last_date).days < 3
        if not active:
            cur.execute(utils.bd_requests.logout_request)
            con.commit()
        con.close()
        if not active:
            self.clear_session_view()
        return active

    def clear_session_view(self):
        self.page2.loginLineEdit.clear()
        self.page2.passwordLineEdit.clear()
        self.cts = None
        self.masks = None
        self.doses = None
        self.dose_max = 0.0
        self.slice_pixmap = None
        self.mask_pixmap = None
        self.dose_pixmap = None
        self.page1.imageLabel.clear()
        self.page1.maskLabel.clear()
        self.page1.doseLabel.clear()
        self.clear_projection_views()
        self.show_patient_data(None)
        self.page1.sliceCounter.setText("Срез: 0 / 0")
        self.list_files = []
        self.folder = ""
        signals_blocked = self.page1.sliceSlider.blockSignals(True)
        self.page1.sliceSlider.setValue(1)
        self.page1.sliceSlider.setMaximum(1)
        self.page1.sliceSlider.blockSignals(signals_blocked)
        self.page1.sliceSlider.setEnabled(False)
        self.page1.fileList.clear()
        self.stack.setCurrentIndex(1)

    def load_folder(self):
        if not self.check_active_session():
            return
        folder = QFileDialog.getExistingDirectory(
            self, "Выберите папку", ""
        )
        if not folder:
            return
        patient_folder = Path(folder)
        try:
            files = utils.dicom_func.get_dicom_files(folder)
            if not files:
                raise ValueError("В папке нет КТ-срезов")

            with TemporaryDirectory() as ct_folder:
                for _, filename in files:
                    source = patient_folder / filename
                    (Path(ct_folder) / filename).symlink_to(source)
                cts, masks, doses, info = prepare_all_data(
                    ct_folder,
                    str(patient_folder / "RS.dcm"),
                    str(patient_folder / "RD.dcm"),
                    str(patient_folder / "RP.dcm"),
                )

            if len(files) != len(cts):
                raise ValueError(
                    "Список файлов не совпадает "
                    "с массивом КТ"
                )
            first_ds = pydicom.dcmread(
                Path(folder) / files[0][1], stop_before_pixels=True
            )
            for (_, filename), position in zip(
                files, info["ct"]["positions"]
            ):
                ds = pydicom.dcmread(
                    Path(folder) / filename, stop_before_pixels=True
                )
                if not np.allclose(ds.ImagePositionPatient, position):
                    raise ValueError(
                        "Порядок файлов не совпадает "
                        "с массивом КТ"
                    )
        except Exception as error:
            message = (
                "Не удалось открыть исследование: "
                f"{error}"
            )
            self.statusBar().showMessage(message, 10000)
            return

        self.folder = folder
        self.cts = cts
        self.masks = masks
        self.doses = doses
        self.dose_max = float(doses.max())
        self.list_files = files
        self.slice_pixmap = None
        self.mask_pixmap = None
        self.dose_pixmap = None
        self.clear_projection_views()

        signals_blocked = self.page1.sliceSlider.blockSignals(True)
        self.page1.sliceSlider.setMaximum(len(self.list_files))
        self.page1.sliceSlider.setValue(1)
        self.page1.sliceSlider.setEnabled(True)
        self.page1.sliceSlider.blockSignals(signals_blocked)

        self.page1.fileList.clear()
        self.page1.fileList.addItems([file for _, file in self.list_files])
        self.page1.sliceCounter.setText(
            f"Срез: 1 / {len(self.list_files)}"
        )
        self.show_patient_data(first_ds)
        self.show_dicom(0)
        self.build_projection_views()
        con = sqlite3.connect("data/main.db")
        cur = con.cursor()
        if not cur.execute(
            utils.bd_requests.check_file_, (self.folder,)
        ).fetchone():
            cur.execute(
                utils.bd_requests.file_add_,
                (self.folder.split("/")[-2], self.folder),
            )
            con.commit()
        cur.execute(utils.bd_requests.action_add_, (self.folder,))
        con.commit()
        con.close()

    def show_folder_path(self):
        self.statusBar().showMessage(
            self.folder or "Папка не выбрана", 5000
        )

    def show_ct_side_views(self):
        self.image_filter = 0
        if self.cts is not None:
            self.build_projection_views()

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
        con = sqlite3.connect("data/main.db")
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

    def eventFilter(self, obj, event):
        if obj in (
            self.page1.imageLabel,
            self.page1.maskLabel,
            self.page1.doseLabel,
        ) and event.type() == QEvent.Type.Resize:
            self.update_slice_pixmap()
            if obj is self.page1.imageLabel:
                self.check_active_session()
        elif obj in (self.page1.firstSideLabel, self.page1.secondSideLabel):
            if event.type() == QEvent.Type.Resize:
                self.update_projection_views()
        return super().eventFilter(obj, event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    ex = DicomReader()
    ex.show()
    sys.exit(app.exec())
