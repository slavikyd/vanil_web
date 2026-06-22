import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.db import connect_db
from app.logging import setup_logging
from app.middleware.cashier_session import CashierSessionTimeoutMiddleware
from app.redis import redis
from app.routes import crud_routes, extra_routes
from app.services.cart_finalizer import finalize_abandoned_carts
from prometheus_fastapi_instrumentator import Instrumentator
import mimetypes

logger = logging.getLogger(__name__)


SESSION_MAX_AGE_SECONDS = int(os.getenv('SESSION_MAX_AGE_SECONDS'))

setup_logging()
app = FastAPI()
mimetypes.add_type('application/vnd.android.package-archive', '.apk')

app.mount('/static', StaticFiles(directory='app/static'), name='static')

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        'http://localhost:3000',
        'http://127.0.0.1:3000',
        'http://xn--90aioe3a8b4a.xn--p1ai',
        'http://mz.vanil-krd.ru',
    ],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.add_middleware(CashierSessionTimeoutMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv('SESSION_SECRET_KEY'),
    max_age=SESSION_MAX_AGE_SECONDS,
)

scheduler = AsyncIOScheduler()


@app.on_event('startup')
async def startup():
    """Initialize database connection on startup."""
    app.state.db = await connect_db()
    app.state.cart = {'items': {}}

    scheduler.add_job(
        finalize_abandoned_carts,
        trigger=CronTrigger(hour=21, minute=0),
        args=[app.state.db],
        id='finalize_abandoned_carts',
        replace_existing=True,
    )
    scheduler.start()
    logger.info('scheduler_started', extra={'jobs': [j.id for j in scheduler.get_jobs()]})


@app.on_event('shutdown')
async def shutdown():
    logger.info('Shutting down application...')

    try:
        scheduler.shutdown(wait=False)
        logger.info('Scheduler shut down')
    except Exception as e:
        logger.warning(f'Error shutting down scheduler: {e}')

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
# app.include_router(admin_routes.router) #self written admin routes disabled in favor of new Django admin 
Instrumentator().instrument(app).expose(app)


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='0.0.0.0', port=8000)