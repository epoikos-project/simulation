import asyncio
from fastapi import APIRouter

from loguru import logger
from nats.js.api import StreamConfig
from broker import Broker

router = APIRouter(prefix="/simulation", tags=["Simulation"])


@router.post("")
async def create_simulation(name: str, broker: Broker):
    try:
        await broker.stream.add_stream(
            StreamConfig(name=f"simulation-{name}", subjects=[f"simulation.{name}.*"])
        )
    except Exception as e:
        logger.error(f"Error creating simulation: {e}")
        return {"message": f"Error creating simulation"}
    return {"message": "Simulation created successfully!"}


@router.post("/{simulation_id}/replay")
async def replay(simulation_id: str, broker: Broker):
    js = broker.stream

    # Get stream info to fetch the total number of messages in the stream
    stream_info = await js.stream_info(f"simulation-{simulation_id}")
    total_messages = (
        stream_info.state.messages
    )  # Total number of messages in the stream
    logger.debug(
        f"[REPLAY {simulation_id}] - Total messages available: {total_messages}"
    )

    # Pull messages from the stream in batches as needed
    sub = await js.pull_subscribe(
        subject=f"simulation.{simulation_id}.*", stream=f"simulation-{simulation_id}"
    )
    messages_retrieved = 0
    batch_size = 10  # Adjust the batch size as needed

    while messages_retrieved < total_messages:
        try:
            # Fetch the next batch of messages, up to the remaining messages
            remaining_messages = total_messages - messages_retrieved
            batch_to_fetch = min(batch_size, remaining_messages)

            msgs = await sub.fetch(batch_to_fetch, timeout=5)

            # Process and acknowledge the messages
            for msg in msgs:
                await broker.publish(
                    subject=msg.subject.replace(
                        simulation_id, f"{simulation_id}-replay"
                    ),
                    message=msg.data.decode(),
                )
                logger.debug(f"[REPLAY {simulation_id}] - Message: {msg.data.decode()}")
                await msg.ack()
                messages_retrieved += 1  # Increment the counter of retrieved messages

            logger.info(
                f"[REPLAY {simulation_id}] - Fetched {len(msgs)} messages, {messages_retrieved}/{total_messages} completed."
            )

        except asyncio.TimeoutError:
            logger.warning("Timeout reached while waiting for messages. Retrying...")
            continue  # Retry fetching messages in case of timeout

    return {"status": "Replay completed"}
