from dataclasses import dataclass
from datetime import date

from pydantic_ai import RunContext
from sqlalchemy import Engine, select

from rolchat.models import (
    Announcement,
    Employee,
    FinancialSummary,
    Leave,
    Meeting,
    Salary,
    Shift,
)
from rolchat.policy import can_use


@dataclass
class Deps:
    role: str
    engine: Engine  # connects as tool_reader (SELECT only)


def _check(ctx: RunContext[Deps], tool: str) -> None:
    if not can_use(ctx.deps.role, tool):
        raise PermissionError(f"role {ctx.deps.role!r} may not use {tool!r}")


def _rows(ctx: RunContext[Deps], stmt) -> list[dict]:
    # One connection per call: the agent may run several tools in parallel threads.
    with ctx.deps.engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(stmt)]


# Level 1


def list_announcements(ctx: RunContext[Deps], limit: int = 5) -> list[dict]:
    """Şirket duyurularını en yeniden eskiye listeler."""
    _check(ctx, "list_announcements")
    a = Announcement
    return _rows(ctx, select(a.title, a.body, a.published_on).order_by(a.published_on.desc()).limit(limit))


def get_shifts(ctx: RunContext[Deps], day: date | None = None, team: str | None = None) -> list[dict]:
    """Vardiya planı. day verilmezse tüm plan; team ile ekip (ör. Montaj) seçilebilir."""
    _check(ctx, "get_shifts")
    s = Shift
    stmt = select(s.day, s.name, s.start_time, s.end_time, s.team).order_by(s.day, s.start_time)
    if day:
        stmt = stmt.where(s.day == day)
    if team:
        stmt = stmt.where(s.team.ilike(f"%{team}%"))
    return _rows(ctx, stmt)


# Level 2


def find_employee(ctx: RunContext[Deps], name: str = "") -> list[dict]:
    """Çalışan iletişim bilgileri (unvan, departman, telefon, e-posta). name ile isim araması yapılır."""
    _check(ctx, "find_employee")
    e = Employee
    stmt = select(e.full_name, e.title, e.department, e.phone, e.email).order_by(e.full_name)
    if name:
        stmt = stmt.where(e.full_name.ilike(f"%{name}%"))
    return _rows(ctx, stmt)


def list_leaves(ctx: RunContext[Deps], on_date: date | None = None) -> list[dict]:
    """Çalışan izinleri. on_date verilirse o gün izinde olanlar."""
    _check(ctx, "list_leaves")
    lv, e = Leave, Employee
    stmt = (
        select(e.full_name, lv.start_date, lv.end_date, lv.leave_type)
        .join(e, e.id == lv.employee_id)
        .order_by(lv.start_date)
    )
    if on_date:
        stmt = stmt.where(lv.start_date <= on_date, lv.end_date >= on_date)
    return _rows(ctx, stmt)


def list_meetings(ctx: RunContext[Deps]) -> list[dict]:
    """Toplantı takvimi."""
    _check(ctx, "list_meetings")
    m = Meeting
    return _rows(ctx, select(m.title, m.starts_at, m.location, m.attendees).order_by(m.starts_at))


# Level 3


def get_salaries(ctx: RunContext[Deps], name: str = "") -> list[dict]:
    """Çalışan maaşları (aylık brüt). name ile isim araması yapılır."""
    _check(ctx, "get_salaries")
    s, e = Salary, Employee
    stmt = (
        select(e.full_name, e.title, s.monthly_gross, s.currency, s.effective_from)
        .join(e, e.id == s.employee_id)
        .order_by(e.full_name)
    )
    if name:
        stmt = stmt.where(e.full_name.ilike(f"%{name}%"))
    return _rows(ctx, stmt)


def get_financial_summary(ctx: RunContext[Deps], months: int = 12) -> list[dict]:
    """Aylık gelir, gider, kâr ve kasa durumu; en yeni aydan geriye months kadar."""
    _check(ctx, "get_financial_summary")
    f = FinancialSummary
    return _rows(
        ctx,
        select(f.period, f.revenue, f.expenses, f.profit, f.cash_balance).order_by(f.period.desc()).limit(months),
    )


TOOLS = [
    list_announcements,
    get_shifts,
    find_employee,
    list_leaves,
    list_meetings,
    get_salaries,
    get_financial_summary,
]
