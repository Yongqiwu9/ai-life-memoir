from fastapi import FastAPI

from app.api.v1.memories import router as memories_router

app = FastAPI(
    title="AI Life Memoir API",
    version="1.0.0",
)

app.include_router(
    memories_router,
    prefix="/api/v1",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
