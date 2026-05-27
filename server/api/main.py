from fastapi import FastAPI

from .routes import auth

app = FastAPI(title="EPIC 1bit2qbit API", version="0.1.0")
app.include_router(auth.router)
