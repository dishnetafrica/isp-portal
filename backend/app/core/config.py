"""
Application Configuration
"""

from pydantic_settings import BaseSettings
from typing import List
import secrets


class Settings(BaseSettings):
    # Application
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    
    # Database
    DATABASE_URL: str = "postgresql://ispportal:password@localhost:5432/ispportal"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # UISP
    UISP_URL: str = "https://uisp.example.com"
    UISP_API_KEY: str = ""
    
    # GenieACS
    GENIEACS_URL: str = "http://localhost:7557"
    
    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8080",
        "https://app.yourdomain.com"
    ]
    
    # JWT
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
