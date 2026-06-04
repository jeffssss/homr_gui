# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import traceback
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SETTINGS_FILENAME = "homr_musicxml_gui_settings.json"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


@dataclass(frozen=True)
class GuiSettings:
    output_dir: Path | None = None


def load_settings(settings_path: Path) -> GuiSettings:
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return GuiSettings()

    raw_output_dir = data.get("output_dir")
    if not isinstance(raw_output_dir, str) or raw_output_dir == "":
        return GuiSettings()

    output_dir = Path(raw_output_dir).expanduser()
    if not output_dir.is_dir():
        return GuiSettings()

    return GuiSettings(output_dir=output_dir.resolve())


def save_settings(settings_path: Path, output_dir: Path) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    data = {"output_dir": str(output_dir.expanduser().resolve())}
    settings_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_timestamped_output_path(output_dir: Path, now: datetime | None = None) -> Path:
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    stem = f"homr_{timestamp}"
    candidate = output_dir / f"{stem}.musicxml"
    suffix = 1
    while candidate.exists():
        candidate = output_dir / f"{stem}_{suffix}.musicxml"
        suffix += 1
    return candidate


def move_musicxml_to_output(temp_xml: Path, output_dir: Path) -> Path:
    if not temp_xml.is_file():
        raise FileNotFoundError(f"MusicXML file was not generated: {temp_xml}")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = build_timestamped_output_path(output_dir)
    shutil.move(str(temp_xml), str(output_path))
    return output_path


def _short_path(path: Path, max_length: int = 34) -> str:
    text = str(path)
    if len(text) <= max_length:
        return text
    return "..." + text[-(max_length - 3) :]


