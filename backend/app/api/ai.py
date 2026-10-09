from __future__ import annotations

import json
import logging
import uuid as uuid_mod

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.api.ownership import require_owned
from app.db.engine import get_db
from app.models.conversation import Conversation, ConversationMessage
from app.models.user import User
from app.schemas.ai import AIChatRequest
from app.services.ai import get_ai_provider
from app.services.ai_tools import TOOL_DEFINITIONS, execute_tool
from app.services.context import assemble_scene_context, assemble_work_context

log = logging.getLogger(__name__)

router = APIRouter()

_STYLE_MATCHING = (
    "STYLE MATCHING — this is your highest priority when writing or editing prose:\n"
    "Before writing anything, study the existing scenes in the work context carefully. "
    "The author's existing prose IS the style guide. Absorb and replicate:\n"
    "- **Sentence structure**: Are sentences long and flowing, or short and punchy? "
    "Mixed? What's the typical rhythm?\n"
    "- **Vocabulary level**: Does the author use simple, direct words or more literary "
    "language? Do NOT elevate or simplify beyond what the author uses.\n"
    "- **Dialogue style**: How are dialogue tags handled? Said-bookisms or plain 'said'? "
    "Action beats or attributions? How does the author format internal thought?\n"
    "- **POV and narrative distance**: How close is the narration to the character's "
    "thoughts? Does the author use deep POV, limited third, or more distant?\n"
    "- **Description density**: How much sensory detail does the author use? "
    "Match their level — don't over-describe if they write spare prose, "
    "don't under-describe if they write richly.\n"
    "- **Tense and person**: Match exactly.\n"
    "- **Paragraph length and scene pacing**: Mirror the author's patterns.\n"
    "- **Punctuation habits**: Em-dashes, semicolons, ellipses — use them only "
    "if and how the author uses them.\n\n"
    "If the work context includes 'Author's AI Instructions', those take precedence "
    "over what you observe in the text. Follow them precisely.\n\n"
    "When in doubt, be conservative — it's better to slightly under-write in the "
    "author's voice than to produce polished prose that sounds like a different writer.\n\n"
)

_ANTI_HALLMARK = (
    "CRITICAL — avoid AI writing hallmarks in ALL prose output:\n"
    "- No em-dashes (—) unless the author's existing text uses them frequently. "
    "Use commas, periods, semicolons, or restructure instead.\n"
    "- No triple-emphasis patterns (stacking italics, dramatic adjectives, "
    "or emotional intensifiers in threes).\n"
    "- Avoid these overused words/phrases: \"delve\", \"tapestry\", \"testament to\", "
    "\"remnants of\", \"vibrant\", \"A silence stretched between them\", "
    "\"couldn't help but\", \"a wave of\", \"pierced through\", \"etched across\", "
    "\"shivers down [someone's] spine\", \"the weight of\", \"swelled within\", "
    "\"hung in the air\", \"let out a breath\", \"eyes glistening\".\n"
    "- Don't bookend scenes with weather, sighs, or characters staring into distance.\n"
    "- Don't summarize emotions the reader can already infer from action and dialogue.\n"
    "- Prefer concrete, specific detail over abstract description.\n"
    "- Vary sentence length and structure. Avoid falling into a rhythm of "
    "compound sentences joined by commas.\n"
    "- Match the author's actual vocabulary level — don't elevate register with "
    "literary-sounding words the author hasn't used.\n"
)

