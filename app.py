from contextlib import asynccontextmanager
from fastapi import FastAPI
from .routes import router

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(lifespan=lifespan, title="TG Lookup API", docs_url=None, redoc_url=None)
app.include_router(router, prefix="/api/v1")