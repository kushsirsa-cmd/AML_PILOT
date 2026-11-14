import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select

from . import models  # noqa: F401  (register tables)
from .config import settings
from .db import Base, SessionLocal, engine
from .routers import auth as auth_router, audit_log, crypto, customers, dashboard, executive, investigations, kyb, mlro, qa, reports, reviews, sars, screening, travel_rule

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("aml")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)  # no-op when sql/schema.sql already created the tables
    if settings.seed_on_startup:
        from . import demo_data

        with SessionLocal() as db:
            demo_data.seed_users(db)
            if not db.scalar(select(func.count(models.Customer.id))):
                log.info("Empty database - loading demo dataset (%s)", settings.seed_size)
                demo_data.seed_everything(db)
    log.info("AML Copilot ready. Claude layer active: %s", settings.llm_active)
    yield


app = FastAPI(title="AML Copilot MVP", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
for r in (customers.router, reviews.router, screening.router, dashboard.router, audit_log.router, kyb.router, crypto.router,
          travel_rule.router, auth_router.router, executive.router, mlro.router, sars.router, qa.router, reports.router, investigations.router):
    app.include_router(r)
