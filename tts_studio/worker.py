from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from tts_studio.project import TtsProject


class GenWorker(QObject):
    progressed = Signal(str)
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
        for sid in self.ids:
            if self._cancel:
                self.stopped.emit()
                return
            try:
                self.project.synthesize_one(sid, self.api_key, self.voice)
                self.progressed.emit(sid)
            except Exception as exc:
                self.failed.emit(sid, str(exc)[:400])
                return
        self.finished.emit()


class GenThread(QThread):
    def __init__(self, worker: GenWorker) -> None:
        super().__init__()
        self.worker = worker
        worker.moveToThread(self)
        self.started.connect(worker.run)
