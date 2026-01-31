"""
MikroTik Router Management API
Includes WiFi config and Hotspot management
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
import asyncio
from concurrent.futures import ThreadPoolExecutor
import structlog
import routeros_api

from app.api.auth import verify_token, TokenPayload

router = APIRouter()
logger = structlog.get_logger()
executor = ThreadPoolExecutor(max_workers=10)


class MikroTikCredentials(BaseModel):
    host: str
    username: str
    password: str
    port: int = 8728


class WifiSettings(BaseModel):
    ssid: Optional[str] = None
    password: Optional[str] = None
    security_profile: str = "default"


class HotspotUser(BaseModel):
    username: str
    password: str
    profile: str = "default"
    limit_uptime: Optional[str] = None  # e.g., "1h", "1d"
    limit_bytes_total: Optional[int] = None
    comment: Optional[str] = None


class HotspotProfile(BaseModel):
    name: str
    rate_limit: str  # e.g., "5M/5M" for 5Mbps up/down
    shared_users: int = 1
    session_timeout: str = "1h"


class VoucherRequest(BaseModel):
    count: int
    profile: str
    prefix: str = "V"
    validity: str = "1d"
    code_length: int = 8


class MikroTikService:
    """MikroTik RouterOS API Service"""
    
    def _connect(self, creds: MikroTikCredentials):
        """Create connection to MikroTik router"""
        try:
            connection = routeros_api.RouterOsApiPool(
                host=creds.host,
                username=creds.username,
                password=creds.password,
                port=creds.port,
                plaintext_login=True
            )
            return connection.get_api()
        except Exception as e:
            logger.error("MikroTik connection failed", host=creds.host, error=str(e))
            raise HTTPException(status_code=503, detail=f"Cannot connect to MikroTik: {str(e)}")
    
    async def _run_sync(self, func, *args):
        """Run synchronous function in executor"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, func, *args)
    
    # ==================== SYSTEM ====================
    
    async def get_system_info(self, creds: MikroTikCredentials) -> dict:
        """Get router system information"""
        def _get_info():
            api = self._connect(creds)
            resource = api.get_resource('/system/resource')
            identity = api.get_resource('/system/identity')
            routerboard = api.get_resource('/system/routerboard')
            
            return {
                "resource": resource.get()[0] if resource.get() else {},
                "identity": identity.get()[0] if identity.get() else {},
                "routerboard": routerboard.get()[0] if routerboard.get() else {}
            }
        
        return await self._run_sync(_get_info)
    
    async def reboot(self, creds: MikroTikCredentials) -> bool:
        """Reboot the router"""
        def _reboot():
            api = self._connect(creds)
            api.get_binary_resource('/').call('system/reboot')
            return True
        
        return await self._run_sync(_reboot)
    
    # ==================== WIFI ====================
    
    async def get_wifi_settings(self, creds: MikroTikCredentials) -> dict:
        """Get WiFi interface settings"""
        def _get_wifi():
            api = self._connect(creds)
            wireless = api.get_resource('/interface/wireless')
            security = api.get_resource('/interface/wireless/security-profiles')
            
            return {
                "interfaces": wireless.get(),
                "security_profiles": security.get()
            }
        
        return await self._run_sync(_get_wifi)
    
    async def set_wifi_password(self, creds: MikroTikCredentials, profile: str, password: str) -> bool:
        """Update WiFi password for a security profile"""
        def _set_password():
            api = self._connect(creds)
            security = api.get_resource('/interface/wireless/security-profiles')
            profiles = security.get(name=profile)
            
            if profiles:
                security.set(
                    id=profiles[0]['id'],
                    **{'wpa2-pre-shared-key': password, 'wpa-pre-shared-key': password}
                )
                return True
            return False
        
        return await self._run_sync(_set_password)
    
    async def set_wifi_ssid(self, creds: MikroTikCredentials, interface: str, ssid: str) -> bool:
        """Update WiFi SSID"""
        def _set_ssid():
            api = self._connect(creds)
            wireless = api.get_resource('/interface/wireless')
            interfaces = wireless.get(name=interface)
            
            if interfaces:
                wireless.set(id=interfaces[0]['id'], ssid=ssid)
                return True
            return False
        
        return await self._run_sync(_set_ssid)
    
    # ==================== HOTSPOT ====================
    
    async def get_hotspot_users(self, creds: MikroTikCredentials) -> List[dict]:
        """Get all hotspot users"""
        def _get_users():
            api = self._connect(creds)
            users = api.get_resource('/ip/hotspot/user')
            return users.get()
        
        return await self._run_sync(_get_users)
    
    async def create_hotspot_user(self, creds: MikroTikCredentials, user: HotspotUser) -> dict:
        """Create a new hotspot user"""
        def _create_user():
            api = self._connect(creds)
            users = api.get_resource('/ip/hotspot/user')
            
            params = {
                'name': user.username,
                'password': user.password,
                'profile': user.profile,
            }
            
            if user.limit_uptime:
                params['limit-uptime'] = user.limit_uptime
            if user.limit_bytes_total:
                params['limit-bytes-total'] = str(user.limit_bytes_total)
            if user.comment:
                params['comment'] = user.comment
            
            user_id = users.add(**params)
            return {"id": user_id, "username": user.username}
        
        return await self._run_sync(_create_user)
    
    async def delete_hotspot_user(self, creds: MikroTikCredentials, username: str) -> bool:
        """Delete a hotspot user"""
        def _delete_user():
            api = self._connect(creds)
            users = api.get_resource('/ip/hotspot/user')
            user_list = users.get(name=username)
            
            if user_list:
                users.remove(id=user_list[0]['id'])
                return True
            return False
        
        return await self._run_sync(_delete_user)
    
    async def generate_vouchers(
        self, 
        creds: MikroTikCredentials, 
        request: VoucherRequest
    ) -> List[dict]:
        """Generate hotspot vouchers"""
        import random
        import string
        
        def _generate():
            api = self._connect(creds)
            users = api.get_resource('/ip/hotspot/user')
            
            vouchers = []
            for i in range(request.count):
                # Generate unique code
                code = request.prefix + ''.join(
                    random.choices(string.ascii_uppercase + string.digits, k=request.code_length)
                )
                
                users.add(
                    name=code,
                    password=code,
                    profile=request.profile,
                    **{'limit-uptime': request.validity},
                    comment=f"Voucher generated automatically"
                )
                
                vouchers.append({
                    "code": code,
                    "profile": request.profile,
                    "validity": request.validity
                })
            
            return vouchers
        
        return await self._run_sync(_generate)
    
    async def get_active_sessions(self, creds: MikroTikCredentials) -> List[dict]:
        """Get active hotspot sessions"""
        def _get_active():
            api = self._connect(creds)
            active = api.get_resource('/ip/hotspot/active')
            return active.get()
        
        return await self._run_sync(_get_active)
    
    async def disconnect_session(self, creds: MikroTikCredentials, session_id: str) -> bool:
        """Disconnect an active hotspot session"""
        def _disconnect():
            api = self._connect(creds)
            active = api.get_resource('/ip/hotspot/active')
            active.remove(id=session_id)
            return True
        
        return await self._run_sync(_disconnect)
    
    async def get_hotspot_profiles(self, creds: MikroTikCredentials) -> List[dict]:
        """Get available hotspot profiles"""
        def _get_profiles():
            api = self._connect(creds)
            profiles = api.get_resource('/ip/hotspot/user/profile')
            return profiles.get()
        
        return await self._run_sync(_get_profiles)
    
    async def create_hotspot_profile(
        self, 
        creds: MikroTikCredentials, 
        profile: HotspotProfile
    ) -> dict:
        """Create a new hotspot user profile"""
        def _create_profile():
            api = self._connect(creds)
            profiles = api.get_resource('/ip/hotspot/user/profile')
            
            profile_id = profiles.add(
                name=profile.name,
                **{
                    'rate-limit': profile.rate_limit,
                    'shared-users': str(profile.shared_users),
                    'session-timeout': profile.session_timeout
                }
            )
            
            return {"id": profile_id, "name": profile.name}
        
        return await self._run_sync(_create_profile)


