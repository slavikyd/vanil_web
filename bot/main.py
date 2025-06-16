import asyncio

from config import bot, dp
from handlers import router  # import the router
from web_app import app


async def main():
    dp.include_router(router)  # register the router
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
