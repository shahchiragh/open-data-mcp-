# FloodGuard — Geospatial Flood-Claims Agent on Amazon Bedrock AgentCore

FloodGuard is a demo AI support chatbot for a fictional flood-insurance agency
("FloodGuard Mutual"). It is built with the **Strands Agents SDK**, is
geospatially aware, understands **Sentinel-1 (SAR)** and **Sentinel-2 (optical)**
Earth-observation data, knows how to discover open data on the **AWS Registry of
Open Data (RODA)** — the same catalog the repo's `OpenDataMCP` server exposes —
and carries tools to perform basic flood analysis for insurance claims. It is
deployed to **Amazon Bedrock AgentCore Runtime** via the **AWS CDK** in
**us-east-1**.

This document records exactly how it was built, run, and deployed, so the demo
is reproducible.

---

## 1. What the agent does

The agent is a claims-support assistant. Given a flood event described in plain
language, it:

1. **Geocodes** the location to a bounding box (OpenStreetMap Nominatim).
2. **Discovers imagery** — searches Sentinel-2 (optical) or Sentinel-1 (SAR)
   scenes over the area and time window via the Earth Search STAC API.
3. **Analyzes flooding**:
   - Optical: **NDWI** = (Green − NIR) / (Green + NIR); water is NDWI > 0. A
     before/after pair yields *newly flooded* land.
   - SAR: **VV backscatter** change; calm flood water is smooth and appears dark
     (low dB). SAR sees through clouds, so it is the workhorse during storms.
4. **Triages the claim** — applies simple, transparent severity bands and returns
   a recommended handling track, an estimated payout band, and next steps.
5. **Discovers open datasets** on RODA by keyword (mirrors `OpenDataMCP`).

All imagery is read cloud-natively (COG byte-range reads over HTTPS) — no bulk
downloads — so it runs inside the AgentCore microVM.

### Tools

| Tool | Purpose |
|------|---------|
| `geocode_place` | Place name → bounding box + centre |
| `search_flood_scenes` | Find Sentinel-1/2 scenes (before/after) |
| `compute_water_extent` | NDWI open-water area for one Sentinel-2 scene |
| `analyze_flood_change` | NDWI before/after → newly flooded km² |
| `analyze_sar_flood` | Sentinel-1 VV backscatter before/after → flooded km² |
| `assess_flood_claim` | Preliminary claim triage from flood extent |
| `search_aws_open_data` | RODA open-dataset discovery by keyword |

---

## 2. Project layout

```
floodguard/
├── agentcore/
│   ├── agentcore.json        # runtime spec (CodeZip, PYTHON_3_12, HTTP, PUBLIC)
│   ├── aws-targets.json       # deployment target: prod / us-east-1
│   └── cdk/                    # @aws/agentcore-cdk L3 constructs (deploy engine)
├── app/floodguard/
│   ├── main.py                # BedrockAgentCoreApp entrypoint + Strands agent
│   ├── flood_tools.py         # the 7 flood-analysis tools
│   ├── model/load.py          # Bedrock Claude Sonnet 4.5 model
│   ├── mcp_client/client.py   # optional OpenDataMCP stdio client (local dev)
│   ├── pyproject.toml         # deps incl. rasterio, numpy, pyproj, httpx
│   ├── test_maui.py           # direct pipeline test (no LLM)
│   └── test_agent.py          # end-to-end LLM + tools test
└── DEPLOYMENT.md              # this file
```

### The OpenDataMCP relationship

The repo's `open_data_mcp.py` is a FastMCP server (RODA search, STAC queries,
NDVI/NDBI). FloodGuard understands and can use it two ways:

- **Local development:** set `OPEN_DATA_MCP_PATH` to the absolute path of
  `open_data_mcp.py` and the agent attaches it as an MCP tool over stdio
  (`mcp_client/client.py`).
