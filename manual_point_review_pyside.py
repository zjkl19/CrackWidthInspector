from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from manual_point_review import (
    DEFAULT_POINT_CONFIG_CSV,
    DEFAULT_SUMMARY,
    POINT_FIELDS,
    MANUAL_ACTUAL_OVERRIDE_SOURCE,
    MANUAL_CONFIRMED_SOURCE,
    MANUAL_BATCH_ALL_IMAGES_SOURCE,
    MANUAL_BATCH_CURRENT_IMAGE_SOURCE,
    MANUAL_BATCH_SELECTED_IMAGES_SOURCE,
    MANUAL_PREFILL_SOURCE,
    POINT_CONFIG_FIELDS,
    build_point_rows,
    create_point_excel,
    evaluate_points_file,
    format_manual_width,
    infer_point_config_from_points,
    is_deleted,
    is_reviewed,
    is_skipped,
    normalize_point_rows,
    read_csv_rows,
    actual_position_pct,
    round_if_number,
    sensor_key,
    to_float,
    valid_profile_rows,
    write_point_config,
    write_csv_rows,
)


def ui_font(size: int = 16):
    for font_path in [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
    ]:
        if font_path.exists():
            try:
                return ImageFont.truetype(str(font_path), size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def app_icon_path() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "assets" / "crack_width_manual_review.ico"


AUTO_DERIVED_MANUAL_SOURCES = {
    "",
    MANUAL_PREFILL_SOURCE,
    MANUAL_BATCH_CURRENT_IMAGE_SOURCE,
    MANUAL_BATCH_SELECTED_IMAGES_SOURCE,
    MANUAL_BATCH_ALL_IMAGES_SOURCE,
}


ORIGINAL_ACTUAL_FIELD_MAP = [
    ("actual_position_pct", "original_actual_position_pct"),
    ("x_px", "original_x_px"),
    ("y_px", "original_y_px"),
    ("left_x_px", "original_left_x_px"),
    ("left_y_px", "original_left_y_px"),
    ("right_x_px", "original_right_x_px"),
    ("right_y_px", "original_right_y_px"),
    ("auto_width_mm", "original_auto_width_mm"),
    ("auto_width_px", "original_auto_width_px"),
    ("mask_width_mm", "original_mask_width_mm"),
    ("contrast", "original_contrast"),
    ("threshold", "original_threshold"),
    ("selection_reason", "original_selection_reason"),
]


def is_auto_derived_manual_source(source: Any) -> bool:
    return str(source or "").strip() in AUTO_DERIVED_MANUAL_SOURCES


ACTUAL_SNAP_MAX_DISTANCE_PX = 120.0


class ImageLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(640, 480)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.click_handler = None

    def mousePressEvent(self, event) -> None:
        if self.click_handler is not None:
            position = event.position() if hasattr(event, "position") else event.pos()
            self.click_handler(float(position.x()), float(position.y()))
            event.accept()
            return
        super().mousePressEvent(event)


class ManualPointReviewWindow(QMainWindow):
    def __init__(self, csv_path: Path, log=None):
        super().__init__()
        self.csv_path = csv_path
        self.log = log or (lambda _msg: None)
        self.rows = normalize_point_rows(read_csv_rows(csv_path))
        if not self.rows:
            raise ValueError(f"No rows found in {csv_path}")
        self.config_path = self.csv_path.parent / DEFAULT_POINT_CONFIG_CSV.name
        if self.config_path.exists():
            self.point_config_rows = self._read_point_config_rows()
        else:
            self.point_config_rows = infer_point_config_from_points(self.rows)
        self.image_ids = sorted(
            {str(row["image_record_id"]) for row in self.rows},
            key=lambda value: int(value) if value.isdigit() else value,
        )
        self.image_to_indices: dict[str, list[int]] = defaultdict(list)
        for idx, row in enumerate(self.rows):
            self.image_to_indices[str(row["image_record_id"])].append(idx)
        for indices in self.image_to_indices.values():
            indices.sort(key=lambda idx: int(float(self.rows[idx].get("point_order") or 0)))

        self.image_pos = 0
        self.point_pos = 0
        self.dirty = False
        self.config_dirty = False
        self.refreshing = False
        self.thumbnail_refreshing = False
        self.thumbnail_cache: dict[str, QIcon] = {}
        self.profile_cache: dict[str, tuple[list[dict[str, str]], list[dict[str, Any]]]] = {}
        self.loaded_manual_value = ""
        self.loaded_status_value = ""
        self.display_scale = 1.0
        self.display_size = (0, 0)
        self.current_image_size = (0, 0)

        self.setWindowTitle("Crack Width Manual Review - 裂缝宽度测点级人工复核")
        icon_path = app_icon_path()
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1500, 900)
        self._build_ui()
        self._apply_style()
        self.refresh_thumbnails()
        self.refresh_all()

    def _build_ui(self) -> None:
        root = QWidget()
        main = QVBoxLayout(root)
        main.setContentsMargins(10, 8, 10, 8)
        main.setSpacing(8)

        toolbar = QHBoxLayout()
        self.open_button = QPushButton("打开 CSV")
        self.save_button = QPushButton("保存 CSV")
        self.export_button = QPushButton("导出 Excel")
        self.eval_button = QPushButton("计算指标")
        self.prev_image_button = QPushButton("上一图 A/←")
        self.next_image_button = QPushButton("下一图 D/→")
        self.first_unfilled_button = QPushButton("首个未填")
        self.config_mode_button = QPushButton("设置测点")
        self.config_mode_button.setCheckable(True)
        self.actual_mode_button = QPushButton("调整实际点")
        self.actual_mode_button.setCheckable(True)
        self.save_config_button = QPushButton("保存测点配置")
        self.rebuild_by_config_button = QPushButton("按配置重建CSV")
        for button in [
            self.open_button,
            self.save_button,
            self.export_button,
            self.eval_button,
            self.prev_image_button,
            self.next_image_button,
            self.first_unfilled_button,
            self.config_mode_button,
            self.actual_mode_button,
            self.save_config_button,
            self.rebuild_by_config_button,
        ]:
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        self.progress_label = QLabel()
        toolbar.addWidget(self.progress_label)
        main.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        thumb_panel = QWidget()
        thumb_layout = QVBoxLayout(thumb_panel)
        thumb_layout.setContentsMargins(0, 0, 8, 0)
        thumb_title = QLabel("预览图（Ctrl/Shift 可多选）")
        self.thumbnail_list = QListWidget()
        self.thumbnail_list.setIconSize(QSize(128, 72))
        self.thumbnail_list.setMinimumWidth(220)
        self.thumbnail_list.setMaximumWidth(280)
        self.thumbnail_list.setUniformItemSizes(False)
        self.thumbnail_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        thumb_layout.addWidget(thumb_title)
        thumb_layout.addWidget(self.thumbnail_list, 1)
        splitter.addWidget(thumb_panel)

        self.image_label = ImageLabel()
        self.image_label.click_handler = self.on_image_clicked
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.image_label)
        splitter.addWidget(self.scroll)

        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(10, 0, 0, 0)
        self.meta_label = QLabel()
        self.meta_label.setWordWrap(True)
        panel_layout.addWidget(self.meta_label)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["测点", "程序/mm", "人工/mm", "状态"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setMinimumHeight(190)
        panel_layout.addWidget(self.table)

        form = QFormLayout()
        self.point_label = QLabel()
        self.auto_label = QLabel()
        self.manual_edit = QLineEdit()
        self.status_combo = QComboBox()
        self.status_combo.addItems(["pending", "reviewed", "skipped", "deleted"])
        self.note_edit = QTextEdit()
        self.note_edit.setFixedHeight(72)
        form.addRow("当前测点", self.point_label)
        form.addRow("程序宽度", self.auto_label)
        form.addRow("人工宽度/mm", self.manual_edit)
        form.addRow("状态", self.status_combo)
        form.addRow("备注", self.note_edit)
        panel_layout.addLayout(form)

        action_row1 = QHBoxLayout()
        action_row2 = QHBoxLayout()
        self.save_current_button = QPushButton("保存当前")
        self.skip_button = QPushButton("跳过测点")
        self.restore_actual_button = QPushButton("恢复自动点")
        self.delete_image_button = QPushButton("删除当前图片")
        self.confirm_current_image_button = QPushButton("确认当前图")
        self.confirm_selected_images_button = QPushButton("确认选中图")
        self.confirm_all_images_button = QPushButton("确认全部图")
        self.prev_point_button = QPushButton("上一测点 W/↑")
        self.next_point_button = QPushButton("下一测点 S/↓")
        action_row1.addWidget(self.save_current_button)
        action_row1.addWidget(self.skip_button)
        action_row1.addWidget(self.restore_actual_button)
        action_row1.addWidget(self.delete_image_button)
        action_row2.addWidget(self.confirm_current_image_button)
        action_row2.addWidget(self.confirm_selected_images_button)
        action_row2.addWidget(self.confirm_all_images_button)
        action_row3 = QHBoxLayout()
        action_row3.addWidget(self.prev_point_button)
        action_row3.addWidget(self.next_point_button)
        panel_layout.addLayout(action_row1)
        panel_layout.addLayout(action_row2)
        panel_layout.addLayout(action_row3)

        self.shortcut_label = QLabel(
            f"快捷键：A/D 或 ←/→ 切图，W/S 或 ↑/↓ 切测点；调整实际点时只可吸附绿色候选区域（≤{ACTUAL_SNAP_MAX_DISTANCE_PX:.0f}px）。"
        )
        self.shortcut_label.setWordWrap(True)
        panel_layout.addWidget(self.shortcut_label)

        self.path_label = QLabel()
        self.path_label.setWordWrap(True)
        panel_layout.addWidget(self.path_label)
        panel_layout.addStretch(1)
        splitter.addWidget(panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 1)
        main.addWidget(splitter, 1)

        self.status_label = QLabel()
        main.addWidget(self.status_label)
        self.setCentralWidget(root)

        self.open_button.clicked.connect(self.open_csv)
        self.save_button.clicked.connect(self.save_csv)
        self.export_button.clicked.connect(self.export_excel)
        self.eval_button.clicked.connect(self.evaluate)
        self.prev_image_button.clicked.connect(self.prev_image)
        self.next_image_button.clicked.connect(self.next_image)
        self.first_unfilled_button.clicked.connect(self.first_unfilled)
        self.config_mode_button.toggled.connect(self.on_config_mode_toggled)
        self.actual_mode_button.toggled.connect(self.on_actual_mode_toggled)
        self.save_config_button.clicked.connect(self.save_point_config)
        self.rebuild_by_config_button.clicked.connect(self.rebuild_points_by_config)
        self.save_current_button.clicked.connect(self.save_current)
        self.skip_button.clicked.connect(self.skip_current)
        self.restore_actual_button.clicked.connect(self.restore_current_actual_point)
        self.delete_image_button.clicked.connect(self.toggle_delete_current_image)
        self.confirm_current_image_button.clicked.connect(self.confirm_current_image)
        self.confirm_selected_images_button.clicked.connect(self.confirm_selected_images)
        self.confirm_all_images_button.clicked.connect(self.confirm_all_images)
        self.prev_point_button.clicked.connect(self.prev_point)
        self.next_point_button.clicked.connect(self.next_point)
        self.table.itemSelectionChanged.connect(self.on_table_selection)
        self.thumbnail_list.currentRowChanged.connect(self.on_thumbnail_selected)
        self.register_shortcuts()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                font-family: "Microsoft YaHei UI";
                font-size: 10pt;
            }
            QPushButton {
                padding: 7px 12px;
            }
            QTableWidget {
                gridline-color: #d6d6d6;
            }
            QLabel {
                color: #202020;
            }
            """
        )

    def register_shortcuts(self) -> None:
        shortcuts = [
            ("A", self.prev_image),
            ("Left", self.prev_image),
            ("D", self.next_image),
            ("Right", self.next_image),
            ("W", self.prev_point),
            ("Up", self.prev_point),
            ("S", self.next_point),
            ("Down", self.next_point),
        ]
        self.navigation_shortcuts = []
        for key, callback in shortcuts:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(lambda cb=callback: self.run_navigation_shortcut(cb))
            self.navigation_shortcuts.append(shortcut)

    def navigation_shortcut_allowed(self) -> bool:
        focus = QApplication.focusWidget()
        if focus is None:
            return True
        blocked = {
            self.manual_edit,
            self.note_edit,
            self.status_combo,
            self.thumbnail_list,
            self.table,
        }
        return not any(focus is widget or widget.isAncestorOf(focus) for widget in blocked)

    def run_navigation_shortcut(self, callback) -> None:
        if self.navigation_shortcut_allowed():
            callback()

    def _read_point_config_rows(self) -> list[dict[str, Any]]:
        rows = read_csv_rows(self.config_path)
        for row in rows:
            for field in POINT_CONFIG_FIELDS:
                row.setdefault(field, "")
        return rows

    def current_sensor_key(self) -> tuple[str, str]:
        return sensor_key(self.current_row())

    def current_sensor_config_rows(self) -> list[dict[str, Any]]:
        key = self.current_sensor_key()
        rows = [row for row in self.point_config_rows if sensor_key(row) == key and str(row.get("enabled", "1")) != "0"]
        rows.sort(key=lambda row: int(to_float(row.get("point_order")) or 0))
        return rows

    def upsert_current_sensor_config(self, point_order: int, x_px: float, y_px: float) -> None:
        key = self.current_sensor_key()
        current = self.current_row()
        target_row = None
        for row in self.point_config_rows:
            if sensor_key(row) == key and int(to_float(row.get("point_order")) or 0) == point_order:
                target_row = row
                break
        if target_row is None:
            target_row = {
                "sn": current.get("sn", ""),
                "device_name": current.get("device_name", ""),
                "point_order": point_order,
                "point_name": f"P{point_order}",
                "search_radius_px": 220,
                "enabled": "1",
                "note": "",
            }
            self.point_config_rows.append(target_row)
        target_row["target_x_px"] = f"{x_px:.3f}"
        target_row["target_y_px"] = f"{y_px:.3f}"
        target_row["search_radius_px"] = target_row.get("search_radius_px") or "220"
        target_row["updated_from_image"] = str(current.get("filename") or "")
        if not target_row.get("note"):
            target_row["note"] = "GUI人工设置"
        self.config_dirty = True

    def store_original_actual_point(self, row: dict[str, Any]) -> None:
        if row.get("actual_override_source") == MANUAL_ACTUAL_OVERRIDE_SOURCE:
            return
        for current_field, original_field in ORIGINAL_ACTUAL_FIELD_MAP:
            row[original_field] = row.get(current_field, "")

    def current_profile_rows(self) -> tuple[list[dict[str, str]], list[dict[str, Any]], str]:
        row = self.current_row()
        profile_path = Path(str(row.get("profile_csv_path") or ""))
        if not profile_path.exists():
            return [], [], f"找不到剖面文件：{profile_path}"
        cache_key = str(profile_path)
        if cache_key in self.profile_cache:
            raw_rows, candidates = self.profile_cache[cache_key]
            return raw_rows, candidates, ""
        try:
            raw_rows = read_csv_rows(profile_path)
        except Exception as exc:
            return [], [], f"剖面文件读取失败：{exc}"
        candidates = valid_profile_rows(raw_rows)
        if not candidates:
            return raw_rows, candidates, "剖面文件中没有可用测宽点。"
        self.profile_cache[cache_key] = (raw_rows, candidates)
        return raw_rows, candidates, ""

    def nearest_profile_point(self, x_px: float, y_px: float) -> tuple[dict[str, Any] | None, list[dict[str, str]], float | None, str]:
        raw_rows, candidates, error = self.current_profile_rows()
        if error:
            return None, raw_rows, None, error
        nearest = min(
            candidates,
            key=lambda item: (
                (float(item["_x"]) - x_px) ** 2 + (float(item["_y"]) - y_px) ** 2,
                float(item["_distance_px"]),
            ),
        )
        distance = math.hypot(float(nearest["_x"]) - x_px, float(nearest["_y"]) - y_px)
        if distance > ACTUAL_SNAP_MAX_DISTANCE_PX:
            return (
                nearest,
                raw_rows,
                distance,
                f"点击点距最近有效测宽剖面 {distance:.1f} px，超过 {ACTUAL_SNAP_MAX_DISTANCE_PX:.0f} px；"
                "请点击绿色可吸附区域附近。",
            )
        return nearest, raw_rows, distance, ""

    def current_target_xy(self) -> tuple[float | None, float | None]:
        row = self.current_row()
        tx = to_float(row.get("target_x_px"))
        ty = to_float(row.get("target_y_px"))
        if tx is not None and ty is not None:
            return tx, ty
        selected_order = int(to_float(row.get("point_order")) or 0)
        for config in self.current_sensor_config_rows():
            if int(to_float(config.get("point_order")) or 0) != selected_order:
                continue
            tx = to_float(config.get("target_x_px"))
            ty = to_float(config.get("target_y_px"))
            if tx is not None and ty is not None:
                return tx, ty
        return None, None

    def apply_actual_profile_point(self, row: dict[str, Any], profile_point: dict[str, Any], profile_rows: list[dict[str, str]], distance_px: float) -> None:
        self.store_original_actual_point(row)
        row["actual_position_pct"] = round_if_number(actual_position_pct(profile_point, profile_rows), 3)
        row["x_px"] = round_if_number(profile_point.get("_x"), 3)
        row["y_px"] = round_if_number(profile_point.get("_y"), 3)
        row["left_x_px"] = round_if_number(to_float(profile_point.get("left_x")), 3)
        row["left_y_px"] = round_if_number(to_float(profile_point.get("left_y")), 3)
        row["right_x_px"] = round_if_number(to_float(profile_point.get("right_x")), 3)
        row["right_y_px"] = round_if_number(to_float(profile_point.get("right_y")), 3)
        row["auto_width_mm"] = round_if_number(profile_point.get("_profile_width_mm"), 6)
        row["auto_width_px"] = round_if_number(to_float(profile_point.get("profile_width_px")), 6)
        row["mask_width_mm"] = round_if_number(to_float(profile_point.get("mask_width_mm")), 6)
        row["contrast"] = round_if_number(to_float(profile_point.get("contrast")), 6)
        row["threshold"] = round_if_number(to_float(profile_point.get("threshold")), 6)
        row["selection_reason"] = MANUAL_ACTUAL_OVERRIDE_SOURCE
        row["actual_override_source"] = MANUAL_ACTUAL_OVERRIDE_SOURCE
        row["actual_override_distance_px"] = round_if_number(distance_px, 3)
        row["marker_contaminated"] = "0"
        row["review_usable"] = "1"
        row["exclude_reason"] = ""
        if is_auto_derived_manual_source(row.get("manual_source")):
            row["manual_width_mm"] = format_manual_width(row.get("auto_width_mm"))
            row["manual_source"] = MANUAL_PREFILL_SOURCE
        row["review_status"] = "pending"

    def restore_current_actual_point(self) -> None:
        row = self.current_row()
        if row.get("actual_override_source") != MANUAL_ACTUAL_OVERRIDE_SOURCE:
            self.status_label.setText("当前测点没有人工调整实际点，无需恢复。")
            return
        restored = False
        for current_field, original_field in ORIGINAL_ACTUAL_FIELD_MAP:
            if row.get(original_field, "") != "":
                row[current_field] = row.get(original_field, "")
                restored = True
            row[original_field] = ""
        if not restored:
            self.status_label.setText("当前测点缺少原自动点备份，无法恢复。")
            return
        row["actual_override_source"] = ""
        row["actual_override_distance_px"] = ""
        if is_auto_derived_manual_source(row.get("manual_source")):
            row["manual_width_mm"] = format_manual_width(row.get("auto_width_mm"))
            row["manual_source"] = MANUAL_PREFILL_SOURCE
        row["review_status"] = "pending"
        self.dirty = True
        self.refresh_all()
        self.status_label.setText("已恢复当前测点的原自动实际位置；点击“保存 CSV”写入文件。")

    def rebuild_index(self) -> None:
        self.image_ids = sorted(
            {str(row["image_record_id"]) for row in self.rows},
            key=lambda value: int(value) if value.isdigit() else value,
        )
        self.image_to_indices = defaultdict(list)
        for idx, row in enumerate(self.rows):
            self.image_to_indices[str(row["image_record_id"])].append(idx)
        for indices in self.image_to_indices.values():
            indices.sort(key=lambda idx: int(float(self.rows[idx].get("point_order") or 0)))

    def image_deleted(self, image_id: str | None = None) -> bool:
        image_id = image_id or self.image_ids[self.image_pos]
        return any(is_deleted(self.rows[idx]) for idx in self.image_to_indices[str(image_id)])

    def image_summary_text(self, image_id: str) -> str:
        indices = self.image_to_indices[image_id]
        row = self.rows[indices[0]]
        prefix = "[删] " if self.image_deleted(image_id) else ""
        reviewed = sum(1 for idx in indices if is_reviewed(self.rows[idx]))
        return (
            f"{prefix}{self.image_ids.index(image_id) + 1:04d} "
            f"{row.get('device_name')} P{reviewed}/{len(indices)}\n"
            f"{row.get('uptime')}"
        )

    def thumbnail_icon(self, image_id: str) -> QIcon:
        if image_id in self.thumbnail_cache:
            return self.thumbnail_cache[image_id]
        row = self.rows[self.image_to_indices[image_id][0]]
        image_path = Path(str(row.get("input_image_path") or ""))
        icon = QIcon()
        if image_path.exists():
            try:
                image = Image.open(image_path).convert("RGB")
                image.thumbnail((128, 72))
                canvas = Image.new("RGB", (128, 72), "white")
                left = (128 - image.width) // 2
                top = (72 - image.height) // 2
                canvas.paste(image, (left, top))
                icon = QIcon(QPixmap.fromImage(ImageQt(canvas)))
            except Exception:
                icon = QIcon()
        self.thumbnail_cache[image_id] = icon
        return icon

    def refresh_thumbnails(self) -> None:
        self.thumbnail_refreshing = True
        self.thumbnail_list.clear()
        for image_id in self.image_ids:
            item = QListWidgetItem(self.image_summary_text(image_id))
            item.setData(Qt.ItemDataRole.UserRole, image_id)
            self.thumbnail_list.addItem(item)
        self.thumbnail_list.setCurrentRow(self.image_pos)
        self.thumbnail_refreshing = False
        self.refresh_thumbnail_window()

    def refresh_thumbnail_window(self, radius: int = 18) -> None:
        if not hasattr(self, "thumbnail_list"):
            return
        start = max(0, self.image_pos - radius)
        end = min(len(self.image_ids), self.image_pos + radius + 1)
        for pos in range(start, end):
            item = self.thumbnail_list.item(pos)
            if item and item.icon().isNull():
                item.setIcon(self.thumbnail_icon(self.image_ids[pos]))

    def refresh_current_thumbnail(self) -> None:
        if not hasattr(self, "thumbnail_list") or self.image_pos >= self.thumbnail_list.count():
            return
        self.refresh_thumbnail_window()
        self.thumbnail_refreshing = True
        item = self.thumbnail_list.item(self.image_pos)
        image_id = self.image_ids[self.image_pos]
        item.setIcon(self.thumbnail_icon(image_id))
        item.setText(self.image_summary_text(image_id))
        self.thumbnail_list.setCurrentRow(self.image_pos)
        self.thumbnail_list.scrollToItem(item)
        self.thumbnail_refreshing = False

    def current_indices(self) -> list[int]:
        return self.image_to_indices[self.image_ids[self.image_pos]]

    def current_row_index(self) -> int:
        indices = self.current_indices()
        self.point_pos = max(0, min(self.point_pos, len(indices) - 1))
        return indices[self.point_pos]

    def current_row(self) -> dict[str, Any]:
        return self.rows[self.current_row_index()]

    def commit_current_fields(self, confirm_manual: bool = False) -> bool:
        row = self.current_row()
        raw_manual = self.manual_edit.text().strip()
        manual = ""
        if raw_manual:
            manual = format_manual_width(raw_manual)
            if not manual:
                QMessageBox.critical(self, "输入错误", "人工宽度必须是数字，单位 mm。")
                return False
        status = self.status_combo.currentText() or "pending"
        note = self.note_edit.toPlainText().strip()
        manual_changed = manual != self.loaded_manual_value
        status_changed = status != self.loaded_status_value
        source = str(row.get("manual_source") or "")

        if status == "deleted":
            for idx in self.current_indices():
                image_row = self.rows[idx]
                image_row["image_deleted"] = "1"
                image_row["review_status"] = "deleted"
                if not image_row.get("delete_reason"):
                    image_row["delete_reason"] = "人工判定该图像不可用"
        elif status == "skipped":
            pass
        elif manual and (confirm_manual or manual_changed or status == "reviewed"):
            status = "reviewed"
            source = MANUAL_CONFIRMED_SOURCE
        elif manual and not source:
            source = MANUAL_PREFILL_SOURCE

        before = (
            row.get("manual_width_mm", ""),
            row.get("manual_source", ""),
            row.get("review_status", ""),
            row.get("manual_note", ""),
            row.get("image_deleted", ""),
            row.get("delete_reason", ""),
        )
        row["manual_width_mm"] = manual
        row["manual_source"] = source
        row["review_status"] = status
        row["manual_note"] = note
        after = (
            row.get("manual_width_mm", ""),
            row.get("manual_source", ""),
            row.get("review_status", ""),
            row.get("manual_note", ""),
            row.get("image_deleted", ""),
            row.get("delete_reason", ""),
        )
        if before != after or manual_changed or status_changed:
            self.dirty = True
        return True

    def save_current(self) -> bool:
        if not self.commit_current_fields(confirm_manual=True):
            return False
        self.refresh_table()
        self.refresh_current_thumbnail()
        self.update_progress()
        self.status_label.setText("当前测点已暂存，点击“保存 CSV”写入文件。")
        return True

    def skip_current(self) -> None:
        self.status_combo.setCurrentText("skipped")
        if not self.note_edit.toPlainText().strip():
            self.note_edit.setPlainText("人工判定该测点不可读")
        if self.save_current():
            self.next_point()

    def can_batch_confirm(self, row: dict[str, Any]) -> bool:
        if is_deleted(row) or is_skipped(row):
            return False
        return to_float(row.get("auto_width_mm")) is not None

    def batch_confirm_indices(self, indices: list[int], source: str) -> dict[str, int]:
        stats = {"changed": 0, "already": 0, "skipped": 0}
        for idx in sorted(set(indices)):
            row = self.rows[idx]
            if is_reviewed(row):
                stats["already"] += 1
                continue
            if not self.can_batch_confirm(row):
                stats["skipped"] += 1
                continue
            manual = format_manual_width(row.get("manual_width_mm") or row.get("auto_width_mm"))
            if not manual:
                stats["skipped"] += 1
                continue
            row["manual_width_mm"] = manual
            row["manual_source"] = source
            row["review_status"] = "reviewed"
            stats["changed"] += 1
        if stats["changed"]:
            self.dirty = True
        return stats

    def selected_image_ids(self) -> list[str]:
        selected_ids: list[str] = []
        for item in self.thumbnail_list.selectedItems():
            image_id = item.data(Qt.ItemDataRole.UserRole)
            if image_id is not None:
                selected_ids.append(str(image_id))
        if not selected_ids:
            selected_ids = [self.image_ids[self.image_pos]]
        return sorted(set(selected_ids), key=lambda value: self.image_ids.index(value))

    def indices_for_images(self, image_ids: list[str]) -> list[int]:
        indices: list[int] = []
        for image_id in image_ids:
            indices.extend(self.image_to_indices[str(image_id)])
        return indices

    def count_confirmable(self, indices: list[int]) -> tuple[int, int]:
        confirmable = 0
        skipped = 0
        for idx in sorted(set(indices)):
            row = self.rows[idx]
            if is_reviewed(row):
                continue
            if self.can_batch_confirm(row):
                confirmable += 1
            else:
                skipped += 1
        return confirmable, skipped

    def finish_batch_confirm(self, stats: dict[str, int], message_prefix: str) -> None:
        self.refresh_table()
        self.refresh_thumbnails()
        self.load_current_fields()
        self.draw_image()
        self.update_progress()
        self.status_label.setText(
            f"{message_prefix}：新增确认 {stats['changed']} 个测点，"
            f"已确认 {stats['already']} 个，跳过 {stats['skipped']} 个。点击“保存 CSV”写入文件。"
        )

    def confirm_current_image(self) -> None:
        if not self.commit_current_fields():
            return
        image_id = self.image_ids[self.image_pos]
        stats = self.batch_confirm_indices(self.image_to_indices[image_id], MANUAL_BATCH_CURRENT_IMAGE_SOURCE)
        self.finish_batch_confirm(stats, "当前图批量确认完成")

    def confirm_selected_images(self) -> None:
        if not self.commit_current_fields():
            return
        image_ids = self.selected_image_ids()
        indices = self.indices_for_images(image_ids)
        confirmable, skipped = self.count_confirmable(indices)
        answer = QMessageBox.question(
            self,
            "确认选中图",
            f"将批量确认 {len(image_ids)} 张图中的 {confirmable} 个可用测点，"
            f"跳过 {skipped} 个不可确认测点。继续吗？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        stats = self.batch_confirm_indices(indices, MANUAL_BATCH_SELECTED_IMAGES_SOURCE)
        self.finish_batch_confirm(stats, f"选中 {len(image_ids)} 张图批量确认完成")

    def confirm_all_images(self) -> None:
        if not self.commit_current_fields():
            return
        indices = list(range(len(self.rows)))
        confirmable, skipped = self.count_confirmable(indices)
        answer = QMessageBox.question(
            self,
            "确认全部图",
            f"将批量确认当前 CSV 中全部图片的 {confirmable} 个可用测点，"
            f"跳过 {skipped} 个不可确认测点。该操作会影响指标统计口径，继续吗？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        stats = self.batch_confirm_indices(indices, MANUAL_BATCH_ALL_IMAGES_SOURCE)
        self.finish_batch_confirm(stats, "全部图批量确认完成")

    def save_csv(self) -> None:
        if not self.commit_current_fields():
            return
        write_csv_rows(self.csv_path, self.rows, POINT_FIELDS)
        self.dirty = False
        self.status_label.setText(f"已保存：{self.csv_path}")
        self.refresh_all()

    def open_csv(self) -> None:
        if self.dirty and QMessageBox.question(self, "未保存", "当前 CSV 有未保存修改，仍要打开新文件吗？") != QMessageBox.StandardButton.Yes:
            return
        path, _ = QFileDialog.getOpenFileName(self, "打开测点复核 CSV", str(self.csv_path.parent), "CSV (*.csv)")
        if not path:
            return
        self.csv_path = Path(path)
        self.rows = normalize_point_rows(read_csv_rows(self.csv_path))
        self.config_path = self.csv_path.parent / DEFAULT_POINT_CONFIG_CSV.name
        self.point_config_rows = self._read_point_config_rows() if self.config_path.exists() else infer_point_config_from_points(self.rows)
        self.rebuild_index()
        self.thumbnail_cache.clear()
        self.profile_cache.clear()
        self.image_pos = 0
        self.point_pos = 0
        self.dirty = False
        self.config_dirty = False
        self.refresh_thumbnails()
        self.refresh_all()

    def export_excel(self) -> None:
        if not self.commit_current_fields():
            return
        write_csv_rows(self.csv_path, self.rows, POINT_FIELDS)
        xlsx_path = self.csv_path.with_suffix(".xlsx")
        create_point_excel(self.csv_path, xlsx_path)
        QMessageBox.information(self, "导出完成", f"已导出：\n{xlsx_path}")

    def evaluate(self) -> None:
        if not self.commit_current_fields():
            return
        write_csv_rows(self.csv_path, self.rows, POINT_FIELDS)
        out_dir = self.csv_path.parent / "manual_point_review_eval"
        outputs = evaluate_points_file(self.csv_path, out_dir, abs_tol_mm=0.02, rel_tol=0.15)
        QMessageBox.information(self, "计算完成", "\n".join(str(path) for path in outputs.values()))

    def refresh_all(self) -> None:
        self.load_current_fields()
        self.refresh_table()
        self.draw_image()
        self.refresh_current_thumbnail()
        self.update_progress()

    def load_current_fields(self) -> None:
        row = self.current_row()
        indices = self.current_indices()
        deleted = self.image_deleted()
        self.point_label.setText(f"{row.get('point_id')}  位置约 {row.get('target_position_pct')}%")
        self.auto_label.setText(f"{row.get('auto_width_mm')} mm")
        self.manual_edit.setText(str(row.get("manual_width_mm") or ""))
        status = str(row.get("review_status") or "pending")
        self.status_combo.setCurrentText(status if status in {"pending", "reviewed", "skipped", "deleted"} else "pending")
        self.note_edit.setPlainText(str(row.get("manual_note") or ""))
        self.loaded_manual_value = str(row.get("manual_width_mm") or "")
        self.loaded_status_value = self.status_combo.currentText()
        self.delete_image_button.setText("恢复当前图片" if deleted else "删除当前图片")
        has_actual_override = row.get("actual_override_source") == MANUAL_ACTUAL_OVERRIDE_SOURCE
        self.restore_actual_button.setEnabled(has_actual_override)
        delete_text = f"\n删除原因：{row.get('delete_reason')}" if deleted and row.get("delete_reason") else ""
        override_text = ""
        if has_actual_override:
            override_text = f"\n实际点调整：人工吸附覆盖，吸附距离 {row.get('actual_override_distance_px', '')} px"
        self.meta_label.setText(
            f"图像 {self.image_pos + 1}/{len(self.image_ids)}，测点 {self.point_pos + 1}/{len(indices)}\n"
            f"构件：{row.get('device_name')}\n"
            f"时间：{row.get('uptime')}\n"
            f"文件：{row.get('filename')}\n"
            f"状态：{'已软删除' if deleted else '可复核'}{delete_text}\n"
            f"选点：{row.get('selection_reason', '')}\n"
            f"{override_text}\n"
            f"取点来源：{row.get('point_config_source', '')}\n"
            f"人工值来源：{row.get('manual_source', '')}\n"
            f"配置文件：{self.config_path.name}"
        )
        self.path_label.setText(str(row.get("input_image_path") or ""))

    def refresh_table(self) -> None:
        self.refreshing = True
        indices = self.current_indices()
        self.table.setRowCount(len(indices))
        current_idx = self.current_row_index()
        for table_row, idx in enumerate(indices):
            row = self.rows[idx]
            values = [
                f"P{row.get('point_order')}",
                str(row.get("auto_width_mm") or ""),
                str(row.get("manual_width_mm") or ""),
                str(row.get("review_status") or ""),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setData(Qt.ItemDataRole.UserRole, idx)
                self.table.setItem(table_row, col, item)
        self.table.resizeColumnsToContents()
        self.table.selectRow(indices.index(current_idx))
        self.refreshing = False

    def on_table_selection(self) -> None:
        if self.refreshing:
            return
        selected = self.table.selectedItems()
        if not selected:
            return
        idx = selected[0].data(Qt.ItemDataRole.UserRole)
        if idx == self.current_row_index():
            return
        if not self.commit_current_fields():
            self.refresh_table()
            return
        indices = self.current_indices()
        if idx in indices:
            self.point_pos = indices.index(idx)
            self.refresh_all()

    def on_thumbnail_selected(self, row_number: int) -> None:
        if self.thumbnail_refreshing or row_number < 0 or row_number == self.image_pos:
            return
        if not self.commit_current_fields():
            self.refresh_current_thumbnail()
            return
        self.image_pos = max(0, min(row_number, len(self.image_ids) - 1))
        self.point_pos = 0
        self.refresh_all()

    def toggle_delete_current_image(self) -> None:
        image_id = self.image_ids[self.image_pos]
        indices = self.current_indices()
        deleted = self.image_deleted(image_id)
        if deleted:
            answer = QMessageBox.question(self, "恢复图片", "恢复当前图片并重新纳入人工复核列表吗？")
            if answer != QMessageBox.StandardButton.Yes:
                return
            for idx in indices:
                row = self.rows[idx]
                row["image_deleted"] = "0"
                row["delete_reason"] = ""
                if str(row.get("review_status") or "").lower() == "deleted":
                    row["review_status"] = "pending"
            self.status_label.setText("当前图片已恢复，点击“保存 CSV”写入文件。")
        else:
            reason, ok = QInputDialog.getText(
                self,
                "删除当前图片",
                "删除原因：",
                text="图像质量不符合人工复核要求",
            )
            if not ok:
                return
            reason = reason.strip() or "图像质量不符合人工复核要求"
            for idx in indices:
                row = self.rows[idx]
                row["image_deleted"] = "1"
                row["delete_reason"] = reason
                row["review_status"] = "deleted"
            self.status_label.setText("当前图片已软删除，原图文件未物理删除。点击“保存 CSV”写入文件。")
        self.dirty = True
        self.refresh_all()

    def on_config_mode_toggled(self, checked: bool) -> None:
        if checked:
            if self.actual_mode_button.isChecked():
                self.actual_mode_button.blockSignals(True)
                self.actual_mode_button.setChecked(False)
                self.actual_mode_button.blockSignals(False)
            self.status_label.setText("测点设置模式：先在右侧表格选择 P1/P2/P3，再点击图像中的固定目标点位置。点击后不会自动切换测点。")
        else:
            self.status_label.setText("已退出测点设置模式。")
        self.draw_image()

    def on_actual_mode_toggled(self, checked: bool) -> None:
        if checked:
            if self.config_mode_button.isChecked():
                self.config_mode_button.blockSignals(True)
                self.config_mode_button.setChecked(False)
                self.config_mode_button.blockSignals(False)
            row = self.current_row()
            self.status_label.setText(
                f"实际点调整模式：当前为 P{row.get('point_order')}。绿色区域为可吸附范围；"
                f"点击点距最近有效剖面不得超过 {ACTUAL_SNAP_MAX_DISTANCE_PX:.0f} px。"
            )
        else:
            self.status_label.setText("已退出实际点调整模式。")
        self.draw_image()

    def display_to_image_coords(self, display_x: float, display_y: float) -> tuple[float, float] | None:
        pixmap = self.image_label.pixmap()
        if pixmap is None or pixmap.isNull() or self.display_scale <= 0:
            return None
        offset_x = max(0.0, (float(self.image_label.width()) - float(pixmap.width())) / 2.0)
        offset_y = max(0.0, (float(self.image_label.height()) - float(pixmap.height())) / 2.0)
        local_x = display_x - offset_x
        local_y = display_y - offset_y
        if local_x < 0 or local_y < 0 or local_x > pixmap.width() or local_y > pixmap.height():
            return None
        image_x = local_x / self.display_scale
        image_y = local_y / self.display_scale
        image_w, image_h = self.current_image_size
        if image_w <= 0 or image_h <= 0:
            return None
        return (
            max(0.0, min(float(image_w - 1), image_x)),
            max(0.0, min(float(image_h - 1), image_y)),
        )

    def on_image_clicked(self, display_x: float, display_y: float) -> None:
        if not self.config_mode_button.isChecked() and not self.actual_mode_button.isChecked():
            return
        coords = self.display_to_image_coords(display_x, display_y)
        if coords is None:
            self.status_label.setText("点击位置不在图像范围内，未更新测点。")
            return
        x_px, y_px = coords
        if self.actual_mode_button.isChecked():
            row = self.current_row()
            profile_point, profile_rows, distance_px, error = self.nearest_profile_point(x_px, y_px)
            if error or profile_point is None or distance_px is None:
                self.status_label.setText(error or "未找到可吸附的实际测点。")
                return
            self.apply_actual_profile_point(row, profile_point, profile_rows, distance_px)
            self.dirty = True
            self.refresh_all()
            warning = "；吸附距离较远，请复核" if distance_px > 120 else ""
            self.status_label.setText(
                f"已调整 {row.get('point_id')} 实际测点："
                f"x={to_float(row.get('x_px')):.1f}, y={to_float(row.get('y_px')):.1f}, "
                f"宽度={row.get('auto_width_mm')} mm，吸附距离={distance_px:.1f} px{warning}。"
                " 点击“保存 CSV”写入文件。"
            )
            return
        row = self.current_row()
        point_order = int(to_float(row.get("point_order")) or (self.point_pos + 1))
        self.upsert_current_sensor_config(point_order, x_px, y_px)
        self.status_label.setText(
            f"已设置 {row.get('device_name')} P{point_order}: x={x_px:.1f}, y={y_px:.1f}。"
            " 当前仍停留在该测点；需要设置 P2/P3 时请手动选择对应测点。"
        )
        self.draw_image()
        self.refresh_current_thumbnail()

    def draw_actual_snap_overlay(self, display: Image.Image, scale: float) -> None:
        if not self.actual_mode_button.isChecked():
            return
        _raw_rows, candidates, _error = self.current_profile_rows()
        if not candidates:
            return
        points = [(float(row["_x"]) * scale, float(row["_y"]) * scale) for row in candidates]
        if not points:
            return
        overlay = Image.new("RGBA", display.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        band_width = max(12, int(ACTUAL_SNAP_MAX_DISTANCE_PX * scale * 2.0))
        path_width = max(2, int(4 * scale))
        if len(points) >= 2:
            overlay_draw.line(points, fill=(40, 190, 90, 35), width=band_width, joint="curve")
            overlay_draw.line(points, fill=(16, 150, 70, 215), width=path_width, joint="curve")
        step = max(1, len(points) // 160)
        dot_radius = max(2, int(3 * scale))
        for x, y in points[::step]:
            overlay_draw.ellipse(
                (x - dot_radius, y - dot_radius, x + dot_radius, y + dot_radius),
                fill=(25, 190, 85, 235),
                outline=(0, 80, 35, 235),
            )
        tx, ty = self.current_target_xy()
        if tx is not None and ty is not None:
            target_x = float(tx) * scale
            target_y = float(ty) * scale
            radius = ACTUAL_SNAP_MAX_DISTANCE_PX * scale
            near_target = any(
                math.hypot(float(row["_x"]) - float(tx), float(row["_y"]) - float(ty)) <= ACTUAL_SNAP_MAX_DISTANCE_PX
                for row in candidates
            )
            color = (35, 170, 80, 210) if near_target else (214, 40, 40, 230)
            overlay_draw.ellipse(
                (target_x - radius, target_y - radius, target_x + radius, target_y + radius),
                outline=color,
                width=max(2, int(3 * scale)),
            )
            if not near_target:
                overlay_draw.text(
                    (target_x + 12, target_y + 12),
                    "目标附近无有效剖面",
                    fill=(214, 40, 40, 245),
                    font=ui_font(14),
                    stroke_width=2,
                    stroke_fill=(255, 255, 255, 230),
                )
        display.alpha_composite(overlay)

    def save_point_config(self) -> None:
        write_point_config(self.config_path, self.point_config_rows)
        self.config_dirty = False
        self.status_label.setText(f"测点配置已保存：{self.config_path}")

    def rebuild_points_by_config(self) -> None:
        if not self.commit_current_fields():
            return
        answer = QMessageBox.question(
            self,
            "按配置重建 CSV",
            "将按传感器测点配置重新生成当前 CSV。人工宽度会重新预填为两位小数，已软删除图片会尽量按文件名保留。继续吗？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        write_point_config(self.config_path, self.point_config_rows)
        self.config_dirty = False
        summary_csv = self.csv_path.parent / DEFAULT_SUMMARY.name
        if not summary_csv.exists():
            QMessageBox.critical(self, "缺少汇总文件", f"找不到：\n{summary_csv}")
            return
        deleted_by_image = {}
        for row in self.rows:
            if is_deleted(row):
                deleted_by_image[(row.get("sn", ""), row.get("filename", ""))] = row.get("delete_reason", "")
        new_rows = build_point_rows(
            summary_csv,
            points_per_image=3,
            avoid_markers=True,
            excluded_csv=self.csv_path.parent / "manual_point_review_excluded_images.csv",
            point_config_csv=self.config_path,
        )
        for row in new_rows:
            reason = deleted_by_image.get((row.get("sn", ""), row.get("filename", "")))
            if reason is not None:
                row["image_deleted"] = "1"
                row["delete_reason"] = reason
                row["review_status"] = "deleted"
        write_csv_rows(self.csv_path, new_rows, POINT_FIELDS)
        create_point_excel(self.csv_path, self.csv_path.with_suffix(".xlsx"))
        self.rows = normalize_point_rows(read_csv_rows(self.csv_path))
        self.rebuild_index()
        self.thumbnail_cache.clear()
        self.profile_cache.clear()
        self.image_pos = 0
        self.point_pos = 0
        self.dirty = False
        self.refresh_thumbnails()
        self.refresh_all()
        self.status_label.setText(f"已按传感器测点配置重建：{self.csv_path}")

    def draw_image(self) -> None:
        row = self.current_row()
        image_path = Path(str(row.get("input_image_path") or ""))
        if not image_path.exists():
            self.image_label.setText(f"图像不存在：\n{image_path}")
            return
        try:
            image = Image.open(image_path).convert("RGB")
        except Exception as exc:
            self.image_label.setText(f"图像读取失败：\n{exc}")
            return
        viewport = self.scroll.viewport().size()
        max_w = max(400, viewport.width() - 8)
        max_h = max(300, viewport.height() - 8)
        scale = min(max_w / image.width, max_h / image.height)
        self.display_scale = scale
        self.current_image_size = (image.width, image.height)
        display_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
        self.display_size = display_size
        display = image.resize(display_size).convert("RGBA")
        self.draw_actual_snap_overlay(display, scale)
        draw = ImageDraw.Draw(display)
        font = ui_font(15)
        if self.image_deleted():
            draw.rectangle((0, 0, 210, 30), fill="#b00020")
            draw.text((10, 8), "SOFT DELETED", fill="white", font=font)
        legend_bottom = 114 if self.actual_mode_button.isChecked() else 88
        draw.rectangle((6, 6, 430, legend_bottom), fill=(255, 255, 255), outline="#d0d0d0")
        draw.line((18, 24, 42, 24), fill="#d62828", width=4)
        draw.text((50, 16), "程序实际法向测宽短线", fill="#222222", font=font)
        target_color = "#ffe600"
        target_outline = "#101010"
        draw.line((24, 42, 24, 58), fill=target_outline, width=6)
        draw.line((16, 50, 32, 50), fill=target_outline, width=6)
        draw.line((24, 42, 24, 58), fill=target_color, width=3)
        draw.line((16, 50, 32, 50), fill=target_color, width=3)
        draw.text((50, 42), "人工固定目标点", fill="#222222", font=font)
        draw.line((18, 76, 42, 76), fill="#f77f00", width=4)
        draw.text((50, 68), "人工调整实际测点", fill="#222222", font=font)
        if self.actual_mode_button.isChecked():
            draw.line((18, 102, 42, 102), fill="#109646", width=5)
            draw.text((50, 94), f"绿色区域可吸附（≤{ACTUAL_SNAP_MAX_DISTANCE_PX:.0f}px）", fill="#222222", font=font)
        selected_order = int(to_float(row.get("point_order")) or 0)
        for config in self.current_sensor_config_rows():
            tx = to_float(config.get("target_x_px"))
            ty = to_float(config.get("target_y_px"))
            if tx is None or ty is None:
                continue
            x = float(tx) * scale
            y = float(ty) * scale
            order = int(to_float(config.get("point_order")) or 0)
            cross = 18 if order == selected_order else 14
            width = 4 if order == selected_order else 3
            outline_width = width + 4
            draw.line((x - cross, y, x + cross, y), fill=target_outline, width=outline_width)
            draw.line((x, y - cross, x, y + cross), fill=target_outline, width=outline_width)
            draw.line((x - cross, y, x + cross, y), fill=target_color, width=width)
            draw.line((x, y - cross, x, y + cross), fill=target_color, width=width)
            draw.rectangle((x - 5, y - 5, x + 5, y + 5), fill=target_outline)
            draw.rectangle((x - 3, y - 3, x + 3, y + 3), fill=target_color)
            label = str(config.get("point_name") or f"P{config.get('point_order')}")
            draw.text(
                (x + cross + 4, y - 26),
                f"{label}目标",
                fill=target_color,
                font=font,
                stroke_width=2,
                stroke_fill=target_outline,
            )
        current_idx = self.current_row_index()
        for idx in self.current_indices():
            point = self.rows[idx]
            order = int(float(point.get("point_order") or 1))
            coords = [to_float(point.get(key)) for key in ("left_x_px", "left_y_px", "right_x_px", "right_y_px", "x_px", "y_px")]
            if any(value is None for value in coords):
                continue
            lx, ly, rx, ry, x, y = [float(value) * scale for value in coords]
            line_width = 5 if idx == current_idx else 3
            overridden = point.get("actual_override_source") == MANUAL_ACTUAL_OVERRIDE_SOURCE
            if overridden:
                line_color = "#f77f00" if idx == current_idx else "#fcbf49"
                center_color = "#00d1ff" if idx == current_idx else "#9be8ff"
            else:
                line_color = "#d62828" if idx == current_idx else "#ef6f6c"
                center_color = "#00a6d6" if idx == current_idx else "#7ccce3"
            draw.line((lx, ly, rx, ry), fill=line_color, width=line_width)
            radius = 6 if idx == current_idx else 4
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=center_color, outline="black", width=2)
            if idx == current_idx:
                label = f"P{order}实际调整" if overridden else f"P{order}实际"
                draw.text((x + 10, y + 6), label, fill=line_color, font=font, stroke_width=2, stroke_fill="white")
        pixmap = QPixmap.fromImage(ImageQt(display))
        self.image_label.setPixmap(pixmap)
        self.image_label.resize(pixmap.size())

    def update_progress(self) -> None:
        reviewed = 0
        skipped = 0
        deleted_images = 0
        for row in self.rows:
            if is_reviewed(row):
                reviewed += 1
            elif is_skipped(row):
                skipped += 1
        for image_id in self.image_ids:
            if self.image_deleted(image_id):
                deleted_images += 1
        total = len(self.rows)
        self.progress_label.setText(
            f"已确认 {reviewed}/{total}，跳过/删除测点 {skipped}，删除图片 {deleted_images}，文件：{self.csv_path.name}"
        )

    def move_to(self, image_pos: int, point_pos: int) -> None:
        if not self.commit_current_fields():
            return
        self.image_pos = max(0, min(image_pos, len(self.image_ids) - 1))
        self.point_pos = max(0, min(point_pos, len(self.current_indices()) - 1))
        self.refresh_all()

    def next_point(self) -> None:
        if self.point_pos + 1 < len(self.current_indices()):
            self.move_to(self.image_pos, self.point_pos + 1)
        elif self.image_pos + 1 < len(self.image_ids):
            self.move_to(self.image_pos + 1, 0)

    def prev_point(self) -> None:
        if self.point_pos > 0:
            self.move_to(self.image_pos, self.point_pos - 1)
        elif self.image_pos > 0:
            prev_indices = self.image_to_indices[self.image_ids[self.image_pos - 1]]
            self.move_to(self.image_pos - 1, len(prev_indices) - 1)

    def next_image(self) -> None:
        self.move_to(self.image_pos + 1, 0)

    def prev_image(self) -> None:
        self.move_to(self.image_pos - 1, 0)

    def first_unfilled(self) -> None:
        if not self.commit_current_fields():
            return
        for image_pos, image_id in enumerate(self.image_ids):
            for point_pos, idx in enumerate(self.image_to_indices[image_id]):
                row = self.rows[idx]
                if not is_skipped(row) and not is_reviewed(row):
                    self.image_pos = image_pos
                    self.point_pos = point_pos
                    self.refresh_all()
                    return
        QMessageBox.information(self, "完成", "没有未填写的测点。")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "image_label"):
            self.draw_image()

    def closeEvent(self, event) -> None:
        if self.dirty:
            answer = QMessageBox.question(self, "未保存", "是否保存 CSV 后退出？")
            if answer == QMessageBox.StandardButton.Yes:
                write_csv_rows(self.csv_path, self.rows, POINT_FIELDS)
            elif answer == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
        if self.config_dirty:
            answer = QMessageBox.question(self, "测点配置未保存", "是否保存传感器测点配置后退出？")
            if answer == QMessageBox.StandardButton.Yes:
                write_point_config(self.config_path, self.point_config_rows)
            elif answer == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
        event.accept()


def run_pyside_gui(points_csv: Path, log=None) -> int:
    if log:
        log(f"run_pyside_gui start: {points_csv}")
    app = QApplication.instance() or QApplication(sys.argv)
    window = ManualPointReviewWindow(points_csv, log=log)
    window.show()
    window.raise_()
    window.activateWindow()
    if log:
        log("pyside window shown")
    return app.exec()
