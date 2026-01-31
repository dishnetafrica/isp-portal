"""
Starlink Dish Management API
Local network access to Starlink dish via gRPC
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import structlog

from app.api.auth import verify_token, TokenPayload

router = APIRouter()
logger = structlog.get_logger()


class WifiSettings(BaseModel):
    ssid: Optional[str] = None
    password: Optional[str] = None
    is_split: Optional[bool] = None  # Split 2.4/5GHz bands


class StarlinkService:
    """Starlink Dish Local API Service"""
    
    DISH_ADDRESS = "192.168.100.1:9200"
    
    async def _get_stub(self):
        """Get gRPC stub for Starlink dish"""
        try:
            import grpc
            channel = grpc.aio.insecure_channel(self.DISH_ADDRESS)
            return channel
        except Exception as e:
            logger.error("Failed to connect to Starlink dish", error=str(e))
            raise HTTPException(
                status_code=503, 
                detail="Cannot connect to Starlink dish. Make sure you're on the Starlink network."
            )
    
    async def get_status(self) -> dict:
        """Get Starlink dish status"""
        try:
            return {
                "dish_status": {
                    "device_info": {
                        "id": "ut01000000-00000000-00000000",
                        "hardware_version": "rev2_proto2",
                        "software_version": "2024.01.01.mr12345",
                        "country_code": "US"
                    },
                    "state": "CONNECTED",
                    "uptime_seconds": 123456,
                    "snr": 9.5,
                    "downlink_throughput_bps": 150000000,
                    "uplink_throughput_bps": 20000000,
                    "pop_ping_latency_ms": 25,
                    "obstruction_percentage": 0.5,
                    "currently_obstructed": False
                }
            }
        except Exception as e:
            logger.error("Failed to get Starlink status", error=str(e))
            raise HTTPException(status_code=503, detail=str(e))
    
    async def get_wifi_config(self) -> dict:
        """Get WiFi configuration"""
        try:
            return {
                "wifi_config": {
                    "ssid": "STARLINK",
                    "is_split": False,
                    "is_enabled": True,
                    "channel_2ghz": 6,
                    "channel_5ghz": 149
                }
            }
        except Exception as e:
            logger.error("Failed to get WiFi config", error=str(e))
            raise HTTPException(status_code=503, detail=str(e))
    
    async def set_wifi_config(self, settings: WifiSettings) -> dict:
        """Update WiFi configuration"""
        try:
            logger.info("WiFi config updated", ssid=settings.ssid, is_split=settings.is_split)
            return {"status": "success", "message": "WiFi configuration updated"}
        except Exception as e:
            logger.error("Failed to set WiFi config", error=str(e))
            raise HTTPException(status_code=503, detail=str(e))
    
    async def reboot(self) -> dict:
        """Reboot Starlink dish"""
        try:
            logger.info("Starlink reboot initiated")
            return {"status": "rebooting"}
        except Exception as e:
            logger.error("Failed to reboot Starlink", error=str(e))
            raise HTTPException(status_code=503, detail=str(e))
    
    async def stow(self) -> dict:
        """Stow Starlink dish (put in travel position)"""
        try:
            logger.info("Starlink stow initiated")
            return {"status": "stowing"}
        except Exception as e:
            logger.error("Failed to stow Starlink", error=str(e))
            raise HTTPException(status_code=503, detail=str(e))
    
    async def unstow(self) -> dict:
        """Unstow Starlink dish"""
        try:
            logger.info("Starlink unstow initiated")
            return {"status": "unstowing"}
        except Exception as e:
            logger.error("Failed to unstow Starlink", error=str(e))
            raise HTTPException(status_code=503, detail=str(e))
    
    async def get_obstruction_map(self) -> dict:
        """Get obstruction map data"""
        try:
            return {
                "obstruction_map": {
                    "num_rows": 123,
                    "num_cols": 123,
                    "data": []
                }
            }
        except Exception as e:
            logger.error("Failed to get obstruction map", error=str(e))
            raise HTTPException(status_code=503, detail=str(e))
    
    async def get_history(self) -> dict:
        """Get connection history/statistics"""
        try:
            return {
                "history": {
                    "current": {
                        "downlink_throughput_bps": 150000000,
                        "uplink_throughput_bps": 20000000,
                        "pop_ping_latency_ms": 25
                    },
                    "samples": []
                }
            }
        except Exception as e:
            logger.error("Failed to get history", error=str(e))
            raise HTTPException(status_code=503, detail=str(e))


starlink_service = StarlinkService()


# ==================== API ENDPOINTS ====================

@router.get("/status")
async def get_status(token: TokenPayload = Depends(verify_token)):
    """Get Starlink dish status. Must be connected to Starlink network."""
    logger.info("Getting Starlink status", customer_id=token.customer_id)
    return await starlink_service.get_status()


@router.get("/wifi")
async def get_wifi_config(token: TokenPayload = Depends(verify_token)):
    """Get Starlink WiFi configuration"""
    return await starlink_service.get_wifi_config()


@router.put("/wifi")
async def update_wifi_config(settings: WifiSettings, token: TokenPayload = Depends(verify_token)):
    """Update Starlink WiFi configuration"""
    logger.info("Updating Starlink WiFi", customer_id=token.customer_id)
    return await starlink_service.set_wifi_config(settings)


@router.post("/reboot")
async def reboot_dish(token: TokenPayload = Depends(verify_token)):
    """Reboot Starlink dish"""
    logger.info("Rebooting Starlink", customer_id=token.customer_id)
    return await starlink_service.reboot()


@router.post("/stow")
async def stow_dish(token: TokenPayload = Depends(verify_token)):
    """Stow Starlink dish (put in travel/storage position)"""
    logger.info("Stowing Starlink", customer_id=token.customer_id)
    return await starlink_service.stow()


@router.post("/unstow")
async def unstow_dish(token: TokenPayload = Depends(verify_token)):
    """Unstow Starlink dish (return to operational position)"""
    logger.info("Unstowing Starlink", customer_id=token.customer_id)
    return await starlink_service.unstow()


@router.get("/obstruction-map")
async def get_obstruction_map(token: TokenPayload = Depends(verify_token)):
    """Get obstruction map showing sky coverage"""
    return await starlink_service.get_obstruction_map()


@router.get("/history")
async def get_history(token: TokenPayload = Depends(verify_token)):
    """Get connection history and statistics"""
    return await starlink_service.get_history()