PERSONA_PROMPTS = {
    "author": (
        "You are a creative writing partner for a novel-writing application called Typecast. "
        "You are encouraging, imaginative, and generative. When the author asks you to write, "
        "you produce prose that is indistinguishable from their own. You brainstorm enthusiastically, "
        "offer alternatives when asked, and celebrate good ideas. You take creative risks and "
        "aren't afraid to suggest bold narrative choices.\n\n"
        "You have tools to create and modify content in the application. "
        "Use them when the user asks you to create, write, update, or organize something. "
        "For read-only questions (summaries, explanations, suggestions), answer directly.\n\n"
        "When creating codex entries, be thorough and well-organized.\n\n"
        + _STYLE_MATCHING
        + _ANTI_HALLMARK +
        "\nFormat responses in markdown."
    ),
    "reviewer": (
        "You are a supportive manuscript reviewer for a novel-writing application "
        "called Typecast. You focus on craft: pacing, character, dialogue, "
        "narrative tension, prose style, and consistency. You are the author's "
        "collaborative partner — your job is to help make good writing better, "
        "not to find fault with everything.\n\n"
        "REVIEW PHILOSOPHY:\n"
        "- Be selective. Only flag things that genuinely weaken the writing. "
        "A scene can be good without needing a comment on every paragraph.\n"
        "- Respect the author's voice and choices. Not every unconventional "
        "choice is an error — consider whether it serves the story.\n"
        "- A scene the AI itself wrote may already be solid. Do not manufacture "
        "critiques just to have something to say. If a scene is working well, "
        "say so in your summary and leave few or no inline comments.\n"
        "- Aim for 3-5 inline comments per scene maximum. If fewer things need "
        "fixing, leave fewer comments. Zero comments is fine for a strong scene.\n\n"
        "INLINE COMMENT RULES:\n"
        "- Every inline comment must be actionable with a concrete suggestion.\n"
        "- Praise belongs in your summary text, not in inline comments.\n"
        "- Keep each comment concise — one or two sentences max.\n"
        "- Focus on the highest-impact issues: things that would most improve "
        "the reader's experience.\n\n"
        "When asked to review a chapter, use the review_chapter tool to leave inline "
        "comments across ALL scenes — not just the current scene. When asked to review "
        "a scene, use review_scene for that single scene. Always use list_chapters first "
        "if you need to find scene IDs.\n\n"
        "After the inline comments, provide a brief summary in your response text. "
        "Lead with what's working well, then cover the most important issues to address.\n\n"
        "When suggesting replacement text in the 'suggestion' field, it MUST match "
        "the author's existing prose style — study the surrounding text carefully. "
        "A suggestion that fixes a craft issue but changes the author's voice is a bad suggestion.\n\n"
        + _STYLE_MATCHING
        + _ANTI_HALLMARK +
        "\nFormat responses in markdown."
    ),
    "advisor": (
        "You are a knowledgeable writing advisor for a novel-writing application called Typecast. "
        "You are neutral, informative, and analytical. You answer questions about craft, "
        "genre conventions, publishing, structure, and technique with clear, well-reasoned "
        "explanations. You don't push a particular creative direction — you present options, "
        "trade-offs, and let the author decide.\n\n"
        "You have tools to create and modify content in the application. "
        "Use them when the user asks you to create, write, update, or organize something. "
        "For informational questions, answer directly with relevant examples.\n\n"
        "If the work context includes 'Author's AI Instructions', reference them when relevant "
        "to give context-aware advice.\n\n"
        + _ANTI_HALLMARK +
        "\nBe concise and practical. Format responses in markdown."
    ),
}

AUTO_CLASSIFY_PROMPT = (
    "Classify this user message into one of three personas:\n"
    "- author: creative writing requests (write, draft, brainstorm, create, continue)\n"
    "- reviewer: feedback requests (review, critique, evaluate, improve, check)\n"
    "- advisor: informational questions (how, what, explain, suggest approach, compare)\n\n"
    "Respond with ONLY the persona name, nothing else.\n\n"
    "Message: {message}"
)


def _sse(event: str, data: str | dict) -> str:
    payload = json.dumps(data) if isinstance(data, dict) else json.dumps(data)
    return f"event: {event}\ndata: {payload}\n\n"


def _friendly_error(exc: Exception) -> str:
    msg = str(exc)
    if "ValidationException" in msg:
        if "on-demand throughput" in msg:
            return (
                "This Bedrock model ID doesn't support on-demand access. "
                "Select a different model or use an inference profile ARN."
            )
        return f"Bedrock validation error: {msg.split(':', 1)[-1].strip()}"
    if "ExpiredTokenException" in type(exc).__name__ or "ExpiredToken" in msg:
        return "AWS credentials have expired. Refresh your credentials and try again."
    if "NoCredentialsError" in type(exc).__name__ or "Unable to locate credentials" in msg:
        return "No AWS credentials found. Configure credentials on the host."
    if "AuthFailure" in msg or "UnrecognizedClientException" in msg:
        return "AWS authentication failed. Check your credentials and region."
    if "invalid_api_key" in msg or "Incorrect API key" in msg:
        return "Invalid API key. Check your key in Settings."
    if "authentication_error" in msg:
        return "Authentication failed. Check your API key in Settings."
    if "rate_limit" in msg.lower():
        return "Rate limit reached. Wait a moment and try again."
    return f"AI request failed: {type(exc).__name__}: {msg.split(chr(10))[0][:200]}"


async def _resolve_persona(provider, persona: str, prompt: str) -> str:
    if persona != "auto":
        return persona
    try:
        result = await provider.generate(
            AUTO_CLASSIFY_PROMPT.format(message=prompt[:500])
        )
        detected = result.strip().lower()
        if detected in PERSONA_PROMPTS:
            return detected
    except Exception:
        pass
    return "author"


