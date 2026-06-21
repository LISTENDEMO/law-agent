from __future__ import annotations

from pathlib import Path

from app.config import Settings


def test_settings_load_both_openai_compatible_providers() -> None:
    environment = {
        "CHAT_BASE_URL": "https://chat.example/v1",
        "CHAT_API_KEY": "chat-secret",
        "CHAT_MODEL": "chat-model",
        "EMBEDDING_BASE_URL": "https://embed.example/v1",
        "EMBEDDING_API_KEY": "embed-secret",
        "EMBEDDING_MODEL": "embed-model",
        "LAWAGENT_ADMIN_API_KEY": "admin-secret",
        "LAWAGENT_OFFLINE_MODE": "true",
    }

    settings = Settings.from_mapping(environment)

    assert settings.chat.base_url == "https://chat.example/v1"
    assert settings.chat.model == "chat-model"
    assert settings.embedding.base_url == "https://embed.example/v1"
    assert settings.embedding.model == "embed-model"
    assert settings.offline_mode is True


def test_settings_repr_redacts_all_secrets() -> None:
    settings = Settings.from_mapping(
        {
            "CHAT_API_KEY": "chat-secret",
            "EMBEDDING_API_KEY": "embed-secret",
            "LAWAGENT_ADMIN_API_KEY": "admin-secret",
        }
    )

    representation = repr(settings)

    assert "chat-secret" not in representation
    assert "embed-secret" not in representation
    assert "admin-secret" not in representation
    assert "**********" in representation


def test_settings_reject_invalid_provider_url() -> None:
    try:
        Settings.from_mapping({"CHAT_BASE_URL": "not-a-url"})
    except ValueError as error:
        assert "CHAT_BASE_URL" in str(error)
    else:
        raise AssertionError("invalid provider URL must be rejected")


def test_settings_load_prefers_process_environment_over_env_file(
    tmp_path: Path, monkeypatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("CHAT_MODEL=file-model\n", encoding="utf-8")
    monkeypatch.setenv("CHAT_MODEL", "container-model")

    settings = Settings.load(env_file)

    assert settings.chat.model == "container-model"
