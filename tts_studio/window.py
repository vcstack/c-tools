from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QColor, QIcon, QKeySequence, QPainter, QPen, QPixmap, QPolygon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ctool.vieneu import FALLBACK_VOICES
from tts_studio.project import (
    STATUS_DONE,
    STATUS_ERROR,
    STATUS_GEN,
    STATUS_STALE,
    TtsProject,
    audio_dir,
    load_prefs,
    save_prefs,
)
from tts_studio.stt_panel import SttPanel
from tts_studio.worker import GenThread, GenWorker, MergeThread, VoiceCatalogThread

_COLORS = {
    STATUS_DONE: QColor("#0a7a28"),
    STATUS_ERROR: QColor("#b00020"),
    STATUS_GEN: QColor("#8a6d00"),
    STATUS_STALE: QColor("#9a5b00"),
}


def _icon(kind: str) -> QIcon:
    pix = QPixmap(20, 20)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    color = QColor("#1a1a1a")
    pen = QPen(color)
    pen.setWidthF(1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(color)

    def poly(*pts: tuple[int, int]) -> None:
        painter.drawPolygon(QPolygon([QPoint(x, y) for x, y in pts]))

    if kind == "open":
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(3, 8, 8, 8)
        painter.drawLine(8, 8, 10, 6)
        painter.drawLine(10, 6, 17, 6)
        painter.drawRect(3, 8, 14, 8)
    elif kind == "save":
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(3, 2, 14, 16)
        painter.fillRect(7, 3, 6, 4, color)
        painter.drawRect(6, 11, 8, 5)
    elif kind == "gen":
        poly((5, 3), (16, 10), (5, 17))
    elif kind == "gen_from":
        painter.drawLine(3, 3, 3, 17)
        poly((7, 3), (17, 10), (7, 17))
    elif kind == "gen_rest":
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(3, 5, 11, 5)
        painter.drawLine(3, 10, 11, 10)
        painter.drawLine(3, 15, 9, 15)
        poly((11, 12), (17, 15), (11, 18))
    elif kind == "stop":
        painter.drawRoundedRect(5, 5, 10, 10, 1, 1)
    elif kind == "merge":
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(2, 4, 8, 4)
        painter.drawLine(2, 10, 8, 10)
        painter.drawLine(2, 16, 8, 16)
        painter.drawLine(8, 10, 13, 10)
        poly((12, 7), (18, 10), (12, 13))
    elif kind == "play":
        poly((6, 3), (16, 10), (6, 17))
    elif kind == "pause":
        painter.drawRoundedRect(5, 4, 3, 12, 1, 1)
        painter.drawRoundedRect(12, 4, 3, 12, 1, 1)
    elif kind == "final":
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(3, 3, 9, 14)
        poly((8, 7), (16, 10), (8, 13))
    elif kind == "folder":
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(3, 8, 8, 8)
        painter.drawLine(8, 8, 10, 6)
        painter.drawLine(10, 6, 17, 6)
        painter.drawRect(3, 8, 14, 8)
    elif kind == "refresh":
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(4, 4, 12, 12, 40 * 16, 250 * 16)
        poly((14, 3), (18, 6), (13, 8))
    elif kind == "key":
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(3, 6, 7, 7)
        painter.drawLine(10, 9, 17, 9)
        painter.drawLine(14, 9, 14, 12)
        painter.drawLine(17, 9, 17, 12)
    painter.end()
    return QIcon(pix)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("C-tool TTS — VieNeu")
        self.resize(1200, 740)
        self.project = TtsProject()
        self._selected: str | None = None
        self._thread: GenThread | None = None
        self._worker: GenWorker | None = None
        self._merge_thread: MergeThread | None = None
        self._voice_thread: VoiceCatalogThread | None = None
        self._player = None
        self._audio_out = None
        self._init_player()

        key, voice = load_prefs()
        self.project.voice = voice

        self._build(key, voice)
        self._set_status("Mở JSON kịch bản (segments[].text).")

    def _init_player(self) -> None:
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

            self._player = QMediaPlayer(self)
            self._audio_out = QAudioOutput(self)
            self._player.setAudioOutput(self._audio_out)
        except Exception:
            self._player = None
            self._audio_out = None

    def _act(self, text: str, slot, kind: str, shortcut: str | None = None) -> QAction:
        act = QAction(_icon(kind), text, self)
        act.setToolTip(text)
        act.setStatusTip(text)
        act.triggered.connect(slot)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        return act

    def _build(self, key: str, voice: str) -> None:
        self.api_edit = QLineEdit(key)
        self.api_edit.setEchoMode(QLineEdit.EchoMode.Password)

        open_act = self._act("Mở JSON", self.open_json, "open", "Ctrl+O")
        save_act = self._act("Lưu JSON", self.save_json, "save", "Ctrl+Shift+S")
        folder_act = self._act("Thư mục audio", self.open_audio_dir, "folder")
        key_act = self._act("API key…", self.edit_api_key, "key")
        gen_one = self._act("Gen câu này", lambda: self.start_gen("one"), "gen")
        gen_from = self._act("Gen từ đây", lambda: self.start_gen("from"), "gen_from")
        gen_rest = self._act("Gen chưa xong", lambda: self.start_gen("pending"), "gen_rest")
        stop_act = self._act("Dừng", self.stop_gen, "stop")
        merge_act = self._act("Ghép file", self.start_merge, "merge")
        self._play_act = self._act("Phát câu này", self.play_selected, "play", "Ctrl+P")
        self._pause_act = self._act("Tạm dừng", self.toggle_pause, "pause")
        self._stop_listen_act = self._act("Dừng nghe", self.stop_audio, "stop")
        self._final_act = self._act("Nghe file ghép", self.play_final, "final")
        refresh_act = self._act("Tải giọng", self.refresh_voices, "refresh")

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(open_act)
        file_menu.addAction(save_act)
        file_menu.addAction(folder_act)
        file_menu.addSeparator()
        file_menu.addAction(key_act)

        gen_menu = self.menuBar().addMenu("Gen")
        gen_menu.addAction(gen_one)
        gen_menu.addAction(gen_from)
        gen_menu.addAction(gen_rest)
        gen_menu.addSeparator()
        gen_menu.addAction(stop_act)
        gen_menu.addAction(merge_act)

        listen_menu = self.menuBar().addMenu("Nghe")
        listen_menu.addAction(self._play_act)
        listen_menu.addAction(self._pause_act)
        listen_menu.addAction(self._stop_listen_act)
        listen_menu.addSeparator()
        listen_menu.addAction(self._final_act)

        bar = QToolBar("Main")
        bar.setMovable(False)
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        bar.setIconSize(QSize(20, 20))
        self.addToolBar(bar)
        for act in (open_act, save_act):
            bar.addAction(act)
        bar.addSeparator()
        for act in (gen_one, gen_from, gen_rest, stop_act, merge_act):
            bar.addAction(act)
        bar.addSeparator()
        bar.addAction(self._play_act)
        bar.addSeparator()
        self.voice_box = QComboBox()
        self.voice_box.setEditable(True)
        self.voice_box.setCompleter(None)
        self.voice_box.setMinimumWidth(160)
        self.voice_box.setToolTip("Giọng")
        self._fill_voices([(name, name) for name in FALLBACK_VOICES], voice)
        QTimer.singleShot(0, self.refresh_voices)
        bar.addWidget(self.voice_box)
        bar.addAction(refresh_act)

        split = QSplitter(Qt.Orientation.Vertical)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["#", "Status", "ID", "Speaker", "Text"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_select)
        self.table.itemDoubleClicked.connect(self._on_double_click)
        split.addWidget(self.table)

        edit_box = QWidget()
        ev = QVBoxLayout(edit_box)
        ev.setContentsMargins(8, 8, 8, 4)
        ev.addWidget(QLabel("Sửa câu đang chọn — Ctrl+S lưu text"))
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Chọn một câu trên bảng…")
        ev.addWidget(self.editor)
        row = QHBoxLayout()
        save_t = QPushButton("Lưu text câu này")
        save_t.clicked.connect(lambda: self.save_editor())
        gen_t = QPushButton("Gen lại câu này")
        gen_t.clicked.connect(lambda: self.start_gen("one"))
        row.addWidget(save_t)
        row.addWidget(gen_t)
        row.addStretch()
        ev.addLayout(row)
        split.addWidget(edit_box)
        split.addWidget(self._build_player())

        log_box = QWidget()
        lv = QVBoxLayout(log_box)
        lv.setContentsMargins(8, 4, 8, 4)
        lv.addWidget(QLabel("Log"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        self.log.setPlaceholderText("Trạng thái gen hiện ở đây…")
        self.log.setMinimumHeight(90)
        lv.addWidget(self.log)
        split.addWidget(log_box)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setStretchFactor(2, 0)
        split.setStretchFactor(3, 1)

        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(split)
        self._tabs = QTabWidget()
        self._tabs.addTab(wrap, "TTS")
        self.setStatusBar(QStatusBar())
        self.stt_panel = SttPanel(self._open_from_stt, self._stt_status)
        self._tabs.addTab(self.stt_panel, "STT")
        self.setCentralWidget(self._tabs)
        save_act = QAction(self)
        save_act.setShortcut(QKeySequence.StandardKey.Save)
        save_act.triggered.connect(lambda: self.save_editor())
        self.addAction(save_act)

    def _stt_status(self, text: str) -> None:
        self.statusBar().showMessage(text)

    def _open_from_stt(self, path: Path) -> None:
        self._tabs.setCurrentIndex(0)
        self._load(path)

    def _build_player(self) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(8, 4, 8, 4)
        row = QHBoxLayout()
        for act in (self._play_act, self._pause_act, self._stop_listen_act, self._final_act):
            button = QToolButton()
            button.setDefaultAction(act)
            button.setAutoRaise(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setIconSize(QSize(20, 20))
            row.addWidget(button)
        self.play_label = QLabel("Chưa phát")
        row.addWidget(self.play_label, 1)
        lay.addLayout(row)
        seek_row = QHBoxLayout()
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderPressed.connect(self._on_seek_press)
        self.seek.sliderReleased.connect(self._on_seek_release)
        self.time_label = QLabel("00:00 / 00:00")
        seek_row.addWidget(self.seek, 1)
        seek_row.addWidget(self.time_label)
        lay.addLayout(seek_row)
        self._scrubbing = False
        if self._player is not None:
            self._player.positionChanged.connect(self._on_pos)
            self._player.durationChanged.connect(self._on_dur)
        return box

    def _set_status(self, text: str) -> None:
        self.statusBar().showMessage(text)
        self._log(text)

    def _log(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self.log.appendPlainText(f"{datetime.now():%H:%M:%S}  {text}")
        bar = self.log.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _counts(self) -> None:
        done, err, n = self.project.counts()
        name = self.project.json_path.name if self.project.json_path else ""
        self._set_status(f"{name} — {done}/{n} xong · {err} lỗi")

    def _fill_voices(self, choices: list[tuple[str, str]], token: str) -> None:
        self.voice_box.blockSignals(True)
        self.voice_box.clear()
        for vid, label in choices:
            self.voice_box.addItem(label or vid, vid)
        self._select_voice(token)
        self.voice_box.blockSignals(False)

    def _select_voice(self, token: str) -> None:
        token = (token or "").strip()
        if not token:
            if self.voice_box.count():
                self.voice_box.setCurrentIndex(0)
            return
        for i in range(self.voice_box.count()):
            if self.voice_box.itemData(i) == token:
                self.voice_box.setCurrentIndex(i)
                return
        idx = self.voice_box.findText(token)
        if idx >= 0:
            self.voice_box.setCurrentIndex(idx)
            return
        self.voice_box.setEditText(token)

    def _selected_voice_id(self) -> str:
        text = self.voice_box.currentText().strip()
        idx = self.voice_box.findText(text)
        if idx >= 0:
            data = self.voice_box.itemData(idx)
            if isinstance(data, str) and data.strip():
                return data.strip()
        return text or "Ngọc Lan"

    def edit_api_key(self) -> None:
        text, ok = QInputDialog.getText(
            self,
            "API key VieNeu",
            "API key",
            QLineEdit.EchoMode.Password,
            self.api_edit.text(),
        )
        if not ok:
            return
        key = text.strip()
        if not key:
            self._set_status("Key trống — không đổi key đã lưu.")
            return
        self.api_edit.setText(key)
        self.save_key()

    def save_key(self) -> None:
        try:
            vid = self._selected_voice_id()
        except ValueError:
            vid = self.voice_box.currentText().strip()
        save_prefs(self.api_edit.text().strip(), vid)
        self._set_status("Đã lưu API key.")

    def refresh_voices(self) -> None:
        if self._voice_thread and self._voice_thread.isRunning():
            return
        data = self.voice_box.currentData()
        token = data.strip() if isinstance(data, str) and data.strip() else self.voice_box.currentText().strip()
        self._voice_token = token
        self._set_status("Đang tải danh sách giọng…")
        thread = VoiceCatalogThread(self.api_edit.text().strip())
        thread.loaded.connect(self._on_voices)
        self._voice_thread = thread
        thread.start()

    def _on_voices(self, payload: object) -> None:
        if isinstance(payload, Exception):
            QMessageBox.critical(self, "VieNeu", str(payload))
            return
        choices = list(payload) if payload else [(name, name) for name in FALLBACK_VOICES]
        self.voice_box.setUpdatesEnabled(False)
        self._fill_voices(choices, getattr(self, "_voice_token", ""))
        self.voice_box.setUpdatesEnabled(True)
        self._set_status(f"Giọng V4: {len(choices)}")

    def open_json(self) -> None:
        start = str(Path(__file__).resolve().parents[1] / "kich-ban")
        path, _ = QFileDialog.getOpenFileName(
            self, "Mở kịch bản JSON", start, "JSON (*.json);;All (*.*)"
        )
        if path:
            self._load(Path(path))

    def _load(self, path: Path) -> None:
        try:
            self.project.load(path)
        except Exception as exc:
            QMessageBox.critical(self, "JSON", str(exc))
            return
        if self.project.voice:
            self._select_voice(self.project.voice)
        self.setWindowTitle(f"C-tool TTS — {path.name}")
        self.refresh_table()
        self._counts()
        ids = self.project.ids()
        if ids:
            self._select_sid(ids[0])

    def refresh_table(self) -> None:
        keep = self._selected
        self.table.blockSignals(True)
        segs = self.project.segments()
        self.table.setRowCount(len(segs))
        for i, seg in enumerate(segs):
            sid = str(seg["id"])
            status = self.project.status_of(sid)
            preview = (seg.get("text") or "").replace("\n", " ")
            if len(preview) > 140:
                preview = preview[:137] + "..."
            vals = [str(i + 1), status, sid, str(seg.get("speaker") or ""), preview]
            color = _COLORS.get(status)
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                if color and col == 1:
                    item.setForeground(color)
                self.table.setItem(i, col, item)
        self.table.blockSignals(False)
        if keep:
            self._select_sid(keep, fill_editor=False)

    def _row_of(self, sid: str) -> int:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 2)
            if item and item.text() == sid:
                return row
        return -1

    def _select_sid(self, sid: str, fill_editor: bool = True) -> None:
        row = self._row_of(sid)
        if row < 0:
            return
        self.table.selectRow(row)
        self.table.scrollToItem(self.table.item(row, 0))
        if fill_editor:
            self._fill_editor(sid)

    def _on_select(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        sid_item = self.table.item(rows[0].row(), 2)
        if not sid_item:
            return
        sid = sid_item.text()
        if self._selected and self._selected != sid:
            self.save_editor(silent=True)
        self._selected = sid
        self._fill_editor(sid)
        err = self.project.error_of(sid)
        if err and self.project.status_of(sid) == STATUS_ERROR:
            self._set_status(f"{sid}: {err[:180]}")

    def _fill_editor(self, sid: str) -> None:
        seg = self.project.segment(sid)
        self.editor.blockSignals(True)
        self.editor.setPlainText((seg or {}).get("text") or "")
        self.editor.blockSignals(False)

    def save_editor(self, silent: bool = False) -> None:
        if not self._selected or not self.project.json_path:
            return
        if self.project.set_text(self._selected, self.editor.toPlainText()):
            self._paint_row(self._selected)
            row = self._row_of(self._selected)
            preview_item = self.table.item(row, 4) if row >= 0 else None
            if preview_item is not None:
                preview = self.editor.toPlainText().replace("\n", " ")
                if len(preview) > 140:
                    preview = preview[:137] + "..."
                preview_item.setText(preview)
            if not silent:
                self._set_status(f"Đã lưu text {self._selected}.")

    def save_json(self) -> None:
        try:
            self.save_editor(silent=True)
            self.project.save_json()
            self.project.flush_state()
        except Exception as exc:
            QMessageBox.information(self, "JSON", str(exc))
            return
        if self.project.json_path:
            self._set_status(f"Đã ghi {self.project.json_path.name}")

    def start_gen(self, mode: str) -> None:
        if self._thread and self._thread.isRunning():
            self._set_status("Đang gen. Bấm Dừng nếu muốn chạy lại.")
            return
        if not self.project.json_path:
            QMessageBox.warning(self, "TTS", "Mở JSON trước.")
            return
        key = self.api_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "TTS", "Thiếu API key VieNeu.")
            return
        self.save_editor(silent=True)
        label = self.voice_box.currentText().strip() or "Ngọc Lan"
        try:
            voice = self._selected_voice_id()
        except ValueError as exc:
            QMessageBox.warning(self, "Giọng", str(exc))
            return
        self.project.voice = voice
        todo = self.project.todo(mode, self._selected)
        if not todo:
            merged = self.project.merge_final()
            if merged:
                self._set_status(f"Đủ câu. Đã ghép {merged.name}")
            elif self.project.final_error:
                self._set_status(self.project.final_error)
            else:
                self._set_status("Không còn câu cần gen.")
            return
        worker = GenWorker(self.project, key, voice, todo)
        thread = GenThread(worker)
        worker.busy.connect(self._on_busy)
        worker.progressed.connect(self._on_progress)
        worker.failed.connect(self._on_fail)
        worker.stopped.connect(self._on_stopped)
        worker.finished.connect(self._on_done)
        worker.failed.connect(thread.quit)
        worker.stopped.connect(thread.quit)
        worker.finished.connect(thread.quit)
        thread.finished.connect(self._clear_thread)
        self._worker = worker
        self._thread = thread
        thread.start()
        self._set_status(f"Gen {len(todo)} câu · {label}.")

    def start_merge(self) -> None:
        if not self.project.json_path:
            self._set_status("Mở JSON trước.")
            return
        if self._thread and self._thread.isRunning():
            self._set_status("Đang gen, bấm Ghép file sau khi dừng hoặc xong.")
            return
        if self._merge_thread and self._merge_thread.isRunning():
            self._set_status("Đang ghép.")
            return
        self._set_status("Đang ghép từ câu đầu…")
        thread = MergeThread(self.project)
        thread.finished_merge.connect(self._on_merged)
        thread.finished.connect(self._clear_merge)
        self._merge_thread = thread
        thread.start()

    def _on_merged(self, path: object, note: str) -> None:
        self._set_status(note)

    def _clear_merge(self) -> None:
        self._merge_thread = None

    def stop_gen(self) -> None:
        if self._worker:
            self._worker.cancel()

    def _paint_row(self, sid: str) -> None:
        row = self._row_of(sid)
        if row < 0:
            return
        status = self.project.status_of(sid)
        item = self.table.item(row, 1)
        if item is None:
            return
        item.setText(status)
        color = _COLORS.get(status)
        if color:
            item.setForeground(color)

    def _on_busy(self, sid: str) -> None:
        if self.project.status_of(sid) == STATUS_ERROR:
            self._paint_row(sid)
            return
        self._paint_row(sid)
        done, _err, n = self.project.counts()
        self._set_status(f"Đang gen {sid} · {done}/{n}")

    def _on_progress(self, sid: str) -> None:
        self._paint_row(sid)
        done, err, n = self.project.counts()
        name = self.project.json_path.name if self.project.json_path else ""
        self.statusBar().showMessage(f"{name} — {done}/{n} xong · {err} lỗi")
        self._log(f"Xong {sid} · {done}/{n}")

    def _on_fail(self, sid: str, msg: str) -> None:
        self._paint_row(sid)
        done, err, n = self.project.counts()
        name = self.project.json_path.name if self.project.json_path else ""
        self.statusBar().showMessage(f"{name} — {done}/{n} xong · {err} lỗi")
        self._log(f"Lỗi {sid}: {msg} — câu trước đó đã lưu.")

    def _on_stopped(self) -> None:
        self._set_status("Đã dừng. Câu đã gen được giữ.")

    def _on_done(self) -> None:
        done, _err, n = self.project.counts()
        if self.project.merged_now and self.project.merged_now.is_file():
            self._set_status(f"Đủ câu. Đã ghép {self.project.merged_now.name}")
        elif self.project.final_error:
            self._set_status(self.project.final_error)
        else:
            self._set_status(f"Xong phần này ({done}/{n}). Câu đã gen được giữ, chưa ghép final.")

    def _clear_thread(self) -> None:
        self._thread = None
        self._worker = None

    def _on_double_click(self, item: QTableWidgetItem) -> None:
        sid_item = self.table.item(item.row(), 2)
        if sid_item:
            self._selected = sid_item.text()
        self.play_selected()

    def _fmt_ms(self, ms: int) -> str:
        sec = max(0, ms) // 1000
        return f"{sec // 60:02d}:{sec % 60:02d}"

    def _play_path(self, audio: Path, caption: str) -> None:
        self.play_label.setText(caption)
        self._log(f"Nghe {caption}")
        if self._player is not None:
            self._player.setSource(QUrl.fromLocalFile(str(audio)))
            self._player.play()
            return
        try:
            os.startfile(audio)  # type: ignore[attr-defined]
        except AttributeError:
            subprocess.Popen(["xdg-open", str(audio)])

    def play_selected(self) -> None:
        if not self._selected:
            self._set_status("Chọn một câu trên bảng để nghe.")
            return
        audio = self.project.audio_of(self._selected)
        if not audio:
            QMessageBox.information(self, "Nghe", "Câu này chưa có file audio.")
            return
        self._play_path(audio, f"{self._selected} · {audio.name}")

    def play_final(self) -> None:
        path = self.project.final_file()
        if path and not path.is_file():
            wav = path.with_suffix(".wav")
            path = wav if wav.is_file() else None
        if not path or not path.is_file():
            QMessageBox.information(self, "Nghe", "Chưa có file ghép. Gen đủ mọi câu thì mới có file .final.mp3.")
            return
        self._play_path(path, path.name)

    def toggle_pause(self) -> None:
        if self._player is None:
            return
        from PySide6.QtMultimedia import QMediaPlayer

        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PausedState:
            self._player.play()
            return
        self.play_selected()

    def stop_audio(self) -> None:
        if self._player is not None:
            self._player.stop()
        self.play_label.setText("Đã dừng")

    def _on_seek_press(self) -> None:
        self._scrubbing = True

    def _on_seek_release(self) -> None:
        self._scrubbing = False
        if self._player is not None:
            self._player.setPosition(self.seek.value())

    def _on_pos(self, pos: int) -> None:
        if not self._scrubbing:
            self.seek.setValue(pos)
        self.time_label.setText(f"{self._fmt_ms(pos)} / {self._fmt_ms(self.seek.maximum())}")

    def _on_dur(self, dur: int) -> None:
        self.seek.setRange(0, max(0, dur))
        self.time_label.setText(f"{self._fmt_ms(self._player.position() if self._player else 0)} / {self._fmt_ms(dur)}")

    def open_audio_dir(self) -> None:
        if not self.project.json_path:
            return
        folder = audio_dir(self.project.json_path)
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)  # type: ignore[attr-defined]

    def closeEvent(self, event: QCloseEvent) -> None:
        self.stop_gen()
        if getattr(self, "stt_panel", None):
            self.stt_panel.stop()
        if self.project.json_path:
            self.save_editor(silent=True)
            self.project.flush_state()
        event.accept()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    app = QApplication(sys.argv)
    app.setApplicationName("C-tool TTS")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
