import json
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .audio_utils import join_mp3_files
from .config_manager import load_config, resolve_output_dir, save_config
from .piper_manager import (
    import_piper_voice,
    list_piper_voices,
    remove_piper_voice,
)
from .subtitle_parser import parse_file
from .tts_engines import DEFAULT_EDGE_VOICES, load_edge_voices
from .utils import open_folder
from .voice_library import (
    import_reference_voice,
    list_reference_voices,
    remove_reference_voice,
)
from .worker import BatchTTSWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.thread: QThread | None = None
        self.worker: BatchTTSWorker | None = None
        self.setWindowTitle("Dani-like Auto TTS Studio")
        self.resize(1220, 820)
        self._build_ui()
        self._load_config_to_ui()
        self._connect_signals()
        self.log("Ứng dụng đã sẵn sàng.")

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)

        top = QHBoxLayout()
        top.addWidget(self._voice_group(), 2)
        top.addWidget(self._settings_group(), 1)
        top.addWidget(self._batch_group(), 2)
        root.addLayout(top)
        root.addWidget(self._control_group())

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Output", "Timing", "Content", "Voice", "Status", "Error"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)

        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.log_box)
        splitter.setSizes([560, 170])
        root.addWidget(splitter, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Sẵn sàng")

    def _voice_group(self) -> QGroupBox:
        group = QGroupBox("Giọng đọc miễn phí")
        layout = QGridLayout(group)
        self.engine_combo = QComboBox()
        self.engine_combo.addItem("Edge TTS Free", "edge")
        self.engine_combo.addItem("gTTS Backup", "gtts")
        self.engine_combo.addItem("Piper Offline", "piper")
        self.engine_combo.addItem("Local Voice Clone", "openvoice")
        self.engine_combo.addItem("XTTS Local", "xtts")
        self.voice_combo = QComboBox()
        self.voice_combo.setEditable(True)
        self._set_default_voices()
        self.load_voices_btn = QPushButton("Load Free Voices")
        self.import_piper_btn = QPushButton("Import Piper Model")
        self.remove_piper_btn = QPushButton("Remove Piper Model")
        self.import_reference_btn = QPushButton("Import WAV/MP3 Voice")
        self.remove_reference_btn = QPushButton("Remove Clone Voice")
        self.save_settings_btn = QPushButton("Lưu cấu hình")
        self.language_combo = QComboBox()
        self.language_combo.addItem("Auto", "auto")
        self.language_combo.addItem("Vietnamese", "vi")
        self.language_combo.addItem("English", "en")
        layout.addWidget(QLabel("TTS Engine"), 0, 0)
        layout.addWidget(self.engine_combo, 0, 1, 1, 2)
        layout.addWidget(QLabel("Voice"), 1, 0)
        layout.addWidget(self.voice_combo, 1, 1, 1, 2)
        layout.addWidget(self.load_voices_btn, 2, 1)
        layout.addWidget(self.import_piper_btn, 2, 2)
        layout.addWidget(self.remove_piper_btn, 3, 1, 1, 2)
        layout.addWidget(self.import_reference_btn, 4, 1, 1, 2)
        layout.addWidget(self.remove_reference_btn, 5, 1, 1, 2)
        layout.addWidget(self.save_settings_btn, 6, 1, 1, 2)
        layout.addWidget(QLabel("Language"), 7, 0)
        layout.addWidget(self.language_combo, 7, 1, 1, 2)
        return group

    def _settings_group(self) -> QGroupBox:
        group = QGroupBox("Voice Settings")
        form = QFormLayout(group)
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.5, 2.0)
        self.speed_spin.setSingleStep(0.05)
        self.speed_spin.setDecimals(2)
        self.speed_spin.setValue(1.0)
        self.pitch_spin = QSpinBox()
        self.pitch_spin.setRange(-100, 100)
        self.pitch_spin.setSuffix(" Hz")
        self.volume_spin = QSpinBox()
        self.volume_spin.setRange(0, 200)
        self.volume_spin.setSuffix("%")
        self.volume_spin.setValue(100)
        self.reset_btn = QPushButton("Reset")
        form.addRow("Speed", self.speed_spin)
        form.addRow("Pitch", self.pitch_spin)
        form.addRow("Volume", self.volume_spin)
        form.addRow(self.reset_btn)
        return group

    def _batch_group(self) -> QGroupBox:
        group = QGroupBox("Batch Job")
        layout = QGridLayout(group)
        self.output_edit = QLineEdit()
        self.browse_btn = QPushButton("Browse")
        self.create_srt = QCheckBox("Tự động tạo SRT")
        self.skip_done = QCheckBox("Bỏ qua dòng đã DONE")
        self.auto_join = QCheckBox("Tự động nối MP3 sau khi xong")
        layout.addWidget(QLabel("Thư mục output"), 0, 0)
        layout.addWidget(self.output_edit, 1, 0)
        layout.addWidget(self.browse_btn, 1, 1)
        layout.addWidget(self.create_srt, 2, 0, 1, 2)
        layout.addWidget(self.skip_done, 3, 0, 1, 2)
        layout.addWidget(self.auto_join, 4, 0, 1, 2)
        layout.setRowStretch(5, 1)
        return group

    def _control_group(self) -> QGroupBox:
        group = QGroupBox("Control")
        layout = QHBoxLayout(group)
        buttons = [
            ("Start", "start_btn"),
            ("Stop", "stop_btn"),
            ("Import File", "import_file_btn"),
            ("Import Folder", "import_folder_btn"),
            ("Import Voice", "import_voice_btn"),
            ("Open Audio Output", "open_output_btn"),
            ("Join MP3", "join_btn"),
            ("Clear", "clear_btn"),
            ("Save Project", "save_project_btn"),
            ("Load Project", "load_project_btn"),
        ]
        for text, name in buttons:
            button = QPushButton(text)
            setattr(self, name, button)
            layout.addWidget(button)
        self.stop_btn.setEnabled(False)
        return group

    def _connect_signals(self) -> None:
        self.load_voices_btn.clicked.connect(self.load_free_voices)
        self.import_piper_btn.clicked.connect(self.import_piper_model)
        self.remove_piper_btn.clicked.connect(self.remove_piper_model)
        self.import_reference_btn.clicked.connect(self.import_reference_model)
        self.remove_reference_btn.clicked.connect(self.remove_reference_model)
        self.save_settings_btn.clicked.connect(self.save_settings)
        self.engine_combo.currentIndexChanged.connect(self.on_engine_changed)
        self.reset_btn.clicked.connect(self.reset_voice_settings)
        self.browse_btn.clicked.connect(self.browse_output)
        self.start_btn.clicked.connect(self.start_batch)
        self.stop_btn.clicked.connect(self.stop_batch)
        self.import_file_btn.clicked.connect(self.import_files)
        self.import_folder_btn.clicked.connect(self.import_folder)
        self.import_voice_btn.clicked.connect(self.import_voice)
        self.open_output_btn.clicked.connect(self.open_output)
        self.join_btn.clicked.connect(self.join_mp3)
        self.clear_btn.clicked.connect(self.clear_table)
        self.save_project_btn.clicked.connect(self.save_project)
        self.load_project_btn.clicked.connect(self.load_project)

    def _set_default_voices(self, selected: str = "") -> None:
        self.voice_combo.clear()
        for voice in DEFAULT_EDGE_VOICES:
            self.voice_combo.addItem(voice, voice)
        if selected:
            self.voice_combo.setCurrentText(selected)

    def _load_config_to_ui(self) -> None:
        engine_index = self.engine_combo.findData(
            self.config.get("default_engine", "edge")
        )
        self.engine_combo.setCurrentIndex(max(0, engine_index))
        configured_voice = str(
            self.config.get("default_voice", DEFAULT_EDGE_VOICES[0])
        )
        if configured_voice and self.voice_combo.findData(configured_voice) < 0:
            self.voice_combo.addItem(configured_voice, configured_voice)
        self.voice_combo.setCurrentText(configured_voice)
        language_map = {"Auto": "auto", "Vietnamese": "vi", "English": "en"}
        language_index = self.language_combo.findData(
            language_map.get(str(self.config.get("language", "Auto")), "auto")
        )
        self.language_combo.setCurrentIndex(max(0, language_index))
        output = resolve_output_dir(self.config.get("output_dir"))
        self.output_edit.setText(str(output))
        self.speed_spin.setValue(float(self.config.get("speed", 1.0)))
        self.pitch_spin.setValue(int(self.config.get("pitch", 0)))
        self.volume_spin.setValue(int(self.config.get("volume", 100)))
        self.on_engine_changed()
        if self.engine_combo.currentData() == "piper":
            self.voice_combo.setCurrentText(
                str(self.config.get("default_piper_voice", ""))
            )
        elif self.engine_combo.currentData() == "openvoice":
            self.voice_combo.setCurrentText(
                str(self.config.get("default_clone_voice", ""))
            )
        elif self.engine_combo.currentData() == "xtts":
            self.voice_combo.setCurrentText(
                str(self.config.get("default_xtts_voice", ""))
            )

    def current_settings(self) -> dict[str, Any]:
        engine = self.engine_combo.currentData()
        language_code = self.language_combo.currentData()
        if language_code == "auto":
            voice = self.voice_combo.currentData() or self.voice_combo.currentText()
            if engine == "xtts":
                language_code = "en"
            else:
                language_code = "vi" if str(voice).lower().startswith("vi-") else "en"
        return {
            "engine": engine,
            "voice": self.voice_combo.currentData() or self.voice_combo.currentText(),
            "language": self.language_combo.currentText(),
            "language_code": language_code,
            "speed": self.speed_spin.value(),
            "pitch": self.pitch_spin.value(),
            "volume": self.volume_spin.value(),
            "skip_done": self.skip_done.isChecked(),
            "create_srt": self.create_srt.isChecked(),
            "auto_join": self.auto_join.isChecked(),
        }

    def save_settings(self) -> None:
        settings = self.current_settings()
        self.config.update(
            {
                "default_engine": settings["engine"],
                "language": settings["language"],
                "output_dir": self.output_edit.text().strip() or "output",
                "speed": settings["speed"],
                "pitch": settings["pitch"],
                "volume": settings["volume"],
            }
        )
        if settings["engine"] == "piper":
            self.config["default_piper_voice"] = settings["voice"]
        elif settings["engine"] == "openvoice":
            self.config["default_clone_voice"] = settings["voice"]
        elif settings["engine"] == "xtts":
            self.config["default_xtts_voice"] = settings["voice"]
        else:
            self.config["default_voice"] = settings["voice"]
        try:
            save_config(self.config)
            self.log("Đã lưu cấu hình miễn phí vào config.json.")
        except OSError as exc:
            self.show_error(f"Không thể lưu config.json: {exc}")

    def load_free_voices(self) -> None:
        if self.engine_combo.currentData() != "edge":
            self.log("gTTS dùng giọng mặc định theo ngôn ngữ; không có danh sách voice.")
            return
        current = self.voice_combo.currentData() or self.voice_combo.currentText()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            voices = load_edge_voices()
            self.voice_combo.clear()
            for voice in voices:
                self.voice_combo.addItem(voice["name"], voice["voice_id"])
            matching = self.voice_combo.findData(current)
            if matching >= 0:
                self.voice_combo.setCurrentIndex(matching)
            else:
                fallback = self.voice_combo.findData("vi-VN-HoaiMyNeural")
                if fallback >= 0:
                    self.voice_combo.setCurrentIndex(fallback)
                self.log(
                    "Voice đã chọn không còn hợp lệ; fallback vi-VN-HoaiMyNeural."
                )
            self.log(f"Đã tải {len(voices)} giọng Edge TTS miễn phí.")
        finally:
            QApplication.restoreOverrideCursor()

    def on_engine_changed(self) -> None:
        engine = self.engine_combo.currentData()
        is_edge = engine == "edge"
        is_piper = engine == "piper"
        is_openvoice = engine == "openvoice"
        is_xtts = engine == "xtts"
        self.voice_combo.setEnabled(is_edge or is_piper or is_openvoice or is_xtts)
        self.load_voices_btn.setEnabled(is_edge)
        self.import_piper_btn.setEnabled(is_piper)
        self.remove_piper_btn.setEnabled(is_piper and self.voice_combo.count() > 0)
        self.import_reference_btn.setEnabled(is_openvoice or is_xtts)
        self.remove_reference_btn.setEnabled(
            (is_openvoice or is_xtts) and self.voice_combo.count() > 0
        )
        self.import_voice_btn.setEnabled(is_edge)
        if is_edge:
            selected = str(self.config.get("default_voice", DEFAULT_EDGE_VOICES[0]))
            self._set_default_voices(selected)
        if engine == "gtts":
            self.log("gTTS Backup dùng giọng mặc định theo ngôn ngữ đã chọn.")
        elif is_piper:
            self._load_piper_voices()
            self.log("Piper chạy offline bằng model ONNX đã import.")
        elif is_openvoice:
            self._load_reference_voices()
            self.log(
                "Local Voice Clone dùng Edge tiếng Việt và đổi sang giọng WAV/MP3 mẫu."
            )

        elif is_xtts:
            self._load_reference_voices(
                str(self.config.get("default_xtts_voice", ""))
            )
            self.log(
                "XTTS Local cho Ä‘á»™ giá»‘ng cao hÆ¡n nhÆ°ng ráº¥t cháº­m trÃªn CPU. "
                "Engine nÃ y hiá»‡n dÃ¹ng tá»‘t cho English vÃ  cÃ¡c ngÃ´n ngá»¯ XTTS há»— trá»£."
            )

    def _load_piper_voices(self, selected: str = "") -> None:
        voices = list_piper_voices()
        self.voice_combo.clear()
        for voice in voices:
            self.voice_combo.addItem(voice["name"], voice["id"])
        preferred = selected or str(self.config.get("default_piper_voice", ""))
        index = self.voice_combo.findData(preferred)
        if index >= 0:
            self.voice_combo.setCurrentIndex(index)
        if not voices:
            self.voice_combo.setEditText("")
            self.log("Chưa có Piper voice. Nhấn Import Piper Model để thêm.")
        self.remove_piper_btn.setEnabled(bool(voices))

    def import_piper_model(self) -> None:
        model_path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn Piper model",
            "",
            "Piper ONNX Model (*.onnx)",
        )
        if not model_path:
            return
        default_name = Path(model_path).stem
        display_name, ok = QInputDialog.getText(
            self,
            "Tên voice Piper",
            "Tên hiển thị:",
            text=default_name,
        )
        if not ok:
            return
        try:
            entry = import_piper_voice(model_path, display_name)
            self._load_piper_voices(entry["id"])
            self.config["default_piper_voice"] = entry["id"]
            save_config(self.config)
            self.log(
                f"Đã import Piper voice: {entry['name']} ({entry['id']})"
            )
            QMessageBox.information(
                self,
                "Import thành công",
                "Đã thêm Piper voice offline.\n"
                f"Model: {entry['model_path']}",
            )
        except Exception as exc:
            self.show_error(f"Không thể import Piper model: {exc}")

    def remove_piper_model(self) -> None:
        voice_id = str(
            self.voice_combo.currentData() or self.voice_combo.currentText()
        ).strip()
        if not voice_id:
            self.show_error("Chưa chọn Piper voice cần xóa.")
            return
        answer = QMessageBox.question(
            self,
            "Xóa Piper voice",
            f"Xóa model '{self.voice_combo.currentText()}' khỏi thư viện?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            remove_piper_voice(voice_id)
            if self.config.get("default_piper_voice") == voice_id:
                self.config["default_piper_voice"] = ""
                save_config(self.config)
            self._load_piper_voices()
            self.log(f"Đã xóa Piper voice: {voice_id}")
        except Exception as exc:
            self.show_error(f"Không thể xóa Piper voice: {exc}")

    def _load_reference_voices(self, selected: str = "") -> None:
        voices = list_reference_voices()
        self.voice_combo.clear()
        for voice in voices:
            self.voice_combo.addItem(voice["name"], voice["id"])
            tooltip_parts = []
            if voice.get("duration_ms"):
                tooltip_parts.append(
                    f"Do dai sau lam sach: {round(int(voice['duration_ms']) / 1000, 1)} giay"
                )
            if voice.get("quality_note"):
                tooltip_parts.append(str(voice["quality_note"]))
            if tooltip_parts:
                self.voice_combo.setItemData(
                    self.voice_combo.count() - 1,
                    "\n".join(tooltip_parts),
                    Qt.ItemDataRole.ToolTipRole,
                )
        preferred = selected or str(self.config.get("default_clone_voice", ""))
        index = self.voice_combo.findData(preferred)
        if index >= 0:
            self.voice_combo.setCurrentIndex(index)
        if not voices:
            self.voice_combo.setEditText("")
            self.log(
                "Chưa có voice mẫu. Nhấn Import WAV/MP3 Voice để thêm."
            )
        self.remove_reference_btn.setEnabled(bool(voices))

    def import_reference_model(self) -> None:
        audio_path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn audio giọng mẫu",
            "",
            "Audio (*.wav *.mp3 *.m4a *.flac *.ogg)",
        )
        if not audio_path:
            return
        default_name = Path(audio_path).stem
        display_name, ok = QInputDialog.getText(
            self,
            "Tên voice clone",
            "Tên hiển thị:",
            text=default_name,
        )
        if not ok:
            return
        try:
            entry = import_reference_voice(audio_path, display_name)
            self._load_reference_voices(entry["id"])
            if self.engine_combo.currentData() == "xtts":
                self.config["default_xtts_voice"] = entry["id"]
            else:
                self.config["default_clone_voice"] = entry["id"]
            save_config(self.config)
            self.log(
                f"Đã import voice mẫu: {entry['name']} ({entry['id']})"
            )
            QMessageBox.information(
                self,
                "Import thành công",
                "Đã thêm voice mẫu. Audio rõ, ít nhạc nền và dài 10–30 giây "
                "sẽ cho kết quả tốt hơn.",
            )
        except Exception as exc:
            self.show_error(f"Không thể import voice mẫu: {exc}")

    def remove_reference_model(self) -> None:
        voice_id = str(
            self.voice_combo.currentData() or self.voice_combo.currentText()
        ).strip()
        if not voice_id:
            self.show_error("Chưa chọn voice clone cần xóa.")
            return
        answer = QMessageBox.question(
            self,
            "Xóa voice clone",
            f"Xóa voice mẫu '{self.voice_combo.currentText()}'?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            remove_reference_voice(voice_id)
            should_save = False
            if self.config.get("default_clone_voice") == voice_id:
                self.config["default_clone_voice"] = ""
                should_save = True
            if self.config.get("default_xtts_voice") == voice_id:
                self.config["default_xtts_voice"] = ""
                should_save = True
            if should_save:
                save_config(self.config)
            self._load_reference_voices()
            self.log(f"Đã xóa voice clone: {voice_id}")
        except Exception as exc:
            self.show_error(f"Không thể xóa voice clone: {exc}")

    def reset_voice_settings(self) -> None:
        self.speed_spin.setValue(1.0)
        self.pitch_spin.setValue(0)
        self.volume_spin.setValue(100)

    def browse_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục output", self.output_edit.text()
        )
        if folder:
            self.output_edit.setText(folder)

    def import_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import phụ đề hoặc văn bản", "", "Text (*.srt *.txt *.dat)"
        )
        self._import_paths([Path(path) for path in paths])

    def import_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục cần import")
        if folder:
            paths = sorted(
                item
                for item in Path(folder).iterdir()
                if item.is_file() and item.suffix.lower() in {".srt", ".txt", ".dat"}
            )
            self._import_paths(paths)

    def _import_paths(self, paths: list[Path]) -> None:
        count = 0
        for path in paths:
            try:
                segments = parse_file(path)
                for segment in segments:
                    self.add_segment(segment)
                    count += 1
                self.log(f"Đã import {len(segments)} dòng từ {path.name}.")
            except Exception as exc:
                self.log(f"Lỗi import {path.name}: {exc}")
        if paths and count == 0:
            self.show_error("Không tìm thấy nội dung hợp lệ để import.")

    def add_segment(self, segment: dict[str, Any]) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = [
            str(row + 1),
            str(segment.get("output", "")),
            str(segment.get("timing", "")),
            str(segment.get("content", "")),
            str(segment.get("voice", "")),
            str(segment.get("status", "WAITING")),
            str(segment.get("error", "")),
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column in {0, 5}:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if column == 6 and value:
                item.setToolTip(value)
            self.table.setItem(row, column, item)
        self._paint_status(row, values[5])

    def table_segments(self) -> list[dict[str, str]]:
        result = []
        for row in range(self.table.rowCount()):
            result.append(
                {
                    "id": self._cell(row, 0),
                    "output": self._cell(row, 1),
                    "timing": self._cell(row, 2),
                    "content": self._cell(row, 3),
                    "voice": self._cell(row, 4),
                    "status": self._cell(row, 5) or "WAITING",
                    "error": self._cell(row, 6),
                }
            )
        return result

    def _cell(self, row: int, column: int) -> str:
        item = self.table.item(row, column)
        return item.text() if item else ""

    def start_batch(self) -> None:
        if self.thread and self.thread.isRunning():
            return
        segments = self.table_segments()
        if not segments:
            self.show_error("Chưa có segment. Hãy import file trước.")
            return
        if self.engine_combo.currentData() == "piper" and not (
            self.voice_combo.currentData() or self.voice_combo.currentText()
        ):
            self.show_error("Chưa có Piper voice. Hãy Import Piper Model trước.")
            return
        if self.engine_combo.currentData() == "openvoice" and not (
            self.voice_combo.currentData() or self.voice_combo.currentText()
        ):
            self.show_error(
                "Chưa có voice mẫu. Hãy Import WAV/MP3 Voice trước."
            )
            return

        if self.engine_combo.currentData() == "xtts" and not (
            self.voice_combo.currentData() or self.voice_combo.currentText()
        ):
            self.show_error(
                "ChÆ°a cÃ³ voice máº«u XTTS. HÃ£y Import WAV/MP3 Voice trÆ°á»›c."
            )
            return
        if (
            self.engine_combo.currentData() == "xtts"
            and self.current_settings().get("language_code") == "vi"
        ):
            self.show_error(
                "XTTS Local hiá»‡n chÆ°a dÃ¹ng tá»‘t cho tiáº¿ng Viá»‡t trong app nÃ y. "
                "HÃ£y chuyá»ƒn sang English hoáº·c dÃ¹ng Local Voice Clone."
            )
            return

        output = self.output_edit.text().strip() or str(Path.cwd() / "output")
        self.output_edit.setText(output)
        self.thread = QThread(self)
        self.worker = BatchTTSWorker(segments, output, self.current_settings())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.row_status.connect(self.update_row_status)
        self.worker.log.connect(self.log)
        self.worker.finished.connect(self.batch_finished)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._thread_finished)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.statusBar().showMessage("Đang chạy batch...")
        self.thread.start()

    def stop_batch(self) -> None:
        if self.worker:
            self.worker.request_stop()
            self.stop_btn.setEnabled(False)
            self.log("Đang chờ segment hiện tại hoàn thành để dừng...")

    def update_row_status(
        self, row: int, status: str, output: str, error: str
    ) -> None:
        if not (0 <= row < self.table.rowCount()):
            return
        if output:
            self.table.setItem(row, 1, QTableWidgetItem(output))
        self.table.setItem(row, 5, QTableWidgetItem(status))
        error_item = QTableWidgetItem(error)
        error_item.setToolTip(error)
        self.table.setItem(row, 6, error_item)
        self._paint_status(row, status)
        self.table.scrollToItem(self.table.item(row, 3))

    def _paint_status(self, row: int, status: str) -> None:
        item = self.table.item(row, 5)
        if not item:
            return
        colors = {
            "WAITING": QColor("#666666"),
            "PROCESSING": QColor("#1565c0"),
            "DONE": QColor("#2e7d32"),
            "DONE_WITH_FALLBACK": QColor("#558b2f"),
            "SILENT_FALLBACK": QColor("#ef6c00"),
            "ERROR": QColor("#c62828"),
            "SKIPPED": QColor("#8d6e63"),
        }
        item.setForeground(colors.get(status, QColor("#000000")))

    def batch_finished(self, success: bool, message: str) -> None:
        self.statusBar().showMessage(message)
        if success:
            QMessageBox.information(self, "Hoàn thành", message)
        else:
            QMessageBox.warning(self, "Kết quả", message)

    def _thread_finished(self) -> None:
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.worker = None
        if self.thread:
            self.thread.deleteLater()
        self.thread = None

    def import_voice(self) -> None:
        voice, ok = QInputDialog.getText(
            self,
            "Import Voice",
            "Nhập mã Edge voice, ví dụ vi-VN-HoaiMyNeural hoặc en-US-GuyNeural:",
        )
        if not ok:
            return
        voice = voice.strip()
        if not voice:
            self.show_error("Tên voice đang trống.")
            return
        if "-" not in voice or not voice.endswith("Neural"):
            self.show_error(
                "Mã Edge voice không hợp lệ. Ví dụ: vi-VN-HoaiMyNeural "
                "hoặc en-US-GuyNeural."
            )
            return
        if self.voice_combo.findData(voice) < 0:
            self.voice_combo.addItem(voice, voice)
            self.voice_combo.setCurrentIndex(self.voice_combo.count() - 1)
        else:
            self.voice_combo.setCurrentIndex(self.voice_combo.findData(voice))
        self.log(f"Đã import voice: {voice}")

    def open_output(self) -> None:
        try:
            open_folder(self.output_edit.text().strip() or "output")
        except Exception as exc:
            self.show_error(str(exc))

    def join_mp3(self) -> None:
        try:
            target = join_mp3_files(self.output_edit.text().strip() or "output")
            self.log(f"Đã nối MP3: {target}")
            QMessageBox.information(self, "Hoàn thành", f"Đã tạo:\n{target}")
        except Exception as exc:
            self.show_error(str(exc))

    def clear_table(self) -> None:
        if self.thread and self.thread.isRunning():
            self.show_error("Hãy dừng batch trước khi xóa bảng.")
            return
        self.table.setRowCount(0)
        self.log("Đã xóa toàn bộ segment.")

    def save_project(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project", "project.json", "JSON (*.json)"
        )
        if not path:
            return
        data = {
            "app": "Dani-like Auto TTS Studio",
            "segments": self.table_segments(),
            "output_dir": self.output_edit.text(),
            "settings": self.current_settings(),
        }
        try:
            Path(path).write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self.log(f"Đã lưu project: {path}")
        except OSError as exc:
            self.show_error(f"Không thể lưu project: {exc}")

    def load_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Project", "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self.table.setRowCount(0)
            for segment in data.get("segments", []):
                self.add_segment(segment)
            self.output_edit.setText(data.get("output_dir", self.output_edit.text()))
            self._restore_settings(data.get("settings", {}))
            self.log(f"Đã load project: {path}")
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            self.show_error(f"Không thể load project: {exc}")

    def _restore_settings(self, settings: dict[str, Any]) -> None:
        engine = self.engine_combo.findData(settings.get("engine", "edge"))
        self.engine_combo.setCurrentIndex(max(0, engine))
        project_voice = str(settings.get("voice", ""))
        if project_voice and self.voice_combo.findData(project_voice) < 0:
            self.voice_combo.addItem(project_voice, project_voice)
        self.voice_combo.setCurrentText(project_voice or DEFAULT_EDGE_VOICES[0])
        language = self.language_combo.findText(str(settings.get("language", "Auto")))
        self.language_combo.setCurrentIndex(max(0, language))
        self.speed_spin.setValue(float(settings.get("speed", 1.0)))
        self.pitch_spin.setValue(int(settings.get("pitch", 0)))
        self.volume_spin.setValue(int(settings.get("volume", 100)))
        self.skip_done.setChecked(bool(settings.get("skip_done", False)))
        self.create_srt.setChecked(bool(settings.get("create_srt", False)))
        self.auto_join.setChecked(bool(settings.get("auto_join", False)))

    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.appendPlainText(f"[{timestamp}] {message}")

    def show_error(self, message: str) -> None:
        self.log(f"LỖI: {message}")
        QMessageBox.critical(self, "Lỗi", message)

    def closeEvent(self, event) -> None:
        if self.thread and self.thread.isRunning():
            answer = QMessageBox.question(
                self,
                "Đang chạy",
                "Batch đang chạy. Bạn muốn yêu cầu dừng và chờ đóng ứng dụng?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            if self.worker:
                self.worker.request_stop()
            self.thread.quit()
            self.thread.wait(5000)
        event.accept()
