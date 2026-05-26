from fastapi import FastAPI

from .db import Base, engine
from .routes import auth


app = FastAPI(title="EPIC 1bit2qbit API", version="0.1.0")
app.include_router(auth.router)


@app.on_event("startup")
def _create_tables() -> None:
    Base.metadata.create_all(bind=engine)
