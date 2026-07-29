# Geospatial MCP Build Labs — Prompts & Instructions

Verbatim capture of the lab guides used to build this repo. This file preserves the exact
prompts, commands, and steps so the Geospatial MCP Build is reproducible.

> Source: AWS Workshop Studio — "Build an MCP server for the Registry of Open Data on AWS."
> Lab 2 and Lab 3 are captured below.

## Contents

- [Lab 2: Build an MCP server for the Registry of Open Data on AWS](#lab-2-build-an-mcp-server-for-the-registry-of-open-data-on-aws)
- [Lab 3: Build Search and Analysis Tools for the MCP server](#lab-3-build-search-and-analysis-tools-for-the-mcp-server)
- [Geospatial MCP Build summary](#geospatial-mcp-build-summary)

---

## Lab 2: Build an MCP server for the Registry of Open Data on AWS

In this lab you build a Model Context Protocol (MCP) server through **vibe coding** with
Kiro — describe what you want in natural language and Kiro generates the code.

### How this Geospatial MCP Build works

**Vibe coding = zero manual coding.** You won't write a single line of code by hand. Instead:

1. Copy a prompt from the lab guides (they look like: *"Create a script called..."*).
2. Paste it into Kiro (your AI coding assistant).
3. Kiro generates the code — complete, tested, production-ready.
4. Run the script and see it come to life.

That's it: natural language → working code.

**Build structure.** The Geospatial MCP Build follows a multipart journey. Each part defines a
tool and then has you build it through vibe coding.

### Prerequisites

Before starting, ensure you have:

- Completed **Lab 1** — Kiro IDE installed and configured.
- An **AWS Account** with permissions for Bedrock, Cognito, Lambda, IAM, CloudWatch.

### Getting started

Click **Part 1: Build Basic MCP Server** in the left navigation under Lab 2 to begin. Each
part builds on the previous one, so follow them in order. You won't write any code manually —
just copy prompts, paste into Kiro, and watch it happen.

---

## Part 1: Build Basic MCP Server

### Background

**What is an MCP server?** Model Context Protocol (MCP) is an open protocol that standardizes
how applications provide context to Large Language Models (LLMs). This Geospatial MCP Build
guides you through building custom MCP servers using Python and the **FastMCP** framework to
extend AI assistant capabilities.

By implementing MCP servers, you can create custom tools that let AI assistants like Kiro
perform specialized tasks — such as finding datasets in the Registry of Open Data — enabling
more powerful, tailored AI assistance for your needs.

**What you'll learn:** Create an MCP server agent with custom tools for searching the
Registry of Open Data on AWS.

**How you'll build it:** Copy the prompts below and paste them into Kiro. No coding required.

### Step 1: Open the project

A project folder has been created for you. Click **Open a project** and select the `Project`
folder.

- If asked whether you trust the authors of files in this folder, click **Yes, I trust the
  authors**.
- You may need to enable MCP so you can define and build your MCP server. If it says
  **Connect external tools and data sources**, you can safely skip this step.

Now that the workspace is set up, install some libraries.

### Step 2: Create a virtual environment

Open a new Terminal, then run the following.

Download and install `uv`:

```bash
pip install uv
```

Create a virtual environment for the libraries you'll need:

```bash
uv venv
```

Activate the virtual environment:

```bash
.venv\Scripts\activate
```

Install the libraries needed for the MCP server:

```bash
uv pip install mcp httpx pyyaml
```

### Step 3: Create a shell MCP server

Open the folder tree and create a new file named:

```
open_data_mcp.py
```

Paste the following code to create a shell MCP server, then save the file:

```python
import httpx
import yaml
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("OpenDataMCP")


def main():
    # Initialize and run the server
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
```

If you don't already have a Terminal open, open a new one and run the MCP server:

```bash
uv run open_data_mcp.py
```

Leave the terminal open. To stop the MCP server at any time, press **Ctrl-C**.

### Step 4: Connect Kiro to the shell MCP server

1. Click the **Kiro ghost icon** in the left navigator.
2. Choose **Edit MCP servers**.
3. Select all of the code in the MCP window and remove it, then paste the following to
   connect to your MCP server:

```json
{
  "mcpServers": {
    "fetch": {
      "command": "uvx",
      "args": ["mcp-server-fetch"],
      "env": {},
      "disabled": true,
      "autoApprove": []
    },
    "OpenDataMCP": {
      "command": "uv",
      "args": [
        "--directory",
        "C:\\workshop",
        "run",
        "open_data_mcp.py"
      ]
    }
  }
}
```

4. Save it (**Cmd/Ctrl-S**). The MCP Servers section should now say
   **OpenDataMCP Connected (0 tools)**.
5. Go back to the Terminal window and press **Ctrl-C** to stop the OpenDataMCP server. You'll
   see a keyboard interrupt in the terminal if you stopped it successfully.

> **Note:** Kiro could have done all of this for you, but it's useful to learn the Kiro IDE so
> you can find things later if you need to rename or adjust settings.

Next, use Kiro to create some tools.

---

## Lab 3: Build Search and Analysis Tools for the MCP server

In this lab you build search and analysis tools for the MCP server, again through vibe
coding. Describe what you want in natural language and Kiro generates the code.

**Vibe coding = zero manual coding.** Same loop as Lab 2: copy a prompt, paste into Kiro,
Kiro generates the code, run it.

### Prerequisites

- Completed **Lab 1** — Kiro IDE installed and configured.
- Completed **Lab 2** — OpenDataMCP built and running.

### Getting started

Click **Part 1: Create Search Tools** in the left navigation under Lab 3 to continue. Each
part builds on the previous one, so follow them in order.

---

## Part 1: Create Search Tools

### Background

Right now you have a working MCP server, but it doesn't do anything yet. MCP servers tell
agentic AI agents what they can do by exposing **tools**. Now you'll start vibe coding —
telling Kiro what you want, and Kiro creates the tools.

To start, you want the ability to search the Registry of Open Data. The Registry UI has a
text search bar but no programmatic way to search the catalog, so it isn't helpful to an AI
agent. Instead, you can use the [Registry of Open Data GitHub repo](https://github.com/awslabs/open-data-registry/tree/main/datasets),
which contains all of the dataset files (YAMLs) exposed in the Registry as dataset pages.

For example, searching for **NEXRAD** and viewing the YAML shows the title "NEXRAD on AWS"
and description "Real-time and archival data from the Next Generation Weather Radar (NEXRAD)
network." The `Name:` and `Description:` fields from the YAML map directly to what you see on
the NEXRAD Registry page. Since the dataset pages are nicely structured YAMLs and you want to
search them programmatically, you can ask Kiro to create a search tool.

### Step 1: Create a search tool

Open the chat panel if it's not already open. Vibe coding is a conversation — provide just
enough context in each prompt for Kiro to solve and write the code.

**Prompt:**

> Create an AWS Open Data MCP server, name it OpenDataMCP, use open_data_mcp.py, and create a
> tool to search for datasets by name, searching the yamls here
> (https://github.com/awslabs/open-data-registry/tree/main/datasets)

Kiro repeats back what you asked, reads the existing `open_data_mcp.py`, and asks permission
to read the YAML structure from GitHub — click **Accept** or **Trust** when prompted. It
reads the YAML structure, may install libraries, and may create a `requirements.txt` and a
`README`. Sometimes Kiro finds and fixes errors as it writes code.

Before trying the tool, **Reconnect** to the updated MCP server to see that you now have 1
tool. (If you didn't like what Kiro wrote, you can revert and try the prompt again.)

**Prompt:**

> Call the OpenDataMCP server and search for Sentinel-2

Kiro asks to call the new tool — click **Trust** so it can call your MCP server without
approval each time.

Kiro will initially read every single YAML from the Registry — but there are over 1,000
YAMLs to parse. After a minute it's likely still sifting through them. Tell Kiro why you
think there's a problem:

**Prompt:**

> There are over 1000 datasets, so the search is really slow. Can you make it faster?

> If you've waited more than a minute or two and Kiro hasn't returned, ask the slowness
> question above and reconnect the MCP server to force the connection to fail. If Kiro hasn't
> found the `index.ndjson` file, tell it: *"you could just read the index.ndjson file"*
> instead of opening many connections to RODA.

Reconnect the MCP server to pick up the latest changes, then ask again:

**Prompt:**

> Call the OpenDataMCP server and search for Sentinel-2

Now it takes just a few seconds to find datasets matching Sentinel-2.

### Step 2: Create a Get Dataset Info tool

Kiro found more than 10 Sentinel-2 datasets (or hit its limit). To drill down to the right
one, create a tool that returns detailed info about a specific dataset.

**Prompt:**

> Given the ability to search for a dataset, now create a new tool to return info about a
> specific dataset

Kiro adds a tool called `get_dataset_info` or similar. (Naming may vary — Kiro is a coding
assistant and can make slightly different decisions.) **Reconnect** to see 2 tools.

**Prompt:**

> Call the OpenDataMCP server and get Digital Earth Africa Sentinel-2 info

Kiro searches the YAMLs for names, descriptions, and tags matching Digital Earth Africa and
Sentinel-2, returning info like bucket names, regions, and a STAC endpoint. **Trust** any
actions so you don't have to accept each one (you can change the allowlist later in Settings).

### Step 3: Create a Search by Tag tool

Add another way to search — by tags — which is a great way to subset the catalog.

**Prompt:**

> Given the list of valid tags
> (https://github.com/awslabs/open-data-registry/blob/main/tags.yaml), now create a new tool
> to return a list of datasets based on one or more tags found in the dataset yaml

Giving Kiro the tags file (a fixed list of valid tags) makes search faster by validating the
tag before searching. **Reconnect** to see 3 tools.

**Prompt:**

> Call the OpenDataMCP server and search for any datasets that contain the tag "geospatial"

You may get back many datasets and use up credits, or Kiro may have set a limit and returned
only ~10. If you see a "Summarization failed" error, Kiro ran out of credits trying to
summarize. Refine the tool:

**Prompt:**

> The search by tags tool could be better. Just return the number of datasets found and the
> Name of each dataset, and I can use another tool to fetch specifics about a dataset that I
> want to investigate more. And do not limit the number of datasets returned - get all
> datasets with tag geospatial.

**Reconnect**, then test again:

> Call the OpenDataMCP server and search for any datasets that contain the tag "geospatial"

Make sure Kiro returns the entire list (roughly 200 datasets). You can verify against the
Registry of Open Data by entering `tags:geospatial` in the Search datasets bar.

Now try two tags, one with a space:

**Prompt:**

> Call the OpenDataMCP server and search for any datasets that contain natural resource tag
> and geospatial tag

Kiro reports what it found and how. If it matched **ANY** of the tags (~199 datasets) rather
than **BOTH**, fix it:

**Prompt:**

> Searching by multiple tags isn't working as I expected. When I search for datasets with
> geospatial and natural resource tags, I meant the dataset must have BOTH tags in order to
> be a valid match. Can you fix it

Kiro requires all tags to match. **Reconnect**, then test again:

> Call the OpenDataMCP server and search for any datasets that contain natural resource tag
> and geospatial tag

### Tips: if you get an error, the session summarizes and closes, or you get a bad response

Kiro can make mistakes. The `search_by_tags` tool will likely cause a problem — left in the
build deliberately so you get the experience of debugging without editing code. The
general rule is to ask Kiro to fix it by:

- **Describe the problem** — tell Kiro what's going wrong.
- **Describe what it should do** — tell Kiro what you expected but didn't get.

Example:

> The search_by_tags tool isn't working right. It returned over 1000+ datasets when searching
> for datasets that contain the geospatial tag, but it should have returned 190.

In that case Kiro was doing substring matching (matching all cases of the tag) instead of
exact matches; it fixed it and retested successfully.

If Kiro keeps summarizing and closing the session, it's in a bad state — type **Stop** in the
chat and hit enter, close all sessions, and start over with your last request.

You can also be prescriptive about things Kiro may not have found, such as the `index.ndjson`
file that lists all RODA datasets in a single file:

> you could use the ndjson file instead of searching the repo, because this is still very slow

This is an incomplete instruction on purpose (the file is really `index.ndjson`) to show how
Kiro tries to find the file, fails, and keeps trying files that start or end with `ndjson`.

---

## Part 2: Create STAC Tools

### Background

**What is STAC?** [STAC](https://stacspec.org/en) (SpatioTemporal Asset Catalog) is a
specification to describe geospatial information, usually with an endpoint you can call
programmatically. You send a STAC endpoint a bounding box and ask for all the data it knows
about for that patch of Earth, with optional parameters like cloud cover to reduce cloudy
optical images. USGS Landsat has a STAC endpoint under "Explore."

**Why do we need it?** An agentic AI agent will want to search datasets programmatically via
a well-defined API. Not all geospatial datasets in the Registry have a STAC catalog, but when
they do, the endpoint appears in the dataset YAML, and we'll want to use it.

### Step 1: Get a STAC endpoints tool

**Prompt:**

> Create a new tool that will search for STAC (https://stacspec.org/en) endpoints within the
> dataset yamls

Kiro reads the spec, understands how STAC is organized and what STAC endpoints look like,
then adds a new STAC search tool. You may see Kiro create helper Python files to inspect
YAMLs or the STAC spec (e.g., to find where STAC URLs live); it cleans them up when done, but
reading them shows how Kiro solves problems. **Reconnect** to the updated server.

**Prompt:**

> Call the OpenDataMCP server and get the Digital Earth Africa Sentinel-2 STAC endpoints

Click **Trust** to let Kiro call the tool. You may get 1 or 2 STAC endpoints (the YAML has 2,
but proceeding with at least 1 is fine).

### Step 2: Get data from a STAC tool

**Prompt:**

> Create a new tool that will query a STAC (https://stacspec.org/en) endpoint for a dataset
> and return the list of images available

Note the prompt doesn't repeat the STAC spec variables (location, time, cloud cover) — Kiro
uses them from the spec. **Reconnect**, then:

**Prompt:**

> Call the OpenDataMCP server and using the Digital Earth Africa STAC endpoint, find some
> recent Sentinel-2 imagery over Boston with 20% or less cloud cover

The Digital Earth Africa endpoint only covers Africa, so it won't have Boston data — Kiro
figures out you really want Sentinel-2 and queries for that. It returns useful info like
percent cloud cover, available bands (RGB, NIR, SWIR, etc.), and platform (Sentinel-2B).

To preview an image:

**Prompt:**

> Create a tool to fetch a thumbnail image for a scene such as S2A_19TCG_20241219_0_L2A from
> the Sentinel-2 STAC endpoint and add that tool to the OpenDataMCP server

Kiro may note that "MCP tools typically return text/JSON data, not binary image data," and
instead create a tool that returns the thumbnail URL and metadata — which is what we want.
**Reconnect**, then:

**Prompt:**

> Call the OpenDataMCP server and fetch a thumbnail image for S2A_19TCG_20241219_0_L2A from
> the Sentinel-2 STAC endpoint

Kiro finds a thumbnail such as
`https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/19/T/CG/2024/12/S2A_19TCG_20241219_0_L2A/thumbnail.jpg`
— showing the arm of Cape Cod, Massachusetts, with some cloud cover and snow (December).

> If Kiro talks about the thumbnail but doesn't give a link, ask it for the link. It may also
> save the thumbnail to your project — check the files folder.

---

## Part 3: Create Analysis Tools

### Why add analysis tools?

Users who aren't trained in geospatial or environmental science might misuse the data (e.g.,
mistaking cloud cover for smoke in a fire-prone region). Analysis tools like NDVI help such
users get correct scientific output. You'll create a few examples — the possibilities are
endless.

### Step 1: Create the first analysis tool — NDVI

Open the chat panel if it's not open. Start with the Normalized Difference Vegetation Index
(NDVI), using an AWS SageMaker notebook that shows the NDVI algorithm and examples.

**Prompt:**

> Now let's create a Normalized Difference Vegetation Index (NDVI) tool. Use this notebook for
> the right algorithm to calculate NDVI
> (https://studiolab.sagemaker.aws/import/github/https://github.com/aws-samples/aws-smsl-geospatial-analysis-deforestation/blob/main/geospatial_analysis_deforestation.ipynb).

This step may take a while (Kiro installs libraries and learns band math). Let it run while
it's reporting progress. **Reconnect** to use the new NDVI tool, then try a drought analysis
for Lake Shasta, California:

**Prompt:**

> Lets do a drought analysis using NDVI. Compare Shasta lake in California from 2021 (extreme
> drought year) and 2017 (recovery year).

Kiro may realize the MCP server runs in its own environment and try to install numpy and
other libraries. Tell it about the environment to speed things up:

**Prompt:**

> OpenDataMCP is running in a uv environment called venv

Kiro installs the right libraries and tests them before proceeding. When done, ask the
drought question again:

> Lets do a drought analysis using NDVI. Compare Shasta lake in California from 2021 (extreme
> drought year) and 2017 (recovery year).

### Step 2: Create a visualization tool

Humans are visual. The SageMaker notebook had a side-by-side comparison — get Kiro to make
one (it saves an image in the project folder).

**Prompt:**

> Create a new tool for the OpenDataMCP server that shows a side by side plot like on line 24
> in the notebook
> (https://studiolab.sagemaker.aws/import/github/https://github.com/aws-samples/aws-smsl-geospatial-analysis-deforestation/blob/main/geospatial_analysis_deforestation.ipynb)

Kiro saves a `.png` in the file explorer. If it only shows the plot inline, ask it to save:

**Prompt:**

> This is great, but can you also save these visualizations as files in the project so I can
> review them later.

If the legend overlaps a pane, have Kiro fix it:

**Prompt:**

> This looks great, but the legend was written on top of the righthand pane covering part of
> the image. Can you fix that?

Spend time here to make the side-by-side comparison look right — you'll reuse it for other
analyses.

### Step 3: Create a classifier tool

Some users want to know what the colors mean (e.g., "Dead forest," "Scrub," "Open Forest,"
"Moderately Dense Forest," "Very Dense Forest"). Have Kiro classify using the SageMaker
notebook.

**Prompt:**

> Create a new tool that will create classes and apply to NDVI results, following lines 25-28
> in the notebook
> (https://studiolab.sagemaker.aws/import/github/https://github.com/aws-samples/aws-smsl-geospatial-analysis-deforestation/blob/main/geospatial_analysis_deforestation.ipynb)

Kiro adds a tool called `classify_ndvi` or similar. **Reconnect**, then:

**Prompt:**

> Call the OpenDataMCP server to plot the Shasta lake in California comparison from 2021
> (extreme drought year) and 2017 (recovery year) and classify the NDVI results

If the classifier comparison isn't saved as a file, tell Kiro you want it saved.

### Step 4: Create an NDBI tool

For a non-vegetation index, use NDBI (Normalized Difference Built-up Index), which uses SWIR
and NIR bands to identify urban, concrete, and built-up areas. With no notebook, provide the
algorithm in the prompt:

**Prompt:**

> Create a new tool that calculates NDBI (Normalized Difference Built-up Index): Focuses on
> short-wave infrared (SWIR) and near-infrared (NIR) bands to accurately identify urban,
> concrete, and built-up areas. Use this algorithm: NDBI = (SWIR-NIR)/(SWIR+NIR) Then show an
> example - before and after

**Reconnect**, then try Las Vegas between 2018 and 2023:

**Prompt:**

> Call the OpenDataMCP server to compare NDBI for the Las Vegas area between 2018 and 2023

Watch the months it compares — seasonal differences shouldn't show up as change. Add that as
context if needed. Kiro does the side-by-side comparison, classifies the output, and gives a
summary.

### Step 5: Create an NDWI tool (do it yourself)

By now you're in a groove: (1) prompt Kiro to create the tool, (2) reconnect, (3) try it,
(4) refine it. Now do it yourself — create a Normalized Difference Water Index (NDWI) tool and
compare Matanuska Glacier in Alaska from 2020 to 2026. Follow the steps: find the algorithm,
define the prompt, test it with Alaska.

Notes on what Kiro might do:

- Did it grab bad months to compare, like June vs July? That's a poor comparison due to
  seasonal change.
- Try **2018 to 2026** — it should grab the same months (June 2018 and June 2026).
- Example analysis: 753,245 net pixels shifted toward wet — 12.6% of the study area
  transitioning from dry/frozen to wet/melting, indicating the glacier is melting.

Try Exit Glacier in Alaska as well, checking the comparison months (you can tell Kiro to
compare months within the same seasons).

### Tips: if Kiro suddenly summarizes

- If Kiro didn't automatically run the visualization, ask: *"Can you run the visualization of
  the side by side comparison for the Shasta lake NDVI?"*
- You'll eventually run out of credits or hit your session limit. Kiro summarizes the session
  and creates a new one to continue — just keep going with your next prompt.
- Kiro is resilient. Reconnecting the MCP server mid-call may fail a task, but it usually
  retries.
- If Kiro seems stuck in a loop, ask: *"Are you still working on this?"* It retries the last
  command and watches for it taking too long.
- If you get "An unexpected error occurred while processing your input," close all active
  chats, restart Kiro, and pick up where you left off. Re-establish context first, e.g.:
  *"Given the current project, Call the OpenDataMCP server and then create your tool..."*

---

## Part 4: Kiro Powers

### What is a Kiro Power?

Kiro Powers are specialized, installable capability modules for the Kiro AI-powered
development environment. They combine MCP servers, workflow guidelines, and automation hooks
into single, on-demand packages, giving your AI agent instant expertise in specific tools
only when you need them.

Like Neo instantly downloading martial-arts expertise in *The Matrix*, powers give the Kiro
agent instant access to specialized knowledge. The key is **dynamic context loading**:
traditional MCP implementations load every tool upfront, but powers activate only when
relevant. So when you mention "STAC," the Kiro geospatial power loads its tools and best
practices.

### Step 1: Load some powers

Copy this Kiro link and paste it into your browser on the remote machine (where Kiro runs):
[https://kiro.dev/powers/](https://kiro.dev/powers/). Scroll down to **Browse Powers**, then:

- Search for **Strands** → **Add to Kiro** → **Install**.
- Click **Back to Powers**, search for **agentcore** → **Add to Kiro** → **Install**.
- Search for **CDK** → **Add to Kiro** → **Install**.

Some Kiro powers live in GitHub repos too. Copy this link and paste it into your browser:
[https://github.com/aws-samples/sample-geospatial-kiro-power-pack](https://github.com/aws-samples/sample-geospatial-kiro-power-pack).
Open a new terminal in the workshop folder, clone the geospatial power repo, and change into
it:

```bash
git clone https://github.com/aws-samples/sample-geospatial-kiro-power-pack.git
cd ./sample-geospatial-kiro-power-pack/
```

Follow the Installation instructions from the repository and install all of the MCP servers
listed, then configure them. You do **not** need to create a new `uv` environment — you're
already in one that's activated. Your existing MCP servers are untouched, and you should now
have the additional geospatial powers.

### Step 2: Create a demo project

Next, give Kiro a large prompt to build a workable demo using demo data it creates and real
data it must find. It will create components in AWS and deploy them, producing a fully
functional Insurance Agency app. **This part alone takes ~30 minutes.**

Open the chat panel, and set the model to **Claude Opus 4.8 or better** for this project.

> You can't fully ignore Kiro as it builds — it will ask you to trust installing libraries,
> and may ask you to choose what to build or how to deploy a component.

**Prompt:**

> Given the current project (that created an OpenDataMCP server), I want to create a demo to
> show how to write a strands agents agent. I want the agent to represent a fictional
> Insurance Agency support chatbot, that is geospatially aware, aware of Sentinel-1 and
> Sentinel-2 data, understands how to use the OpenDataMCP that we just created, and has tools
> to do basic flooding analysis for insurance claims. Then I want to deploy that same agent to
> Amazon Bedrock agentcore runtime. I want to use the CDK to deploy, and you must use the
> us-east-1 region.
>
> I want you to create the code, make sure it runs, deploy it to my account using the CLI,
> fixing bugs along the way. Document all the deployment steps in a markdown file. We want to
> test the demo using real imagery and flooding analysis of the Maui, Hawaii flooding in 2026.

Kiro activates the powers it needs, breaks the problem into pieces, and works through each.
Unlike earlier labs, this creates AWS resources in your account. Keep an eye on Kiro — it
will ask several times to allow/trust new commands.

To watch what's deploying, open the AWS Console, search for **CloudFormation**, and open it.
Ignore the workshop stacks (`kiro-ec2`, `idc`). You should see a new `CDKToolkit` stack (and
then the app stack) appear as Kiro launches services.

Maui is often cloudy, so Kiro may choose Sentinel-1 SAR imagery over Sentinel-2 optical. When
done, Kiro gives a confirmation message with hints for using the app. Ask for a test case:

**Prompt:**

> can you give me a test sample that I can try?

Kiro points you to a README or DEPLOYMENT markdown for usage, or you can ask it to deploy the
app and run the first sample. Open your browser to `http://localhost:8081/` (the AgentCore UI)
and enter a sample prompt:

**Sample prompt 1:**

> I'm a claims adjuster at Meridian Mutual. For claim FL-2026-0042, the insured property is in
> central Maui near Kahului, Hawaii (bbox -156.50,20.87,-156.44,20.92). It flooded during the
> March 2026 Kona low storm that peaked March 14-18. Use Sentinel-1 radar to compare a before
> scene around March 6 against a during-storm scene around March 18, then give me a
> preliminary claim assessment.

**Sample prompt 2:**

> Claim #PS-2026-0417: A policyholder at 123 Halemaʻumaʻu Pl, Kihei, Maui (approx -156.45,
> 20.76) reports flood damage from the late February 2026 storms. Their home is insured for
> $850,000 on a small ~0.002 km² lot.
> Please:
> 1. Find a low-cloud Sentinel-2 scene over south Maui between 2026-02-20 and 2026-03-01.
> 2. Run a flood-extent (NDWI) analysis on a small box around Kihei (about -156.46, 20.74 to
>    -156.44, 20.77).
> 3. Give me an indicative claim-triage tier assuming floodwater reached the structure.
> 4. Note the key caveats a human adjuster should keep in mind.

Sample 2 has low cloud cover and finds a high risk of the entire structure being inundated
(likely 100% loss), with a caveat for the human adjuster to vet on a site visit.

Then explore the app and consider changes. For example, you shouldn't require the insurance
agent to pick before/after dates — but the dates must be close to the event yet avoid
season-change noise. How would you get Kiro to address that?

### Tips

- Kiro may deploy the insurance app to your AWS account, which is fine, but you can also just
  run it locally from the Kiro Terminal: `agentcore dev`.
- If you get signed out, go to the main page
  (`https://catalog.us-east-1.prod.workshops.aws/event/dashboard/en-US`) and use the
  RDPUsername and RDPPassword to log back in.

---

## Geospatial MCP Build summary

Participants built a complete MCP server entirely through vibe coding — eleven custom tools
for searching, retrieving, and analyzing data from the Registry of Open Data on AWS — then
packaged the expertise with Kiro Powers and deployed a Strands agent to Amazon Bedrock
AgentCore.

### Final MCP server capabilities (eleven tools)

1. `search_datasets` — find datasets by name
2. `get_dataset_info` — get detailed dataset information
3. `search_datasets_by_tags` — search using one or more tags (BOTH-match logic)
4. `search_stac_endpoints` — find STAC-enabled datasets
5. `query_stac_endpoint` — query for imagery by bbox / time / cloud cover / collection
6. `get_stac_thumbnail` — retrieve thumbnail URLs for scenes
7. `calculate_ndvi` — compute vegetation index for a scene
8. side-by-side visualization — plot and compare two scenes as an image
9. `classify_ndvi` — classify NDVI results into land-cover categories
10. `calculate_ndbi` — compute built-up index for urban analysis
11. `calculate_ndwi` — compute water index for water/melt detection

### Key learnings

- **Vibe coding workflow:** copy prompt → paste into Kiro → review generated code → test →
  iterate with follow-up prompts.
- **Debugging without coding:** describe the problem and the expected behavior; Kiro analyzes
  and fixes, then you retest.
- **Context is key:** links to specs (STAC), data sources (GitHub repos), examples of
  expected behavior, and constraints all improve results.
- **Trust and permissions:** Kiro asks permission for external operations; "Trust" remembers
  them, and they can be managed in Settings.
- **Control for seasonality:** compare the same months across years so real change isn't
  masked by seasonal noise.
- **Powers give instant expertise:** they load only when relevant (dynamic context loading),
  and Kiro can carry a project from local code to a deployed AWS agent (creating real
  resources like CloudFormation stacks along the way).

### Resources

- Kiro IDE: https://kiro.dev/
- Registry of Open Data on AWS: https://registry.opendata.aws/
- STAC Specification: https://stacspec.org/en
- Open Data Registry GitHub: https://github.com/awslabs/open-data-registry