- **Deployed (cloud):** the local stdio server isn't present in the microVM, so
  the agent uses its self-contained `flood_tools`, which call the *same* open
  Earth Search STAC + RODA registry directly. Behaviour is identical to a
  policyholder; only the transport differs.

---

## 3. Prerequisites (already present on this machine)

- **Python 3.12+** and the **`uv`** package manager.
- **Node.js** (for the CDK-based `@aws/agentcore` CLI).
- **`@aws/agentcore` CLI** v0.25.0 (`npm install -g @aws/agentcore`).
- **AWS credentials** — here, an EC2 instance role in account `597288150864`.
- **`AWS_REGION=us-east-1`**.
- **Amazon Bedrock model access** to `global.anthropic.claude-sonnet-4-5`.
- Docker is **not** required — the runtime uses the **CodeZip** build type.

---

## 4. Build steps (reproduce from scratch)

### 4.1 Scaffold the project (CDK-managed, CodeZip)

```bash
agentcore create --name floodguard --project-name floodguard \
  --build CodeZip --language Python --framework Strands \
  --model-provider Bedrock --protocol HTTP --memory none --skip-git --json
```

This creates the `floodguard/` tree above with a CDK project under
`agentcore/cdk/` (the CLI deploys through CDK).

### 4.2 Set the deployment target to us-east-1

`agentcore/aws-targets.json`:

```json
[
  { "name": "prod", "account": "597288150864", "region": "us-east-1" }
]
```

### 4.3 Pin the runtime to Python 3.12

In `agentcore/agentcore.json`, set `"runtimeVersion": "PYTHON_3_12"` (mature
ARM64 wheels for rasterio/numpy/pyproj resolve reliably on 3.12).

### 4.4 Add the agent code

- `app/floodguard/flood_tools.py` — the 7 tools (see §1).
- `app/floodguard/main.py` — wires the tools + insurance system prompt into a
  Strands `Agent`, wrapped by `BedrockAgentCoreApp` with an `@app.entrypoint`.
- `app/floodguard/mcp_client/client.py` — optional OpenDataMCP stdio client.

### 4.5 Add geospatial dependencies

In `app/floodguard/pyproject.toml`, add to `dependencies`:

```
"httpx >= 0.27",
"numpy >= 1.26",
"rasterio >= 1.3",
"pyproj >= 3.6",
```

### 4.6 Install and test locally

```bash
cd app/floodguard
uv sync

# Direct pipeline test against real Maui 2026 imagery (no LLM):
uv run python test_maui.py

# Full agent test (LLM + tools):
uv run python test_agent.py
```

---

## 5. Deploy to AWS (CDK, us-east-1)

From the project root (`floodguard/`):

```bash
# Validate the configuration
agentcore validate

# Preview (synth + bootstrap check, no deploy)
agentcore deploy --target prod --dry-run

# Deploy (auto-bootstraps CDK the first time, auto-confirms)
agentcore deploy --target prod --yes --verbose
```

`agentcore deploy` synthesizes the CDK app in `agentcore/cdk/`, bootstraps the
CDK toolkit stack in us-east-1 (first run only), zips `app/floodguard/`, uploads
it, and creates the `AWS::BedrockAgentCore::Runtime` plus its IAM execution role
via CloudFormation stack `AgentCore-floodguard-prod`.

### Deployed resources (this run)

| Resource | Value |
|----------|-------|
| Region | `us-east-1` |
| Account | `597288150864` |
| CloudFormation stack | `AgentCore-floodguard-prod` |
| Runtime ID | `floodguard_floodguard-5pF5cg5iwv` |
| Runtime ARN | `arn:aws:bedrock-agentcore:us-east-1:597288150864:runtime/floodguard_floodguard-5pF5cg5iwv` |
| Execution role | `arn:aws:iam::597288150864:role/AgentCore-floodguard-prod-ApplicationAgentFloodguar-ZdSlosQFkU3O` |
| Build type | CodeZip (ARM64, `PYTHON_3_12`) |
| Protocol / Network | HTTP / PUBLIC |

