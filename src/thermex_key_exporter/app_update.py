"""Read-only monitoring of the public Thermex Home Google Play listing."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

THERMEX_HOME_PACKAGE = "com.thermex.ru"
VERIFIED_THERMEX_HOME_VERSION = "1.0.8"
GOOGLE_PLAY_DETAILS_URL = "https://play.google.com/store/apps/details"
_PACKAGE_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+")
_VERSION_PATTERN = re.compile(
    r'\[\[\["(?P<version>[0-9][0-9A-Za-z._-]*)"\]\],\s*\[\[\[\d+\]\],\s*\[\[\[\d+,\s*"[0-9.]+"\]\]\]\]'
)
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)


class AppUpdateCheckError(RuntimeError):
    """Raised when the official store listing cannot be checked safely."""


@dataclass(frozen=True, slots=True)
class AppUpdateStatus:
    """The observed Google Play version versus the profile verified in this build."""

    verified_version: str
    store_version: str

    @property
    def update_available(self) -> bool:
        return self.store_version != self.verified_version


def google_play_url(package_name: str = THERMEX_HOME_PACKAGE) -> str:
    """Return the public listing URL for the expected Android package."""
    _validate_package_name(package_name)
    return f"{GOOGLE_PLAY_DETAILS_URL}?{urlencode({'id': package_name, 'hl': 'en_US', 'gl': 'US'})}"


def fetch_google_play_version(
    package_name: str = THERMEX_HOME_PACKAGE,
    *,
    opener: Callable[..., Any] = urlopen,
    timeout: float = 20.0,
) -> str:
    """Fetch and parse the version exposed by the public Google Play listing.

    This monitor never downloads an APK and never uses a Google account.  It
    fails closed if the listing changes shape instead of guessing a version.
    """
    _validate_package_name(package_name)
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    request = Request(
        google_play_url(package_name),
        headers={"User-Agent": _USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
    )
    try:
        with opener(request, timeout=timeout) as response:
            page = response.read().decode("utf-8")
    except (HTTPError, URLError, OSError, UnicodeDecodeError) as error:
        raise AppUpdateCheckError("could not read the public Google Play listing") from error
    return parse_google_play_version(page, package_name)


def parse_google_play_version(page: str, package_name: str = THERMEX_HOME_PACKAGE) -> str:
    """Extract the version field from a current Google Play details document."""
    _validate_package_name(package_name)
    if f'"{package_name}"' not in page:
        raise AppUpdateCheckError("Google Play did not return the expected Thermex Home listing")
    matches = {match.group("version") for match in _VERSION_PATTERN.finditer(page)}
    if len(matches) != 1:
        raise AppUpdateCheckError("Google Play version data has an unsupported format")
    return matches.pop()


def check_thermex_home_update(
    *,
    opener: Callable[..., Any] = urlopen,
    timeout: float = 20.0,
) -> AppUpdateStatus:
    """Compare the public store version with the profile verified in this build."""
    return AppUpdateStatus(
        verified_version=VERIFIED_THERMEX_HOME_VERSION,
        store_version=fetch_google_play_version(opener=opener, timeout=timeout),
    )


def _validate_package_name(package_name: str) -> None:
    if not _PACKAGE_PATTERN.fullmatch(package_name):
        raise ValueError("package name must be a valid Android package name")
