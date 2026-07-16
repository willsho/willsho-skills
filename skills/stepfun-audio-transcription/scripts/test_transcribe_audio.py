#!/usr/bin/env python3
"""Offline unit tests for transcribe_audio.py."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


SCRIPT = Path(__file__).with_name("transcribe_audio.py")
SPEC = importlib.util.spec_from_file_location("stepfun_transcribe_audio", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class TestHotwords(unittest.TestCase):
    def test_extracts_title_entities_and_removes_episode_label(self):
        hotwords = MODULE.extract_title_hotwords(
            "No.225 对话 Yuri 尤栗打造者汗青：AI 虚拟偶像"
        )
        self.assertIn("Yuri", hotwords)
        self.assertIn("尤栗", hotwords)
        self.assertIn("汗青", hotwords)
        self.assertIn("AI", hotwords)
        self.assertNotIn("No.225", hotwords)

    def test_manual_hotwords_are_first_and_deduplicated(self):
        hotwords = MODULE.merge_hotwords("聊聊 StepAudio", ["阶跃星辰", "StepAudio"])
        self.assertEqual(hotwords[:2], ["阶跃星辰", "StepAudio"])
        self.assertEqual(hotwords.count("StepAudio"), 1)


class TestSSE(unittest.TestCase):
    def test_done_event_returns_final_text(self):
        lines = [
            b'data: {"type":"transcript.text.delta","delta":"\xe8\xaf\x86\xe5\x88\xab"}\n',
            b"\n",
            b'data: {"type":"transcript.text.done","text":"\xe8\xaf\x86\xe5\x88\xab\xe5\xae\x8c\xe6\x88\x90"}\n',
            b"\n",
        ]
        self.assertEqual(MODULE.parse_stepfun_sse(lines), "识别完成")

    def test_done_without_text_uses_deltas(self):
        lines = [
            'data: {"type":"transcript.text.delta","delta":"第一段"}\n',
            "\n",
            'data: {"type":"transcript.text.delta","delta":"第二段"}\n',
            "\n",
            'data: {"type":"transcript.text.done"}\n',
            "\n",
        ]
        self.assertEqual(MODULE.parse_stepfun_sse(lines), "第一段第二段")

    def test_error_event_raises(self):
        lines = ['data: {"type":"error","message":"invalid audio"}\n', "\n"]
        with self.assertRaisesRegex(MODULE.TranscriptionError, "invalid audio"):
            MODULE.parse_stepfun_sse(lines)


class TestRequest(unittest.TestCase):
    @patch.object(MODULE.urllib.request, "urlopen")
    def test_request_payload_matches_mercury_protocol(self, mock_urlopen):
        response = MagicMock()
        response.__enter__.return_value = [
            'data: {"type":"transcript.text.done","text":"转录文本"}\n',
            "\n",
        ]
        mock_urlopen.return_value = response

        with tempfile.TemporaryDirectory() as directory:
            chunk = Path(directory) / "chunk.mp3"
            chunk.write_bytes(b"audio")
            text = MODULE.transcribe_chunk(chunk, "secret", "zh", ["阶跃星辰"])

        self.assertEqual(text, "转录文本")
        request = mock_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        transcription = payload["audio"]["input"]["transcription"]
        self.assertEqual(transcription["model"], "stepaudio-2.5-asr")
        self.assertEqual(transcription["hotwords"], ["阶跃星辰"])
        self.assertEqual(payload["audio"]["input"]["format"], {"type": "mp3"})
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")


class TestTimeBasedSegmentation(unittest.TestCase):
    @patch.object(MODULE.subprocess, "run")
    def test_ffmpeg_transcodes_and_segments_in_one_pass(self, mock_run):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.m4a"
            source.write_bytes(b"media")

            def create_chunks(*_args, **_kwargs):
                (root / "chunk_000.mp3").write_bytes(b"first")
                (root / "chunk_001.mp3").write_bytes(b"second")

            mock_run.side_effect = create_chunks
            chunks = MODULE.compress_and_split(source, root, segment_seconds=600)

        self.assertEqual([item.name for item in chunks], ["chunk_000.mp3", "chunk_001.mp3"])
        command = mock_run.call_args.args[0]
        self.assertEqual(command[command.index("-segment_time") + 1], "600")
        self.assertEqual(command[command.index("-reset_timestamps") + 1], "1")
        self.assertEqual(command.count("ffmpeg"), 1)
        self.assertNotIn("mono.mp3", command)


class TestCLI(unittest.TestCase):
    @patch.dict(MODULE.os.environ, {}, clear=True)
    def test_missing_key_is_actionable(self):
        self.assertEqual(MODULE.main(["missing.mp3"]), 2)

    def test_missing_local_input(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(MODULE.TranscriptionError, "input does not exist"):
                MODULE.resolve_input(str(Path(directory) / "missing.mp3"), Path(directory))


if __name__ == "__main__":
    unittest.main()
