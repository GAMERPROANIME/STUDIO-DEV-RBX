#!/usr/bin/env python3
"""Run a real autonomous loop with any OpenAI-compatible model + OMNIBRIDGE tools.

Works with: DeepSeek API, OpenAI API, Groq, Ollama (local), LM Studio.
The model calls OMNIBRIDGE tools through standard function calling; the loop is Python.

Setup
-----
    export DEEPSEEK_API_KEY=...        # or OPENAI_API_KEY / GROQ_API_KEY
    # Ollama / LM Studio need no key:
    #   ollama serve ; ollama pull qwen2.5-coder:7b

Usage
-----
    python examples/openai-compatible-agent.py "Inspect this project and list the TODO items"
    python examples/openai-compatible-agent.py --provider ollama --model qwen2.5-coder:7b "Analyse src/server"
    python examples/openai-compatible-agent.py --provider deepseek --level 3 \
        "Ajoute un RemoteEvent de test dans src/server et vérifie-le"

Nothing is simulated: each tool call is executed by the Python core with the usual
permission checks (level 4 still requires confirm=true, which this script never sets).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from omnibridge.config import load_config  # noqa: E402
from omnibridge.core.app import OmniBridge  # noqa: E402
from omnibridge.openai_agent import AgentConfig, OpenAIToolAgent, PROVIDERS  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description="OMNIBRIDGE + OpenAI-compatible model")
    parser.add_argument("prompt", help="what the model should accomplish")
    parser.add_argument("--provider", default=os.environ.get("OMNIBRIDGE_LLM_PROVIDER", "deepseek"),
                        choices=sorted(PROVIDERS))
    parser.add_argument("--model", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--api-key", default="", help="prefer the provider's env var")
    parser.add_argument("--level", type=int, choices=[1, 2, 3, 4], default=2)
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--json", action="store_true", help="print the full transcript")
    args = parser.parse_args()

    cfg = load_config(permission_level=args.level,
                      workspace_root=Path(args.workspace).expanduser().resolve())
    bridge = OmniBridge(cfg)
    agent_cfg = AgentConfig(provider=args.provider, base_url=args.base_url, api_key=args.api_key,
                            model=args.model, max_steps=args.max_steps).resolve()
    agent = OpenAIToolAgent(bridge, agent_cfg)

    async def on_event(event: dict) -> None:
        flag = "ok " if event["ok"] else "ERR"
        print(f"  [{flag}] step {event['step']}: {event['tool']}", file=sys.stderr)

    print(f"provider={agent_cfg.provider} model={agent_cfg.model} tools={bridge.registry.size} "
          f"level={cfg.permission_level}", file=sys.stderr)
    try:
        result = await agent.run(args.prompt, on_event=on_event)
    finally:
        await agent.close()
        await bridge.close()

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    elif result["ok"]:
        print(result["final"])
    else:
        print(f"ERROR: {result.get('error')}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
