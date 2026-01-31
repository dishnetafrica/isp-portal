"""
TR-069 Device Management API
Supports D-Link, TP-Link, and other TR-069 compatible devices via GenieACS
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
import httpx
import structlog
import json

from app.api.auth import verify_token, TokenPayload
from app.core.config import settings

router = APIRouter()
logger = structlog.get_logger()


class WifiSettings(BaseModel):
    ssid: Optional[str] = None
    password: Optional[str] = None
    channel: Optional[int] = None
    enabled: Optional[bool] = None


class DeviceTask(BaseModel):
    task_id: str
    status: str
    device_id: str


class TR069Service:
    """TR-069 ACS (GenieACS) Integration Service"""
    
    def __init__(self):
        self.base_url = settings.GENIEACS_URL.rstrip('/')
    
    async def _request(self, method: str, path: str, **kwargs):
        """Make request to GenieACS NBI"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method,
                f"{self.base_url}{path}",
                **kwargs
            )
            
            if response.status_code >= 400:
                logger.error("GenieACS request failed", 
                           path=path, 
                           status=response.status_code,
                           response=response.text)
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"GenieACS error: {response.text}"
                )
            
            if response.text:
                return response.json()
            return None
    
    async def get_devices(self, query: dict = None) -> List[dict]:
        """Get all TR-069 devices"""
        params = {}
        if query:
            params["query"] = json.dumps(query)
        
        return await self._request("GET", "/devices", params=params)
    
    async def get_device(self, device_id: str) -> dict:
        """Get specific device by ID"""
        devices = await self._request(
            "GET", 
            "/devices",
            params={"query": json.dumps({"_id": device_id})}
        )
        if devices:
            return devices[0]
        raise HTTPException(status_code=404, detail="Device not found")
    
    async def get_device_parameters(self, device_id: str, parameters: List[str]) -> dict:
        """Get specific parameters from device"""
        result = {}
        
        for param in parameters:
            try:
                data = await self._request(
                    "GET",
                    f"/devices/{device_id}/parameters/{param}"
                )
                if data:
                    result[param.split('.')[-1]] = data
            except Exception as e:
                logger.warning(f"Failed to get parameter {param}", error=str(e))
        
        return result
    
    async def set_device_parameter(
        self, 
        device_id: str, 
        parameter: str, 
        value: str,
        connection_request: bool = True
    ) -> dict:
        """Set a device parameter via TR-069"""
        task = {
            "name": "setParameterValues",
            "parameterValues": [[parameter, value, "xsd:string"]]
        }
        
        params = {}
        if connection_request:
            params["connection_request"] = "true"
        
        return await self._request(
            "POST",
            f"/devices/{device_id}/tasks",
            json=task,
            params=params
        )
    
    async def reboot_device(self, device_id: str) -> dict:
        """Reboot device via TR-069"""
        task = {"name": "reboot"}
        return await self._request(
            "POST",
            f"/devices/{device_id}/tasks",
            json=task,
            params={"connection_request": "true"}
        )
    
    async def factory_reset(self, device_id: str) -> dict:
        """Factory reset device via TR-069"""
        task = {"name": "factoryReset"}
        return await self._request(
            "POST",
            f"/devices/{device_id}/tasks",
            json=task,
            params={"connection_request": "true"}
        )
    
    async def refresh_device(self, device_id: str) -> dict:
        """Request device to refresh all parameters"""
        task = {"name": "refreshObject", "objectName": ""}
        return await self._request(
            "POST",
            f"/devices/{device_id}/tasks",
            json=task,
            params={"connection_request": "true"}
        )
    
    async def get_pending_tasks(self, device_id: str) -> List[dict]:
        """Get pending tasks for device"""
        return await self._request(
            "GET",
            "/tasks",
            params={"query": json.dumps({"device": device_id})}
        )
    
    async def delete_task(self, task_id: str) -> None:
        """Delete a pending task"""
        await self._request("DELETE", f"/tasks/{task_id}")
    
    # ==================== WIFI MANAGEMENT ====================
    
    # TR-069 parameter paths (may vary by device manufacturer)
    WIFI_PARAMS = {
        "default": {
            "ssid": "InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.SSID",
            "password": "InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.PreSharedKey.1.PreSharedKey",
            "enabled": "InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.Enable",
            "channel": "InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.Channel",
        },
        "tr181": {
            "ssid": "Device.WiFi.SSID.1.SSID",
            "password": "Device.WiFi.AccessPoint.1.Security.KeyPassphrase",
            "enabled": "Device.WiFi.SSID.1.Enable",
            "channel": "Device.WiFi.Radio.1.Channel",
        }
    }
    
    def _get_wifi_params(self, device: dict) -> dict:
        """Determine correct WiFi parameter paths for device"""
        # Check if device uses TR-181 data model
        device_data = device.get("Device", {})
        if device_data:
            return self.WIFI_PARAMS["tr181"]
        return self.WIFI_PARAMS["default"]
    
    async def get_wifi_settings(self, device_id: str) -> dict:
        """Get WiFi settings from TR-069 device"""
        device = await self.get_device(device_id)
        params = self._get_wifi_params(device)
        
        return await self.get_device_parameters(device_id, list(params.values()))
    
    async def set_wifi_ssid(self, device_id: str, ssid: str) -> dict:
        """Set WiFi SSID"""
        device = await self.get_device(device_id)
        params = self._get_wifi_params(device)
        
        return await self.set_device_parameter(
            device_id, 
            params["ssid"], 
            ssid
        )
    
    async def set_wifi_password(self, device_id: str, password: str) -> dict:
        """Set WiFi password"""
        device = await self.get_device(device_id)
        params = self._get_wifi_params(device)
        
        return await self.set_device_parameter(
            device_id,
            params["password"],
            password
        )
    
    async def set_wifi_enabled(self, device_id: str, enabled: bool) -> dict:
        """Enable/disable WiFi"""
        device = await self.get_device(device_id)
        params = self._get_wifi_params(device)
        
        return await self.set_device_parameter(
            device_id,
            params["enabled"],
            "1" if enabled else "0"
        )
    
    async def get_device_status(self, device_id: str) -> dict:
        """Get comprehensive device status"""
        device = await self.get_device(device_id)
        
        # Extract useful info from device data
        device_id_info = device.get("_deviceId", {})
        
        # Try to get common status parameters
        status_params = [
            "InternetGatewayDevice.DeviceInfo.UpTime",
            "InternetGatewayDevice.DeviceInfo.SoftwareVersion",
            "InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANIPConnection.1.ExternalIPAddress",
            "InternetGatewayDevice.LANDevice.1.LANHostConfigManagement.DHCPServerEnable",
        ]
        
        status = await self.get_device_parameters(device_id, status_params)
        
        return {
            "device_id": device.get("_id"),
            "manufacturer": device_id_info.get("_Manufacturer"),
            "model": device_id_info.get("_ProductClass"),
            "serial": device_id_info.get("_SerialNumber"),
            "last_inform": device.get("_lastInform"),
            "registered": device.get("_registered"),
            "status": status
        }


