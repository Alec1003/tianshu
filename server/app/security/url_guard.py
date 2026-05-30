"""Outbound URL validation for user-configured provider endpoints."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

_BLOCKED_HOSTS = {
    "metadata.google.internal",
}
_TRUSTED_PUBLIC_HOSTS = {
    "api.anthropic.com",
    "api.deepseek.com",
    "api.minimax.chat",
    "api.openai.com",
    "dashscope.aliyuncs.com",
    "generativelanguage.googleapis.com",
    "open.bigmodel.cn",
    "openrouter.ai",
}
_BLOCKED_IPS = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("100.100.100.200"),
    ipaddress.ip_address("fd00:ec2::254"),
}
_BLOCKED_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
)


class UnsafeBaseUrlError(ValueError):
    """Raised when a configured model endpoint can target unsafe networks."""


def normalize_and_validate_base_url(
    base_url: str,
    *,
    allow_private_network: bool = False,
) -> str:
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        raise UnsafeBaseUrlError("base URL is required")
    if not normalized.startswith(("http://", "https://")):
        normalized = f"https://{normalized}"

    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeBaseUrlError("base URL must use http or https")
    if parsed.username or parsed.password:
        raise UnsafeBaseUrlError("base URL must not contain credentials")
    if not parsed.hostname:
        raise UnsafeBaseUrlError("base URL must include a host")

    host = parsed.hostname.strip().lower().rstrip(".")
    _validate_host(host, allow_private_network=allow_private_network)
    return normalized


def _validate_host(host: str, *, allow_private_network: bool) -> None:
    if host in _BLOCKED_HOSTS:
        raise UnsafeBaseUrlError("base URL points to a metadata service")
    if host == "localhost" or host.endswith(_BLOCKED_SUFFIXES):
        if allow_private_network:
            return
        raise UnsafeBaseUrlError("base URL points to a local/internal host")
    if host in _TRUSTED_PUBLIC_HOSTS:
        return

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        _validate_resolved_addresses(host, allow_private_network=allow_private_network)
        return

    _validate_ip(address, allow_private_network=allow_private_network)


def _validate_resolved_addresses(host: str, *, allow_private_network: bool) -> None:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeBaseUrlError("base URL host could not be resolved") from exc

    addresses = {info[4][0] for info in infos if info[4]}
    if not addresses:
        raise UnsafeBaseUrlError("base URL host could not be resolved")
    for raw_address in addresses:
        _validate_ip(
            ipaddress.ip_address(raw_address),
            allow_private_network=allow_private_network,
        )


def _validate_ip(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    allow_private_network: bool,
) -> None:
    if address in _BLOCKED_IPS:
        raise UnsafeBaseUrlError("base URL points to a metadata service")
    if address.is_link_local or address.is_multicast or address.is_unspecified:
        raise UnsafeBaseUrlError("base URL points to a private or non-routable network")
    if allow_private_network and (address.is_loopback or address.is_private):
        return
    if not address.is_global:
        raise UnsafeBaseUrlError("base URL points to a private or non-routable network")
