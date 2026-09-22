"""Network target validation shared by browser-facing Python code."""
from __future__ import annotations
import ipaddress,socket
from urllib.parse import urlsplit
BLOCKED_HOSTNAMES={"localhost","localhost.localdomain","ip6-localhost","ip6-loopback","broadcasthost","0.0.0.0","::","[::]"}
def blocked_ip(address:str)->bool:
    try:value=ipaddress.ip_address(address)
    except ValueError:return True
    return bool(value.is_private or value.is_loopback or value.is_link_local or value.is_reserved or value.is_unspecified or value.is_multicast)
def validate_http_url(value:str,*,resolve:bool=False)->str:
    parts=urlsplit(value); host=parts.hostname
    if parts.scheme not in {"http","https"} or not host or parts.username or parts.password: raise ValueError("Use a clean HTTP or HTTPS address")
    normalized=host.rstrip(".").casefold()
    if normalized in BLOCKED_HOSTNAMES: raise ValueError("Local and loopback addresses are not allowed")
    try:literal=ipaddress.ip_address(normalized)
    except ValueError:literal=None
    if literal is not None and blocked_ip(str(literal)): raise ValueError("Private, loopback, or reserved addresses are not allowed")
    if resolve:
        try:addresses={item[4][0] for item in socket.getaddrinfo(normalized,parts.port or (443 if parts.scheme=="https" else 80),type=socket.SOCK_STREAM)}
        except OSError as exc:raise ValueError("The browser could not resolve the requested host") from exc
        if not addresses or any(blocked_ip(address) for address in addresses): raise ValueError("The browser blocked a private or reserved network target")
    return value
