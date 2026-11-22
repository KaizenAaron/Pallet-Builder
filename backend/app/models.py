"""SQLAlchemy models.

Tables that hold a company's own data inherit `TenantMixin`: they get a non-null `company_id`
and Postgres row-level security (`app/rls.py`). `memberships` and `invites` also carry a
company_id but are looked up *before* a tenant is known (sign-in, invite links), so they are
protected by application checks and `tests/test_tenancy.py` instead of RLS.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


ROLES = ("owner", "admin", "member")
ROLE_RANK = {"member": 1, "admin": 2, "owner": 3}


class TenantMixin:
    __tenant__ = True

    @declared_attr
    def company_id(cls) -> Mapped[int]:
        return mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    address_line1: Mapped[str] = mapped_column(String(200), default="")
    address_line2: Mapped[str] = mapped_column(String(200), default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    state: Mapped[str] = mapped_column(String(100), default="")
    postal_code: Mapped[str] = mapped_column(String(20), default="")
    country: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    units: Mapped[str] = mapped_column(String(10), default="imperial")  # imperial | metric (display only)
    plan: Mapped[str] = mapped_column(String(30), default="free")
    billing_customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="company", cascade="all, delete-orphan")


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "company_id", name="uq_membership_user_company"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(10), default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="memberships")
    company: Mapped[Company] = relationship(back_populates="memberships")


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(254), index=True)
    role: Mapped[str] = mapped_column(String(10), default="member")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    invited_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    company: Mapped[Company] = relationship()
    invited_by: Mapped[User | None] = relationship()


class AuthToken(Base):
    """Single-use email-verification and password-reset tokens (only the SHA-256 is stored)."""

    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(20))  # verify_email | reset_password
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship()


class PalletType(TenantMixin, Base):
    __tablename__ = "pallet_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    length: Mapped[float] = mapped_column(Float, default=48.0)
    width: Mapped[float] = mapped_column(Float, default=40.0)
    deck_height: Mapped[float] = mapped_column(Float, default=5.5)
    tare_weight: Mapped[float] = mapped_column(Float, default=45.0)
    max_total_height: Mapped[float] = mapped_column(Float, default=72.0)
    max_gross_weight: Mapped[float] = mapped_column(Float, default=2500.0)
    max_overhang: Mapped[float] = mapped_column(Float, default=0.0)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Product(TenantMixin, Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("company_id", "sku", name="uq_product_company_sku"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(300), default="")
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | import | odoo
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    boxes: Mapped[list["ProductBox"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", order_by="ProductBox.box_no"
    )


class ProductBox(TenantMixin, Base):
    """One box of a product. A unit ships in `qty_per_unit` of each of its product's boxes;
    `units_per_box` units share one box. Inches and pounds."""

    __tablename__ = "product_boxes"
    __table_args__ = (UniqueConstraint("product_id", "box_no", name="uq_product_box_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    box_no: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(200), default="")
    qty_per_unit: Mapped[int] = mapped_column(Integer, default=1)
    units_per_box: Mapped[int] = mapped_column(Integer, default=1)
    length: Mapped[float] = mapped_column(Float)
    width: Mapped[float] = mapped_column(Float)
    height: Mapped[float] = mapped_column(Float)
    weight: Mapped[float] = mapped_column(Float)
    this_side_up: Mapped[bool] = mapped_column(Boolean, default=False)
    stackable: Mapped[bool] = mapped_column(Boolean, default=True)
    max_load_on_top: Mapped[float] = mapped_column(Float, default=0.0)  # 0 = no limit

    product: Mapped[Product] = relationship(back_populates="boxes")


def tenant_tables() -> list[str]:
    return sorted(
        m.class_.__tablename__
        for m in Base.registry.mappers
        if getattr(m.class_, "__tenant__", False)
    )
