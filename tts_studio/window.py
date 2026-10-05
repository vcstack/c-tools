from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QColor, QKeySequence
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
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ctool.vieneu import FALLBACK_VOICES, list_voice_catalog, resolve_voice
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
from tts_studio.worker import GenThread, GenWorker

_COLORS = {
    STATUS_DONE: QColor("#0a7a28"),
    STATUS_ERROR: QColor("#b00020"),
    STATUS_GEN: QColor("#8a6d00"),
    STATUS_STALE: QColor("#9a5b00"),
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("C-tool TTS — VieNeu")
        self.resize(1200, 740)
        self.project = TtsProject()
        self._selected: str | None = None
        self._thread: GenThread | None = None
        self._worker: GenWorker | None = None
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

    def _build(self, key: str, voice: str) -> None:
        bar = QToolBar("Main")
        bar.setMovable(False)
        self.addToolBar(bar)

        def btn(label: str, slot, shortcut: str | None = None) -> None:
            act = QAction(label, self)
            act.triggered.connect(slot)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            bar.addAction(act)

        btn("Mở JSON", self.open_json, "Ctrl+O")
        btn("Lưu JSON", self.save_json, "Ctrl+Shift+S")
        bar.addSeparator()
        btn("Gen câu này", lambda: self.start_gen("one"))
        btn("Gen từ đây", lambda: self.start_gen("from"))
        btn("Gen chưa xong", lambda: self.start_gen("pending"))
        btn("Dừng", self.stop_gen)
        bar.addSeparator()
        btn("Nghe", self.play_selected, "Ctrl+P")
        btn("Thư mục audio", self.open_audio_dir)

        bar.addSeparator()
        bar.addWidget(QLabel(" Giọng "))
        self.voice_box = QComboBox()
        self.voice_box.setEditable(True)
        self.voice_box.setMinimumWidth(180)
        self._fill_voices([(name, name) for name in FALLBACK_VOICES], voice)
        QTimer.singleShot(0, self.refresh_voices)
        bar.addWidget(self.voice_box)
        load_v = QPushButton("Tải giọng")
        load_v.clicked.connect(self.refresh_voices)
        bar.addWidget(load_v)
        bar.addWidget(QLabel("  API "))
        self.api_edit = QLineEdit(key)
        self.api_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_edit.setMinimumWidth(220)
        bar.addWidget(self.api_edit)
        save_k = QPushButton("Lưu key")
        save_k.clicked.connect(self.save_key)
        bar.addWidget(save_k)

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(bar.actions()[0])
        file_menu.addAction(bar.actions()[1])

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
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)

        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(split)
        self.setCentralWidget(wrap)

        self.setStatusBar(QStatusBar())
        save_act = QAction(self)
        save_act.setShortcut(QKeySequence.StandardKey.Save)
        save_act.triggered.connect(lambda: self.save_editor())
        self.addAction(save_act)

    def _set_status(self, text: str) -> None:
        self.statusBar().showMessage(text)

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
        return resolve_voice(text or "Ngọc Lan")

    def save_key(self) -> None:
        try:
            vid = self._selected_voice_id()
        except ValueError:
            vid = self.voice_box.currentText().strip()
        save_prefs(self.api_edit.text().strip(), vid)
        self._set_status("Đã lưu API key.")

    def refresh_voices(self) -> None:
        token = ""
        if self.voice_box.count():
            data = self.voice_box.currentData()
            token = data.strip() if isinstance(data, str) and data.strip() else self.voice_box.currentText().strip()
        try:
            choices = list_voice_catalog(self.api_edit.text().strip())
        except Exception as exc:
            QMessageBox.critical(self, "VieNeu", str(exc))
            return
        if not choices:
            choices = [(name, name) for name in FALLBACK_VOICES]
        self._fill_voices(choices, token)
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
            self.refresh_table()
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
            QMessageBox.information(self, "TTS", "Đang gen. Bấm Dừng nếu muốn.")
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
        worker.progressed.connect(self._on_progress)
        worker.failed.connect(self._on_fail)
        worker.need_key.connect(self._on_need_key, Qt.ConnectionType.QueuedConnection)
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

    def stop_gen(self) -> None:
        if self._worker:
            self._worker.cancel()

    def _on_progress(self, _sid: str) -> None:
        self.refresh_table()
        self._counts()

    def _on_need_key(self, sid: str, msg: str) -> None:
        self.refresh_table()
        self._select_sid(sid)
        self._set_status(f"{sid}: hết hạn mức token. Câu đã gen vẫn giữ.")
        text, ok = QInputDialog.getText(
            self,
            "VieNeu hết hạn mức",
            f"Câu {sid} dừng vì token hết hạn hoặc hết hạn mức.\n"
            "Dán API key mới để chạy tiếp từ câu này. Không gen lại câu đã xong.\n\n"
            f"{msg[:280]}",
            QLineEdit.EchoMode.Password,
        )
        key = text.strip() if ok else ""
        if not self._worker:
            return
        if not key:
            self._worker.supply_key(None)
            return
        self.api_edit.setText(key)
        save_prefs(key, self.voice_box.currentText().strip())
        self._set_status(f"Đổi key, chạy tiếp từ {sid}.")
        self._worker.supply_key(key)

    def _on_fail(self, sid: str, msg: str) -> None:
        self.refresh_table()
        self._counts()
        self._set_status(f"Lỗi {sid}: {msg[:180]} — câu trước đó đã lưu.")

    def _on_stopped(self) -> None:
        self.refresh_table()
        self._counts()
        self._set_status("Đã dừng. Câu đã gen được giữ. Dán key mới rồi bấm Gen chưa xong.")

    def _on_done(self) -> None:
        self.refresh_table()
        self._counts()
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

    def play_selected(self) -> None:
        if not self._selected:
            return
        audio = self.project.audio_of(self._selected)
        if not audio:
            QMessageBox.information(self, "Nghe", "Câu này chưa có file audio.")
            return
        if self._player is not None:
            self._player.setSource(QUrl.fromLocalFile(str(audio)))
            self._player.play()
            return
        try:
            os.startfile(audio)  # type: ignore[attr-defined]
        except AttributeError:
            subprocess.Popen(["xdg-open", str(audio)])

    def open_audio_dir(self) -> None:
        if not self.project.json_path:
            return
        folder = audio_dir(self.project.json_path)
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)  # type: ignore[attr-defined]

    def closeEvent(self, event: QCloseEvent) -> None:
        self.stop_gen()
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
