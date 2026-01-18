import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.db import connect_db
from app.logging import setup_logging
from app.redis import redis
from app.routes import admin_routes, crud_routes, extra_routes

logger = logging.getLogger(__name__)


setup_logging()
app = FastAPI()
app.mount('/static', StaticFiles(directory='app/static'), name='static')

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        'http://localhost:3000',
        'http://127.0.0.1:3000',
        'http://yourdomain.com',
        'https://yourdomain.com',
    ],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.add_middleware(SessionMiddleware, secret_key=os.getenv('SESSION_SECRET_KEY'))


@app.on_event('startup')
async def startup():
    """Initialize database connection on startup."""
    app.state.db = await connect_db()
    app.state.cart = {'items': {}}


@app.on_event('shutdown')
async def shutdown():
    logger.info('Shutting down application...')

    try:
        await redis.close()
        logger.info('Redis connection closed')
    except Exception as e:
        logger.warning(f'Error closing Redis: {e}')

    try:
        await app.state.db.close()
        logger.info('Database pool closed')
    except Exception as e:
        logger.warning(f'Error closing DB pool: {e}')


app.include_router(extra_routes.router)
app.include_router(crud_routes.router)
app.include_router(admin_routes.router)
if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='0.0.0.0', port=8000)
