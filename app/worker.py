import asyncio
import json
import uuid

import aio_pika

from app.views import router

RABBITMQ_URL = "amqp://guest:guest@rabbitmq/"


async def main():
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        queue = await channel.declare_queue("add_to_order", durable=True)

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    data = json.loads(message.body)

                    session_id = data["session_id"]
                    item_id = data["item_id"]
                    quantity = data["quantity"]

                    if session_id not in router.carts:
                        router.carts[session_id] = {}

                    if quantity > 0:
                        router.carts[session_id][item_id] = quantity
                    else:
                        router.carts[session_id].pop(item_id, None)

                    print(f"Processed cart update for session {session_id}: {item_id}={quantity}")

if __name__ == "__main__":
    asyncio.run(main())
