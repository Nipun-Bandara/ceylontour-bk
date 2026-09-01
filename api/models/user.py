"""users (plan.md section 8). Authority logins for the dashboard."""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    # A hash only. Plain passwords are never stored (features.md F8).
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
