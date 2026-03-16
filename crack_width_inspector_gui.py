import re
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
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
        self.current_result = None
        self.current_preview_path = None

        self.setWindowTitle("裂缝宽度检测系统 | Crack Width Inspector")
        self.resize(1460, 920)
        self._apply_theme()

        self.input_edit = QLineEdit()
        self.output_edit = QLineEdit(str(runtime_base_dir() / "outputs"))
        self.scale_spin = QDoubleSpinBox()
        self.sample_spin = QSpinBox()

        self.start_button = QPushButton("开始检测")
        self.open_output_button = QPushButton("打开输出目录")
        self.open_overlay_button = QPushButton("打开叠加图")
        self.open_csv_button = QPushButton("打开数据表")

        self.status_badge = QLabel("待开始")
        self.summary_label = QLabel("尚未开始任务")
        self.progress_bar = QProgressBar()

        self.results_tree = QTreeWidget()
        self.preview_label = QLabel("请选择结果记录以查看叠加图")
        self.log_edit = QPlainTextEdit()

        self.metric_count_value = QLabel("0")
        self.metric_current_value = QLabel("未选择")
        self.metric_max_width_value = QLabel("0.00 mm")
        self.metric_state_value = QLabel("准备就绪")

        self.detail_source_value = QLabel("-")
        self.detail_output_value = QLabel("-")
        self.detail_max_width_value = QLabel("-")
        self.detail_mean_width_value = QLabel("-")
        self.detail_path_length_value = QLabel("-")
        self.detail_skeleton_value = QLabel("-")
        self.detail_samples_value = QLabel("-")
        self.detail_overlay_value = QLabel("-")
        self.detail_csv_value = QLabel("-")

        self._build_ui()
        self._connect_signals()
        self._set_status("ready", "待开始")
        self._set_controls_enabled(True)
        self._set_result_buttons_enabled(False)

    def _apply_theme(self):
        self.setStyleSheet(
            """
            QMainWindow {
                background: #efe6db;
                color: #1d2d35;
            }
            QWidget {
                font-family: "Microsoft YaHei UI";
                font-size: 10pt;
            }
            QFrame#HeroCard {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #17324a,
                    stop: 0.55 #264d66,
                    stop: 1 #d4883a
                );
                border-radius: 24px;
            }
            QFrame#PanelCard, QGroupBox {
                background: #fbf7f1;
                border: 1px solid #d7c6b3;
                border-radius: 18px;
            }
            QGroupBox {
                margin-top: 14px;
                padding-top: 14px;
                font-weight: 700;
                color: #22333b;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 4px;
            }
            QFrame#MetricCard {
                background: #203849;
                border-radius: 18px;
                border: none;
            }
            QLabel#MetricTitle {
                color: #d7e3eb;
                font-size: 9pt;
            }
            QLabel#MetricValue {
                color: #fff8ee;
                font-size: 18pt;
                font-weight: 700;
            }
            QLabel#HeroTitle {
                color: #fffaf3;
                font-size: 24pt;
                font-weight: 700;
            }
            QLabel#HeroSubtitle {
                color: #e0ebf2;
                font-size: 10pt;
            }
            QLabel#StatusBadge {
                color: #fffaf3;
                padding: 7px 14px;
                border-radius: 14px;
                font-weight: 700;
                background: rgba(255, 250, 243, 0.18);
            }
            QLabel#SectionTitle {
                font-size: 13pt;
                font-weight: 700;
                color: #21343f;
            }
            QLabel#HintText {
                color: #5a6a72;
                line-height: 1.45;
            }
            QLabel#DetailValue {
                color: #20323a;
                background: #fffdf9;
                border: 1px solid #e4d9cc;
                border-radius: 10px;
                padding: 8px 10px;
            }
            QLineEdit, QDoubleSpinBox, QSpinBox, QPlainTextEdit, QTreeWidget {
                background: #fffdf9;
                border: 1px solid #d7c6b3;
                border-radius: 12px;
                padding: 8px 10px;
                selection-background-color: #c97329;
            }
            QTreeWidget {
                padding: 6px;
            }
            QTreeWidget::item {
                height: 34px;
            }
            QHeaderView::section {
                background: #efe3d4;
                color: #24353e;
                padding: 8px;
                border: none;
                border-bottom: 1px solid #d7c6b3;
                font-weight: 700;
            }
            QPushButton {
                background: #203849;
                color: #fffaf3;
                border: none;
                border-radius: 12px;
                padding: 10px 16px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #2a4a60;
            }
            QPushButton:pressed {
                background: #173142;
            }
            QPushButton#PrimaryButton {
                background: #c97329;
                color: #fffaf3;
                padding: 12px 18px;
            }
            QPushButton#PrimaryButton:hover {
                background: #d9843c;
            }
            QPushButton:disabled {
                background: #bfb3a6;
                color: #f7f0e8;
            }
            QTabWidget::pane {
                border: 1px solid #d7c6b3;
                border-radius: 16px;
                background: #fbf7f1;
                top: -1px;
            }
            QTabBar::tab {
                background: #e7dbcd;
                color: #41545e;
                padding: 10px 18px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #fbf7f1;
                color: #22333b;
                font-weight: 700;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QLabel#PreviewLabel {
                background: #16212a;
                border: 1px solid #334a5a;
                border-radius: 16px;
                color: #dbe6ee;
                padding: 18px;
            }
            QProgressBar {
                min-height: 12px;
                max-height: 12px;
                border: none;
                border-radius: 6px;
                background: rgba(255, 250, 243, 0.2);
                text-align: center;
            }
            QProgressBar::chunk {
                border-radius: 6px;
                background: #f2c078;
            }
            """
        )

    def _build_ui(self):
        self.scale_spin.setDecimals(4)
        self.scale_spin.setRange(0.0001, 9999.0)
        self.scale_spin.setValue(0.1)
        self.scale_spin.setSingleStep(0.01)

        self.sample_spin.setRange(1, 100)
        self.sample_spin.setValue(5)

        self.start_button.setObjectName("PrimaryButton")
        self.log_edit.setReadOnly(True)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.preview_label.setObjectName("PreviewLabel")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setWordWrap(True)
        self.preview_label.setMinimumSize(720, 480)
        self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.results_tree.setColumnCount(5)
        self.results_tree.setHeaderLabels(
            ["图像", "最大宽度(mm)", "平均宽度(mm)", "骨架点", "采样点"]
        )
        self.results_tree.setRootIsDecorated(False)
        self.results_tree.setAlternatingRowColors(False)
        self.results_tree.setUniformRowHeights(True)

        for label in (
            self.detail_source_value,
            self.detail_output_value,
            self.detail_max_width_value,
            self.detail_mean_width_value,
            self.detail_path_length_value,
            self.detail_skeleton_value,
            self.detail_samples_value,
            self.detail_overlay_value,
            self.detail_csv_value,
        ):
            label.setObjectName("DetailValue")
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            label.setWordWrap(True)

        hero_card = QFrame()
        hero_card.setObjectName("HeroCard")
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setContentsMargins(28, 24, 28, 24)
        hero_top = QHBoxLayout()
        hero_text = QVBoxLayout()
        hero_title = QLabel("裂缝宽度检测系统")
        hero_title.setObjectName("HeroTitle")
        hero_subtitle = QLabel(
            "Crack Width Inspector | 面向工程交付的混凝土裂缝识别、测宽与结果导出工具"
        )
        hero_subtitle.setObjectName("HeroSubtitle")
        hero_subtitle.setWordWrap(True)
        hero_text.addWidget(hero_title)
        hero_text.addWidget(hero_subtitle)
        hero_top.addLayout(hero_text, 1)
        self.status_badge.setObjectName("StatusBadge")
        hero_top.addWidget(self.status_badge, 0, Qt.AlignTop)
        hero_layout.addLayout(hero_top)
        hero_layout.addSpacing(16)
        hero_layout.addWidget(self.progress_bar)
        hero_layout.addSpacing(8)
        self.summary_label.setStyleSheet("color:#fff7ed;font-size:10pt;")
        hero_layout.addWidget(self.summary_label)

        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(14)
        metrics_row.addWidget(
            self._build_metric_card("结果数量", self.metric_count_value), 1
        )
        metrics_row.addWidget(
            self._build_metric_card("当前图像", self.metric_current_value), 2
        )
        metrics_row.addWidget(
            self._build_metric_card("全局最大宽度", self.metric_max_width_value), 1
        )
        metrics_row.addWidget(
            self._build_metric_card("系统状态", self.metric_state_value), 1
        )

        config_group = QGroupBox("任务配置")
        config_layout = QGridLayout()
        config_layout.setHorizontalSpacing(10)
        config_layout.setVerticalSpacing(12)
        config_layout.addWidget(QLabel("输入对象"), 0, 0)
        config_layout.addWidget(self.input_edit, 0, 1, 1, 3)
        self.choose_file_button = QPushButton("选择图片")
        self.choose_folder_button = QPushButton("选择文件夹")
        config_layout.addWidget(self.choose_file_button, 0, 4)
        config_layout.addWidget(self.choose_folder_button, 0, 5)

        config_layout.addWidget(QLabel("输出目录"), 1, 0)
        config_layout.addWidget(self.output_edit, 1, 1, 1, 4)
        self.choose_output_button = QPushButton("浏览")
        config_layout.addWidget(self.choose_output_button, 1, 5)

        config_layout.addWidget(QLabel("标定系数"), 2, 0)
        config_layout.addWidget(self.scale_spin, 2, 1)
        config_layout.addWidget(QLabel("单位：mm/px"), 2, 2)
        config_layout.addWidget(QLabel("采样点数"), 2, 3)
        config_layout.addWidget(self.sample_spin, 2, 4)
        config_layout.addWidget(self.start_button, 2, 5)
        config_group.setLayout(config_layout)

        guide_card = self._build_panel_card("使用说明")
        guide_layout = guide_card.layout()
        guide_text = QLabel(
            "1. 选择单张裂缝图片或包含多张图片的文件夹。\n"
            "2. 设置输出目录、标定系数和采样点数。\n"
            "3. 点击“开始检测”，系统会自动输出掩膜、骨架、叠加图和 CSV 数据。\n"
            "4. 若未完成相机标定，毫米结果仅作为估算值。"
        )
        guide_text.setObjectName("HintText")
        guide_text.setWordWrap(True)
        guide_layout.addWidget(guide_text)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(14)
        left_layout.addWidget(config_group)
        left_layout.addWidget(guide_card)
        left_layout.addStretch(1)

        result_card = self._build_panel_card("检测结果")
        result_layout = result_card.layout()
        result_layout.addWidget(self.results_tree)
        result_buttons = QHBoxLayout()
        result_buttons.setSpacing(10)
        result_buttons.addWidget(self.open_output_button)
        result_buttons.addWidget(self.open_overlay_button)
        result_buttons.addWidget(self.open_csv_button)
        result_buttons.addStretch(1)
        result_layout.addLayout(result_buttons)

        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setWidget(self.preview_label)

        details_tab = QWidget()
        details_layout = QFormLayout(details_tab)
        details_layout.setLabelAlignment(Qt.AlignLeft)
        details_layout.setFormAlignment(Qt.AlignTop)
        details_layout.setHorizontalSpacing(14)
        details_layout.setVerticalSpacing(10)
        details_layout.addRow("源文件", self.detail_source_value)
        details_layout.addRow("输出目录", self.detail_output_value)
        details_layout.addRow("最大宽度", self.detail_max_width_value)
        details_layout.addRow("平均宽度", self.detail_mean_width_value)
        details_layout.addRow("主路径长度", self.detail_path_length_value)
        details_layout.addRow("骨架点数", self.detail_skeleton_value)
        details_layout.addRow("采样点数", self.detail_samples_value)
        details_layout.addRow("叠加图", self.detail_overlay_value)
        details_layout.addRow("数据表", self.detail_csv_value)

        preview_tab = QWidget()
        preview_layout = QVBoxLayout(preview_tab)
        preview_layout.addWidget(preview_scroll)

        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        log_layout.addWidget(self.log_edit)

        tabs = QTabWidget()
        tabs.addTab(preview_tab, "结果预览")
        tabs.addTab(details_tab, "结果详情")
        tabs.addTab(log_tab, "运行日志")

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(14)
        right_layout.addWidget(result_card, 2)
        right_layout.addWidget(tabs, 3)

        body_layout = QHBoxLayout()
        body_layout.setSpacing(18)
        body_layout.addWidget(left_panel, 2)
        body_layout.addWidget(right_panel, 5)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(22, 18, 22, 18)
        central_layout.setSpacing(18)
        central_layout.addWidget(hero_card)
        central_layout.addLayout(metrics_row)
        central_layout.addLayout(body_layout, 1)
        self.setCentralWidget(central)

    def _build_metric_card(self, title: str, value_label: QLabel):
        card = QFrame()
        card.setObjectName("MetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)
        title_label = QLabel(title)
        title_label.setObjectName("MetricTitle")
        value_label.setObjectName("MetricValue")
        value_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        return card

    def _build_panel_card(self, title: str):
        card = QFrame()
        card.setObjectName("PanelCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        layout.addWidget(title_label)
        return card

    def _connect_signals(self):
        self.choose_file_button.clicked.connect(self.choose_file)
        self.choose_folder_button.clicked.connect(self.choose_folder)
        self.choose_output_button.clicked.connect(self.choose_output_dir)
        self.start_button.clicked.connect(self.start_processing)
        self.open_output_button.clicked.connect(self.open_output_dir)
        self.open_overlay_button.clicked.connect(self.open_selected_overlay)
        self.open_csv_button.clicked.connect(self.open_selected_csv)
        self.results_tree.currentItemChanged.connect(self.on_result_selected)
        self.results_tree.itemDoubleClicked.connect(self.on_result_double_clicked)

    def _set_status(self, mode: str, text: str):
        colors = {
            "ready": "background: rgba(255,250,243,0.18);",
            "running": "background: rgba(242,192,120,0.28);",
            "success": "background: rgba(126,191,145,0.24);",
            "error": "background: rgba(203,98,72,0.26);",
        }
        self.status_badge.setStyleSheet(
            "QLabel#StatusBadge { color:#fffaf3; padding:7px 14px; border-radius:14px; "
            f"font-weight:700; {colors.get(mode, colors['ready'])} }}"
        )
        self.status_badge.setText(text)
        state_text = {
            "ready": "准备就绪",
            "running": "正在处理",
            "success": "处理完成",
            "error": "处理失败",
        }
        self.metric_state_value.setText(state_text.get(mode, text))

    def _set_controls_enabled(self, enabled: bool):
        for widget in (
            self.input_edit,
            self.output_edit,
            self.scale_spin,
            self.sample_spin,
            self.start_button,
            self.choose_file_button,
            self.choose_folder_button,
            self.choose_output_button,
        ):
            widget.setEnabled(enabled)

    def _set_result_buttons_enabled(self, enabled: bool):
        self.open_output_button.setEnabled(True)
        self.open_overlay_button.setEnabled(enabled)
        self.open_csv_button.setEnabled(enabled)

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择裂缝图像",
            str(runtime_base_dir()),
            "Images (*.jpg *.jpeg *.png *.bmp *.tif *.tiff)",
        )
        if path:
            self.input_edit.setText(path)

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(
            self, "选择图像文件夹", str(runtime_base_dir())
        )
        if path:
            self.input_edit.setText(path)

    def choose_output_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "选择输出目录", self.output_edit.text() or str(runtime_base_dir())
        )
        if path:
            self.output_edit.setText(path)

    def start_processing(self):
        input_text = self.input_edit.text().strip()
        output_text = self.output_edit.text().strip()
        if not input_text:
            QMessageBox.warning(self, "缺少输入", "请选择一张图片或一个文件夹。")
            return
        if not output_text:
            QMessageBox.warning(self, "缺少输出目录", "请选择结果输出目录。")
            return

        input_path = Path(input_text)
        output_dir = Path(output_text)
        if not input_path.exists():
            QMessageBox.warning(self, "输入无效", f"路径不存在：\n{input_path}")
            return

        self.results.clear()
        self.current_result = None
        self.current_preview_path = None
        self.results_tree.clear()
        self.preview_label.setPixmap(QPixmap())
        self.preview_label.setText("正在处理，请稍候...")
        self.log_edit.clear()
        self._clear_details()
        self.metric_count_value.setText("0")
        self.metric_current_value.setText(input_path.name)
        self.metric_max_width_value.setText("0.00 mm")
        self.summary_label.setText("系统正在执行裂缝识别、骨架提取和宽度计算。")
        self.progress_bar.setRange(0, 0)
        self._set_status("running", "处理中")
        self._set_controls_enabled(False)
        self._set_result_buttons_enabled(False)

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

    def append_log(self, message: str):
        self.log_edit.appendPlainText(message)
        match = re.match(r"^\[(\d+)/(\d+)\]\s+(.+)$", message)
        if match:
            self.metric_current_value.setText(match.group(3))
            self.summary_label.setText(
                f"正在处理第 {match.group(1)} / {match.group(2)} 张图像：{match.group(3)}"
            )

    def handle_success(self, results):
        self.worker = None
        self.results = results
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self._set_controls_enabled(True)
        self._set_status("success", "处理完成")
        self.metric_count_value.setText(str(len(results)))

        overall_max_width = max((result.max_width_mm for result in results), default=0.0)
        self.metric_max_width_value.setText(f"{overall_max_width:.2f} mm")
        self.summary_label.setText(
            f"共完成 {len(results)} 张图像处理，结果文件已输出到目标目录。"
        )
        self.append_log("处理完成。")

        for result in results:
            item = QTreeWidgetItem(
                [
                    result.input_path.name,
                    f"{result.max_width_mm:.3f}",
                    f"{result.mean_width_mm:.3f}",
                    str(result.skeleton_points),
                    str(result.sampled_points),
                ]
            )
            item.setData(0, Qt.UserRole, result)
            item.setToolTip(0, str(result.input_path))
            self.results_tree.addTopLevelItem(item)

        self.results_tree.resizeColumnToContents(0)
        self._set_result_buttons_enabled(bool(results))
        if self.results_tree.topLevelItemCount():
            self.results_tree.setCurrentItem(self.results_tree.topLevelItem(0))
        else:
            self.metric_current_value.setText("无结果")

    def handle_failure(self, traceback_text: str):
        self.worker = None
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self._set_controls_enabled(True)
        self._set_status("error", "处理失败")
        self.summary_label.setText("任务执行失败，请查看日志。")
        self.metric_state_value.setText("异常")
        self.append_log(traceback_text)
        QMessageBox.critical(self, "处理失败", traceback_text)

    def _clear_details(self):
        for label in (
            self.detail_source_value,
            self.detail_output_value,
            self.detail_max_width_value,
            self.detail_mean_width_value,
            self.detail_path_length_value,
            self.detail_skeleton_value,
            self.detail_samples_value,
            self.detail_overlay_value,
            self.detail_csv_value,
        ):
            label.setText("-")

    def on_result_selected(self, current: QTreeWidgetItem, previous: QTreeWidgetItem):
        if current is None:
            self.current_result = None
            self.current_preview_path = None
            self.preview_label.setText("请选择结果记录以查看叠加图")
            self._set_result_buttons_enabled(False)
            return

        result = current.data(0, Qt.UserRole)
        self.current_result = result
        self.current_preview_path = result.overlay_path
        self.metric_current_value.setText(result.input_path.name)
        self._populate_details(result)
        self._set_result_buttons_enabled(True)
        self.update_preview()

    def _populate_details(self, result):
        self.detail_source_value.setText(str(result.input_path))
        self.detail_output_value.setText(str(result.output_dir))
        self.detail_max_width_value.setText(
            f"{result.max_width_mm:.4f} mm / {result.max_width_px:.4f} px"
        )
        self.detail_mean_width_value.setText(
            f"{result.mean_width_mm:.4f} mm / {result.mean_width_px:.4f} px"
        )
        self.detail_path_length_value.setText(f"{result.main_path_length_px:.2f} px")
        self.detail_skeleton_value.setText(str(result.skeleton_points))
        self.detail_samples_value.setText(str(result.sampled_points))
        self.detail_overlay_value.setText(str(result.overlay_path))
        csv_target = result.samples_csv or result.profile_csv or result.widths_csv
        self.detail_csv_value.setText(str(csv_target))
        self.summary_label.setText(
            f"当前查看：{result.input_path.name} | 最大宽度 {result.max_width_mm:.3f} mm"
        )

    def update_preview(self):
        if not self.current_preview_path:
            return

        pixmap = QPixmap(str(self.current_preview_path))
        if pixmap.isNull():
            self.preview_label.setText(f"预览加载失败：\n{self.current_preview_path}")
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

    def _open_path(self, path: Path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def open_output_dir(self):
        output_text = self.output_edit.text().strip()
        if not output_text:
            return
        path = Path(output_text)
        if not path.exists():
            QMessageBox.warning(self, "目录不存在", f"输出目录不存在：\n{path}")
            return
        self._open_path(path)

    def open_selected_overlay(self):
        if self.current_result is None:
            return
        self._open_path(self.current_result.overlay_path)

    def open_selected_csv(self):
        if self.current_result is None:
            return
        csv_target = (
            self.current_result.samples_csv
            or self.current_result.profile_csv
            or self.current_result.widths_csv
        )
        self._open_path(csv_target)

    def on_result_double_clicked(self, item: QTreeWidgetItem, column: int):
        result = item.data(0, Qt.UserRole)
        self._open_path(result.overlay_path)


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
