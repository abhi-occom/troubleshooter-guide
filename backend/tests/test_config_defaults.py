from app.config import Settings


def test_minimax_cloud_is_the_default_ollama_model(monkeypatch, tmp_path):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    settings = Settings(_env_file=None, data_dir=tmp_path)

    assert settings.llm_provider == "ollama"
    assert settings.ollama_model == "minimax-m2.5:cloud"
