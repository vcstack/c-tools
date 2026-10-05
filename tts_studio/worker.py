from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QThread, Signal

from ctool.vieneu import is_key_limit_error
from tts_studio.project import TtsProject


class GenWorker(QObject):
    progressed = Signal(str)
    failed = Signal(str, str)
    need_key = Signal(str, str)
    stopped = Signal()
    finished = Signal()

    def __init__(self, project: TtsProject, api_key: str, voice: str, ids: list[str]) -> None:
        super().__init__()
        self.project = project
        self.api_key = api_key
        self.voice = voice
        self.ids = ids
        self._cancel = False
        self._new_key: str | None = None
        self._key_event = threading.Event()

    def cancel(self) -> None:
        self._cancel = True
        self._new_key = None
        self._key_event.set()

    def supply_key(self, key: str | None) -> None:
        self._new_key = (key or "").strip() or None
        if self._new_key:
            self.api_key = self._new_key
        self._key_event.set()

    def _wait_for_key(self, sid: str, message: str) -> str | None:
        self._new_key = None
        self._key_event.clear()
        self.need_key.emit(sid, message)
        self._key_event.wait()
        if self._cancel:
            return None
        return self._new_key

    def run(self) -> None:
        for sid in self.ids:
            while True:
                if self._cancel:
                    self.stopped.emit()
                    return
                try:
                    self.project.synthesize_one(sid, self.api_key, self.voice)
                    self.progressed.emit(sid)
                    break
                except Exception as exc:
                    message = str(exc)[:400]
                    if is_key_limit_error(message):
                        key = self._wait_for_key(sid, message)
                        if not key:
                            self.stopped.emit()
                            return
                        continue
                    self.failed.emit(sid, message)
                    return
        self.project.merge_final()
        self.finished.emit()


class GenThread(QThread):
    def __init__(self, worker: GenWorker) -> None:
        super().__init__()
        self.worker = worker
        worker.moveToThread(self)
        self.started.connect(worker.run)
