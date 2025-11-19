"""
Database models and connection management for the package registry.
Supports both SQLite (for local development) and PostgreSQL (for production on AWS RDS).
"""

import os
from datetime import datetime
from typing import Optional, List
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Boolean, JSON, Float, Text, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import enum

# Base class for all models
Base = declarative_base()

# Enums for user roles and audit actions
class UserRole(str, enum.Enum):
    ADMIN = "admin"
    UPLOADER = "uploader"
    SEARCHER = "searcher"
    DOWNLOADER = "downloader"

class AuditAction(str, enum.Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DOWNLOAD = "DOWNLOAD"
    RATE = "RATE"
    AUDIT = "AUDIT"
    DELETE = "DELETE"

class User(Base):
    """User model for authentication and authorization."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.SEARCHER)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role.value,
            "created_at": self.created_at.isoformat(),
            "is_active": self.is_active
        }

class Package(Base):
    """Package/Artifact model for storing metadata."""
    __tablename__ = "packages"
    
    id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False, index=True)
    version = Column(String(100), nullable=False)
    artifact_type = Column(String(50), nullable=False, index=True)  # model, dataset, code
    url = Column(Text, nullable=True)
    scores = Column(JSON, nullable=True)
    # metadata = Column(JSON, nullable=True)
    is_sensitive = Column(Boolean, default=False, nullable=False)
    monitoring_script = Column(Text, nullable=True)  # JavaScript code for sensitive models
    uploader_username = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "artifact_type": self.artifact_type,
            "url": self.url,
            "scores": self.scores,
            # "metadata": self.metadata,
            "is_sensitive": self.is_sensitive,
            "uploader_username": self.uploader_username,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }

class AuditLog(Base):
    """Audit log for tracking all operations on artifacts."""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    artifact_id = Column(String(255), nullable=False, index=True)
    artifact_type = Column(String(50), nullable=False)
    action = Column(SQLEnum(AuditAction), nullable=False)
    username = Column(String(100), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    details = Column(JSON, nullable=True)
    
    def to_dict(self):
        return {
            "id": self.id,
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "action": self.action.value,
            "username": self.username,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details
        }

class TokenUsage(Base):
    """Track API call usage per JWT token."""
    __tablename__ = "token_usage"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    token_id = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=False, index=True)
    call_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class SystemHealth(Base):
    """Track system health metrics over time."""
    __tablename__ = "system_health"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    component_name = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False)  # ok, degraded, critical, unknown
    response_time_ms = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    details = Column(JSON, nullable=True)

# Database connection management
class DatabaseManager:
    """Manages database connections and sessions."""
    
    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize database connection.
        
        Args:
            database_url: Database connection string. If None, uses environment variable
                         or defaults to SQLite for local development.
        """
        if database_url is None:
            database_url = os.environ.get(
                "DATABASE_URL",
                "sqlite:///./package_registry.db"
            )
        
        # Handle PostgreSQL URL format from Heroku/AWS
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        
        self.engine = create_engine(
            database_url,
            pool_pre_ping=True,  # Verify connections before using
            pool_recycle=3600,   # Recycle connections after 1 hour
        )
        
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
    
    def create_tables(self):
        """Create all tables if they don't exist."""
        Base.metadata.create_all(bind=self.engine)
    
    def drop_tables(self):
        """Drop all tables. USE WITH CAUTION!"""
        Base.metadata.drop_all(bind=self.engine)
    
    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()
    
    def reset_database(self):
        """Reset database to initial state (for /reset endpoint)."""
        self.drop_tables()
        self.create_tables()

# Global database manager instance
db_manager = DatabaseManager()

def get_db() -> Session:
    """
    Dependency function to get database session.
    Use with Flask app context or manually close session.
    """
    return db_manager.get_session()

def init_db():
    """Initialize database with tables and default admin user."""
    db_manager.create_tables()
    
    # Create default admin user if not exists
    from auth_service import AuthService
    session = get_db()
    try:
        auth_service = AuthService(session)
        existing_admin = session.query(User).filter_by(username="admin").first()
        
        if not existing_admin:
            admin_user = auth_service.create_user(
                username="admin",
                password="admin123!",  # Change this in production!
                role=UserRole.ADMIN
            )
            print(f"Created default admin user: {admin_user.username}")
        
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Error initializing database: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    # For testing: initialize database
    print("Initializing database...")
    init_db()
    print("Database initialized successfully!")