tr069_service = TR069Service()


# ==================== API ENDPOINTS ====================

@router.get("/devices")
async def list_devices(
    token: TokenPayload = Depends(verify_token)
):
    """List all TR-069 devices"""
    logger.info("Listing TR-069 devices", customer_id=token.customer_id)
    devices = await tr069_service.get_devices()
    
    # Return simplified device list
    return [
        {
            "device_id": d.get("_id"),
            "manufacturer": d.get("_deviceId", {}).get("_Manufacturer"),
            "model": d.get("_deviceId", {}).get("_ProductClass"),
            "serial": d.get("_deviceId", {}).get("_SerialNumber"),
            "last_seen": d.get("_lastInform"),
        }
        for d in devices
    ]


@router.get("/devices/{device_id}")
async def get_device(
    device_id: str,
    token: TokenPayload = Depends(verify_token)
):
    """Get TR-069 device details"""
    return await tr069_service.get_device(device_id)


@router.get("/devices/{device_id}/status")
async def get_device_status(
    device_id: str,
    token: TokenPayload = Depends(verify_token)
):
    """Get device status summary"""
    logger.info("Getting device status", device_id=device_id, customer_id=token.customer_id)
    return await tr069_service.get_device_status(device_id)


@router.get("/devices/{device_id}/wifi")
async def get_wifi_settings(
    device_id: str,
    token: TokenPayload = Depends(verify_token)
):
    """Get WiFi settings"""
    return await tr069_service.get_wifi_settings(device_id)


@router.put("/devices/{device_id}/wifi")
async def update_wifi_settings(
    device_id: str,
    settings: WifiSettings,
    token: TokenPayload = Depends(verify_token)
):
    """Update WiFi settings"""
    logger.info("Updating WiFi settings", device_id=device_id, customer_id=token.customer_id)
    
    tasks = []
    
    if settings.ssid is not None:
        task = await tr069_service.set_wifi_ssid(device_id, settings.ssid)
        tasks.append({"parameter": "ssid", "task": task})
    
    if settings.password is not None:
        task = await tr069_service.set_wifi_password(device_id, settings.password)
        tasks.append({"parameter": "password", "task": task})
    
    if settings.enabled is not None:
        task = await tr069_service.set_wifi_enabled(device_id, settings.enabled)
        tasks.append({"parameter": "enabled", "task": task})
    
    return {"tasks": tasks, "message": "Settings queued for device update"}


@router.post("/devices/{device_id}/reboot")
async def reboot_device(
    device_id: str,
    token: TokenPayload = Depends(verify_token)
):
    """Reboot TR-069 device"""
    logger.info("Rebooting device", device_id=device_id, customer_id=token.customer_id)
    task = await tr069_service.reboot_device(device_id)
    return {"status": "reboot_requested", "task": task}


@router.post("/devices/{device_id}/factory-reset")
async def factory_reset_device(
    device_id: str,
    token: TokenPayload = Depends(verify_token)
):
    """Factory reset TR-069 device (use with caution!)"""
    logger.warning("Factory reset requested", device_id=device_id, customer_id=token.customer_id)
    task = await tr069_service.factory_reset(device_id)
    return {"status": "factory_reset_requested", "task": task}


@router.post("/devices/{device_id}/refresh")
async def refresh_device(
    device_id: str,
    token: TokenPayload = Depends(verify_token)
):
    """Request device to refresh all parameters"""
    logger.info("Refreshing device", device_id=device_id, customer_id=token.customer_id)
    task = await tr069_service.refresh_device(device_id)
    return {"status": "refresh_requested", "task": task}


@router.get("/devices/{device_id}/tasks")
async def get_pending_tasks(
    device_id: str,
    token: TokenPayload = Depends(verify_token)
):
    """Get pending tasks for device"""
    return await tr069_service.get_pending_tasks(device_id)


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str,
    token: TokenPayload = Depends(verify_token)
):
    """Delete a pending task"""
    await tr069_service.delete_task(task_id)
    return {"status": "deleted"}
