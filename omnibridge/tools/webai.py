"""Tools exposing the universal bridges: chat-only AIs (prompt bridge) and
OpenAI-compatible providers (function-calling schemas + agent loop)."""
from __future__ import annotations

from ..core.permissions import ToolDef
from ..core.registry import Registry
from ..webai import build_prompt, openai_tools, run_calls


def register_webai_tools(reg: Registry) -> None:
    async def webai_prompt(args: dict, ctx) -> dict:
        categories = args.get("categories") or None
        return build_prompt(ctx.bridge, int(args.get("budgetChars", 7000)), categories)

    async def webai_run(args: dict, ctx) -> dict:
        text = str(args["reply"])
        result = await run_calls(ctx.bridge, text, confirm=bool(args.get("confirm", False)))
        return result

    async def webai_openai_tools(args: dict, ctx) -> dict:
        tools = openai_tools(ctx.bridge)
        if args.get("category"):
            tools = [t for t in tools if f"· {args['category']}]" in t["function"]["description"]]
        return {"count": len(tools), "format": "openai-chat-completions", "tools": tools,
                "usage": "POST these to any OpenAI-compatible endpoint's `tools` field "
                         "(OpenAI, DeepSeek, Groq, Ollama, LM Studio) or run "
                         "`python examples/openai-compatible-agent.py`."}

    async def webai_providers(args: dict, ctx) -> dict:
        from ..openai_agent import PROVIDERS

        return {"providers": [{"name": k, "baseUrl": v[0], "apiKeyEnv": v[1], "defaultModel": v[2],
                               "needsKey": bool(v[1])} for k, v in PROVIDERS.items()],
                "note": "Keys stay in the user's environment; OMNIBRIDGE never stores them. "
                        "The agent loop is omnibridge/openai_agent.py."}

    reg.register(ToolDef("webai_prompt",
                         "Build a paste-ready system prompt that lets a chat-only AI (ChatGPT web, "
                         "DeepSeek web, Gemini, Copilot…) call OMNIBRIDGE tools through a JSON "
                         "protocol. Includes the real tool catalogue within a character budget.",
                         {"budgetChars": {"type": "integer", "default": 7000, "minimum": 1500, "maximum": 40000},
                          "categories": {"type": "array", "items": {"type": "string"},
                                         "description": "Optional category filter, e.g. [\"roblox\",\"code\"]"}},
                         [], 1, "webai", True, webai_prompt))
    reg.register(ToolDef("webai_run",
                         "Execute the tool calls contained in a chat model's reply and return a "
                         "would-paste-back block of real results. Each call is individually "
                         "permission-checked; level-4 tools still require confirm.",
                         {"reply": {"type": "string"},
                          "confirm": {"type": "boolean", "default": False,
                                      "description": "Allow level-4 calls found in the reply"}},
                         ["reply"], 3, "webai", False, webai_run))
    reg.register(ToolDef("webai_openai_tools",
                         "Export all OMNIBRIDGE tools as OpenAI/DeepSeek/Ollama function-calling "
                         "definitions, for any OpenAI-compatible chat-completions API.",
                         {"category": {"type": "string"}}, [], 1, "webai", True, webai_openai_tools))
    reg.register(ToolDef("webai_providers",
                         "List supported OpenAI-compatible providers with their base URL, key "
                         "environment variable and default model, plus how to run the agent loop.",
                         {}, [], 1, "webai", True, webai_providers))
