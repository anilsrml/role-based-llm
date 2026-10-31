from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, make_url, text

from rolchat.models import ADMIN_DATABASE_URL, TOOL_DATABASE_URL

ROOT = Path(__file__).resolve().parents[1]
TEST_DB = "company_test"
ADMIN_TEST_URL = make_url(ADMIN_DATABASE_URL).set(database=TEST_DB)
TOOL_TEST_URL = make_url(TOOL_DATABASE_URL).set(database=TEST_DB)


@pytest.fixture(scope="session")
def engine():
    # CREATE/DROP DATABASE cannot run inside a transaction.
    admin = create_engine(ADMIN_DATABASE_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB}"))

    cfg = Config(ROOT / "alembic.ini")
    cfg.set_main_option("sqlalchemy.url", ADMIN_TEST_URL.render_as_string(hide_password=False))
    command.upgrade(cfg, "head")

    engine = create_engine(ADMIN_TEST_URL)
    with engine.begin() as conn:
        # Default privileges from init.sql only cover database "company".
        conn.execute(text("GRANT SELECT ON ALL TABLES IN SCHEMA public TO tool_reader"))
    yield engine

    engine.dispose()
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE {TEST_DB} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture(scope="session")
def reader_engine(engine):
    # Same test database, but connected as the SELECT-only user the tools use.
    reader = create_engine(TOOL_TEST_URL)
    yield reader
    reader.dispose()


@pytest.fixture(scope="session")
def seeded(engine):
    from sqlalchemy.orm import Session

    from rolchat.seed import seed

    with Session(engine) as session:
        seed(session)