def main() -> None:
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts=false;qt.qpa.mime=false")
    warnings.filterwarnings(
        "ignore",
        message=r"urllib3 .*doesn't match a supported version!",
        category=Warning,
        module=r"requests",
    )

    from PyQt6.QtCore import QPoint, QThread, QTimer, Qt, QUrl, pyqtSignal
    from PyQt6.QtGui import QColor, QDesktopServices
    from PyQt6.QtWidgets import (
        QApplication,
        QFileDialog,
        QGraphicsDropShadowEffect,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    from homr.main import ProcessingConfig, download_weights, process_image
    from homr.music_xml_generator import XmlGeneratorArguments
    from homr.onnxruntime_utils import (
        configure_onnxruntime_logging,
        is_cuda_available,
        log_onnxruntime_status,
        preload_cuda_dlls,
    )

    preload_cuda_dlls()
    configure_onnxruntime_logging(enable_debug=False)

    cfg = {
        "window_size": (260, 330),
        "margins": (14, 22, 14, 10),
        "radius_card": 22,
        "font_family": "'Helvetica Neue', 'Inter', 'Microsoft YaHei UI', sans-serif",
        "color_text_title": "#FFFFFF",
        "color_text_sub": "#666666",
        "color_text_footer": "#444444",
        "states": {
            "idle": {
                "title": "框选乐谱",
                "sub": "截图后自动识别",
                "bg": "#8CA6BA",
                "bg_hover": "#9EB5C7",
                "color": "#050505",
                "shadow_color": QColor(140, 166, 186, 0),
                "shadow_active": QColor(140, 166, 186, 140),
            },
            "processing": {
                "title": "解析中",
                "sub": "HOMR Engine Running",
                "bg": "#D9C88C",
                "bg_hover": "#E6D6A1",
                "color": "#050505",
                "shadow_color": QColor(217, 200, 140, 0),
                "shadow_active": QColor(217, 200, 140, 140),
            },
            "success": {
                "title": "转换成功",
                "sub": "",
                "bg": "#9AB593",
                "bg_hover": "#ADC9A6",
                "color": "#050505",
                "shadow_color": QColor(154, 181, 147, 0),
                "shadow_active": QColor(154, 181, 147, 140),
            },
            "error": {
                "title": "识别失败",
                "sub": "请重新截图",
                "bg": "#C78B8B",
                "bg_hover": "#D99C9C",
                "color": "#050505",
                "shadow_color": QColor(199, 139, 139, 0),
                "shadow_active": QColor(199, 139, 139, 140),
            },
        },
    }

    class WorkerThread(QThread):
        succeeded = pyqtSignal(str)
        failed = pyqtSignal(str)

        def __init__(self, img_path: Path, temp_dir: Path, output_dir: Path):
            super().__init__()
            self.img_path = img_path
            self.temp_dir = temp_dir
            self.output_dir = output_dir

        def run(self) -> None:
            try:
                use_gpu_inference = is_cuda_available()
                log_onnxruntime_status(use_gpu_inference)
                download_weights(use_gpu_inference)

                config = ProcessingConfig(
                    enable_debug=False,
                    enable_cache=False,
                    write_staff_positions=False,
                    read_staff_positions=False,
                    selected_staff=-1,
                    use_gpu_inference=use_gpu_inference,
                )
                xml_args = XmlGeneratorArguments(False, None, None)

                process_image(str(self.img_path), config, xml_args)

                temp_xml = self.img_path.with_suffix(".musicxml")
                output_path = move_musicxml_to_output(temp_xml, self.output_dir)
                self.succeeded.emit(str(output_path))
            except Exception as exc:
                print(traceback.format_exc())
                self.failed.emit(f"识别失败: {exc}")
            finally:
                shutil.rmtree(self.temp_dir, ignore_errors=True)

    class HomrMusicXmlGui(QWidget):
        _drag_pos = QPoint()

        def __init__(self) -> None:
            super().__init__()
            self.settings_path = ROOT_DIR / SETTINGS_FILENAME
            self.output_dir = load_settings(self.settings_path).output_dir
            self.current_output_file: Path | None = None
            self.last_image_id: int | None = None
            self._clipboard_pending = False
            self.current_state_cfg = None
            self.thread: WorkerThread | None = None

            self.init_ui()
            QApplication.clipboard().dataChanged.connect(self.schedule_clipboard_check)

        def init_ui(self) -> None:
            self.setWindowTitle("HOMR · MusicXML")
            self.setFixedSize(*cfg["window_size"])
            self.setWindowFlags(
                Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint
            )
            self.setStyleSheet("background-color: #000000;")

            layout = QVBoxLayout(self)
            layout.setContentsMargins(*cfg["margins"])
            layout.setSpacing(0)

            header_layout = QHBoxLayout()
            header_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

            title_layout = QVBoxLayout()
            title_layout.setSpacing(0)

            title_lbl = QLabel("HOMR.")
            title_lbl.setStyleSheet(
                f"""
                color: {cfg['color_text_title']};
                font-family: {cfg['font_family']};
                font-size: 26px;
                font-weight: 900;
                background-color: transparent;
                """
            )

            sub_lbl = QLabel("Score to MusicXML")
            sub_lbl.setStyleSheet(
                f"""
                color: {cfg['color_text_sub']};
                font-family: {cfg['font_family']};
                font-size: 10px;
                font-weight: 700;
                background-color: transparent;
                """
            )

            title_layout.addWidget(title_lbl)
            title_layout.addWidget(sub_lbl)
            header_layout.addLayout(title_layout)
            header_layout.addStretch()

            close_btn = QPushButton("×", self)
            close_btn.setFixedSize(24, 24)
            close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            close_btn.setStyleSheet(
                f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    color: {cfg['color_text_sub']};
                    font-size: 22px;
                    font-weight: 300;
                    padding-bottom: 4px;
                }}
                QPushButton:hover {{ color: {cfg['color_text_title']}; }}
                """
            )
            close_btn.clicked.connect(self.close)
            header_layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignTop)
            layout.addLayout(header_layout)
            layout.addSpacing(22)

            self.btn = QPushButton(self)
            self.btn.setFixedSize(self.width() - cfg["margins"][0] - cfg["margins"][2], 112)
            self.btn.setCursor(Qt.CursorShape.ArrowCursor)

            self.shadow = QGraphicsDropShadowEffect()
            self.shadow.setBlurRadius(0)
            self.shadow.setOffset(0, 8)
            self.btn.setGraphicsEffect(self.shadow)

            self.btn_layout = QVBoxLayout(self.btn)
            self.btn_layout.setContentsMargins(18, 18, 18, 18)
            self.btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.btn_layout.setSpacing(2)

            self.btn_title = QLabel()
            self.btn_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.btn_subtitle = QLabel()
            self.btn_subtitle.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

            self.btn_layout.addWidget(self.btn_title)
            self.btn_layout.addWidget(self.btn_subtitle)
            self.btn.pressed.connect(self._on_btn_pressed)
            self.btn.released.connect(self._on_btn_released)
            layout.addWidget(self.btn, alignment=Qt.AlignmentFlag.AlignCenter)

            layout.addSpacing(14)

            self.folder_label = QLabel()
            self.folder_label.setStyleSheet(
                f"""
                color: {cfg['color_text_sub']};
                font-family: {cfg['font_family']};
                font-size: 10px;
                font-weight: 500;
                background-color: transparent;
                """
            )
            self.folder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self.folder_label)

            layout.addSpacing(8)

            button_layout = QHBoxLayout()
            button_layout.setSpacing(8)
            self.choose_folder_btn = self._make_small_button("选择文件夹")
            self.open_folder_btn = self._make_small_button("打开文件夹")
            self.choose_folder_btn.clicked.connect(self.choose_output_folder)
            self.open_folder_btn.clicked.connect(self.open_output_folder)
            button_layout.addWidget(self.choose_folder_btn)
            button_layout.addWidget(self.open_folder_btn)
            layout.addLayout(button_layout)

            layout.addStretch()

            footer = QLabel("Powered by HOMR Engine")
            footer.setStyleSheet(
                f"""
                color: {cfg['color_text_footer']};
                font-family: {cfg['font_family']};
                font-size: 9px;
                font-weight: 600;
                background-color: transparent;
                """
            )
            layout.addWidget(footer)

            self._refresh_folder_state()
            self._apply_state("idle")

        def _make_small_button(self, text: str) -> QPushButton:
            button = QPushButton(text, self)
            button.setFixedHeight(30)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: #1A1A1A;
                    border: 1px solid #2B2B2B;
                    border-radius: 8px;
                    color: #D8D8D8;
                    font-family: {cfg['font_family']};
                    font-size: 11px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background-color: #242424;
                    border-color: #3A3A3A;
                }}
                QPushButton:disabled {{
                    color: #555555;
                    background-color: #101010;
                    border-color: #1A1A1A;
                }}
                """
            )
            return button

        def _idle_subtitle(self) -> str:
            if self.output_dir is None:
                return "先选择文件夹"
            return f"保存到 {self.output_dir.name}"

        def _apply_state(self, state_name: str, subtitle_override: str | None = None) -> None:
            state = cfg["states"].get(state_name, cfg["states"]["idle"])
            self.current_state_cfg = state
            subtitle = subtitle_override
            if subtitle is None:
                subtitle = self._idle_subtitle() if state_name == "idle" else state["sub"]

            self.btn.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {state['bg']};
                    border-radius: {cfg['radius_card']}px;
                    border: none;
                }}
                QPushButton:hover {{
                    background-color: {state['bg_hover']};
                }}
                """
            )

            self.btn_title.setText(state["title"])
            self.btn_title.setStyleSheet(
                f"""
                color: {state['color']};
                font-family: {cfg['font_family']};
                font-size: 19px;
                font-weight: 800;
                background-color: transparent;
                """
            )

            sub_color = QColor(state["color"])
            sub_color.setAlpha(160)
            self.btn_subtitle.setText(subtitle)
            self.btn_subtitle.setStyleSheet(
                f"""
                color: {sub_color.name(QColor.NameFormat.HexArgb)};
                font-family: {cfg['font_family']};
                font-size: 11px;
                font-weight: 500;
                background-color: transparent;
                """
            )
            self.shadow.setColor(state["shadow_color"])

        def _on_btn_pressed(self) -> None:
            if self.current_state_cfg is None:
                return
            self.shadow.setColor(self.current_state_cfg["shadow_active"])
            self.shadow.setBlurRadius(32)
            self.shadow.setOffset(0, 12)

        def _on_btn_released(self) -> None:
            if self.current_state_cfg is None:
                return
            self.shadow.setColor(self.current_state_cfg["shadow_color"])
            self.shadow.setBlurRadius(0)
            self.shadow.setOffset(0, 8)

        def _refresh_folder_state(self) -> None:
            has_output_dir = self.output_dir is not None and self.output_dir.is_dir()
            self.open_folder_btn.setEnabled(has_output_dir)
            if has_output_dir and self.output_dir is not None:
                self.folder_label.setText(f"输出: {_short_path(self.output_dir)}")
            else:
                self.folder_label.setText("未设置输出文件夹")

        def _set_output_dir(self, output_dir: Path) -> None:
            self.output_dir = output_dir.expanduser().resolve()
            save_settings(self.settings_path, self.output_dir)
            self._refresh_folder_state()
            self._apply_state("idle")

        def choose_output_folder(self) -> bool:
            start_dir = str(self.output_dir or ROOT_DIR)
            selected = QFileDialog.getExistingDirectory(self, "选择 MusicXML 保存文件夹", start_dir)
            if not selected:
                return False
            self._set_output_dir(Path(selected))
            return True

        def ensure_output_folder(self) -> bool:
            if self.output_dir is not None and self.output_dir.is_dir():
                return True
            return self.choose_output_folder()

        def open_output_folder(self) -> None:
            if self.output_dir is None or not self.output_dir.is_dir():
                self._apply_state("error", "输出文件夹无效")
                self._refresh_folder_state()
                return

            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output_dir)))
            if not opened:
                self._apply_state("error", "无法打开文件夹")

        def mousePressEvent(self, event) -> None:
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

        def mouseMoveEvent(self, event) -> None:
            if event.buttons() == Qt.MouseButton.LeftButton:
                self.move(event.globalPosition().toPoint() - self._drag_pos)

        def schedule_clipboard_check(self) -> None:
            if self._clipboard_pending:
                return
            self._clipboard_pending = True
            QTimer.singleShot(250, self.on_clipboard_change)

        def on_clipboard_change(self) -> None:
            self._clipboard_pending = False
            clipboard = QApplication.clipboard()
            mime_data = clipboard.mimeData()

            if not mime_data.hasImage():
                return

            img = clipboard.image()
            if img.isNull():
                return

            img_id = img.cacheKey()
            if img_id == self.last_image_id:
                return

            if not self.ensure_output_folder():
                self._apply_state("idle")
                return

            if self.output_dir is None:
                self._apply_state("error", "输出文件夹无效")
                return

            self.last_image_id = img_id
            self._apply_state("processing")

            temp_dir = Path(tempfile.mkdtemp(prefix="homr_musicxml_"))
            img_path = temp_dir / "score.png"
            if not img.save(str(img_path)):
                shutil.rmtree(temp_dir, ignore_errors=True)
                self._apply_state("error", "无法保存截图")
                return

            self.thread = WorkerThread(img_path, temp_dir, self.output_dir)
            self.thread.succeeded.connect(self.on_process_success)
            self.thread.failed.connect(self.on_process_error)
            self.thread.start()

        def on_process_success(self, output_file: str) -> None:
            self.current_output_file = Path(output_file)
            self._refresh_folder_state()
            self._apply_state("success", self.current_output_file.name)

        def on_process_error(self, err_msg: str) -> None:
            print("识别错误:", err_msg)
            self._refresh_folder_state()
            self._apply_state("error")

    app = QApplication(sys.argv)
    window = HomrMusicXmlGui()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
