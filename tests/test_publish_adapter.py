"""Hub 백업의 파일 유출 방지와 로컬 학습 결과 보존을 검증한다."""

from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from training.publish_adapter import collect_adapter_files, publish_adapter
from training import train_qlora


class PublishAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name).resolve()
        # 파일 선별 검증용 바이트이며 실제 학습 모델이 아니다.
        self.saved = {
            "adapter_config.json": json.dumps({"base_model_name_or_path": "Qwen/test"}).encode(),
            "adapter_model.safetensors": b"test-only-weights",
            "tokenizer.json": b"{}",
            "tokenizer_config.json": b"{}",
            "run_manifest.json": b'{"seed": 42}',
            "chat_templates/default.jinja": b"{{ messages }}",
            ".env": b"HF_TOKEN=test-secret",
            "token": b"test-secret",
            "train.jsonl": b"private training data",
            "optimizer.pt": b"optimizer state",
            "checkpoint-50/adapter_model.safetensors": b"intermediate weights",
        }
        for name, content in self.saved.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.api = Mock()
        self.api.model_info.return_value = SimpleNamespace(private=True, sha="previous-commit")
        self.api.create_commit.return_value = SimpleNamespace(commit_url="https://huggingface.co/test/adapter/commit/new")
        self.api_factory = Mock(return_value=self.api)
        # 실제 SDK/인증/GPU 없이 외부로 전달될 파일과 호출 경계를 검사한다.
        modules = {
            "huggingface_hub": SimpleNamespace(HfApi=self.api_factory, CommitOperationAdd=SimpleNamespace),
            "huggingface_hub.utils": SimpleNamespace(validate_repo_id=Mock()),
        }
        self.enterContext(patch.dict("sys.modules", modules))
        self.enterContext(redirect_stdout(io.StringIO()))

    def test_upload_excludes_secrets_data_and_checkpoints_and_records_checksums(self):
        url = publish_adapter(self.root, "test/adapter")
        self.assertEqual(url, self.api.create_commit.return_value.commit_url)
        self.api.create_repo.assert_called_once_with(
            repo_id="test/adapter", repo_type="model", private=True, exist_ok=True,
        )
        call = self.api.create_commit.call_args.kwargs
        payload = {op.path_in_repo: op.path_or_fileobj for op in call["operations"]}
        expected = {
            "adapter_config.json", "adapter_model.safetensors", "tokenizer.json",
            "tokenizer_config.json", "run_manifest.json", "chat_templates/default.jinja",
        }
        self.assertEqual(set(payload), expected | {"SHA256SUMS.txt"})
        checksum_lines = payload["SHA256SUMS.txt"].decode().splitlines()
        self.assertEqual(len(checksum_lines), len(expected))
        for line in checksum_lines:
            digest, name = line.split("  ", 1)
            self.assertEqual(digest, hashlib.sha256(Path(payload[name]).read_bytes()).hexdigest())
        self.assertEqual(call["parent_commit"], "previous-commit")

    def test_dry_run_never_connects_to_hub(self):
        self.assertIsNone(publish_adapter(self.root, "test/adapter", dry_run=True))
        self.api_factory.assert_not_called()

    def test_missing_or_empty_weights_fail_before_remote_access(self):
        weights = self.root / "adapter_model.safetensors"
        weights.unlink()
        with self.assertRaisesRegex(ValueError, "부족"):
            publish_adapter(self.root, "test/adapter")
        weights.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "빈"):
            publish_adapter(self.root, "test/adapter")
        self.api_factory.assert_not_called()

    def test_private_mode_blocks_existing_public_repo(self):
        self.api.model_info.return_value.private = False
        with self.assertRaisesRegex(ValueError, "이미 공개"):
            publish_adapter(self.root, "test/adapter")
        self.api.create_commit.assert_not_called()

    def test_public_upload_requires_explicit_option(self):
        self.api.model_info.return_value.private = False
        publish_adapter(self.root, "test/adapter", private=False)
        self.assertFalse(self.api.create_repo.call_args.kwargs["private"])
        self.api.create_commit.assert_called_once()

    def test_failed_upload_preserves_local_files(self):
        self.api.create_commit.side_effect = RuntimeError("network unavailable")
        with self.assertRaisesRegex(RuntimeError, "network unavailable"):
            publish_adapter(self.root, "test/adapter")
        actual = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(actual, self.saved)

    def test_outside_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as outside_dir:
            outside_file = Path(outside_dir) / "private.json"
            outside_file.write_text("private", encoding="utf-8")
            try:
                (self.root / "special_tokens_map.json").symlink_to(outside_file)
            except OSError:
                self.skipTest("이 환경에는 symlink 생성 권한이 없습니다.")
            with self.assertRaisesRegex(ValueError, "폴더 밖"):
                collect_adapter_files(self.root)

    def test_training_failure_never_starts_upload(self):
        args = SimpleNamespace(config="unused", validate_only=False, hub_repo_id="test/adapter", hub_public=False)
        config = {"training": {"seed": 42, "output_dir": str(self.root)}}
        with patch.object(train_qlora, "parse_args", return_value=args), \
             patch.object(train_qlora, "load_config", return_value=config), \
             patch.object(train_qlora, "set_seed"), \
             patch.object(train_qlora, "train", side_effect=RuntimeError("training failed")), \
             patch("training.publish_adapter.publish_adapter") as upload:
            with self.assertRaisesRegex(RuntimeError, "training failed"):
                train_qlora.main()
            upload.assert_not_called()

    def test_training_upload_is_opt_in_and_runs_after_local_save(self):
        args = SimpleNamespace(config="unused", validate_only=False, hub_repo_id=None, hub_public=False)
        config = {"training": {"seed": 42, "output_dir": str(self.root)}}
        events = []
        with patch.object(train_qlora, "parse_args", return_value=args), \
             patch.object(train_qlora, "load_config", return_value=config), \
             patch.object(train_qlora, "set_seed"), \
             patch.object(train_qlora, "train", side_effect=lambda _: events.append("saved")), \
             patch("training.publish_adapter.publish_adapter", side_effect=lambda *a, **kw: events.append("uploaded")) as upload:
            train_qlora.main()
            upload.assert_not_called()
            events.clear()
            args.hub_repo_id = "test/adapter"
            train_qlora.main()
            self.assertEqual(events, ["saved", "uploaded"])
            upload.assert_called_once_with(str(self.root), "test/adapter", private=True)


if __name__ == "__main__":
    unittest.main()
