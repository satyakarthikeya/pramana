from pathlib import Path

import pytest
from pydantic import ValidationError

from pramana.common.config import RuntimeConfig, load_config_file, load_runtime_config
from pramana.common.langfuse_client import get_langfuse_client
from pramana.common.paths import CONFIG_DIR, PROJECT_ROOT, config_path


def test_canonical_paths_point_into_repository() -> None:
    assert CONFIG_DIR == PROJECT_ROOT / "configs"
    assert config_path("runtime") == CONFIG_DIR / "runtime.yaml"


@pytest.mark.parametrize("name", ["../runtime", "folder/runtime", "", ".."])
def test_config_path_rejects_traversal(name: str) -> None:
    with pytest.raises(ValueError):
        config_path(name)


def test_runtime_config_loads() -> None:
    config = load_runtime_config()
    assert config.run.graph_timeout_seconds > 0
    assert config.run.on_exhausted_retries == "degrade"
    assert config.logging.format == "json"


def test_runtime_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://example:6379/4")
    monkeypatch.setenv("PRAMANA_LOG_LEVEL", "DEBUG")
    config = load_runtime_config()
    assert config.queue.broker_url == "redis://example:6379/4"
    assert config.logging.level == "DEBUG"


def test_invalid_runtime_file_fails_validation(tmp_path: Path) -> None:
    path = tmp_path / "runtime.yaml"
    path.write_text("run: {}\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config_file(path, RuntimeConfig)


def test_unknown_runtime_key_fails_validation(tmp_path: Path) -> None:
    path = tmp_path / "runtime.yaml"
    path.write_text(
        """
run:
  graph_timeout_seconds: 30
  max_node_retries: 0
  on_exhausted_retries: degrade
  typo: true
queue:
  broker_url: redis://localhost/0
  result_backend: redis://localhost/1
  task_soft_time_limit: 5
  task_hard_time_limit: 6
  result_timeout_seconds: 7
langfuse:
  enabled: false
logging:
  level: INFO
  format: json
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="typo"):
        load_config_file(path, RuntimeConfig)


def test_langfuse_is_optional_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    settings = load_runtime_config().langfuse
    assert get_langfuse_client(settings) is None
