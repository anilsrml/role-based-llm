from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, make_url, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from rolchat.models import ADMIN_DATABASE_URL, TABLE_LEVELS, TOOL_DATABASE_URL
from rolchat.seed import seed

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


def row_counts(engine):
    with engine.connect() as conn:
        return {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in TABLE_LEVELS}


def test_migration_creates_exactly_the_level_tables(engine):
    tables = set(inspect(engine).get_table_names()) - {"alembic_version"}
    assert tables == set(TABLE_LEVELS) == {
        "announcements", "shifts",
        "employees", "leaves", "meetings",
        "salaries", "financial_summary",
    }
    assert set(TABLE_LEVELS.values()) == {1, 2, 3}


def test_seed_fills_every_table_and_is_idempotent(engine):
    with Session(engine) as session:
        seed(session)
    first = row_counts(engine)
    with engine.connect() as conn:
        names = conn.execute(text("SELECT full_name FROM employees ORDER BY id")).scalars().all()

    with Session(engine) as session:
        seed(session)
    assert all(n > 0 for n in first.values()), first
    assert row_counts(engine) == first
    assert first["employees"] == first["salaries"]
    assert first["financial_summary"] == 12
    with engine.connect() as conn:
        assert conn.execute(text("SELECT full_name FROM employees ORDER BY id")).scalars().all() == names


def test_tool_reader_can_select_but_not_insert(engine):
    reader = create_engine(TOOL_TEST_URL)
    try:
        assert set(row_counts(reader)) == set(TABLE_LEVELS)
        with reader.begin() as conn, pytest.raises(ProgrammingError) as exc:
            conn.execute(text(
                "INSERT INTO announcements (title, body, published_on) VALUES ('x', 'y', current_date)"
            ))
        assert isinstance(exc.value.orig, psycopg.errors.InsufficientPrivilege)
    finally:
        reader.dispose()
