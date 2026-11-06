import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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
        self.slice_pixmap = None
        self.front_image = None
        self.side_image = None
        self.page1.label.installEventFilter(self)
        self.page1.firstSideLabel.installEventFilter(self)
        self.page1.secondSideLabel.installEventFilter(self)
        self.page1.actionOpenFolder.triggered.connect(self.load_folder)
        self.list_files = []
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

    def log_out(self):
        self.clear_session_view()
        con = sqlite3.connect("data/main.db")
        cur = con.cursor()
        cur.execute(utils.bd_requests.logout_request)
        con.commit()
        con.close()

    def clear_session_view(self):
        self.page2.loginLineEdit.clear()
        self.page2.passwordLineEdit.clear()
        self.slice_pixmap = None
        self.page1.label.clear()
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

    def show_register_page(self):
        self.stack.setCurrentIndex(2)
        self.page3.loginLineEdit.clear()
        self.page3.passwordLineEdit.clear()

    def show_login_page(self):
        self.stack.setCurrentIndex(1)
        self.page2.loginLineEdit.clear()
        self.page2.passwordLineEdit.clear()

    def log_in(self):
        login = self.page2.loginLineEdit.text()
        password = self.page2.passwordLineEdit.text()
        if not login or not password:
            self.statusBar().showMessage("Введите логин и пароль", 5000)
            return
        con = sqlite3.connect("data/main.db")
        try:
            cur = con.cursor()
            result = cur.execute(utils.bd_requests.log_in_, (login,)).fetchone()
            if result is None:
                self.statusBar().showMessage("Неверный логин или пароль", 5000)
                return
            stored_password_hash = result[0]
            try:
                self.ph.verify(stored_password_hash, password)
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
                self.statusBar().showMessage("Неверный логин или пароль", 5000)
        finally:
            con.close()

    def register(self):
        login = self.page3.loginLineEdit.text()
        password = self.page3.passwordLineEdit.text()
        if not login or not password:
            self.statusBar().showMessage("Заполните все поля", 5000)
            return
        con = sqlite3.connect("data/main.db")
        cur = con.cursor()
        result = cur.execute(utils.bd_requests.reg_in_, (login,)).fetchone()
        if result:
            self.statusBar().showMessage("Пользователь с таким логином уже существует", 5000)
            con.close()
            return
        password_hash = self.ph.hash(password)
        cur.execute(utils.bd_requests.check_password_, (login, password_hash))
        con.commit()
        con.close()
        self.statusBar().showMessage("Пользователь успешно зарегистрирован", 5000)
        self.stack.setCurrentIndex(1)

    def show_folder_path(self):
        folder = getattr(self, "folder", "")
        self.statusBar().showMessage(folder or "Папка не выбрана", 5000)

    def open_file(self, item):
        if not self.check_active_session():
            return
        index = self.page1.fileList.row(item)
        if self.page1.sliceSlider.value() == index + 1:
            self.show_dicom(index)
        else:
            self.page1.sliceSlider.setValue(index + 1)

    def load_folder(self):
        if not self.check_active_session():
            return
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку", "")
        if not folder:
            return
        self.list_files = []
        self.folder = folder
        self.clear_projection_views()
        self.page1.sliceSlider.setValue(1)
        self.list_files = utils.dicom_func.get_dicom_files(self.folder)
        self.page1.fileList.clear()
        self.page1.fileList.addItems([file for number, file in self.list_files])
        self.page1.sliceSlider.setEnabled(bool(self.list_files))
        if not self.list_files:
            self.page1.sliceCounter.setText("Срез: 0 / 0")
            self.slice_pixmap = None
            self.page1.label.clear()
            self.show_patient_data(None)
            return
        self.page1.sliceSlider.setMaximum(len(self.list_files))
        self.page1.sliceCounter.setText(f"Срез: 1 / {len(self.list_files)}")
        self.show_dicom(0)
        self.build_projection_views()
        con = sqlite3.connect("data/main.db")
        cur = con.cursor()
        if not cur.execute(utils.bd_requests.сheck_file_, (self.folder,)).fetchone():
            cur.execute(
                utils.bd_requests.file_add_,
                (self.folder.split("/")[-2], self.folder),
            )
            con.commit()
        cur.execute(utils.bd_requests.action_add_, (self.folder,))
        con.commit()
        con.close()

    def slider_edit(self):
        if not self.check_active_session():
            return
        if not self.list_files:
            return
        value = self.page1.sliceSlider.value()
        self.show_dicom(value - 1)
        self.page1.sliceCounter.setText(f"Срез: {value} / {len(self.list_files)}")
        self.update_projection_views()

    def clear_projection_views(self):
        self.front_image = None
        self.side_image = None
        self.page1.firstSideLabel.clear()
        self.page1.secondSideLabel.clear()

    def build_projection_views(self):
        try:
            front_pixels, side_pixels = utils.dicom_func.build_projection_views(
                self.folder, self.list_files
            )
        except ValueError:
            self.clear_projection_views()
            self.statusBar().showMessage(
                "Не удалось построить дополнительные виды: размеры срезов различаются",
                5000,
            )
            return
        self.front_image = self.pixels_to_image(front_pixels)
        self.side_image = self.pixels_to_image(side_pixels)
        self.update_projection_views()

    def pixels_to_image(self, pixels):
        height, width = pixels.shape
        return QImage(
            pixels.tobytes(),
            width,
            height,
            width,
            QImage.Format.Format_Grayscale8,
        ).copy()

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

    def show_dicom(self, index):
        ds, pixels = utils.dicom_func.get_slice(self.folder, self.list_files, index)
        image = self.pixels_to_image(pixels)
        self.slice_pixmap = QPixmap.fromImage(image)
        self.update_slice_pixmap()
        self.show_patient_data(ds)
        self.update_last_date()

    def update_last_date(self):
        today = datetime.now(ZoneInfo("Europe/Moscow"))
        date = f"{today.day}.{today.month}.{today.year}"
        con = sqlite3.connect("data/main.db")
        try:
            con.execute(utils.bd_requests.add_date_, (date,))
            con.commit()
        finally:
            con.close()

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

    def eventFilter(self, obj, event):
        if obj is self.page1.label and event.type() == QEvent.Type.Resize:
            self.update_slice_pixmap()
            self.check_active_session()
        elif obj in (self.page1.firstSideLabel, self.page1.secondSideLabel):
            if event.type() == QEvent.Type.Resize:
                self.update_projection_views()
        return super().eventFilter(obj, event)

    def update_slice_pixmap(self):
        if self.slice_pixmap is None:
            return
        pixmap = self.slice_pixmap.scaled(
            self.page1.label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.page1.label.setPixmap(pixmap)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    ex = DicomReader()
    ex.show()
    sys.exit(app.exec())
