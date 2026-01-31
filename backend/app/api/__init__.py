"""
API Routers
"""

from app.api import auth, devices, starlink, mikrotik, tr069, billing, hotspot

__all__ = ['auth', 'devices', 'starlink', 'mikrotik', 'tr069', 'billing', 'hotspot']
