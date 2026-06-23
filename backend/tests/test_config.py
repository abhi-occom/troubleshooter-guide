from app.config import Settings


def test_frontend_origins_accepts_comma_separated_environment_value(
    monkeypatch, tmp_path
):
    monkeypatch.setenv(
        "FRONTEND_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )

    settings = Settings(data_dir=tmp_path)

    assert settings.frontend_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
