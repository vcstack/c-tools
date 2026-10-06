"""Tab STT: file/URL → whisper-jax + diarization → JSON, chạy ngoài luồng UI."""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

_STEP_RE = re.compile(r"\[(\d+)/(\d+)\]\s*(.+)")
_CHUNK_RE = re.compile(r"chunk\s+(\d+)/(\d+)", re.IGNORECASE)
_PARTS_RE = re.compile(r"STT in (\d+) parts", re.IGNORECASE)

_ROOT = Path(__file__).resolve().parents[1]
_CREATE_NO_WINDOW = 0x08000000
_MODELS = ("tiny", "base", "small", "medium", "large-v2", "large-v3")


def _hide_console(args) -> None:
    flags = int(getattr(args, "flags", 0) or 0)
    args.flags = flags | _CREATE_NO_WINDOW


class SttPanel(QWidget):
    def __init__(self, on_open_json, on_status) -> None:
        super().__init__()
        self._on_open_json = on_open_json
        self._on_status = on_status
        self._out_touched = False
        self._proc = QProcess(self)
        self._proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._proc.setWorkingDirectory(str(_ROOT))
        self._proc.readyReadStandardOutput.connect(self._on_output)
        self._proc.finished.connect(self._on_finished)
        self._proc.errorOccurred.connect(self._on_error)
        if sys.platform == "win32" and hasattr(self._proc, "setCreateProcessArgumentsModifier"):
            self._proc.setCreateProcessArgumentsModifier(_hide_console)
        self._build()
        self._load_token()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)

        self.source = QLineEdit()
        self.source.setPlaceholderText("File audio/video hoặc URL YouTube")
        self.output = QLineEdit()
        self.output.setPlaceholderText("File JSON kết quả")
        self.output.textEdited.connect(self._mark_output)

        form = QFormLayout()
        form.addRow("Nguồn", self._browse_row(self.source, self._pick_source))
        form.addRow("JSON ra", self._browse_row(self.output, self._pick_output))

        self.model = QComboBox()
        self.model.addItems(_MODELS)
        self.model.setCurrentText("large-v2")
        self.language = QComboBox()
        self.language.addItem("Tự nhận", "")
        self.language.addItem("Tiếng Việt", "vi")
        self.language.addItem("English", "en")
        self.language.setCurrentIndex(1)
        self.device = QComboBox()
        self.device.addItems(["auto", "cpu", "cuda"])
        self.max_speakers = QSpinBox()
        self.max_speakers.setRange(1, 10)
        self.max_speakers.setValue(1)
        self.batch = QSpinBox()
        self.batch.setRange(1, 16)
        self.batch.setValue(4)
        self.chunk = QCheckBox("Chia file dài để đỡ tốn RAM")
        self.chunk.setChecked(True)

        opts = QHBoxLayout()
        opts.addWidget(QLabel("Model"))
        opts.addWidget(self.model)
        opts.addWidget(QLabel("Ngôn ngữ"))
        opts.addWidget(self.language)
        opts.addWidget(QLabel("Thiết bị"))
        opts.addWidget(self.device)
        opts.addWidget(QLabel("Speaker"))
        opts.addWidget(self.max_speakers)
        opts.addWidget(QLabel("Batch"))
        opts.addWidget(self.batch)
        opts.addStretch()

        self.hf = QLineEdit()
        self.hf.setEchoMode(QLineEdit.EchoMode.Password)
        self.hf.setPlaceholderText("Chỉ cần khi speaker > 1 (pyannote)")

        row = QHBoxLayout()
        self.run_btn = QPushButton("Chạy STT")
        self.run_btn.clicked.connect(self.start)
        self.stop_btn = QPushButton("Dừng")
        self.stop_btn.clicked.connect(self.stop)
        self.stop_btn.setEnabled(False)
        self.open_btn = QPushButton("Mở ở tab TTS")
        self.open_btn.clicked.connect(self.open_in_tts)
        row.addWidget(self.run_btn)
        row.addWidget(self.stop_btn)
        row.addWidget(self.open_btn)
        row.addStretch()

        self.task_label = QLabel("Chưa chạy")
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(16)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(4000)
        self.log.setPlaceholderText("Log whisper-jax hiện ở đây…")

        lay.addLayout(form)
        lay.addLayout(opts)
        lay.addWidget(self.chunk)
        lay.addWidget(QLabel("HF token"))
        lay.addWidget(self.hf)
        lay.addLayout(row)
        lay.addWidget(self.task_label)
        lay.addWidget(self.progress)
        lay.addWidget(self.log, 1)

    def _browse_row(self, edit: QLineEdit, slot) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        button = QPushButton("…")
        button.setFixedWidth(32)
        button.clicked.connect(slot)
        row.addWidget(edit, 1)
        row.addWidget(button)
        return box

    def _load_token(self) -> None:
        token = ""
        try:
            from ctool.settings import load_settings

            token = (load_settings().get("hf_token") or "").strip()
        except Exception:
            token = ""
        if not token:
            import os

            token = (os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN") or "").strip()
        if token:
            self.hf.setText(token)

    def _mark_output(self) -> None:
        self._out_touched = True

    def _pick_source(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn audio hoặc video",
            str(_ROOT),
            "Media (*.mp3 *.wav *.m4a *.mp4 *.mkv *.webm *.flac *.ogg);;All (*.*)",
        )
        if not path:
            return
        self.source.setText(path)
        if not self._out_touched:
            self.output.setText(str(_suggest_output(path)))

    def _pick_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "JSON kết quả",
            self.output.text().strip() or str(_ROOT / "output" / "transcript.json"),
            "JSON (*.json)",
        )
        if path:
            self.output.setText(path)
            self._out_touched = True

    def _append(self, text: str) -> None:
        text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            return
        for line in text.split("\n"):
            line = line.strip()
            if line:
                self.log.appendPlainText(line)
                self._touch_task(line)
        bar = self.log.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _note(self, text: str) -> None:
        self._append(f"{datetime.now():%H:%M:%S}  {text}")
        if self._on_status:
            self._on_status(text)

    def running(self) -> bool:
        return self._proc.state() != QProcess.ProcessState.NotRunning

    def start(self) -> None:
        if self.running():
            self._note("STT đang chạy.")
            return
        source = self.source.text().strip()
        if not source:
            self._note("Chọn file hoặc dán URL.")
            return
        if not _is_url(source) and not Path(source).is_file():
            self._note("Không thấy file nguồn.")
            return
        if not self.output.text().strip():
            self.output.setText(str(_suggest_output(source)))
        out = Path(self.output.text().strip())
        if out.suffix.lower() != ".json":
            out = out.with_suffix(".json")
            self.output.setText(str(out))
        speakers = int(self.max_speakers.value())
        token = self.hf.text().strip()
        if speakers > 1 and not token:
            self._note("Speaker > 1 cần HF token (pyannote).")
            return
        out.parent.mkdir(parents=True, exist_ok=True)
        if token:
            try:
                from ctool.settings import save_settings

                save_settings(hf_token=token)
            except Exception as exc:
                self._append(f"Không lưu được HF token: {exc}")

        args = [
            str(_ROOT / "main.py"),
            "--input",
            source,
            "--output",
            str(out),
            "--model",
            self.model.currentText(),
            "--device",
            self.device.currentText(),
            "--batch-size",
            str(int(self.batch.value())),
            "--min-speakers",
            "1",
            "--max-speakers",
            str(speakers),
            "--work-dir",
            str(_ROOT / ".cache" / "pipeline"),
        ]
        lang = self.language.currentData()
        if isinstance(lang, str) and lang.strip():
            args.extend(["--language", lang.strip()])
        if speakers <= 1:
            args.extend(["--diarization-model", "disable"])
        if self.chunk.isChecked():
            args.append("--auto-chunk")

        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("MPLBACKEND", "Agg")
        if token:
            env.insert("HF_TOKEN", token)
            env.insert("HUGGING_FACE_HUB_TOKEN", token)
        self._proc.setProcessEnvironment(env)
        self.log.clear()
        self._set_busy(True, "Đang chạy STT")
        self._note(f"Chạy STT → {out.name}")
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._proc.start(sys.executable, args)

    def stop(self) -> None:
        if not self.running():
            return
        self._note("Đang dừng STT…")
        self._proc.terminate()
        if not self._proc.waitForFinished(3000):
            self._proc.kill()

    def open_in_tts(self) -> None:
        raw = self.output.text().strip()
        if not raw or not Path(raw).is_file():
            self._note("Chưa có file JSON.")
            return
        self._on_open_json(Path(raw))

    def _on_output(self) -> None:
        data = bytes(self._proc.readAllStandardOutput())
        text = data.decode("utf-8", errors="replace")
        self._append(text)

    def _on_error(self, err) -> None:
        if err != QProcess.ProcessError.FailedToStart:
            return
        self._note(self._proc.errorString() or "Không chạy được process STT.")
        self._set_busy(False, "Không chạy được")
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _on_finished(self, code: int, _status) -> None:
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        out = Path(self.output.text().strip()) if self.output.text().strip() else None
        if code == 0 and out and out.is_file():
            self._set_busy(False, "Xong")
            self._note(f"Xong. JSON: {out}")
            return
        self._set_busy(False, "Đã dừng")
        self._note(f"STT dừng, mã {code}.")

    def _set_busy(self, busy: bool, caption: str) -> None:
        self.task_label.setText(caption)
        if busy:
            self.progress.setRange(0, 0)
            return
        self.progress.setRange(0, 1)
        self.progress.setValue(1 if caption == "Xong" else 0)

    def _touch_task(self, line: str) -> None:
        if not self.running():
            return
        parts = _PARTS_RE.search(line)
        if parts:
            self._set_busy(True, f"Chia {parts.group(1)} phần")
        chunk = _CHUNK_RE.search(line)
        if chunk:
            self._set_busy(True, f"Nhận dạng chunk {chunk.group(1)}/{chunk.group(2)}")
        elif "Loading whisper-jax" in line:
            self._set_busy(True, f"{self.task_label.text()} · đang tải model")
        step = _STEP_RE.search(line)
        if step and not chunk:
            self._set_busy(True, f"Bước {step.group(1)}/{step.group(2)} · {step.group(3).strip()}")


def _is_url(text: str) -> bool:
    low = text.lower()
    return low.startswith("http://") or low.startswith("https://")


def _suggest_output(source: str) -> Path:
    if _is_url(source):
        tail = source.rstrip("/").split("/")[-1].split("?")[0]
        stem = Path(tail).stem or "url"
    else:
        stem = Path(source).stem or "transcript"
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in stem)[:80] or "transcript"
    return _ROOT / "output" / f"{safe}.json"
