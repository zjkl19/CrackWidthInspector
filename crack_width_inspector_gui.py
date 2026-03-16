import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from crack_width_inspector import default_model_dir, process_images, runtime_base_dir


class ProcessingWorker(QThread):
    message = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, input_path: Path, output_dir: Path, scale: float, sample_count: int):
        super().__init__()
        self.input_path = input_path
        self.output_dir = output_dir
        self.scale = scale
        self.sample_count = sample_count

    def run(self):
        try:
            results = process_images(
                input_path=self.input_path,
                out_dir=self.output_dir,
                scale=self.scale,
                sample_count=self.sample_count,
                model_dir=default_model_dir(),
                status_callback=self.message.emit,
            )
            self.succeeded.emit(results)
        except Exception:
            self.failed.emit(traceback.format_exc())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.results = []
        self.current_preview_path = None

        self.setWindowTitle("Crack Width Inspector")
        self.resize(1280, 820)

        self.input_edit = QLineEdit()
        self.output_edit = QLineEdit(str(runtime_base_dir() / "outputs"))
        self.scale_spin = QDoubleSpinBox()
        self.sample_spin = QSpinBox()
        self.start_button = QPushButton("Start")
        self.open_output_button = QPushButton("Open Output")
        self.results_list = QListWidget()
        self.preview_label = QLabel("No preview")
        self.log_edit = QPlainTextEdit()
        self.summary_label = QLabel("Ready")

        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        self.scale_spin.setDecimals(4)
        self.scale_spin.setRange(0.0001, 9999.0)
        self.scale_spin.setValue(0.1)
        self.scale_spin.setSingleStep(0.01)

        self.sample_spin.setRange(1, 100)
        self.sample_spin.setValue(5)

        self.log_edit.setReadOnly(True)
        self.results_list.setMinimumWidth(320)

        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(600, 400)
        self.preview_label.setStyleSheet(
            "background:#1f2933;color:#d9e2ec;border:1px solid #52606d;"
        )

        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setWidget(self.preview_label)

        form_group = QGroupBox("Processing")
        form_layout = QGridLayout()
        form_layout.addWidget(QLabel("Input"), 0, 0)
        form_layout.addWidget(self.input_edit, 0, 1)

        browse_file_button = QPushButton("Image")
        browse_folder_button = QPushButton("Folder")
        form_layout.addWidget(browse_file_button, 0, 2)
        form_layout.addWidget(browse_folder_button, 0, 3)

        form_layout.addWidget(QLabel("Output"), 1, 0)
        form_layout.addWidget(self.output_edit, 1, 1)
        browse_output_button = QPushButton("Browse")
        form_layout.addWidget(browse_output_button, 1, 2, 1, 2)

        form_layout.addWidget(QLabel("Scale (mm/px)"), 2, 0)
        form_layout.addWidget(self.scale_spin, 2, 1)
        form_layout.addWidget(QLabel("Sample Count"), 2, 2)
        form_layout.addWidget(self.sample_spin, 2, 3)

        button_row = QHBoxLayout()
        button_row.addWidget(self.start_button)
        button_row.addWidget(self.open_output_button)
        button_row.addStretch(1)
        button_row.addWidget(self.summary_label)

        form_wrapper = QVBoxLayout()
        form_wrapper.addLayout(form_layout)
        form_wrapper.addLayout(button_row)
        form_group.setLayout(form_wrapper)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("Result Files"))
        left_layout.addWidget(self.results_list)

        right_top = QWidget()
        right_top_layout = QVBoxLayout(right_top)
        right_top_layout.addWidget(QLabel("Overlay Preview"))
        right_top_layout.addWidget(preview_scroll)

        right_bottom = QWidget()
        right_bottom_layout = QVBoxLayout(right_bottom)
        right_bottom_layout.addWidget(QLabel("Log"))
        right_bottom_layout.addWidget(self.log_edit)

        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.addWidget(right_top)
        right_splitter.addWidget(right_bottom)
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 2)

        main_splitter = QSplitter()
        main_splitter.addWidget(left_panel)
        main_splitter.addWidget(right_splitter)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 3)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.addWidget(form_group)
        central_layout.addWidget(main_splitter)
        self.setCentralWidget(central)

        self.browse_file_button = browse_file_button
        self.browse_folder_button = browse_folder_button
        self.browse_output_button = browse_output_button

    def _connect_signals(self):
        self.browse_file_button.clicked.connect(self.choose_file)
        self.browse_folder_button.clicked.connect(self.choose_folder)
        self.browse_output_button.clicked.connect(self.choose_output_dir)
        self.start_button.clicked.connect(self.start_processing)
        self.open_output_button.clicked.connect(self.open_output_dir)
        self.results_list.currentItemChanged.connect(self.on_result_selected)

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image",
            str(runtime_base_dir()),
            "Images (*.jpg *.jpeg *.png *.bmp *.tif *.tiff)",
        )
        if path:
            self.input_edit.setText(path)

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Folder", str(runtime_base_dir())
        )
        if path:
            self.input_edit.setText(path)

    def choose_output_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", self.output_edit.text() or str(runtime_base_dir())
        )
        if path:
            self.output_edit.setText(path)

    def start_processing(self):
        input_text = self.input_edit.text().strip()
        output_text = self.output_edit.text().strip()
        if not input_text:
            QMessageBox.warning(self, "Missing Input", "Please choose an image or folder.")
            return
        if not output_text:
            QMessageBox.warning(self, "Missing Output", "Please choose an output directory.")
            return

        input_path = Path(input_text)
        output_dir = Path(output_text)
        if not input_path.exists():
            QMessageBox.warning(self, "Invalid Input", f"Path does not exist:\n{input_path}")
            return

        self.results.clear()
        self.results_list.clear()
        self.preview_label.setPixmap(QPixmap())
        self.preview_label.setText("Processing...")
        self.log_edit.clear()
        self.summary_label.setText("Running")
        self.set_controls_enabled(False)

        self.worker = ProcessingWorker(
            input_path=input_path,
            output_dir=output_dir,
            scale=self.scale_spin.value(),
            sample_count=self.sample_spin.value(),
        )
        self.worker.message.connect(self.append_log)
        self.worker.succeeded.connect(self.handle_success)
        self.worker.failed.connect(self.handle_failure)
        self.worker.start()

    def set_controls_enabled(self, enabled: bool):
        for widget in (
            self.input_edit,
            self.output_edit,
            self.scale_spin,
            self.sample_spin,
            self.start_button,
            self.browse_file_button,
            self.browse_folder_button,
            self.browse_output_button,
        ):
            widget.setEnabled(enabled)

    def append_log(self, message: str):
        self.log_edit.appendPlainText(message)

    def handle_success(self, results):
        self.worker = None
        self.results = results
        self.set_controls_enabled(True)
        self.summary_label.setText(f"Done: {len(results)} image(s)")
        self.append_log("Processing completed.")

        for result in results:
            item = QListWidgetItem(result.input_path.name)
            item.setData(Qt.UserRole, result)
            item.setToolTip(str(result.overlay_path))
            self.results_list.addItem(item)

        if self.results_list.count():
            self.results_list.setCurrentRow(0)

    def handle_failure(self, traceback_text: str):
        self.worker = None
        self.set_controls_enabled(True)
        self.summary_label.setText("Failed")
        self.append_log(traceback_text)
        QMessageBox.critical(self, "Processing Failed", traceback_text)

    def on_result_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        if current is None:
            return
        result = current.data(Qt.UserRole)
        self.current_preview_path = result.overlay_path
        self.summary_label.setText(
            f"{result.input_path.name} | skeleton: {result.skeleton_points} | samples: {result.sampled_points}"
        )
        self.update_preview()

    def update_preview(self):
        if not self.current_preview_path:
            return

        pixmap = QPixmap(str(self.current_preview_path))
        if pixmap.isNull():
            self.preview_label.setText(f"Failed to load preview:\n{self.current_preview_path}")
            return

        scaled = pixmap.scaled(
            self.preview_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)
        self.preview_label.setText("")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.current_preview_path:
            self.update_preview()

    def open_output_dir(self):
        output_text = self.output_edit.text().strip()
        if not output_text:
            return
        path = Path(output_text)
        if not path.exists():
            QMessageBox.warning(self, "Missing Directory", f"Output directory not found:\n{path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