> **Security note:** the runtime is deployed with `networkMode: PUBLIC` and is
> reachable by any caller in the account that holds
> `bedrock-agentcore:InvokeAgentRuntime` on the runtime ARN (IAM SigV4 — there is
> no unauthenticated access). For a production deployment, scope invoke
> permissions to specific principals and consider a `CUSTOM_JWT` authorizer or
> VPC network mode.

---

## 6. Verify the deployment

```bash
agentcore status --target prod
# floodguard: Deployed - Runtime: READY

# Smoke test
agentcore invoke --target prod --prompt "What can you help with as FloodGuard?"
```

---

## 7. Demo: Maui, Hawaii 2026 flooding

Background: the **2026 Hawaii floods** were caused by a slow-moving Kona low,
~**March 9–22, 2026** (peak March 13–15), with severe flooding in **Kīhei** and
**Lahaina** on Maui.

Run the deployed agent against the event:

```bash
agentcore invoke --target prod --prompt-file maui_demo_prompt.txt
```

`maui_demo_prompt.txt`:

> A policyholder named Keola in Kihei, Maui was flooded during the March 2026
> Kona storm. As our claims support assistant, find Sentinel-2 imagery before
> (early March 2026) and after (late March 2026) the event, estimate how much new
> flooding occurred near Kihei using a small analysis area, and give a
> preliminary claim triage. Cite the scene IDs and dates you used.

### Representative output (real imagery)

The agent geocoded Kīhei, selected a ~5 km analysis box, discovered real
Sentinel-2 scenes, ran NDWI change detection reading COGs over HTTPS inside the
AgentCore microVM, and returned a triage:

- **Before scene:** `S2B_4QGH_20260305_0_L2A` (2026-03-05, 8.6% cloud)
- **After scene:** `S2B_4QGH_20260325_0_L2A` (2026-03-25, 2.6% cloud)
- **Newly flooded area:** ~0.066 km² (≈16 acres)
- **Triage:** Moderate severity, standard adjuster track, est. $37.5k–$125k
  against a $250k limit, with cited scene IDs for auditability.

It also cross-checks Sentinel-1 SAR (`analyze_sar_flood`) for cloud-obscured
dates. Exact numbers vary with the chosen bounding box, scene pair, and NDWI/dB
thresholds; the agent explains that automated triage is preliminary and never a
coverage decision.

> Note on scene selection: the analysis quality depends on which before/after
> scenes the model picks. For the cleanest flood signal, prefer a genuine
> pre-event scene and a during/just-after scene over a tight land bounding box
> (a large box dominated by ocean makes the sea the largest "water" feature).

---

## 8. Local development with the OpenDataMCP server

To let the local agent also drive the repo's `OpenDataMCP` server over stdio:

```bash
# PowerShell
$env:OPEN_DATA_MCP_PATH = "C:\workshop\open_data_mcp.py"
cd floodguard
agentcore dev                                  # local server on :8080
agentcore invoke --dev --prompt "Find open Sentinel datasets on AWS for flood mapping"
```

When `OPEN_DATA_MCP_PATH` is unset (the default, and always in the cloud), the
agent uses its self-contained `flood_tools`.

---

## 9. Operate, update, and tear down

```bash
# Stream logs
agentcore logs --target prod

# Redeploy after code changes (creates a new immutable runtime version)
agentcore deploy --target prod --yes

# Stop an active session early (saves microVM cost)
agentcore invoke --target prod --prompt "..." --session-id <id>   # reuse a session

# Tear everything down
agentcore remove all
agentcore deploy --target prod --yes      # applies the removal (destroys the stack)
```

### Cost notes

- You are billed for AgentCore Runtime only while a session is active; idle
  sessions auto-terminate after 15 minutes by default.
- Imagery reads hit public, credential-free open buckets (no egress account
  cost for the data itself).
- The CDK bootstrap stack and the runtime definition persist until deleted.
