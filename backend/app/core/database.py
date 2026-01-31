"""
Database Configuration and Connection
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON
from sqlalchemy.sql import func
from app.core.config import settings


# Convert sync URL to async
database_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(
    database_url,
    echo=settings.ENVIRONMENT == "development",
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


# Database Models
class Customer(Base):
    __tablename__ = "customers"
    
    id = Column(Integer, primary_key=True, index=True)
    uisp_customer_id = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255))
    phone = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_active = Column(Boolean, default=True)


class CustomerDevice(Base):
    __tablename__ = "customer_devices"
    
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    device_type = Column(String(50), nullable=False)  # starlink, mikrotik, tr069
    device_identifier = Column(String(255), nullable=False)
    nickname = Column(String(100))
    
    # MikroTik specific
    mikrotik_host = Column(String(255))
    mikrotik_api_user = Column(String(100))
    mikrotik_api_password_encrypted = Column(Text)
    
    # TR-069 specific
    tr069_device_id = Column(String(255))
    
    # Metadata
    last_seen = Column(DateTime(timezone=True))
    config_data = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_active = Column(Boolean, default=True)


class HotspotVoucher(Base):
    __tablename__ = "hotspot_vouchers"
    
    id = Column(Integer, primary_key=True, index=True)
    customer_device_id = Column(Integer, ForeignKey("customer_devices.id"), nullable=False)
    voucher_code = Column(String(50), unique=True, nullable=False, index=True)
    profile = Column(String(100))
    validity = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    used_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)


class UISPCache(Base):
    __tablename__ = "uisp_cache"
    
    id = Column(Integer, primary_key=True, index=True)
    uisp_customer_id = Column(String(255), nullable=False, index=True)
    data_type = Column(String(50), nullable=False)  # invoices, services, profile
    data = Column(JSON, nullable=False)
    cached_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50))
    resource_id = Column(String(255))
    details = Column(JSON)
    ip_address = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """Dependency for getting database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
