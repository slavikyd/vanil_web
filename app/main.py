import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.db import connect_db
from app.routes import admin_routes, crud_routes, extra_routes


app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")


# Add session middleware for cart and cashier tracking
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET_KEY"))


@app.on_event("startup")
async def startup():
    """Initialize database connection on startup."""
    app.state.db = await connect_db()
    app.state.cart = {"items": {}}


@app.on_event("shutdown")
async def shutdown():
    """Close database connection on shutdown."""
    await app.state.db.close()


# Include all route modules
app.include_router(extra_routes.router)      # Auth & main routes (GET /, POST /login, POST /logout)
app.include_router(crud_routes.router)       # CRUD operations (POST /add-to-order, POST /place_order, GET /orders)
app.include_router(admin_routes.router)      # Admin operations (GET /admin/*, POST /admin/*)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
