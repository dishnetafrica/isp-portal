"""
Authentication API - UISP Integration
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
import jwt
import httpx
import structlog
from typing import Optional

from app.core.config import settings
from app.core.database import get_db, Customer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

router = APIRouter()
logger = structlog.get_logger()


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    customer: dict
    services: list


class TokenPayload(BaseModel):
    customer_id: int
    uisp_customer_id: str
    email: str
    exp: datetime


def create_access_token(data: dict) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRATION_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def verify_token(authorization: str = Header(...)) -> TokenPayload:
    """Verify JWT token from Authorization header"""
    try:
        token = authorization.replace("Bearer ", "")
        payload = jwt.decode(
            token, 
            settings.SECRET_KEY, 
            algorithms=[settings.JWT_ALGORITHM]
        )
        return TokenPayload(**payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


class UISPService:
    """UISP API Integration Service"""
    
    def __init__(self):
        self.base_url = settings.UISP_URL.rstrip('/')
        self.api_key = settings.UISP_API_KEY
    
    async def authenticate(self, username: str, password: str) -> dict:
        """Authenticate user against UISP"""
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            # Method 1: Try session-based login
            response = await client.post(
                f"{self.base_url}/api/v2.1/user/login",
                json={"username": username, "password": password}
            )
            
            if response.status_code == 200:
                token = response.headers.get('x-auth-token')
                
                # Get user/customer info
                user_response = await client.get(
                    f"{self.base_url}/api/v2.1/user",
                    headers={"x-auth-token": token}
                )
                
                if user_response.status_code == 200:
                    user_data = user_response.json()
                    
                    # Get customer details if this is a client user
                    customer_id = user_data.get('clientId')
                    if customer_id:
                        customer = await self.get_customer(client, token, customer_id)
                        services = await self.get_customer_services(client, token, customer_id)
                        return {
                            "token": token,
                            "user": user_data,
                            "customer": customer,
                            "services": services
                        }
            
            raise HTTPException(status_code=401, detail="Invalid UISP credentials")
    
    async def get_customer(self, client: httpx.AsyncClient, token: str, customer_id: str) -> dict:
        """Get customer details from UISP"""
        response = await client.get(
            f"{self.base_url}/api/v2.1/clients/{customer_id}",
            headers={"x-auth-token": token}
        )
        if response.status_code == 200:
            return response.json()
        return {}
    
    async def get_customer_services(self, client: httpx.AsyncClient, token: str, customer_id: str) -> list:
        """Get customer services from UISP"""
        response = await client.get(
            f"{self.base_url}/api/v2.1/clients/{customer_id}/services",
            headers={"x-auth-token": token}
        )
        if response.status_code == 200:
            return response.json()
        return []
    
    async def get_invoices(self, token: str, customer_id: str) -> list:
        """Get customer invoices from UISP"""
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/api/v2.1/clients/{customer_id}/invoices",
                headers={"x-auth-token": token}
            )
            if response.status_code == 200:
                return response.json()
            return []
    
    async def get_payments(self, token: str, customer_id: str) -> list:
        """Get customer payments from UISP"""
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/api/v2.1/clients/{customer_id}/payments",
                headers={"x-auth-token": token}
            )
            if response.status_code == 200:
                return response.json()
            return []


uisp_service = UISPService()


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Authenticate user via UISP credentials
    """
    logger.info("Login attempt", username=request.username)
    
    try:
        # Authenticate with UISP
        auth_result = await uisp_service.authenticate(request.username, request.password)
        
        uisp_customer_id = str(auth_result["customer"].get("id", ""))
        email = auth_result["user"].get("email", request.username)
        
        # Check if customer exists in our database
        result = await db.execute(
            select(Customer).where(Customer.uisp_customer_id == uisp_customer_id)
        )
        customer = result.scalar_one_or_none()
        
        # Create customer if not exists
        if not customer:
            customer = Customer(
                uisp_customer_id=uisp_customer_id,
                email=email,
                name=f"{auth_result['customer'].get('firstName', '')} {auth_result['customer'].get('lastName', '')}".strip(),
                phone=auth_result['customer'].get('phone', ''),
            )
            db.add(customer)
            await db.commit()
            await db.refresh(customer)
            logger.info("New customer created", customer_id=customer.id)
        
        # Create our JWT token
        access_token = create_access_token({
            "customer_id": customer.id,
            "uisp_customer_id": uisp_customer_id,
            "email": email,
            "uisp_token": auth_result["token"],  # Store UISP token for API calls
        })
        
        logger.info("Login successful", customer_id=customer.id)
        
        return LoginResponse(
            access_token=access_token,
            customer=auth_result["customer"],
            services=auth_result["services"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Login failed", error=str(e))
        raise HTTPException(status_code=401, detail="Authentication failed")


@router.get("/me")
async def get_current_user(token: TokenPayload = Depends(verify_token)):
    """
    Get current authenticated user info
    """
    return {
        "customer_id": token.customer_id,
        "email": token.email,
        "uisp_customer_id": token.uisp_customer_id
    }


@router.post("/refresh")
async def refresh_token(token: TokenPayload = Depends(verify_token)):
    """
    Refresh access token
    """
    new_token = create_access_token({
        "customer_id": token.customer_id,
        "uisp_customer_id": token.uisp_customer_id,
        "email": token.email,
    })
    return {"access_token": new_token, "token_type": "bearer"}
