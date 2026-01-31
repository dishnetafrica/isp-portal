"""
Hotspot Management API
Unified hotspot management interface
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
import structlog

from app.api.auth import verify_token, TokenPayload
from app.api.mikrotik import mikrotik_service, MikroTikCredentials, HotspotUser, VoucherRequest

router = APIRouter()
logger = structlog.get_logger()


class QuickVoucher(BaseModel):
    """Quick voucher generation with presets"""
    preset: str  # "1hour", "1day", "1week", "1month"
    count: int = 1


class BulkVoucherPrint(BaseModel):
    """Voucher codes for printing"""
    vouchers: List[dict]
    format: str = "thermal"  # "thermal", "a4", "card"


VOUCHER_PRESETS = {
    "1hour": {"profile": "1hour", "validity": "1h", "rate": "5M/5M"},
    "1day": {"profile": "1day", "validity": "1d", "rate": "10M/10M"},
    "1week": {"profile": "1week", "validity": "7d", "rate": "10M/10M"},
    "1month": {"profile": "1month", "validity": "30d", "rate": "20M/20M"},
}


@router.post("/quick-vouchers")
async def generate_quick_vouchers(
    creds: MikroTikCredentials,
    request: QuickVoucher,
    token: TokenPayload = Depends(verify_token)
):
    """
    Generate vouchers using presets
    Presets: 1hour, 1day, 1week, 1month
    """
    if request.preset not in VOUCHER_PRESETS:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid preset. Available: {list(VOUCHER_PRESETS.keys())}"
        )
    
    preset = VOUCHER_PRESETS[request.preset]
    
    logger.info(
        "Generating quick vouchers",
        preset=request.preset,
        count=request.count,
        customer_id=token.customer_id
    )
    
    voucher_request = VoucherRequest(
        count=request.count,
        profile=preset["profile"],
        validity=preset["validity"],
        prefix=request.preset.upper()[:2]
    )
    
    vouchers = await mikrotik_service.generate_vouchers(creds, voucher_request)
    
    return {
        "vouchers": vouchers,
        "preset": request.preset,
        "preset_details": preset
    }


@router.post("/print-vouchers")
async def format_vouchers_for_print(
    request: BulkVoucherPrint,
    token: TokenPayload = Depends(verify_token)
):
    """
    Format vouchers for printing
    Returns formatted HTML/text for different print formats
    """
    if request.format == "thermal":
        # Format for 58mm thermal printer
        output = []
        for v in request.vouchers:
            output.append(f"""
================================
     WIFI VOUCHER
================================
  Code: {v['code']}
  Valid: {v.get('validity', 'N/A')}
  Speed: {v.get('profile', 'Standard')}
--------------------------------
  Connect to: YOUR_WIFI_NAME
  Open browser, enter code
================================
""")
        return {"format": "text", "content": "\n".join(output)}
    
    elif request.format == "a4":
        # Format for A4 paper (multiple vouchers per page)
        html = """
<!DOCTYPE html>
<html>
<head>
<style>
.voucher-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.voucher { border: 2px dashed #333; padding: 15px; text-align: center; }
.code { font-size: 24px; font-weight: bold; letter-spacing: 2px; }
.details { font-size: 12px; color: #666; margin-top: 10px; }
@media print { .voucher { break-inside: avoid; } }
</style>
</head>
<body>
<div class="voucher-grid">
"""
        for v in request.vouchers:
            html += f"""
<div class="voucher">
    <div>WiFi Voucher</div>
    <div class="code">{v['code']}</div>
    <div class="details">
        Valid for: {v.get('validity', 'N/A')}<br>
        Speed: {v.get('profile', 'Standard')}
    </div>
</div>
"""
        html += "</div></body></html>"
        return {"format": "html", "content": html}
    
    elif request.format == "card":
        # Business card size format
        html = """
<!DOCTYPE html>
<html>
<head>
<style>
.card { width: 85mm; height: 54mm; border: 1px solid #333; 
        padding: 10px; margin: 5px; display: inline-block; }
.code { font-size: 20px; font-weight: bold; margin: 10px 0; }
</style>
</head>
<body>
"""
        for v in request.vouchers:
            html += f"""
<div class="card">
    <h3>WiFi Access</h3>
    <div class="code">{v['code']}</div>
    <small>Valid: {v.get('validity', 'N/A')} | {v.get('profile', '')}</small>
</div>
"""
        html += "</body></html>"
        return {"format": "html", "content": html}
    
    raise HTTPException(status_code=400, detail="Invalid format")


@router.get("/presets")
async def get_voucher_presets(token: TokenPayload = Depends(verify_token)):
    """Get available voucher presets"""
    return {
        "presets": [
            {"id": k, **v, "description": f"{k} access voucher"}
            for k, v in VOUCHER_PRESETS.items()
        ]
    }


@router.post("/dashboard")
async def get_hotspot_dashboard(
    creds: MikroTikCredentials,
    token: TokenPayload = Depends(verify_token)
):
    """
    Get hotspot dashboard with summary statistics
    """
    logger.info("Getting hotspot dashboard", customer_id=token.customer_id)
    
    # Get all data in parallel
    import asyncio
    users, active, profiles = await asyncio.gather(
        mikrotik_service.get_hotspot_users(creds),
        mikrotik_service.get_active_sessions(creds),
        mikrotik_service.get_hotspot_profiles(creds)
    )
    
    # Calculate statistics
    total_users = len(users)
    active_sessions = len(active)
    unused_vouchers = sum(1 for u in users if u.get('uptime', '0s') == '0s')
    
    # Calculate bandwidth usage from active sessions
    total_download = sum(int(s.get('bytes-in', 0)) for s in active)
    total_upload = sum(int(s.get('bytes-out', 0)) for s in active)
    
    return {
        "summary": {
            "total_users": total_users,
            "active_sessions": active_sessions,
            "unused_vouchers": unused_vouchers,
            "available_profiles": len(profiles)
        },
        "bandwidth": {
            "download_bytes": total_download,
            "upload_bytes": total_upload,
            "download_mb": round(total_download / 1024 / 1024, 2),
            "upload_mb": round(total_upload / 1024 / 1024, 2)
        },
        "active_sessions": active[:10],  # Return first 10
        "profiles": profiles
    }
