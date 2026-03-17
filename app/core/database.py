"""Database connection and session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, scoped_session
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
from .config import get_settings

settings = get_settings()

# Create engine with connection pooling
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,
    echo=settings.DEBUG,
)

# Session factory
SessionFactory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# Scoped session for thread-safe access
ScopedSession = scoped_session(SessionFactory)


def get_session() -> Session:
    """Get a new database session."""
    return SessionFactory()


@contextmanager
def session_scope() -> Session:
    """
    Provide a transactional scope around a series of operations.
    
    Usage:
        with session_scope() as session:
            session.add(model)
    """
    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Initialize database tables."""
    from app.models import Event, Commit, Branch, MergeRequest, AISummary
    from sqlalchemy.orm import declarative_base
    
    Base = declarative_base()
    Base.metadata.create_all(bind=engine)
