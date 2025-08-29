# app/db/models.py
from __future__ import annotations
import uuid
from datetime import datetime, date
from enum import Enum

from sqlalchemy import (
    Date, DateTime, Enum as SAEnum, ForeignKey, Integer, Text, func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# --- Enums (match the strings you extract) ---
class ActivityCategory(str, Enum):
    EQUIPOS = "compras de equipos y maquinaria"
    PRESIEMBRA = "pre-siembra"
    SIEMBRA = "siembra"
    FERTILIZACION = "fertilización"
    MANEJO = "manejo del cultivo"
    COSECHA = "cosecha"
    VENTA = "venta"


class TxnType(str, Enum):
    INGRESO = "ingreso"
    GASTO = "gasto"


# --- Transaction table ---
class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,               # python-side UUID; avoids DB extensions
    )

    # For MVP we won't enforce FK for farm_id (no farms table yet)
    farm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    date: Mapped[date] = mapped_column(Date, nullable=False)

    activitycategory: Mapped[ActivityCategory] = mapped_column(
        SAEnum(ActivityCategory, name="activitycategory_enum"), nullable=False
    )

    type: Mapped[TxnType] = mapped_column(
        SAEnum(TxnType, name="txn_type_enum"), nullable=False
    )

    description: Mapped[str | None] = mapped_column(Text)

    quantity: Mapped[int | None] = mapped_column(Integer)
    unit: Mapped[str | None] = mapped_column(Text)
    unit_price: Mapped[int | None] = mapped_column(Integer)
    total_value: Mapped[int | None] = mapped_column(Integer)

    currency: Mapped[str] = mapped_column(Text, default="COP", nullable=False)

    source_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
