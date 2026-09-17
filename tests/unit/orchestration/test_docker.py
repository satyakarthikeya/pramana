import yaml

from pramana.common.paths import PROJECT_ROOT

DOCKER_DIR = PROJECT_ROOT / "docker"


def test_dev_compose_contains_required_services_and_worker_limits() -> None:
    compose = yaml.safe_load((DOCKER_DIR / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert {"api", "worker", "redis", "chromadb"} <= services.keys()
    worker = services["worker"]
    assert worker["read_only"] is True
    assert worker["cap_drop"] == ["ALL"]
    assert worker["pids_limit"] > 0
    assert worker["networks"] == ["queue"]
    assert services["redis"]["networks"] == ["queue"]
    assert services["chromadb"]["networks"] == ["storage"]
    assert worker["volumes"] == ["run-data:/data/pramana:ro"]
    assert "run-data:/data/pramana" in services["api"]["volumes"]
    assert compose["networks"]["queue"]["internal"] is True
    assert compose["networks"]["storage"]["internal"] is True


def test_dockerfiles_use_non_root_user() -> None:
    for filename in ("Dockerfile.api", "Dockerfile.worker"):
        text = (DOCKER_DIR / filename).read_text(encoding="utf-8")
        assert "FROM python:3.11-slim" in text
        assert "COPY configs /app/configs" in text
        assert "USER pramana" in text


def test_docker_build_context_excludes_secrets_and_local_data() -> None:
    for filename in ("Dockerfile.api.dockerignore", "Dockerfile.worker.dockerignore"):
        patterns = (DOCKER_DIR / filename).read_text(encoding="utf-8").splitlines()
        assert {".git", ".env", ".venv", "data", "artifacts", "chroma"} <= set(patterns)
