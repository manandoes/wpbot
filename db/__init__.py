"""
db/__init__.py
Database engine and session factory initialization.
Configured for Supabase (PostgreSQL) via DATABASE_URL in .env
"""

import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os

load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in .env")

# PostgreSQL connection pool settings
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,       # Detect stale connections automatically
    pool_size=5,              # Keep 5 connections open
    max_overflow=10,          # Allow up to 10 extra connections under load
    pool_recycle=1800,        # Recycle connections every 30 minutes
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Yield a database session and close it when done."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# create_all() only creates missing *tables* — it never adds a column to a
# table that already exists, so columns added after the first deploy have to be
# applied by hand. These are written to be safe to run on every startup.
_COLUMN_MIGRATIONS = (
    "ALTER TABLE registrations ADD COLUMN IF NOT EXISTS followup_due_at TIMESTAMP WITHOUT TIME ZONE",
    "ALTER TABLE registrations ADD COLUMN IF NOT EXISTS followup_count INTEGER NOT NULL DEFAULT 0",
)


def init_db():
    """Create all tables in the Supabase database if they don't exist."""
    from db.models import Contact, Conversation, Registration  # noqa: F401
    Base.metadata.create_all(bind=engine)

    with engine.begin() as connection:
        for statement in _COLUMN_MIGRATIONS:
            connection.execute(text(statement))

    logger.info("Supabase tables created / verified.")
