"""Regenerate sql/schema.sql from the SQLAlchemy models:  python backend/scripts/dump_schema.py"""
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite://")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy.dialects import postgresql  # noqa: E402
from sqlalchemy.schema import CreateIndex, CreateTable  # noqa: E402

from app import models  # noqa: E402,F401
from app.db import Base  # noqa: E402

d = postgresql.dialect()
out = [
    "-- AML Copilot MVP - PostgreSQL schema",
    "-- Generated from backend/app/models.py via backend/scripts/dump_schema.py. Safe to run on an empty database.",
    "",
]
for t in Base.metadata.sorted_tables:
    out.append(str(CreateTable(t, if_not_exists=True).compile(dialect=d)).strip() + ";\n")
    for ix in sorted(t.indexes, key=lambda i: i.name):
        out.append(str(CreateIndex(ix, if_not_exists=True).compile(dialect=d)).strip() + ";")
    out.append("")
(ROOT / "sql" / "schema.sql").write_text("\n".join(out))
print("wrote sql/schema.sql")
