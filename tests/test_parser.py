from __future__ import annotations

import unittest

from openclaw_log_ingestor.parser import parse_log_line


SAMPLE_LINE = (
    '{"0":"{\\"subsystem\\":\\"gateway/ws\\"}","1":"webchat connected",'
    '"_meta":{"runtime":"node","runtimeVersion":"25.8.1","hostname":"unknown",'
    '"name":"{\\"subsystem\\":\\"gateway/ws\\"}","parentNames":["openclaw"],'
    '"date":"2026-03-28T23:45:37.881Z","logLevelId":3,"logLevelName":"INFO",'
    '"path":{"fullFilePath":"file:///opt/homebrew/lib/node_modules/openclaw/dist/subsystem.js:454:14",'
    '"fileName":"subsystem.js","fileColumn":"14","fileLine":"454","filePath":"opt/homebrew/lib/node_modules/openclaw/dist/subsystem.js","method":"logToFile"}},'
    '"time":"2026-03-28T16:45:37.882-07:00"}'
)

STRUCTURED_LINE = (
    '{"0":"{\\"module\\":\\"slack-auto-reply\\"}",'
    '"1":{"channel":"C0AN9S5E5A8","reason":"no-mention"},'
    '"2":"skipping channel message",'
    '"_meta":{"name":"{\\"module\\":\\"slack-auto-reply\\"}","parentNames":["openclaw"],"date":"2026-03-28T23:46:57.620Z"},'
    '"time":"2026-03-28T16:46:57.621-07:00"}'
)

RUN_LINE = (
    '{"0":"{\\"subsystem\\":\\"agent/embedded\\"}",'
    '"1":{"event":"embedded_run_agent_end","runId":"31d7fc6a-aa5f-4664-971c-68b925be4a8a","isError":true},'
    '"2":"embedded run agent end",'
    '"_meta":{"name":"{\\"subsystem\\":\\"agent/embedded\\"}","parentNames":["openclaw"],"date":"2026-03-28T23:48:57.979Z"},'
    '"time":"2026-03-28T16:48:57.979-07:00"}'
)


class ParserTests(unittest.TestCase):
    def test_parses_string_context_and_metadata(self) -> None:
        parsed = parse_log_line(SAMPLE_LINE, line_number=12)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.line_number, 12)
        self.assertEqual(parsed.metadata.logger_name, '{"subsystem":"gateway/ws"}')
        self.assertEqual(parsed.metadata.parent_names, ("openclaw",))
        self.assertEqual(parsed.context_json, {"subsystem": "gateway/ws"})
        self.assertEqual(parsed.field1_text, "webchat connected")
        self.assertIsNone(parsed.field1_json)
        self.assertEqual(parsed.metadata.source_file_line, 454)
        self.assertEqual(parsed.metadata.source_file_column, 14)

    def test_parses_structured_fields(self) -> None:
        parsed = parse_log_line(STRUCTURED_LINE, line_number=4)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.context_json, {"module": "slack-auto-reply"})
        self.assertEqual(parsed.field1_json, {"channel": "C0AN9S5E5A8", "reason": "no-mention"})
        self.assertIsNone(parsed.field1_text)
        self.assertEqual(parsed.field2_text, "skipping channel message")

    def test_extracts_run_id_from_field1_json(self) -> None:
        parsed = parse_log_line(RUN_LINE, line_number=12)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(str(parsed.run_id), "31d7fc6a-aa5f-4664-971c-68b925be4a8a")
        self.assertEqual(parsed.field2_text, "embedded run agent end")

    def test_returns_none_for_blank_line(self) -> None:
        self.assertIsNone(parse_log_line("   ", line_number=1))


if __name__ == "__main__":
    unittest.main()
