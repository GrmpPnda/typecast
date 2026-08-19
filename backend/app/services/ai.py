from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.config import get_config_value


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class GenerateResult:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"


class AIProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, context: str = "") -> str: ...

    @abstractmethod
    async def stream_generate(self, prompt: str, context: str = "") -> AsyncIterator[str]: ...

    @abstractmethod
    async def parse_structured(self, prompt: str, content: str) -> dict[str, Any]: ...

    @abstractmethod
    async def generate_with_tools(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
    ) -> GenerateResult: ...

    @abstractmethod
    def format_tool_result(self, tool_call_id: str, result: dict) -> dict: ...


class AnthropicProvider(AIProvider):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        import anthropic

        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model

    async def generate(self, prompt: str, context: str = "") -> str:
        messages = []
        if context:
            messages.append({"role": "user", "content": context})
            messages.append({
                "role": "assistant",
                "content": "I understand the context. What would you like me to help with?",
            })
        messages.append({"role": "user", "content": prompt})

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=messages,
        )
        return response.content[0].text

    async def stream_generate(self, prompt: str, context: str = "") -> AsyncIterator[str]:
        messages = []
        if context:
            messages.append({"role": "user", "content": context})
            messages.append({
                "role": "assistant",
                "content": "I understand the context. What would you like me to help with?",
            })
        messages.append({"role": "user", "content": prompt})

        async with self.client.messages.stream(
            model=self.model,
            max_tokens=4096,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def parse_structured(self, prompt: str, content: str) -> dict[str, Any]:
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=8192,
            messages=[
                {"role": "user", "content": f"{prompt}\n\n---\n\n{content}"},
                {"role": "assistant", "content": "{"},
            ],
        )
        raw = "{" + response.content[0].text
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(raw)

    def _prepare_messages(self, messages: list[dict]) -> list[dict]:
        """Convert generic multimodal messages to Anthropic format."""
        prepared = []
        for msg in messages:
            if isinstance(msg.get("content"), list):
                content = []
                for block in msg["content"]:
                    if block.get("type") == "text":
                        content.append({"type": "text", "text": block["text"]})
                    elif block.get("type") == "image":
                        content.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": block["mime_type"],
                                "data": block["data"],
                            },
                        })
                    else:
                        content.append(block)
                prepared.append({**msg, "content": content})
            else:
                prepared.append(msg)
        return prepared

    async def generate_with_tools(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
    ) -> GenerateResult:
        anthropic_tools = [
            {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
            for t in tools
        ]
        prepared = self._prepare_messages(messages)
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=8192,
            system=system,
            messages=prepared,
            tools=anthropic_tools,
        )
        result = GenerateResult(stop_reason=response.stop_reason or "end_turn")
        for block in response.content:
            if block.type == "text":
                result.text += block.text
            elif block.type == "tool_use":
                result.tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    input=block.input,
                ))
        return result

    def format_tool_result(self, tool_call_id: str, result: dict) -> dict:
        return {
            "type": "tool_result",
            "tool_use_id": tool_call_id,
            "content": json.dumps(result),
        }


class OpenAIProvider(AIProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def generate(self, prompt: str, context: str = "") -> str:
        messages = []
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": prompt})

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
        )
        return response.choices[0].message.content or ""

    async def stream_generate(self, prompt: str, context: str = "") -> AsyncIterator[str]:
        messages = []
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": prompt})

        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def parse_structured(self, prompt: str, content: str) -> dict[str, Any]:
        system_msg = "You are a helpful assistant that responds only in valid JSON."
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": f"{prompt}\n\n---\n\n{content}"},
        ]
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content or "{}")

    def _prepare_messages(self, messages: list[dict]) -> list[dict]:
        """Convert generic multimodal messages to OpenAI format."""
        prepared = []
        for msg in messages:
            if isinstance(msg.get("content"), list):
                content = []
                for block in msg["content"]:
                    if block.get("type") == "text":
                        content.append({"type": "text", "text": block["text"]})
                    elif block.get("type") == "image":
                        data_url = f"data:{block['mime_type']};base64,{block['data']}"
                        content.append({
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        })
                    else:
                        content.append(block)
                prepared.append({**msg, "content": content})
            else:
                prepared.append(msg)
        return prepared

    async def generate_with_tools(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
    ) -> GenerateResult:
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in tools
        ]
        prepared = self._prepare_messages(messages)
        openai_msgs = [{"role": "system", "content": system}, *prepared]
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=openai_msgs,
            tools=openai_tools,
        )
        choice = response.choices[0]
        result = GenerateResult(
            text=choice.message.content or "",
            stop_reason="tool_calls" if choice.finish_reason == "tool_calls" else "end_turn",
        )
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                result.tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    input=json.loads(tc.function.arguments),
                ))
        return result

    def format_tool_result(self, tool_call_id: str, result: dict) -> dict:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": json.dumps(result),
        }