mikrotik_service = MikroTikService()


# ==================== API ENDPOINTS ====================

@router.post("/system/info")
async def get_system_info(
    creds: MikroTikCredentials,
    token: TokenPayload = Depends(verify_token)
):
    """Get MikroTik system information"""
    logger.info("Getting MikroTik system info", host=creds.host, customer_id=token.customer_id)
    return await mikrotik_service.get_system_info(creds)


@router.post("/system/reboot")
async def reboot_router(
    creds: MikroTikCredentials,
    token: TokenPayload = Depends(verify_token)
):
    """Reboot MikroTik router"""
    logger.info("Rebooting MikroTik", host=creds.host, customer_id=token.customer_id)
    await mikrotik_service.reboot(creds)
    return {"status": "rebooting"}


@router.post("/wifi")
async def get_wifi_settings(
    creds: MikroTikCredentials,
    token: TokenPayload = Depends(verify_token)
):
    """Get MikroTik WiFi settings"""
    return await mikrotik_service.get_wifi_settings(creds)


@router.put("/wifi")
async def update_wifi_settings(
    creds: MikroTikCredentials,
    settings: WifiSettings,
    token: TokenPayload = Depends(verify_token)
):
    """Update MikroTik WiFi settings"""
    results = {}
    
    if settings.password:
        results["password_updated"] = await mikrotik_service.set_wifi_password(
            creds, settings.security_profile, settings.password
        )
    
    if settings.ssid:
        # Update SSID on all wireless interfaces
        wifi = await mikrotik_service.get_wifi_settings(creds)
        for interface in wifi.get("interfaces", []):
            await mikrotik_service.set_wifi_ssid(creds, interface["name"], settings.ssid)
        results["ssid_updated"] = True
    
    logger.info("WiFi settings updated", host=creds.host, customer_id=token.customer_id)
    return results


