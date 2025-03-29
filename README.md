# EpOikoS Simulation

This project runs a [FastAPI](https://fastapi.tiangolo.com) Webserver as well as the [Faststream Plugin](https://faststream.airt.ai/latest/getting-started/integrations/fastapi/) to integrate with [NATS](https://nats.io), a highly performant messaging system.

## Installation

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

- `clients/`: Contains the clients for the different services used in the application in our case
  - `milvus.py`: Contains the Milvus client.
  - `nats.py`: Contains the NATS client.
  - `tinydb.py`: Contains the TinyDB client.
- `config/`: Contains the configuration files. It uses [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) to manage the settings. 
- `data/`: The data directory will only be created once the application is running. It contains the data storage for the application.
- `models/`: Contains the logic of our entities in the application. Mainly
  - `agent.py`: Contains the Agent model.
  - `simulation.py`: Contains the Simulation model.
- `routers/`: Contains the FastAPI routers.
- `subscribers/`: Contains the NATS subscribers.
- `main.py`: The main entrypoint for the FastAPI application.