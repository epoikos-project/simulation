# Epoikos Simulation

## Installation

### Prerequisites

1. Make sure to have NATS installed. You can follow the [installation guide](https://docs.nats.io/running-a-nats-service/introduction/installation).
2. Run the NATS server with the config located in `config/nats-server.conf` to enable the jetstream storage:
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

Once the application is running, you can access the API documentation is available at [`http://localhost:8000/docs`](http://localhost:8000/docs).