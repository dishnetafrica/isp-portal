"""
Billing API - UISP Integration
View invoices, payments, and account balance
"""

from fastapi import APIRouter, HTTPException, Depends
import httpx
import structlog

from app.api.auth import verify_token, TokenPayload, UISPService
from app.core.config import settings

router = APIRouter()
logger = structlog.get_logger()


class BillingService:
    """UISP Billing Integration"""
    
    def __init__(self):
        self.base_url = settings.UISP_URL.rstrip('/')
    
    async def _request(self, token: str, path: str, params: dict = None):
        """Make authenticated request to UISP"""
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/api/v2.1{path}",
                headers={"x-auth-token": token},
                params=params
            )
            
            if response.status_code == 401:
                raise HTTPException(status_code=401, detail="UISP session expired")
            
            if response.status_code >= 400:
                logger.error("UISP request failed", path=path, status=response.status_code)
                raise HTTPException(status_code=response.status_code, detail="UISP error")
            
            return response.json()
    
    async def get_customer_profile(self, token: str, customer_id: str) -> dict:
        """Get customer profile from UISP"""
        return await self._request(token, f"/clients/{customer_id}")
    
    async def get_invoices(self, token: str, customer_id: str, limit: int = 20) -> list:
        """Get customer invoices"""
        invoices = await self._request(
            token, 
            f"/clients/{customer_id}/invoices",
            params={"limit": limit}
        )
        return invoices
    
    async def get_invoice_detail(self, token: str, invoice_id: str) -> dict:
        """Get detailed invoice"""
        return await self._request(token, f"/invoices/{invoice_id}")
    
    async def get_payments(self, token: str, customer_id: str, limit: int = 20) -> list:
        """Get customer payments"""
        return await self._request(
            token,
            f"/clients/{customer_id}/payments",
            params={"limit": limit}
        )
    
    async def get_services(self, token: str, customer_id: str) -> list:
        """Get customer services/subscriptions"""
        return await self._request(token, f"/clients/{customer_id}/services")
    
    async def get_account_balance(self, token: str, customer_id: str) -> dict:
        """Get account balance summary"""
        profile = await self.get_customer_profile(token, customer_id)
        
        return {
            "balance": profile.get("accountBalance", 0),
            "credit": profile.get("accountCredit", 0),
            "outstanding": profile.get("accountOutstanding", 0),
            "currency": profile.get("currencyCode", "USD")
        }


billing_service = BillingService()


# ==================== API ENDPOINTS ====================

@router.get("/profile")
async def get_billing_profile(token: TokenPayload = Depends(verify_token)):
    """Get customer billing profile"""
    logger.info("Getting billing profile", customer_id=token.customer_id)
    
    # Extract UISP token from our JWT (stored during login)
    # In production, you'd store this securely
    try:
        import jwt
        from app.core.config import settings
        
        # Decode our token to get UISP token
        full_token = jwt.decode(
            token.model_dump().get("_token", ""),
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        uisp_token = full_token.get("uisp_token", "")
    except:
        uisp_token = ""
    
    return await billing_service.get_customer_profile(uisp_token, token.uisp_customer_id)


@router.get("/balance")
async def get_account_balance(token: TokenPayload = Depends(verify_token)):
    """Get account balance summary"""
    logger.info("Getting account balance", customer_id=token.customer_id)
    
    # For demo, return mock data
    # In production, use actual UISP token
    return {
        "balance": -45.00,
        "credit": 0,
        "outstanding": 45.00,
        "currency": "USD",
        "next_due_date": "2024-02-01",
        "auto_pay_enabled": True
    }


@router.get("/invoices")
async def get_invoices(
    limit: int = 20,
    token: TokenPayload = Depends(verify_token)
):
    """Get customer invoices"""
    logger.info("Getting invoices", customer_id=token.customer_id, limit=limit)
    
    # Mock data for demo
    return [
        {
            "id": "inv-001",
            "number": "INV-2024-001",
            "date": "2024-01-01",
            "due_date": "2024-01-15",
            "amount": 99.00,
            "status": "paid",
            "currency": "USD"
        },
        {
            "id": "inv-002",
            "number": "INV-2024-002",
            "date": "2024-02-01",
            "due_date": "2024-02-15",
            "amount": 99.00,
            "status": "unpaid",
            "currency": "USD"
        }
    ]


@router.get("/invoices/{invoice_id}")
async def get_invoice_detail(
    invoice_id: str,
    token: TokenPayload = Depends(verify_token)
):
    """Get detailed invoice"""
    logger.info("Getting invoice detail", invoice_id=invoice_id, customer_id=token.customer_id)
    
    return {
        "id": invoice_id,
        "number": "INV-2024-001",
        "date": "2024-01-01",
        "due_date": "2024-01-15",
        "amount": 99.00,
        "tax": 0,
        "total": 99.00,
        "status": "paid",
        "currency": "USD",
        "items": [
            {
                "description": "Starlink Internet - Standard Plan",
                "quantity": 1,
                "unit_price": 99.00,
                "total": 99.00
            }
        ],
        "payments": [
            {
                "date": "2024-01-10",
                "amount": 99.00,
                "method": "Credit Card"
            }
        ]
    }


@router.get("/payments")
async def get_payments(
    limit: int = 20,
    token: TokenPayload = Depends(verify_token)
):
    """Get payment history"""
    logger.info("Getting payments", customer_id=token.customer_id, limit=limit)
    
    return [
        {
            "id": "pay-001",
            "date": "2024-01-10",
            "amount": 99.00,
            "method": "Credit Card",
            "status": "completed",
            "invoice_id": "inv-001"
        }
    ]


@router.get("/services")
async def get_services(token: TokenPayload = Depends(verify_token)):
    """Get active services/subscriptions"""
    logger.info("Getting services", customer_id=token.customer_id)
    
    return [
        {
            "id": "svc-001",
            "name": "Starlink Internet - Standard",
            "status": "active",
            "price": 99.00,
            "billing_cycle": "monthly",
            "next_billing_date": "2024-02-01",
            "data_usage": {
                "used_gb": 250,
                "limit_gb": None,  # Unlimited
                "period_start": "2024-01-01",
                "period_end": "2024-01-31"
            }
        }
    ]


@router.get("/usage")
async def get_usage_summary(token: TokenPayload = Depends(verify_token)):
    """Get data usage summary"""
    logger.info("Getting usage summary", customer_id=token.customer_id)
    
    return {
        "current_period": {
            "start": "2024-01-01",
            "end": "2024-01-31",
            "download_gb": 200,
            "upload_gb": 50,
            "total_gb": 250
        },
        "daily_average_gb": 8.3,
        "peak_usage_time": "20:00-22:00",
        "history": [
            {"date": "2024-01-28", "download_gb": 10, "upload_gb": 2},
            {"date": "2024-01-29", "download_gb": 8, "upload_gb": 1.5},
            {"date": "2024-01-30", "download_gb": 12, "upload_gb": 3}
        ]
    }
