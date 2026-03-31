from __future__ import annotations

from datetime import date
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Checkpoint:
    consumer_name: str
    log_path: str
    file_device: int | None
    file_inode: int | None
    byte_offset: int
    line_number: int


@dataclass(frozen=True)
class RawLogLine:
    line_number: int
    text: str


@dataclass(frozen=True)
class TailBatch:
    lines: list[RawLogLine]
    checkpoint: Checkpoint


class DailyLogFileLocator:
    def __init__(self, directory: Path, today_provider: Callable[[], date] | None = None) -> None:
        self._directory = directory
        self._today_provider = today_provider or date.today

    def find_active_file(self) -> Path | None:
        active_file = self._directory / f"openclaw-{self._today_provider().isoformat()}.log"
        if not active_file.exists():
            return None

        return active_file


class FileTailer:
    def __init__(self, consumer_name: str, start_position: str) -> None:
        self._consumer_name = consumer_name
        self._start_position = start_position

    def initial_checkpoint(self, path: Path) -> Checkpoint:
        stat_result = path.stat()
        resolved_path = str(path.resolve())

        if self._start_position == "end":
            return Checkpoint(
                consumer_name=self._consumer_name,
                log_path=resolved_path,
                file_device=_optional_int(getattr(stat_result, "st_dev", None)),
                file_inode=_optional_int(getattr(stat_result, "st_ino", None)),
                byte_offset=stat_result.st_size,
                line_number=self._count_lines(path),
            )

        return Checkpoint(
            consumer_name=self._consumer_name,
            log_path=resolved_path,
            file_device=_optional_int(getattr(stat_result, "st_dev", None)),
            file_inode=_optional_int(getattr(stat_result, "st_ino", None)),
            byte_offset=0,
            line_number=0,
        )

    def read_batch(self, path: Path, checkpoint: Checkpoint, max_lines: int) -> TailBatch:
        stat_result = path.stat()
        device = _optional_int(getattr(stat_result, "st_dev", None))
        inode = _optional_int(getattr(stat_result, "st_ino", None))

        if self._file_was_replaced(checkpoint, device, inode, stat_result.st_size):
            checkpoint = Checkpoint(
                consumer_name=checkpoint.consumer_name,
                log_path=str(path.resolve()),
                file_device=device,
                file_inode=inode,
                byte_offset=0,
                line_number=0,
            )

        lines: list[RawLogLine] = []
        next_offset = checkpoint.byte_offset
        next_line_number = checkpoint.line_number

        with path.open("rb") as handle:
            handle.seek(checkpoint.byte_offset)
            while len(lines) < max_lines:
                start_offset = handle.tell()
                raw_line = handle.readline()
                if not raw_line:
                    break

                if not raw_line.endswith(b"\n"):
                    handle.seek(start_offset)
                    break

                next_offset = handle.tell()
                next_line_number += 1
                lines.append(
                    RawLogLine(
                        line_number=next_line_number,
                        text=raw_line[:-1].decode("utf-8", errors="replace"),
                    )
                )

        next_checkpoint = Checkpoint(
            consumer_name=checkpoint.consumer_name,
            log_path=str(path.resolve()),
            file_device=device,
            file_inode=inode,
            byte_offset=next_offset,
            line_number=next_line_number,
        )

        return TailBatch(lines=lines, checkpoint=next_checkpoint)

    def _file_was_replaced(
        self,
        checkpoint: Checkpoint,
        device: int | None,
        inode: int | None,
        size: int,
    ) -> bool:
        if size < checkpoint.byte_offset:
            return True

        if checkpoint.file_inode is None or checkpoint.file_device is None:
            return False

        return checkpoint.file_inode != inode or checkpoint.file_device != device

    def _count_lines(self, path: Path) -> int:
        count = 0
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                count += chunk.count(b"\n")
        return count


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)
