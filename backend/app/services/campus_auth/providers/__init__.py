from backend.app.services.campus_auth.providers.base import CampusAuthProvider
from backend.app.services.campus_auth.providers.browser_cookie_provider import (
    BrowserCookieCampusAuthProvider,
)
from backend.app.services.campus_auth.providers.szu_web_provider import SzuWebCampusAuthProvider

__all__ = [
    "BrowserCookieCampusAuthProvider",
    "CampusAuthProvider",
    "SzuWebCampusAuthProvider",
]
