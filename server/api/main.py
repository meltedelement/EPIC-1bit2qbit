import os

from fastapi import FastAPI

from .database.db import Base, engine
from .routes import auth


app = FastAPI(title="EPIC 1bit2qbit API", version="0.1.0")
app.include_router(auth.router)


if os.getenv("ENV") == "development":
    Base.metadata.create_all(bind=engine)
