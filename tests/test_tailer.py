from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from openclaw_log_ingestor.tailer import Checkpoint, FileTailer, LogFileLocator


class TailerTests(unittest.TestCase):
    def test_locator_picks_latest_matching_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "openclaw-2026-03-28.log").write_text("a\n", encoding="utf-8")
            (root / "openclaw-2026-03-30.log").write_text("b\n", encoding="utf-8")

            locator = LogFileLocator(directory=root)

            self.assertEqual(locator.find_active_file(), root / "openclaw-2026-03-30.log")

    def test_tailer_waits_for_complete_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_path = root / "openclaw-2026-03-30.log"
            log_path.write_bytes(b'{"time":"2026-03-30T23:00:00Z"}\n{"time":"2026-03-30T23:00:01Z"}')

            tailer = FileTailer(consumer_name="test", start_position="beginning")
            checkpoint = Checkpoint(
                consumer_name="test",
                log_path=str(log_path.resolve()),
                file_device=None,
                file_inode=None,
                byte_offset=0,
                line_number=0,
            )

            batch = tailer.read_batch(log_path, checkpoint, max_lines=10)

            self.assertEqual(len(batch.lines), 1)
            self.assertEqual(batch.lines[0].line_number, 1)
            self.assertEqual(batch.checkpoint.line_number, 1)


if __name__ == "__main__":
    unittest.main()
