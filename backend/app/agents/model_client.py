from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Protocol

from openai import AsyncOpenAI, OpenAI, OpenAIError

from app.config import ProviderSettings


class ProviderFailure(RuntimeError):
    """A provider error safe to expose without request content or credentials."""


class ModelTransport(Protocol):
    async def chat(self, **request: object) -> str: ...

    async def embeddings(self, **request: object) -> list[list[float]]: ...


class OpenAITransport:
    def __init__(
        self,
        chat: ProviderSettings,
        embedding: ProviderSettings,
        *,
        max_retries: int = 2,
        timeout: float = 30.0,
    ) -> None:
        self._chat_client = AsyncOpenAI(
            api_key=chat.api_key.get_secret_value(),
            base_url=chat.base_url,
            max_retries=max_retries,
            timeout=timeout,
        )
        self._embedding_client = AsyncOpenAI(
            api_key=embedding.api_key.get_secret_value(),
            base_url=embedding.base_url,
            max_retries=max_retries,
            timeout=timeout,
        )

    async def chat(self, **request: object) -> str:
        try:
            response = await self._chat_client.chat.completions.create(**request)
        except OpenAIError as error:
            raise ProviderFailure(f"chat provider failed: {type(error).__name__}") from error
        content = response.choices[0].message.content
        if not content:
            raise ProviderFailure("chat provider returned empty content")
        return content

    async def embeddings(self, **request: object) -> list[list[float]]:
        try:
            response = await self._embedding_client.embeddings.create(**request)
        except OpenAIError as error:
            raise ProviderFailure(f"embedding provider failed: {type(error).__name__}") from error
        return [item.embedding for item in response.data]


class ModelClient:
    def __init__(self, transport: ModelTransport, chat_model: str, embedding_model: str) -> None:
        self._transport = transport
        self._chat_model = chat_model
        self._embedding_model = embedding_model

    async def chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
        try:
            content = await self._transport.chat(
                model=self._chat_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )
            parsed = json.loads(content)
        except ProviderFailure:
            raise
        except Exception as error:
            raise ProviderFailure("chat provider returned invalid structured output") from error
        if not isinstance(parsed, dict):
            raise ProviderFailure("chat provider returned a non-object JSON value")
        return parsed

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._transport.embeddings(model=self._embedding_model, input=list(texts))


class OpenAIEmbeddingClient:
    def __init__(
        self,
        provider: ProviderSettings,
        *,
        max_retries: int = 2,
        timeout: float = 60.0,
    ) -> None:
        self.model = provider.model
        self._client = OpenAI(
            api_key=provider.api_key.get_secret_value(),
            base_url=provider.base_url,
            max_retries=max_retries,
            timeout=timeout,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            response = self._client.embeddings.create(model=self.model, input=texts)
        except OpenAIError as error:
            raise ProviderFailure(f"embedding provider failed: {type(error).__name__}") from error
        return [item.embedding for item in response.data]


class OpenAIStructuredClient:
    def __init__(
        self,
        provider: ProviderSettings,
        *,
        max_retries: int = 2,
        timeout: float = 60.0,
    ) -> None:
        self.model = provider.model
        self._client = OpenAI(
            api_key=provider.api_key.get_secret_value(),
            base_url=provider.base_url,
            max_retries=max_retries,
            timeout=timeout,
        )

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, object]:
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )
        except OpenAIError as error:
            raise ProviderFailure(f"chat provider failed: {type(error).__name__}") from error
        content = response.choices[0].message.content
        if not content:
            raise ProviderFailure("chat provider returned empty content")
        try:
            value = json.loads(content)
        except json.JSONDecodeError as error:
            raise ProviderFailure("chat provider returned invalid structured output") from error
        if not isinstance(value, dict):
            raise ProviderFailure("chat provider returned a non-object JSON value")
        return value
