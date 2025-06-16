import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.db import connect_db
from app.views import router

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")


app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET_KEY"))
@app.on_event("startup")
async def startup():
    app.state.db = await connect_db()
    app.state.cart = {"items": {}}

@app.on_event("shutdown")
async def shutdown():
    await app.state.db.close()

app.include_router(router)
