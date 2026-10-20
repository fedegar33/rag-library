"""FastAPI application entry point."""

from fastapi import FastAPI

from rag_library import __version__
from rag_library.api.routes import router

app = FastAPI(
    title="RAG Library API",
    description="A book catalog agent backed by PostgreSQL.",
    version=__version__,
)
app.include_router(router)