async def _get_or_create_conversation(
    db: AsyncSession,
    conversation_id: uuid_mod.UUID | None,
    work_id: uuid_mod.UUID | None,
    persona: str,
    user: User,
) -> Conversation:
    # Ownership of conversation_id is checked by the caller. This lookup used to
    # accept any ID, which loaded another account's chat history into yours.
    if conversation_id:
        result = await db.execute(
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .options(selectinload(Conversation.messages))
        )
        conv = result.scalar_one_or_none()
        if conv:
            return conv

    conv = Conversation(
        user_id=user.id,
        work_id=work_id,
        persona=persona,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv, ["messages"])
    return conv


def _rebuild_history(messages: list[ConversationMessage]) -> list[dict]:
    """Rebuild LLM message history from stored messages."""
    history: list[dict] = []
    for msg in messages:
        if msg.role == "user":
            history.append({"role": "user", "content": msg.content})
        elif msg.role == "assistant" and msg.content:
            history.append({"role": "assistant", "content": msg.content})
    return history


# @mention type -> resource kind. Mentions pull the target's full text into
# the prompt, so naming someone else's chapter is the same as reading it.
_MENTION_KINDS = {"codex": "codex_entry", "chapter": "chapter", "scene": "scene", "work": "work"}


@router.post("/chat")
async def ai_chat(
    req: AIChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Checked before the provider, so the answer is the same whether or not AI
    # is configured, and before anything is read into the prompt.
    await require_owned(db, user, "work", req.work_id)
    await require_owned(db, user, "chapter", req.chapter_id)
    await require_owned(db, user, "scene", req.scene_id)
    await require_owned(db, user, "conversation", req.conversation_id)
    for mention in req.mentions:
        kind = _MENTION_KINDS.get(mention.type)
        if kind is None:
            raise HTTPException(status_code=422, detail=f"Unknown mention type {mention.type!r}")
        await require_owned(db, user, kind, mention.id)

    try:
        provider = await get_ai_provider(db)
    except ValueError as exc:
        return StreamingResponse(
            iter([_sse("error", str(exc))]),
            media_type="text/event-stream",
        )

    persona = req.persona or "author"

    conv = await _get_or_create_conversation(
        db, req.conversation_id, req.work_id, persona, user,
    )

    if persona == "auto":
        persona = await _resolve_persona(provider, persona, req.prompt)
        if conv.persona != persona:
            conv.persona = persona
            await db.commit()

    system_parts = [PERSONA_PROMPTS.get(persona, PERSONA_PROMPTS["author"])]
    effective_work_id = req.work_id or conv.work_id
    if effective_work_id:
        system_parts.append(f"The user is viewing work_id: {effective_work_id}")
        if req.chapter_id:
            system_parts.append(f"Current chapter_id: {req.chapter_id}")
            if not req.scene_id:
                system_parts.append(
                    "The user is viewing this chapter. When they refer to "
                    "'this scene' or 'the scene', use the scene_id(s) from "
                    "the CURRENT chapter context — not from other chapters. "
                    "Use review_chapter to review all scenes at once."
                )
        if req.scene_id:
            system_parts.append(f"Current scene_id: {req.scene_id}")

        has_focus = bool(req.chapter_id or req.scene_id)
        work_context = await assemble_work_context(
            db,
            effective_work_id,
            include_full_text=has_focus,
            chapter_id=req.chapter_id,
            scene_id=req.scene_id,
        )
        if work_context:
            system_parts.append(f"## Current Work Context\n{work_context}")

    if req.scene_id:
        scene_context = await assemble_scene_context(db, req.scene_id)
        if scene_context:
            system_parts.append(f"## Current Scene Context\n{scene_context}")

    system = "\n\n".join(system_parts)

    if req.mentions:
        from app.services.context import resolve_mentions

        mention_result = await resolve_mentions(db, req.mentions)
        if mention_result["text"]:
            system += f"\n\n## Referenced Items (mentioned by user with @)\n{mention_result['text']}"
        mention_images = mention_result.get("images", [])
    else:
        mention_images = []

    all_images = []
    for att in req.attachments:
        all_images.append({"data": att.data, "mime_type": att.mime_type, "name": att.name})
    all_images.extend(mention_images)

    next_sort = max((m.sort_order for m in conv.messages), default=-1) + 1

    user_msg = ConversationMessage(
        conversation_id=conv.id,
        role="user",
        content=req.prompt,
        sort_order=next_sort,
    )
    db.add(user_msg)
    next_sort += 1

    if len(conv.messages) == 0:
        title_words = req.prompt.strip().split()
        conv.title = " ".join(title_words[:8]) + ("..." if len(title_words) > 8 else "")

    await db.commit()

    async def event_stream():
        nonlocal next_sort
        try:
            yield _sse("conversation", {
                "id": str(conv.id),
                "persona": persona,
            })

            history = _rebuild_history(conv.messages)
            if all_images:
                user_content = [{"type": "text", "text": req.prompt}]
                for img in all_images:
                    user_content.append({
                        "type": "image",
                        "data": img["data"],
                        "mime_type": img["mime_type"],
                    })
                history.append({"role": "user", "content": user_content})
            else:
                history.append({"role": "user", "content": req.prompt})
            max_rounds = 10

            full_assistant_text = ""

            for _ in range(max_rounds):
                result = await provider.generate_with_tools(
                    history, system, TOOL_DEFINITIONS,
                )

                if result.text:
                    full_assistant_text += result.text
                    yield _sse("token", result.text)

                if not result.tool_calls:
                    break

                assistant_msg = _build_assistant_msg(provider, result)
                history.append(assistant_msg)

                if result.text:
                    a_msg = ConversationMessage(
                        conversation_id=conv.id,
                        role="assistant",
                        content=result.text,
                        sort_order=next_sort,
                    )
                    db.add(a_msg)
                    next_sort += 1
                    full_assistant_text = ""

                tool_result_contents = []
                for tc in result.tool_calls:
                    yield _sse("tool_start", {"tool": tc.name, "input": tc.input})

                    tool_result = await execute_tool(db, tc.name, tc.input, user)

                    # Send a lightweight version to the frontend (no base64 in SSE)
                    display_result = {
                        k: v for k, v in tool_result.items() if k != "image_data"
                    }
                    if "image_data" in tool_result:
                        display_result["has_image"] = True
                    yield _sse("tool_result", {"tool": tc.name, "result": display_result})

                    # Strip base64 image data from storage and LLM history
                    lean_result = {
                        k: v for k, v in tool_result.items()
                        if k not in ("image_data",)
                    }

                    t_msg = ConversationMessage(
                        conversation_id=conv.id,
                        role="tool",
                        content=json.dumps({"tool": tc.name, "result": lean_result}),
                        tool_name=tc.name,
                        sort_order=next_sort,
                    )
                    db.add(t_msg)
                    next_sort += 1

                    formatted = provider.format_tool_result(tc.id, lean_result)
                    tool_result_contents.append(formatted)

                _append_tool_results(provider, history, tool_result_contents)

            if full_assistant_text:
                a_msg = ConversationMessage(
                    conversation_id=conv.id,
                    role="assistant",
                    content=full_assistant_text,
                    sort_order=next_sort,
                )
                db.add(a_msg)
                next_sort += 1

            await db.commit()
            yield _sse("done", "")
        except Exception as exc:
            log.exception("AI chat error")
            if full_assistant_text:
                a_msg = ConversationMessage(
                    conversation_id=conv.id,
                    role="assistant",
                    content=full_assistant_text,
                    sort_order=next_sort,
                )
                db.add(a_msg)
                try:
                    await db.commit()
                except Exception:
                    pass
            yield _sse("error", _friendly_error(exc))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _build_assistant_msg(provider, result) -> dict:
    from app.services.ai import AnthropicProvider, BedrockProvider, OpenAIProvider

    if isinstance(provider, AnthropicProvider):
        content = []
        if result.text:
            content.append({"type": "text", "text": result.text})
        for tc in result.tool_calls:
            content.append({
                "type": "tool_use",
                "id": tc.id,
                "name": tc.name,
                "input": tc.input,
            })
        return {"role": "assistant", "content": content}

    elif isinstance(provider, OpenAIProvider):
        msg: dict = {"role": "assistant", "content": result.text or None}
        if result.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.input),
                    },
                }
                for tc in result.tool_calls
            ]
        return msg

    elif isinstance(provider, BedrockProvider):
        raw = getattr(result, "_raw_content", None)
        if raw:
            return {"role": "assistant", "_raw_content": raw, "content": result.text}
        content = []
        if result.text:
            content.append({"text": result.text})
        for tc in result.tool_calls:
            content.append({
                "toolUse": {"toolUseId": tc.id, "name": tc.name, "input": tc.input}
            })
        return {"role": "assistant", "_raw_content": content, "content": result.text}

    return {"role": "assistant", "content": result.text}


def _append_tool_results(provider, messages: list[dict], results: list[dict]):
    from app.services.ai import AnthropicProvider, BedrockProvider, OpenAIProvider

    if isinstance(provider, AnthropicProvider):
        messages.append({"role": "user", "content": results})
    elif isinstance(provider, OpenAIProvider):
        messages.extend(results)
    elif isinstance(provider, BedrockProvider):
        messages.append({"role": "tool_result", "content": results})
