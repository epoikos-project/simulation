# EpOikoS Simulation

This project runs a [FastAPI](https://fastapi.tiangolo.com) Webserver as well as the [Faststream Plugin](https://faststream.airt.ai/latest/getting-started/integrations/fastapi/) to integrate with [NATS](https://nats.io), a highly performant messaging system. This project is best used in conjunction with the [EpOikoS UI](https://github.com/epoikos-project/ui-configuration), which allows you to easily manage your simulation environment.

## Installation

### Clone the GitHub Repo

Clone the repository to your local machine using the following command:
```shell
git clone https://github.com/epoikos-project/simulation epoikos-simulation
cd epoikos-simulation
```

### Devcontainer Setup (Recommended)
If you are using [Visual Studio Code](https://code.visualstudio.com/), you can open the project in a dev container. This will provide you with a consistent development environment and simplify the setup process.
You can do this by opening the command palette (Ctrl+Shift+P) and selecting "Remote-Containers: Open Folder in Container...". This will build the container based on the `devcontainer.json` file in the `.devcontainer` directory.

The dev container will automatically install all the necessary dependencies and set up the environment for you.


### Manual Setup (Alternative)

#### NATS Server
Make sure to have NATS installed. You can follow the [installation guide](https://docs.nats.io/running-a-nats-service/introduction/installation). Run the NATS server with the config located in `config/nats-server.conf` to enable the jetstream storage:
```shell
nats-server -c config/nats-server.conf
```

#### PostgreSQL
Make sure to have PostgreSQL installed. You can follow the [installation guide](https://www.postgresql.org/docs/current/tutorial-install.html). 
If you are on macOS, you can use [Homebrew](https://brew.sh/) to install PostgreSQL:
```shell
brew install postgresql
```

#### Python Setup

Install Packages using [uv](https://docs.astral.sh/uv/getting-started/installation/).
```shell
uv sync
```

Enable precommit hooks:
```shell
uv run pre-commit
```

This will ensure that you only push formatted code to github. _Be aware that commits may fail at the first attempt_.

#### Environment Variables
Copy the `.env.example` file to `.env` and update the values as needed.

```shell
cp .env.example .env
```

> [!IMPORTANT] 
> Make sure to update the envs to your local setup! Particularly the OPENAI_API_KEY and DB_URL.


```conf
# Replace in .env
OPENAI_APIKEY=<your-key>
DB_URL=<your-db-url>
```

#### Database Migration
Run the database migrations using Alembic to set up the database schema:
```shell
uv run alembic upgrade head
```

#### Running the Application
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
├── alembic.ini
├── main.py
├── utils.py
├── uv.lock
├── clients/
│   ├── __init__.py
│   ├── db.py
│   ├── milvus.py
│   ├── nats.py
│   └── README.md
├── config/
│   ├── __init__.py
│   ├── base.py
│   ├── db.py
│   ├── milvus.py
│   ├── nats-server.conf
│   ├── nats.py
│   └── openai.py
├── data/
│   ├── database.db
│   ├── jetstream/
│   ├── milvus/
│   └── tinydb/
├── engine/
│   ├── grid.py
│   ├── sentiment.py
│   ├── context/
│   ├── llm/
│   ├── runners/
│   └── tools/
├── messages/
│   ├── __init__.py
│   ├── message_base.py
│   ├── README.md
│   ├── agent/
│   ├── simulation/
│   └── world/
├── migrations/
├── routers/
│   ├── __init__.py
│   ├── agent.py
│   ├── ...
│   └── world.py
├── schemas/
│   ├── action_log.py
│   ├── ...
│   └── world.py
├── services/
│   ├── action_log.py
│   ├── ...
│   ├── simulation.py
│   └── world.py
└── subscribers/
    ├── __init__.py
    ├── agent.py
    ├── ...
    └── world.py
```

- `clients/`: Contains the clients for the different services used in the application. For more details, see the [Clients README](clients/README.md).
  - `db.py`: Contains the database client.
  - `milvus.py`: Contains the Milvus client.
  - `nats.py`: Contains the NATS client.
- `config/`: Contains the configuration files. It uses [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) to manage the settings.
- `data/`: The data directory contains the data storage for the application.
- `engine/`: Contains the core simulation engine components.
  - `grid.py`: Grid-based simulation logic.
  - `sentiment.py`: Sentiment analysis functionality.
  - `context/`: Context management for agents.
  - `llm/`: Large language model integrations.
  - `runners/`: Simulation and agent runners.
  - `tools/`: Various tools for the simulation engine.
- `messages/`: This folder is used for an aligned message protocol to be used on the EventStream. It uses [pydantic](https://docs.pydantic.dev/latest/) to define the messages. You can read more about messages in the [Messages README](messages/README.md).
- `migrations/`: Database migration files using Alembic.
- `routers/`: Contains the FastAPI routers.
- `schemas/`: Pydantic schemas for data validation and serialization.
- `services/`: Business logic and service layer components.
- `subscribers/`: Contains the NATS subscribers.
- `main.py`: The main entrypoint for the FastAPI application.
- `utils.py`: Utility functions used throughout the application.
- `pyproject.toml`: Project configuration and dependencies.
- `alembic.ini`: Alembic configuration for database migrations.