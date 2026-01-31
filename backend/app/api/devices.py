"""
Device Detection API
Auto-detect connected network devices (Starlink, MikroTik, TR-069)
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import asyncio
import socket
import httpx
import structlog

from app.api.auth import verify_token, TokenPayload
from app.core.config import settings

router = APIRouter()
logger = structlog.get_logger()


class DeviceDetectionRequest(BaseModel):
    gateway_ip: str


class DeviceInfo(BaseModel):
    device_type: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    device_id: Optional[str] = None
    ip_address: Optional[str] = None
    capabilities: list = []


async def check_port(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check if a port is open on a host"""
    try:
        loop = asyncio.get_event_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = await loop.run_in_executor(
            None, 
            lambda: sock.connect_ex((host, port))
        )
        sock.close()
        return result == 0
    except Exception:
        return False


async def detect_starlink(ip: str) -> Optional[DeviceInfo]:
    """Detect Starlink dish at the given IP"""
    if ip != "192.168.100.1":
        return None
    
    # Check if gRPC port is open
    if await check_port(ip, 9200):
        return DeviceInfo(
            device_type="starlink",
            manufacturer="SpaceX",
            model="Starlink Dish",
            ip_address=ip,
            capabilities=["wifi_config", "status", "reboot", "stow"]
        )
    return None


async def detect_mikrotik(ip: str) -> Optional[DeviceInfo]:
    """Detect MikroTik router at the given IP"""
    # Check RouterOS API port (8728) or WinBox port (8291)
    api_port_open = await check_port(ip, 8728)
    winbox_port_open = await check_port(ip, 8291)
    
    if api_port_open or winbox_port_open:
        capabilities = ["wifi_config", "status", "reboot"]
        
        # Check if hotspot is likely available (check for port 80)
        if await check_port(ip, 80):
            capabilities.extend(["hotspot_users", "hotspot_vouchers", "hotspot_profiles"])
        
        return DeviceInfo(
            device_type="mikrotik",
            manufacturer="MikroTik",
            ip_address=ip,
            capabilities=capabilities
        )
    return None


async def detect_tr069_device(ip: str) -> Optional[DeviceInfo]:
    """Check GenieACS for TR-069 devices with this IP"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Search GenieACS for device by IP
            response = await client.get(
                f"{settings.GENIEACS_URL}/devices",
                params={
                    "query": f'{{"InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANIPConnection.1.ExternalIPAddress":"{ip}"}}'
                }
            )
            
            if response.status_code == 200:
                devices = response.json()
                if devices:
                    device = devices[0]
                    device_id = device.get("_deviceId", {})
                    
                    return DeviceInfo(
                        device_type="tr069",
                        manufacturer=device_id.get("_Manufacturer", "Unknown"),
                        model=device_id.get("_ProductClass", "Unknown"),
                        device_id=device.get("_id"),
                        ip_address=ip,
                        capabilities=["wifi_config", "status", "reboot", "firmware_update"]
                    )
    except Exception as e:
        logger.warning("TR-069 detection failed", error=str(e))
    
    return None


async def detect_by_http_fingerprint(ip: str) -> Optional[DeviceInfo]:
    """Try to identify device by HTTP response fingerprint"""
    try:
        async with httpx.AsyncClient(timeout=3.0, verify=False) as client:
            response = await client.get(f"http://{ip}/")
            
            content = response.text.lower()
            headers = dict(response.headers)
            server = headers.get("server", "").lower()
            
            # TP-Link detection
            if "tp-link" in content or "tp-link" in server:
                return DeviceInfo(
                    device_type="tr069",
                    manufacturer="TP-Link",
                    ip_address=ip,
                    capabilities=["wifi_config", "status", "reboot"]
                )
            
            # D-Link detection
            if "d-link" in content or "d-link" in server:
                return DeviceInfo(
                    device_type="tr069",
                    manufacturer="D-Link",
                    ip_address=ip,
                    capabilities=["wifi_config", "status", "reboot"]
                )
            
            # ASUS detection
            if "asus" in content or "asuswrt" in content:
                return DeviceInfo(
                    device_type="asus",
                    manufacturer="ASUS",
                    ip_address=ip,
                    capabilities=["wifi_config", "status"]
                )
            
            # Ubiquiti detection
            if "ubnt" in content or "ubiquiti" in content or "unifi" in content:
                return DeviceInfo(
                    device_type="ubiquiti",
                    manufacturer="Ubiquiti",
                    ip_address=ip,
                    capabilities=["status"]
                )
                
    except Exception:
        pass
    
    return None


@router.post("/detect", response_model=DeviceInfo)
async def detect_device(
    request: DeviceDetectionRequest,
    token: TokenPayload = Depends(verify_token)
):
    """
    Auto-detect device type based on gateway IP
    """
    ip = request.gateway_ip
    logger.info("Device detection started", ip=ip, customer_id=token.customer_id)
    
    # Run all detection methods concurrently
    results = await asyncio.gather(
        detect_starlink(ip),
        detect_mikrotik(ip),
        detect_tr069_device(ip),
        detect_by_http_fingerprint(ip),
        return_exceptions=True
    )
    
    # Return first successful detection
    for result in results:
        if isinstance(result, DeviceInfo):
            logger.info(
                "Device detected",
                device_type=result.device_type,
                manufacturer=result.manufacturer,
                ip=ip
            )
            return result
    
    # No device detected
    logger.warning("No device detected", ip=ip)
    return DeviceInfo(
        device_type="unknown",
        ip_address=ip,
        capabilities=[]
    )


@router.get("/supported")
async def get_supported_devices():
    """
    Get list of supported device types and their capabilities
    """
    return {
        "devices": [
            {
                "type": "starlink",
                "name": "Starlink Dish",
                "capabilities": [
                    "wifi_config",
                    "dish_status",
                    "obstruction_map",
                    "speed_test",
                    "reboot",
                    "stow"
                ]
            },
            {
                "type": "mikrotik",
                "name": "MikroTik Router",
                "capabilities": [
                    "wifi_config",
                    "hotspot_users",
                    "hotspot_vouchers",
                    "hotspot_profiles",
                    "active_sessions",
                    "bandwidth_monitor",
                    "reboot"
                ]
            },
            {
                "type": "tr069",
                "name": "TR-069 Device (D-Link, TP-Link, etc.)",
                "capabilities": [
                    "wifi_config",
                    "device_status",
                    "firmware_update",
                    "reboot",
                    "factory_reset"
                ]
            }
        ]
    }