@router.post("/hotspot/users")
async def get_hotspot_users(
    creds: MikroTikCredentials,
    token: TokenPayload = Depends(verify_token)
):
    """Get all hotspot users"""
    return await mikrotik_service.get_hotspot_users(creds)


@router.post("/hotspot/users/create")
async def create_hotspot_user(
    creds: MikroTikCredentials,
    user: HotspotUser,
    token: TokenPayload = Depends(verify_token)
):
    """Create a new hotspot user"""
    logger.info("Creating hotspot user", username=user.username, customer_id=token.customer_id)
    return await mikrotik_service.create_hotspot_user(creds, user)


@router.delete("/hotspot/users/{username}")
async def delete_hotspot_user(
    username: str,
    creds: MikroTikCredentials,
    token: TokenPayload = Depends(verify_token)
):
    """Delete a hotspot user"""
    logger.info("Deleting hotspot user", username=username, customer_id=token.customer_id)
    success = await mikrotik_service.delete_hotspot_user(creds, username)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "deleted"}


@router.post("/hotspot/vouchers")
async def generate_vouchers(
    creds: MikroTikCredentials,
    request: VoucherRequest,
    token: TokenPayload = Depends(verify_token)
):
    """Generate hotspot vouchers"""
    logger.info(
        "Generating vouchers",
        count=request.count,
        profile=request.profile,
        customer_id=token.customer_id
    )
    vouchers = await mikrotik_service.generate_vouchers(creds, request)
    return {"vouchers": vouchers, "count": len(vouchers)}


@router.post("/hotspot/active")
async def get_active_sessions(
    creds: MikroTikCredentials,
    token: TokenPayload = Depends(verify_token)
):
    """Get active hotspot sessions"""
    return await mikrotik_service.get_active_sessions(creds)


@router.post("/hotspot/active/{session_id}/disconnect")
async def disconnect_session(
    session_id: str,
    creds: MikroTikCredentials,
    token: TokenPayload = Depends(verify_token)
):
    """Disconnect an active hotspot session"""
    logger.info("Disconnecting session", session_id=session_id, customer_id=token.customer_id)
    await mikrotik_service.disconnect_session(creds, session_id)
    return {"status": "disconnected"}


@router.post("/hotspot/profiles")
async def get_hotspot_profiles(
    creds: MikroTikCredentials,
    token: TokenPayload = Depends(verify_token)
):
    """Get available hotspot profiles"""
    return await mikrotik_service.get_hotspot_profiles(creds)


@router.post("/hotspot/profiles/create")
async def create_hotspot_profile(
    creds: MikroTikCredentials,
    profile: HotspotProfile,
    token: TokenPayload = Depends(verify_token)
):
    """Create a new hotspot user profile"""
    logger.info("Creating hotspot profile", name=profile.name, customer_id=token.customer_id)
    return await mikrotik_service.create_hotspot_profile(creds, profile)