class BedrockProvider(AIProvider):
    def __init__(
        self,
        region: str = "us-east-1",
        model_id: str = "us.anthropic.claude-sonnet-4-6",
        aws_profile: str = "",
    ):
        self._region = region
        self._aws_profile = aws_profile or None
        self.model_id = model_id

    def _get_client(self):
        import boto3
        from botocore.config import Config

        session = boto3.Session(profile_name=self._aws_profile or "default")
        return session.client(
            "bedrock-runtime",
            region_name=self._region,
            config=Config(
                read_timeout=300,
                connect_timeout=10,
                retries={"max_attempts": 2},
            ),
        )

    def _build_messages(self, prompt: str, context: str = "") -> list[dict]:
        messages = []
        if context:
            messages.append({"role": "user", "content": [{"text": context}]})
            messages.append({
                "role": "assistant",
                "content": [
                    {"text": "I understand the context. What would you like me to help with?"}
                ],
            })
        messages.append({"role": "user", "content": [{"text": prompt}]})
        return messages

    async def generate(self, prompt: str, context: str = "") -> str:
        import asyncio

        messages = self._build_messages(prompt, context)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._get_client().converse(
                modelId=self.model_id,
                messages=messages,
                inferenceConfig={"maxTokens": 4096},
            ),
        )
        return response["output"]["message"]["content"][0]["text"]

    async def stream_generate(self, prompt: str, context: str = "") -> AsyncIterator[str]:
        import asyncio

        messages = self._build_messages(prompt, context)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._get_client().converse_stream(
                modelId=self.model_id,
                messages=messages,
                inferenceConfig={"maxTokens": 4096},
            ),
        )
        stream = response["stream"]
        for event in stream:
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"]["delta"]
                if "text" in delta:
                    yield delta["text"]

    async def parse_structured(self, prompt: str, content: str) -> dict[str, Any]:
        raw = await self.generate(
            f"{prompt}\n\nRespond ONLY with valid JSON, no markdown fences.\n\n---\n\n{content}"
        )
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(raw)

    async def generate_with_tools(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
    ) -> GenerateResult:
        import asyncio

        bedrock_tools = [
            {
                "toolSpec": {
                    "name": t["name"],
                    "description": t["description"],
                    "inputSchema": {"json": t["input_schema"]},
                }
            }
            for t in tools
        ]

        bedrock_msgs = []
        for msg in messages:
            if msg["role"] == "user":
                if isinstance(msg["content"], str):
                    content = [{"text": msg["content"]}]
                else:
                    import base64 as b64

                    content = []
                    for block in msg["content"]:
                        if block.get("type") == "text":
                            content.append({"text": block["text"]})
                        elif block.get("type") == "image":
                            fmt = block["mime_type"].split("/")[-1]
                            if fmt == "jpg":
                                fmt = "jpeg"
                            content.append({
                                "image": {
                                    "format": fmt,
                                    "source": {"bytes": b64.b64decode(block["data"])},
                                },
                            })
                        else:
                            content.append(block)
                bedrock_msgs.append({"role": "user", "content": content})
            elif msg["role"] == "assistant":
                bedrock_msgs.append({
                    "role": "assistant",
                    "content": msg.get("_raw_content", [{"text": msg.get("content", "")}]),
                })
            elif msg["role"] == "tool_result":
                bedrock_msgs.append({
                    "role": "user",
                    "content": msg["content"],
                })

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._get_client().converse(
                modelId=self.model_id,
                messages=bedrock_msgs,
                system=[{"text": system}],
                toolConfig={"tools": bedrock_tools},
                inferenceConfig={"maxTokens": 8192},
            ),
        )

        result = GenerateResult(
            stop_reason="tool_use" if response["stopReason"] == "tool_use" else "end_turn",
        )
        for block in response["output"]["message"]["content"]:
            if "text" in block:
                result.text += block["text"]
            elif "toolUse" in block:
                tu = block["toolUse"]
                result.tool_calls.append(ToolCall(
                    id=tu["toolUseId"],
                    name=tu["name"],
                    input=tu["input"],
                ))
        result._raw_content = response["output"]["message"]["content"]
        return result

    def format_tool_result(self, tool_call_id: str, result: dict) -> dict:
        return {
            "toolResult": {
                "toolUseId": tool_call_id,
                "content": [{"json": result}],
            }
        }


async def get_ai_provider(
    db: AsyncSession, provider_name: str | None = None,
) -> AIProvider:
    name = provider_name or await get_config_value(db, "ai_provider")

    if name == "anthropic":
        api_key = await get_config_value(db, "anthropic_api_key")
        model = await get_config_value(db, "anthropic_model")
        return AnthropicProvider(
            api_key=api_key, model=model or "claude-sonnet-4-6",
        )
    elif name == "openai":
        api_key = await get_config_value(db, "openai_api_key")
        model = await get_config_value(db, "openai_model")
        return OpenAIProvider(api_key=api_key, model=model or "gpt-4o")
    elif name == "bedrock":
        enabled = await get_config_value(db, "bedrock_enabled")
        if enabled != "true":
            raise ValueError("Bedrock provider is not enabled")
        region = await get_config_value(db, "bedrock_region")
        model_id = await get_config_value(db, "bedrock_model_id")
        aws_profile = await get_config_value(db, "bedrock_aws_profile")
        return BedrockProvider(
            region=region or "us-east-1",
            model_id=model_id or "us.anthropic.claude-sonnet-4-6",
            aws_profile=aws_profile,
        )
    else:
        raise ValueError(f"Unknown AI provider: {name}")
