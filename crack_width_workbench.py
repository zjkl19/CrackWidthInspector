from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from crack_width_inspector_gui import MainWindow as InspectorWindow
from manual_point_review import DEFAULT_POINTS_CSV, POINT_FIELDS, write_csv_rows, write_point_config
from manual_point_review_gui_launcher import write_log
from manual_point_review_pyside import ManualPointReviewWindow, app_icon_path


def executable_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def default_points_csv() -> Path:
    base_dir = Path(__file__).resolve().parent
    exe_dir = executable_dir()
    candidates = [
        Path.cwd() / DEFAULT_POINTS_CSV,
        exe_dir / DEFAULT_POINTS_CSV,
        exe_dir.parent / DEFAULT_POINTS_CSV,
        exe_dir.parent.parent / DEFAULT_POINTS_CSV,
        base_dir / DEFAULT_POINTS_CSV,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


class MissingReviewCsvTab(QWidget):
    def __init__(self, csv_path: Path, open_callback):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(14)

        title = QLabel("未找到人工复核 CSV")
        title_font = QFont("Microsoft YaHei UI", 15)
        title_font.setBold(True)
        title.setFont(title_font)

        detail = QLabel(
            "统一工作台已经打开，但没有找到默认测点复核文件。\n"
            f"默认查找路径：{csv_path}\n\n"
            "可以点击下方按钮手动选择 manual_point_review_points.csv。"
        )
        detail.setWordWrap(True)
        detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        open_button = QPushButton("选择复核 CSV")
        open_button.clicked.connect(open_callback)

        layout.addWidget(title)
        layout.addWidget(detail)
        layout.addWidget(open_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)


class CrackWidthWorkbench(QMainWindow):
    def __init__(self, points_csv: Path | None = None):
        super().__init__()
        self.inspector_window: InspectorWindow | None = None
        self.review_window: ManualPointReviewWindow | None = None
        self.review_tab: QWidget | None = None

        self.setWindowTitle("Crack Width Inspector - 自动识别与人工复核工作台")
        icon_path = app_icon_path()
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1680, 980)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._build_inspector_tab(), "自动识别")
        self.review_tab = self._build_review_tab(points_csv or default_points_csv())
        self.tabs.addTab(self.review_tab, "人工复核与指标")
        self.setCentralWidget(self.tabs)

    def _build_inspector_tab(self) -> QWidget:
        self.inspector_window = InspectorWindow()
        return self.inspector_window

    def _build_review_tab(self, points_csv: Path) -> QWidget:
        if not points_csv.exists():
            self.review_window = None
            return MissingReviewCsvTab(points_csv, self.open_review_csv)
        self.review_window = ManualPointReviewWindow(points_csv, log=write_log)
        return self.review_window

    def open_review_csv(self) -> None:
        csv_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择人工复核 CSV",
            str(default_points_csv().parent),
            "CSV 文件 (*.csv);;所有文件 (*.*)",
        )
        if not csv_path:
            return
        self.replace_review_tab(Path(csv_path))

    def replace_review_tab(self, points_csv: Path) -> None:
        if not self._confirm_review_save():
            return
        old_tab = self.review_tab
        review_index = self.tabs.indexOf(old_tab) if old_tab is not None else 1
        if review_index < 0:
            review_index = self.tabs.count()
        if old_tab is not None:
            self.tabs.removeTab(review_index)
            old_tab.deleteLater()
        self.review_tab = self._build_review_tab(points_csv)
        self.tabs.insertTab(review_index, self.review_tab, "人工复核与指标")
        self.tabs.setCurrentWidget(self.review_tab)

    def _confirm_review_save(self) -> bool:
        if self.review_window is None:
            return True
        if self.review_window.dirty:
            answer = QMessageBox.question(self, "未保存", "当前复核 CSV 有未保存修改，是否保存？")
            if answer == QMessageBox.StandardButton.Yes:
                write_csv_rows(self.review_window.csv_path, self.review_window.rows, POINT_FIELDS)
                self.review_window.dirty = False
            elif answer == QMessageBox.StandardButton.Cancel:
                return False
        if self.review_window.config_dirty:
            answer = QMessageBox.question(self, "测点配置未保存", "当前测点配置有未保存修改，是否保存？")
            if answer == QMessageBox.StandardButton.Yes:
                write_point_config(self.review_window.config_path, self.review_window.point_config_rows)
                self.review_window.config_dirty = False
            elif answer == QMessageBox.StandardButton.Cancel:
                return False
        return True

    def closeEvent(self, event) -> None:
        if not self._confirm_review_save():
            event.ignore()
            return
        event.accept()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the unified crack-width inspection workbench.")
    parser.add_argument("--points-csv", type=Path, default=None, help="Manual review point CSV.")
    parser.add_argument("--self-test", action="store_true", help="Check imports and default review CSV discovery.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    points_csv = args.points_csv or default_points_csv()
    if args.self_test:
        print(f"OK: workbench imports loaded; default_points_csv={points_csv}; exists={points_csv.exists()}")
        return 0

    app = QApplication.instance() or QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    window = CrackWidthWorkbench(points_csv)
    window.show()
    return app.exec()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        detail = traceback.format_exc()
        write_log(detail)
        raise
