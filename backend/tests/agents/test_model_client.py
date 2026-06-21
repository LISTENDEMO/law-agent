from __future__ import annotations

import json

import pytest
from app.agents.model_client import ModelClient, ProviderFailure


class FakeTransport:
    def __init__(self) -> None:
        self.chat_calls: list[dict[str, object]] = []
        self.embedding_calls: list[dict[str, object]] = []

    async def chat(self, **request: object) -> str:
        self.chat_calls.append(request)
        return json.dumps({"route": "research"}, ensure_ascii=False)

    async def embeddings(self, **request: object) -> list[list[float]]:
        self.embedding_calls.append(request)
        return [[1.0, 0.0], [0.0, 1.0]]


@pytest.mark.asyncio
async def test_model_client_builds_structured_chat_request() -> None:
    transport = FakeTransport()
    client = ModelClient(
        transport=transport, chat_model="chat-model", embedding_model="embed-model"
    )

    result = await client.chat_json("system rules", "user question")

    assert result == {"route": "research"}
    assert transport.chat_calls == [
        {
            "model": "chat-model",
            "messages": [
                {"role": "system", "content": "system rules"},
                {"role": "user", "content": "user question"},
            ],
            "response_format": {"type": "json_object"},
        }
    ]


@pytest.mark.asyncio
async def test_model_client_batches_embeddings() -> None:
    transport = FakeTransport()
    client = ModelClient(
        transport=transport, chat_model="chat-model", embedding_model="embed-model"
    )

    vectors = await client.embed_texts(["第一条", "第二条"])

    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert transport.embedding_calls == [{"model": "embed-model", "input": ["第一条", "第二条"]}]


@pytest.mark.asyncio
async def test_model_client_maps_invalid_json_to_redacted_failure() -> None:
    class InvalidTransport(FakeTransport):
        async def chat(self, **request: object) -> str:
            return "not-json sk-secret-value"

    client = ModelClient(
        transport=InvalidTransport(), chat_model="chat-model", embedding_model="embed-model"
    )

    with pytest.raises(ProviderFailure) as captured:
        await client.chat_json("system", "user")

    assert "sk-secret-value" not in str(captured.value)
