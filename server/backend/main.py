from fastapi import FastAPI

from .routes import auth

app = FastAPI(title="1bit2qbit", version="0.1.0")
app.include_router(auth.router)
