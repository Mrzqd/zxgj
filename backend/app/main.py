from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    activity,
    auth,
    comparisons,
    expenses,
    inspections,
    knowledge,
    meta,
    progress,
    projects,
    stage_tasks,
    stages,
    todos,
    uploads,
)
from app.core.config import settings
from app.db.bootstrap import prepare_database
from app.db.session import Base, engine


def create_app() -> FastAPI:
    prepare_database(engine)
    Base.metadata.create_all(bind=engine)
    prepare_database(engine)
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(projects.router, prefix=settings.api_prefix)
    app.include_router(uploads.router, prefix=settings.api_prefix)
    app.include_router(expenses.router, prefix=settings.api_prefix)
    app.include_router(stage_tasks.router, prefix=settings.api_prefix)
    app.include_router(comparisons.router, prefix=settings.api_prefix)
    app.include_router(inspections.router, prefix=settings.api_prefix)
    app.include_router(todos.router, prefix=settings.api_prefix)
    app.include_router(activity.router, prefix=settings.api_prefix)
    app.include_router(progress.router, prefix=settings.api_prefix)
    app.include_router(stages.router, prefix=settings.api_prefix)
    app.include_router(meta.router, prefix=settings.api_prefix)
    app.include_router(knowledge.router, prefix=settings.api_prefix)
    return app


app = create_app()
