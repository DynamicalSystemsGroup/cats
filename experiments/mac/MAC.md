# [Multi-Agent Collaboration (MAC) Demo Template intended for CAT of Order Composition](./car_demo.py)

**Description:** LangGraph demo with collaborating LLM agents (research + chart outline). Separate from the CAT mesh in [DEMO.md](../../docs/DEMO.md)—no IPFS, Docker, or CAT node required.
- **Purpose:** *CAT Order Composition*
- **Design Context:** *[Multi-Agent Collaboration (MAC) for CATs using Content-Addressable Router (CAR) facilitated by the Architectural purpose of CATs as a Function](https://github.com/DynamicalSystemsGroup/cats/wiki/Research-Articles#multi-agent-collaboration-mac-for-cats-using-content-addressable-router-car-facilitated-by-the-architectural-purpose-of-cats-as-a-function)*
- **Status:** This experiment implements **Action/Control-plane orchestration patterns only** (multi-agent graph, routers, `ToolNode`). **CAR**, **CAT Order** composition, BOM governance, and cadCAD policy nodes are **not yet integrated**. `[cats_demo.py](../../notebooks/cats_demo.py)` remains the demo of the mesh as built today; `[car_demo.py](./car_demo.py)` is an early LangGraph shell toward the June 2024 MAC/CAR vision.

#### Demonstrates the following

`car_demo.py` builds a small multi-agent collaboration graph using LangChain + LangGraph:

1. Two specialized agents sharing one conversation (MessagesState):
  - Researcher — has Tavily web search; gathers current information
  - Chart generator — no tools; turns research into a chart outline/description
2. Orchestration via a state graph:
  - researcher → may call Tavily (call_tool) → back to researcher
  - → hands off to chart_generator
  - → can loop back to researcher until someone emits FINAL ANSWER
  - Routers decide: run tools, switch agents, or stop
3. Operational wiring:
  - API keys from `.env` (OpenAI, LangChain/LangSmith, Tavily)
  - LangSmith tracing (LANGCHAIN_TRACING_V2, project "Multi-agent Collaboration")
  - Marimo UI with a Run button so the graph doesn’t fire on every cell rerun

#### Steps:

##### 1. [Create the environment](../../docs/ENV.md) and install dependencies:

```bash
# CATs working directory
cd cats
uv sync --extra ops
uv pip install -r experiments/mac/requirements-mac.txt
```

The base install includes `python-dotenv`; `--extra ops` adds Marimo. `experiments/mac/requirements-mac.txt`
adds the LangChain/LangGraph packages used only by this experiment — it's installed with `uv pip install`
directly into the project's `.venv` and isn't part of `pyproject.toml`/`uv.lock`, since it's experiment-only
and not a package extra of `cats`. `uv run` (below) uses this `.venv` automatically — no manual activation
needed.

##### 3. Configure API keys *in the repo root* (`.env` is gitignored; same file `cats` loads on import — see [`ENV.md`](../../docs/ENV.md)):

```bash
OPENAI_API_KEY=sk-...
LANGCHAIN_API_KEY=...
TAVILY_API_KEY=...
```

- **OpenAI** — LLM calls (`gpt-4o-mini` by default in the notebook)
- **LangChain / LangSmith** — optional tracing (`LANGCHAIN_TRACING_V2=true`)
- **Tavily** — web search tool for the research agent

##### 4. Run the Marimo notebook: [Demo](./car_demo.py)

```bash
uv run marimo edit experiments/mac/car_demo.py
```

Work through the cells top to bottom, then click **Run multi-agent demo** to invoke the graph. Each run calls OpenAI and Tavily; ensure your OpenAI account has available quota.

- **Optional:** Shut down Marimo with `Ctrl+C` in the terminal running the editor.
