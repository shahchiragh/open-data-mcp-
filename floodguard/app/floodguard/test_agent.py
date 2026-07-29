"""End-to-end test of the FloodGuard agent (LLM + tools) for the Maui 2026 flood.

Invokes the agent the same way AgentCore does — through the module's agent
factory — with a realistic policyholder prompt, and prints the streamed text.
"""

import io
import sys
import asyncio

# Force UTF-8 on the Windows console so emoji/unicode in model output don't crash.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


async def run(prompt: str):
    import main

    # Fresh agent with the default console callback disabled so we control output.
    from strands import Agent
    from strands.agent.conversation_manager.null_conversation_manager import NullConversationManager
    from model.load import load_model

    agent = Agent(
        model=load_model(),
        system_prompt=main.SYSTEM_PROMPT,
        tools=main.tools,
        conversation_manager=NullConversationManager(),
        callback_handler=None,
    )
    print(f"\n>>> USER: {prompt}\n")
    print(">>> FLOODGUARD:")
    text_parts = []
    async for event in agent.stream_async(prompt):
        if isinstance(event, dict) and "data" in event:
            chunk = event["data"]
            text_parts.append(chunk)
            print(chunk, end="", flush=True)
    print("\n")
    return "".join(text_parts)


PROMPT = (
    "A policyholder named Keola in Kihei, Maui was flooded during the March 2026 "
    "Kona storm. As our claims support assistant, find Sentinel imagery before and "
    "during the event, estimate how much new flooding occurred near Kihei, and give "
    "a preliminary claim triage. Keep the analysis area small so it runs quickly."
)

if __name__ == "__main__":
    asyncio.run(run(PROMPT))
