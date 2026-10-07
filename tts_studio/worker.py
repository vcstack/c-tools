from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from ctool.vieneu import brief_api_error, is_key_limit_error, list_voice_catalog, resolve_voice
from tts_studio.project import TtsProject

_KEY_HINT = " Giữ nguyên key. File → API key… để đổi, rồi Gen chưa xong."


class GenWorker(QObject):
    progressed = Signal(str)
    busy = Signal(str)
    failed = Signal(str, str)
    stopped = Signal()
    finished = Signal()

    def __init__(self, project: TtsProject, api_key: str, voice: str, ids: list[str]) -> None:
        super().__init__()
        self.project = project
        self.api_key = api_key
        self.voice = voice
        self.ids = ids
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            self.voice = resolve_voice(self.voice)
        except Exception as exc:
            self.failed.emit(self.ids[0] if self.ids else "", str(exc)[:400])
            return
        for sid in self.ids:
            while True:
                if self._cancel:
                    self.stopped.emit()
                    return
                try:
                    self.busy.emit(sid)
                    self.project.synthesize_one(sid, self.api_key, self.voice)
                    self.progressed.emit(sid)
                    break
                except Exception as exc:
                    raw = str(exc)
                    message = brief_api_error(raw)
                    if is_key_limit_error(raw) or is_key_limit_error(message):
                        message = f"{message}{_KEY_HINT}"
                    self.failed.emit(sid, message)
                    return
        self.project.merge_final()
        self.finished.emit()


class VoiceCatalogThread(QThread):
    loaded = Signal(object)

    def __init__(self, api_key: str) -> None:
        super().__init__()
        self.api_key = api_key

    def run(self) -> None:
        try:
            self.loaded.emit(list_voice_catalog(self.api_key))
        except Exception as exc:
            self.loaded.emit(exc)


class MergeThread(QThread):
    finished_merge = Signal(object, str)

    def __init__(self, project: TtsProject) -> None:
        super().__init__()
        self.project = project

    def run(self) -> None:
        try:
            path, note = self.project.merge_prefix()
        except Exception as exc:
            self.finished_merge.emit(None, str(exc)[:300])
            return
        self.finished_merge.emit(path, note)


class GenThread(QThread):
    """Chạy gen trên luồng này. Không moveToThread — run() chặn sẽ không đơ cửa sổ."""

    def __init__(self, worker: GenWorker) -> None:
        super().__init__()
        self.worker = worker

    def run(self) -> None:
        self.worker.run()
