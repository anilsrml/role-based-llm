import os

import psycopg
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from rolchat.models import ROLE_LEVELS, TABLE_LEVELS
from rolchat.seed import seed

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


def test_tool_reader_can_select_but_not_insert(reader_engine):
    assert set(row_counts(reader_engine)) == set(TABLE_LEVELS)
    with reader_engine.begin() as conn, pytest.raises(ProgrammingError) as exc:
        conn.execute(text(
            "INSERT INTO announcements (title, body, published_on) VALUES ('x', 'y', current_date)"
        ))
    assert isinstance(exc.value.orig, psycopg.errors.InsufficientPrivilege)


def test_test_database_name_comes_from_env(engine):
    # Parallel worktrees set TEST_DB so their runs do not drop each other's database.
    assert engine.url.database == os.environ.get("TEST_DB", "company_test")


@pytest.mark.parametrize("level", [1, 2, 3])
def test_level_reader_selects_only_tables_at_or_below_its_level(level_engines, level):
    # Third layer: even a buggy tool cannot read a table above the role's level.
    with level_engines[level].connect() as conn:
        for table, table_level in TABLE_LEVELS.items():
            if table_level <= level:
                conn.execute(text(f"SELECT count(*) FROM {table}"))
            else:
                with pytest.raises(ProgrammingError) as exc:
                    conn.execute(text(f"SELECT count(*) FROM {table}"))
                assert isinstance(exc.value.orig, psycopg.errors.InsufficientPrivilege)
                conn.rollback()


def test_each_role_has_a_level():
    assert ROLE_LEVELS == {"isci": 1, "sekreter": 2, "patron": 3}
