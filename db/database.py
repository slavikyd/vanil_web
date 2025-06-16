import asyncpg


async def create_db_connection(dsn: str):
    return await asyncpg.connect(dsn)
