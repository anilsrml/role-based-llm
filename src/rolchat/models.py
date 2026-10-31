import os
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Fallbacks match .env.example so local runs work without a .env file.
ADMIN_DATABASE_URL = os.environ.get(
    "ADMIN_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5433/company"
)
TOOL_DATABASE_URL = os.environ.get(
    "TOOL_DATABASE_URL", "postgresql+psycopg://tool_reader:tool_reader@localhost:5433/company"
)

# 1 = isci, 2 = sekreter, 3 = patron. A role sees its level and below.
TABLE_LEVELS = {
    "announcements": 1,
    "shifts": 1,
    "employees": 2,
    "leaves": 2,
    "meetings": 2,
    "salaries": 3,
    "financial_summary": 3,
}


class Base(DeclarativeBase):
    pass


# Level 1

class Announcement(Base):
    __tablename__ = "announcements"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    body: Mapped[str] = mapped_column(Text)
    published_on: Mapped[date]


class Shift(Base):
    __tablename__ = "shifts"
    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date]
    name: Mapped[str]
    start_time: Mapped[time]
    end_time: Mapped[time]
    team: Mapped[str]


# Level 2

class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str]
    title: Mapped[str]
    department: Mapped[str]
    phone: Mapped[str]
    email: Mapped[str]


class Leave(Base):
    __tablename__ = "leaves"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    start_date: Mapped[date]
    end_date: Mapped[date]
    leave_type: Mapped[str]


class Meeting(Base):
    __tablename__ = "meetings"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    starts_at: Mapped[datetime]
    location: Mapped[str]
    attendees: Mapped[str] = mapped_column(Text)


# Level 3

class Salary(Base):
    __tablename__ = "salaries"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    monthly_gross: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(default="TRY", server_default="TRY")
    effective_from: Mapped[date]


class FinancialSummary(Base):
    __tablename__ = "financial_summary"
    id: Mapped[int] = mapped_column(primary_key=True)
    period: Mapped[date]  # first day of the month
    revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    expenses: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    profit: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2))
