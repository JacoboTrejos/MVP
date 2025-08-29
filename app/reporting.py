from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
import uuid

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db.models import Transaction, TxnType

@dataclass
class DateRange:
    start: date
    end: date


def _week_range(d: date) -> DateRange:
    # Monday-Sunday range for the week
    start = d - timedelta(days=d.weekday())
    end = start + timedelta(days=6)
    return DateRange(start, end)


def _month_range(d: date) -> DateRange:
    start = d.replace(day=1)
    if d.month == 12:
        next_month_start = date(d.year + 1, 1, 1)
    else:
        next_month_start = date(d.year, d.month + 1, 1)
    end = next_month_start - timedelta(days=1)
    return DateRange(start, end)


def _quarter_range(d: date) -> DateRange:
    q = (d.month - 1) // 3  # 0..3
    start_month = 3 * q + 1
    start = date(d.year, start_month, 1)

    nm = start_month + 3
    if nm > 12:
        next_q_start = date(d.year + 1, nm - 12, 1)
    else:
        next_q_start = date(d.year, nm, 1)

    end = next_q_start - timedelta(days=1)
    return DateRange(start, end)


def _year_range(d: date) -> DateRange:
    return DateRange(date(d.year, 1, 1), date(d.year, 12, 31))


def _format_cop(n: int | None) -> str:
    """Format as Colombian pesos text: 1.234.567 (no decimals)."""
    if n is None:
        n = 0
    # Python formats 1,234,567. We swap commas for dots.
    return f"{int(n):,}".replace(",", ".") + " COP"


def get_range(period: str, ref: date) -> DateRange:
    period = period.lower()
    if period in ("semana", "semanal", "weekly", "week"):
        return _week_range(ref)
    if period in ("mes", "mensual", "monthly", "month"):
        return _month_range(ref)
    if period in ("trimestre", "trimestral", "quarter"):
        return _quarter_range(ref)
    if period in ("año", "anual", "year", "anio"):
        return _year_range(ref)
    raise ValueError("Periodo no soportado. Usa: semanal | mensual | quarter | año")


def _title(period: str) -> str:
    period = period.lower()
    if period in ("semana", "semanal", "weekly", "week"):
        return "Reporte semanal"
    if period in ("mes", "mensual", "monthly", "month"):
        return "Reporte mensual"
    if period in ("trimestre", "trimestral", "quarter"):
        return "Reporte trimestral"
    if period in ("año", "anual", "year", "anio"):
        return "Reporte anual"
    return "Reporte"


def _sum_by_type(db: Session, farm_id: uuid.UUID, dr: DateRange) -> tuple[int, int]:
    """Returns (ingresos, gastos) in COP for farm_id and range."""
    stmt = (
        select(Transaction.type, func.coalesce(func.sum(Transaction.total_value), 0))
        .where(
            Transaction.farm_id == farm_id,
            Transaction.date >= dr.start,
            Transaction.date <= dr.end,
        )
        .group_by(Transaction.type)
    )
    ingresos = 0
    gastos = 0
    for tx_type, s in db.execute(stmt):
        if tx_type == TxnType.INGRESO:
            ingresos = int(s or 0)
        elif tx_type == TxnType.GASTO:
            gastos = int(s or 0)
    return ingresos, gastos


def build_text_report(db: Session, farm_id: uuid.UUID, period: str, ref: date) -> str:
    dr = get_range(period, ref)
    ingresos, gastos = _sum_by_type(db, farm_id, dr)
    ganancias = ingresos - gastos

    title = _title(period)
    # Include range so the user knows what is covered
    rango = f"{dr.start.isoformat()} - {dr.end.isoformat()}"

    text = (
        f"[ {title} ]\n"
        f"Rango: {rango}\n"
        f"Ingresos = {_format_cop(ingresos)}\n"
        f"Gastos = {_format_cop(gastos)}\n"
        f"Total Ganancias = {_format_cop(ganancias)}"
    )
    return text
