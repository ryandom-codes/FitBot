from pathlib import Path

import pytest

from src.config import load_settings


def test_real_records_default_outside_repository(tmp_path, monkeypatch):
    monkeypatch.delenv('FITNESS_PRIVATE_DIR', raising=False)
    monkeypatch.delenv('OLLAMA_HOST', raising=False)
    repo = tmp_path / 'fitness-research-assistant'
    repo.mkdir()
    settings = load_settings(repo)
    assert settings.private_dir == tmp_path / 'fitness-research-assistant-private'
    assert not settings.database_path.is_relative_to(repo)
    assert settings.model == 'qwen3.5:4b-q4_K_M'


def test_rejects_private_database_folder_inside_repo(tmp_path, monkeypatch):
    repo = tmp_path / 'project'
    repo.mkdir()
    monkeypatch.setenv('FITNESS_PRIVATE_DIR', str(repo / 'records'))
    with pytest.raises(ValueError, match='outside'):
        load_settings(repo)


@pytest.mark.parametrize('host', ['https://api.example.com', 'http://192.168.1.2:11434'])
def test_rejects_remote_model_endpoint_for_local_v1(tmp_path, monkeypatch, host):
    monkeypatch.delenv('FITNESS_PRIVATE_DIR', raising=False)
    monkeypatch.setenv('OLLAMA_HOST', host)
    with pytest.raises(ValueError, match='local'):
        load_settings(tmp_path / 'project')


def test_accepts_explicit_external_private_folder(tmp_path, monkeypatch):
    monkeypatch.setenv('FITNESS_PRIVATE_DIR', str(tmp_path / 'private'))
    monkeypatch.setenv('OLLAMA_HOST', 'http://localhost:11434')
    settings = load_settings(tmp_path / 'project')
    assert settings.database_path.parent == Path(tmp_path / 'private').resolve()
