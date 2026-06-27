from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class SecretValue:
    """A tiny secret wrapper that never reveals its value through repr or str."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def get_secret_value(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "SecretValue('**********')"

    __str__ = __repr__


@dataclass(frozen=True)
class ProviderSettings:
    base_url: str
    api_key: SecretValue
    model: str


@dataclass(frozen=True)
class Settings:
    chat: ProviderSettings
    embedding: ProviderSettings
    admin_api_key: SecretValue
    data_dir: Path
    corpus_dir: Path
    offline_mode: bool
    max_retries: int
    max_tool_calls: int
    max_input_chars: int
    model_timeout_seconds: float

    @classmethod
    def from_mapping(cls, environment: Mapping[str, str]) -> Settings:
        chat_url = environment.get("CHAT_BASE_URL", "https://example.invalid/v1")
        embedding_url = environment.get(
            "EMBEDDING_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        _validate_url("CHAT_BASE_URL", chat_url)
        _validate_url("EMBEDDING_BASE_URL", embedding_url)

        return cls(
            chat=ProviderSettings(
                base_url=chat_url.rstrip("/"),
                api_key=SecretValue(environment.get("CHAT_API_KEY", "")),
                model=environment.get("CHAT_MODEL", "gpt-5.4-mini"),
            ),
            embedding=ProviderSettings(
                base_url=embedding_url.rstrip("/"),
                api_key=SecretValue(environment.get("EMBEDDING_API_KEY", "")),
                model=environment.get("EMBEDDING_MODEL", "text-embedding-v4"),
            ),
            admin_api_key=SecretValue(environment.get("LAWAGENT_ADMIN_API_KEY", "")),
            data_dir=Path(environment.get("LAWAGENT_DATA_DIR", "./data")),
            corpus_dir=Path(environment.get("LAWAGENT_CORPUS_DIR", "./RAG")),
            offline_mode=_to_bool(environment.get("LAWAGENT_OFFLINE_MODE", "false")),
            max_retries=_positive_int(environment, "LAWAGENT_MAX_RETRIES", 2),
            max_tool_calls=_positive_int(environment, "LAWAGENT_MAX_TOOL_CALLS", 12),
            max_input_chars=_positive_int(environment, "LAWAGENT_MAX_INPUT_CHARS", 6000),
            model_timeout_seconds=_positive_float(
                environment, "LAWAGENT_MODEL_TIMEOUT_SECONDS", 18.0
            ),
        )

    @classmethod
    def load(cls, env_file: str | Path = ".env") -> Settings:
        from dotenv import dotenv_values

        values = {
            key: value for key, value in dotenv_values(env_file).items() if value is not None
        }
        values.update(os.environ)
        return cls.from_mapping(values)


def _validate_url(name: str, value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{name} must be an absolute HTTP(S) URL")


def _positive_int(environment: Mapping[str, str], name: str, default: int) -> int:
    value = int(environment.get(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _positive_float(environment: Mapping[str, str], name: str, default: float) -> float:
    value = float(environment.get(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _to_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {value}")
