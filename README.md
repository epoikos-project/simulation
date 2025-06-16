# EpOikoS Simulation

This project runs a [FastAPI](https://fastapi.tiangolo.com) Webserver as well as the [Faststream Plugin](https://faststream.airt.ai/latest/getting-started/integrations/fastapi/) to integrate with [NATS](https://nats.io), a highly performant messaging system.

## Installation

### Clone the GitHub Repo

Clone the repository to your local machine using the following command:
```shell
git clone https://github.com/epoikos-project/simulation epoikos-simulation
cd epoikos-simulation
```

### Prerequisites

Make sure to have NATS installed. You can follow the [installation guide](https://docs.nats.io/running-a-nats-service/introduction/installation). Run the NATS server with the config located in `config/nats-server.conf` to enable the jetstream storage:
```shell
nats-server -c config/nats-server.conf
```
### Python Setup

Install Packages using [uv](https://docs.astral.sh/uv/getting-started/installation/).
```shell
uv sync
```

Enable precommit hooks:
```shell
uv run pre-commit
```

This will ensure that you only push formatted code to github. _Be aware that commits may fail at the first attempt_.

### Environment Variables
Copy the `.env.example` file to `.env` and update the values as needed.

```shell
cp .env.example .env
```

### Simulation Tick Limit

You can optionally limit the maximum number of simulation ticks by setting the `MAX_STEPS` constant in `config/base.py`.
By default (`MAX_STEPS=None`), the simulation will run indefinitely (until manually stopped).

```python
# in config/base.py
MAX_STEPS = 100  # run at most 100 ticks, override for benchmarking/profiling
```

### Cluster Optimization Flag

Enable or disable asynchronous cluster‐based execution via the `CLUSTER_OPTIMIZATION` constant in `config/base.py` (default `True`).
When disabled (`CLUSTER_OPTIMIZATION=False`), agents are ticked sequentially in a fixed order
  (tick1→agent1, tick1→agent2, tick2→agent1, ...) for deterministic fallback behavior.

### Legacy Sequential Workflow

When cluster optimization is disabled (fallback mode), the simulation follows this legacy sequence each tick:
1. Backup current DB state
2. Increment and persist the global tick counter
3. Call `world.tick()` to update world resources
4. Broadcast a `SimulationTickMessage` for the new tick
5. Sequentially load and run each agent (`agent.trigger()`) in sorted ID order
6. After all agents have ticked, perform periodic DB backups for persistence

This workflow ensures a clear, deterministic order for world and agent updates in fallback mode.

### Asynchronous Cluster Optimization Workflow

When `CLUSTER_OPTIMIZATION=true` (the default), the simulation uses an out‑of‑order, per‑cluster scheduler to parallelize work across independent agent groups while respecting cross‐cluster dependencies:

1. **Initial clustering**: at startup, `ClusterScheduler` computes initial clusters of agents (connected by proximity) via `ClusterManager.compute_clusters()`, and publishes a `SimulationClustersMessage` (tick=0) with the initial topology.
2. **Cluster loops**: for each cluster, `_cluster_loop` runs in its own asyncio Task, looping over ticks:
   - wait on an unblock Event,
   - call `ClusterExecutor.run(cluster, tick)` to tick resources and agents in that cluster,
   - record the tick and notify the controller.
3. **Controller loop** (`_controller_loop`): after each cluster tick:
   - recompute clusters based on the latest agent positions,
   - save a snapshot of agent positions and dependency edges to TinyDB,
   - publish a `SimulationClustersMessage` for the new cluster topology,
   - reconcile cluster tasks (merge/split) to match the new topology,
   - unblock any cluster loops whose dependencies (based on tick gap, vision range, and movement) are satisfied.
4. **ClusterExecutor**: for each cluster/tick, ticks resources in range of the cluster (`world.tick_resources_for_agents`) and triggers all agents in parallel, then publishes a `SimulationTickMessage`.
5. **Shutdown & flush**: when the simulation stops, `ClusterScheduler.stop()` cancels controller and cluster Tasks, then runs any lagging clusters up to the maximum tick in‐line to ensure no cluster falls behind on shutdown.

This optimized workflow maximizes parallelism of independent clusters while guaranteeing correctness via dynamic dependency checks.

> [!IMPORTANT] 
> Make sure to update the envs to your local setup! Particularly the OPENAI_API_KEY.


```conf
# Replace in .env
OPENAI_APIKEY=<your-key>
```

## Running the Application
Start the application using the following command:
```shell
uv run fastapi dev
```
Alternatively, if the above does not work run it using uvicorn:
```shell
uv run uvicorn main:app --port 8000 --reload
```

Once the application is running, you can access the API documentation is available at [`http://localhost:8000/docs`](http://localhost:8000/docs).

## File Structure

```
.
├── README.md
├── clients
│   ├── milvus.py
│   ├── nats.py
│   └── tinydb.py
├── config
│   ├── base.py
│   ├── milvus.py
│   ├── nats-server.conf
│   ├── nats.py
│   └── tinydb.py
├── data
│   ├── jetstream
│   ├── milvus
│   └── tinydb
├── main.py
├── messages
│   ├── agent
│   ├── world
│   └── message_base.py
├── models
│   ├── agent.py
│   └── simulation.py
├── routers
│   ├── agent.py
│   ├── debug.py
│   ├── simulation.py
│   └── world.py
├── subscribers
│   └── world.py
└── uv.lock
```

- `clients/`: Contains the clients for the different services used in the application; in our case, there are three clients. For more details, see the [Clients README](clients/README.md).
  - `milvus.py`: Contains the Milvus client.
  - `nats.py`: Contains the NATS client.
  - `tinydb.py`: Contains the TinyDB client.
- `config/`: Contains the configuration files. It uses [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) to manage the settings. 
- `data/`: The data directory will only be created once the application is running. It contains the data storage for the application.
- `messages/`: This folder is used for an aligned message protocol to be used on the EventStream. It uses [pydantic](https://docs.pydantic.dev/latest/) to define the messages. You can read more about messages in the [Messages README](messages/README.md).
- `models/`: Contains the logic of our entities in the application. Mainly
  - `agent.py`: Contains the Agent model.
  - `simulation.py`: Contains the Simulation model.
- `routers/`: Contains the FastAPI routers.
- `subscribers/`: Contains the NATS subscribers.
- `main.py`: The main entrypoint for the FastAPI application.