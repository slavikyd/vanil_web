"""Background worker for processing cart updates from RabbitMQ.

This worker listens to the "add_to_order" queue and processes cart updates
using the router's cart storage (shared with the FastAPI application).
"""

import asyncio
import json

import aio_pika

from app.routes import crud_routes

RABBITMQ_URL = "amqp://guest:guest@rabbitmq/"


async def main():
    """Main worker loop that processes messages from RabbitMQ."""
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        queue = await channel.declare_queue("add_to_order", durable=True)

        print("Worker started. Listening for cart updates...")

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    try:
                        data = json.loads(message.body)

                        session_id = data["session_id"]
                        item_id = data["item_id"]
                        quantity = data["quantity"]

                        # Initialize cart storage if not present
                        if not hasattr(crud_routes.router, "carts"):
                            crud_routes.router.carts = {}

                        # Initialize session cart if not present
                        if session_id not in crud_routes.router.carts:
                            crud_routes.router.carts[session_id] = {}

                        # Update cart based on quantity
                        if quantity > 0:
                            crud_routes.router.carts[session_id][item_id] = quantity
                        else:
                            crud_routes.router.carts[session_id].pop(item_id, None)

                        print(f"✓ Cart update processed - Session: {session_id}, Item: {item_id}, Qty: {quantity}")

                    except json.JSONDecodeError as e:
                        print(f"✗ Failed to parse message: {e}")
                    except KeyError as e:
                        print(f"✗ Missing required field in message: {e}")
                    except Exception as e:
                        print(f"✗ Error processing message: {e}")


if __name__ == "__main__":
    asyncio.run(main())
