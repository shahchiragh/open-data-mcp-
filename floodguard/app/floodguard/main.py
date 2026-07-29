from collections import OrderedDict
from strands import Agent
from strands.agent.conversation_manager.null_conversation_manager import NullConversationManager
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from model.load import load_model
from mcp_client.client import get_open_data_mcp_client
from flood_tools import FLOOD_TOOLS

app = BedrockAgentCoreApp()
log = app.logger


SYSTEM_PROMPT = """You are FloodGuard, the AI support assistant for FloodGuard Mutual,
a fictional property insurance agency that specializes in flood coverage.

Your job is to help support agents and policyholders understand flood risk and
triage flood insurance claims using satellite imagery. You are geospatially aware
and you understand Earth observation data:

- Sentinel-2 is optical (visible/near-infrared) imagery at 10 m resolution. You
  use the NDWI index (green vs near-infrared) to map open water on clear days.
- Sentinel-1 is C-band Synthetic Aperture Radar (SAR). It sees through clouds and
  at night, so it is the primary sensor during active storms. Calm flood water
  looks dark in SAR VV backscatter.
- For a flood claim you compare a "before" (dry baseline) scene with an "after"
  (during/just after the event) scene to measure newly inundated land.
- Open imagery lives in the AWS Registry of Open Data (RODA) and is queried via
  STAC catalogs like Earth Search. You can discover other open datasets there too.

How to help with a flood claim, step by step:
1. If the location is described in words, call geocode_place to get a bounding box.
2. Use a SMALL bounding box (a neighbourhood or property cluster) for analysis so
   reads are fast — refine the geocoded bbox down when needed.
3. Call search_flood_scenes to find a before and an after scene. Prefer optical
   (Sentinel-2) when skies are clear; use SAR (Sentinel-1) when the event was
   cloudy/stormy.
4. Call analyze_flood_change (optical) or analyze_sar_flood (SAR) to quantify the
   newly flooded area.
5. Call assess_flood_claim to produce a preliminary triage for the policyholder.

Always explain what the numbers mean in plain language for a non-technical
policyholder. Be clear that automated satellite triage is preliminary and never a
final coverage decision. Cite the scene ids and dates you used so the analysis is
auditable. If a tool fails (e.g. no cloud-free scene exists for a date), say so and
suggest the SAR alternative or a different date window.
"""


# Assemble tools: the self-contained flood-analysis toolset, plus the OpenDataMCP
# stdio client when running locally with OPEN_DATA_MCP_PATH set.
tools = list(FLOOD_TOOLS)

open_data_mcp = get_open_data_mcp_client()
if open_data_mcp is not None:
    tools.append(open_data_mcp)


def agent_factory():
    """Reuse one Agent per session_id so each conversation keeps its own history.

    Bounded LRU cache of 128 sessions; oldest is evicted. Resets on cold start.
    """
    cache: "OrderedDict[str, Agent]" = OrderedDict()

    def get_or_create_agent(session_id):
        if session_id in cache:
            cache.move_to_end(session_id)
            return cache[session_id]
        if len(cache) >= 128:
            cache.popitem(last=False)
        cache[session_id] = Agent(
            model=load_model(),
            system_prompt=SYSTEM_PROMPT,
            tools=tools,
            conversation_manager=NullConversationManager(),
        )
        return cache[session_id]

    return get_or_create_agent


get_or_create_agent = agent_factory()


def _extract_prompt(payload: dict):
    """Accept harness-style messages[], tool_results[], or a plain prompt string."""
    if "messages" in payload:
        return payload["messages"]
    if "tool_results" in payload:
        return [{"role": "user", "content": [{"toolResult": {
            "toolUseId": tr["toolUseId"],
            "status": tr.get("status", "success"),
            "content": tr.get("content", []),
        }} for tr in payload["tool_results"]]}]
    return payload.get("prompt", "")


@app.entrypoint
async def invoke(payload, context):
    log.info("FloodGuard invoked.")
    session_id = getattr(context, "session_id", "default-session")
    agent = get_or_create_agent(session_id)
    prompt = _extract_prompt(payload)

    async for event in agent.stream_async(prompt):
        if not isinstance(event, dict) or "event" not in event:
            continue
        cbs = event["event"].get("contentBlockStart")
        if cbs is not None and not cbs.get("start"):
            continue
        yield event


if __name__ == "__main__":
    app.run()
