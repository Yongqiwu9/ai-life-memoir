from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1 import (
    audios,
    auth,
    collaboration,
    families,
    family_members,
    identity_verifications,
    interviews,
    rights_auth,
    sessions,
    transcripts,
    users,
)
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.LOG_LEVEL)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

register_exception_handlers(app)

app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(audios.router, prefix=settings.API_V1_PREFIX)
app.include_router(collaboration.router, prefix=settings.API_V1_PREFIX)
app.include_router(families.router, prefix=settings.API_V1_PREFIX)
app.include_router(family_members.router, prefix=settings.API_V1_PREFIX)
app.include_router(interviews.router, prefix=settings.API_V1_PREFIX)
app.include_router(identity_verifications.router, prefix=settings.API_V1_PREFIX)
app.include_router(sessions.router, prefix=settings.API_V1_PREFIX)
app.include_router(transcripts.router, prefix=settings.API_V1_PREFIX)
app.include_router(users.router, prefix=settings.API_V1_PREFIX)
app.include_router(rights_auth.router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {"name": settings.APP_NAME, "version": settings.APP_VERSION}
