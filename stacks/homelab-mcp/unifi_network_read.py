"""Bounded official UniFi Network API inspection. No writes or legacy endpoints."""
import ipaddress
import re
import uuid


def _uuid(value):
    if not isinstance(value, str):
        raise ValueError("Canonical UUID required.")
    try:
        parsed = str(uuid.UUID(value))
    except ValueError:
        raise ValueError("Canonical UUID required.") from None
    if parsed != value.lower():
        raise ValueError("Canonical UUID required.")
    return parsed


def _obj(value):
    return value if isinstance(value, dict) else {}


def _fields(row, fields):
    if not isinstance(row, dict):
        raise RuntimeError("Unexpected network API object.")
    return {k: v[:256] if isinstance(v, str) else v for k in fields
            if (v := row.get(k)) is None or type(v) in (str, bool, int)}


def _ip(value, version=None):
    if not isinstance(value, str):
        return None
    try:
        addr = ipaddress.ip_address(value)
        return str(addr) if version is None or addr.version == version else None
    except ValueError:
        return None


def _network(row):
    out = _fields(row, ("id", "name", "enabled", "vlanId", "management", "default", "zoneId"))
    cfg = _obj(row.get("ipv4Configuration"))
    dhcp = _obj(cfg.get("dhcpConfiguration"))
    addr = _ip(cfg.get("hostIpAddress"), 4)
    prefix = cfg.get("prefixLength")
    subnet = None
    if addr and type(prefix) is int and 0 <= prefix <= 32:
        subnet = str(ipaddress.IPv4Network(f"{addr}/{prefix}", strict=False))
    pool = _obj(dhcp.get("ipAddressRange"))
    start, stop = _ip(pool.get("start"), 4), _ip(pool.get("stop"), 4)
    valid = False
    if subnet and start and stop:
        net = ipaddress.IPv4Network(subnet)
        a, b = ipaddress.IPv4Address(start), ipaddress.IPv4Address(stop)
        valid = a in net and b in net and a <= b
    dns = dhcp.get("dnsServerIpAddressesOverride")
    out["ipv4"] = {"gateway_host": addr, "subnet": subnet,
        "dhcp_mode": _fields(dhcp, ("mode",))["mode"],
        "dhcp_range_start": start if valid else None, "dhcp_range_stop": stop if valid else None,
        "gateway_override": _ip(dhcp.get("gatewayIpAddressOverride"), 4),
        "dns_override": [_ip(x) for x in dns[:4]] if isinstance(dns, list) else None,
        "lease_seconds": _fields(dhcp, ("leaseTimeSeconds",))["leaseTimeSeconds"],
        "conflict_detection": _fields(dhcp, ("pingConflictDetectionEnabled",))["pingConflictDetectionEnabled"]}
    return out


def _policy(row):
    out = _fields(row, ("id", "name", "enabled", "index", "type"))
    out["action"] = _fields(_obj(row.get("action")), ("type",))["type"]
    for side in ("source", "destination"):
        out[side] = _fields(_obj(row.get(side)), ("zoneId",))
        out[side]["traffic_filter_type"] = _fields(
            _obj(_obj(row.get(side)).get("trafficFilter")), ("type",))["type"]
    return out


def _dns(row):
    # TXT record values may be sensitive; omit them and all unrecognized fields.
    return _fields(row, ("id", "enabled", "type", "domain", "ipv4Address",
                        "ipv6Address", "targetDomain", "ipAddress", "ttlSeconds"))


async def _get(get, path, params=None):
    try:
        return await get(path, params=params)
    except Exception:
        # Never expose controller response bodies, request metadata or key material.
        raise RuntimeError("UniFi read failed; check API version, permissions and connectivity.") from None


async def _page(get, site, resource, project, limit=100, offset=0, extra=None):
    site = _uuid(site)
    if type(limit) is not int or not 1 <= limit <= 200 or type(offset) is not int or not 0 <= offset <= 10000:
        raise ValueError("Limit 1-200 and offset 0-10000 required.")
    raw = await _get(get, f"/v1/sites/{site}/{resource}",
                     {"limit": limit, "offset": offset, **(extra or {})})
    if not isinstance(raw, dict) or not isinstance(raw.get("data"), list):
        raise RuntimeError("Unexpected UniFi page.")
    rows = raw["data"]
    total = raw.get("totalCount")
    if len(rows) > limit or type(total) is not int or total < 0:
        raise RuntimeError("Unexpected UniFi page bounds.")
    return {"items": [project(r) for r in rows], "offset": offset, "limit": limit,
            "total_count": total, "possibly_more": offset + len(rows) < total}


async def networks(get, site, limit=100, offset=0):
    return await _page(get, site, "networks",
        lambda r: _fields(r, ("id", "name", "enabled", "vlanId", "management", "default")),
        limit, offset)


async def network(get, site, network_id):
    site, network_id = _uuid(site), _uuid(network_id)
    raw = await _get(get, f"/v1/sites/{site}/networks/{network_id}")
    if not isinstance(raw, dict) or raw.get("id") != network_id:
        raise RuntimeError("Network identity not verified.")
    return {**_network(raw), "coverage": "Configured IPv4/DHCP settings; not lease or reservation inventory."}


async def dns_policies(get, site, limit=100, offset=0):
    return await _page(get, site, "dns/policies", _dns, limit, offset)


async def firewall_policies(get, site, limit=100, offset=0):
    return {**await _page(get, site, "firewall/policies", _policy, limit, offset),
            "coverage": "Policy summaries only; not full match conditions, rule evaluation or port forwarding inventory."}


async def address_observation(get, site, network_id, address):
    addr = _ip(address, 4)
    if addr is None:
        raise ValueError("IPv4 address required.")
    net = await network(get, site, network_id)
    cfg = net["ipv4"]
    inside = None if cfg["subnet"] is None else ipaddress.IPv4Address(addr) in ipaddress.IPv4Network(cfg["subnet"])
    pool = None
    if cfg["dhcp_range_start"] and cfg["dhcp_range_stop"]:
        pool = ipaddress.IPv4Address(cfg["dhcp_range_start"]) <= ipaddress.IPv4Address(addr) <= ipaddress.IPv4Address(cfg["dhcp_range_stop"])
    clients = await _page(get, site, "clients", lambda r: _fields(r, ("id", "name", "ipAddress", "macAddress")),
                          200, 0, {"filter": f"ipAddress.eq('{addr}')"})
    matches = [r for r in clients["items"] if r["ipAddress"] == addr]
    return {"address": addr, "network_id": network_id, "inside_subnet": inside,
            "inside_dhcp_range": pool, "matches": matches,
            "matches_gateway": addr in (cfg["gateway_host"], cfg["gateway_override"]),
            "possibly_more_clients": clients["possibly_more"],
            "reservation_inventory_verified": False, "safe_to_assign": False,
            "coverage": "Connected-client observation only; offline devices, DHCP reservations, leases and static hosts may be missing. Never authorizes address assignment."}


def register(mcp, get):
    @mcp.tool
    async def unifi_networks(site_id: str, limit: int = 100, offset: int = 0):
        """List configured networks and VLANs through the official read-only API."""
        return await networks(get, site_id, limit, offset)

    @mcp.tool
    async def unifi_network(site_id: str, network_id: str):
        """Inspect one network's configured IPv4 subnet, DHCP range, gateway and DNS overrides."""
        return await network(get, site_id, network_id)

    @mcp.tool
    async def unifi_dns_policies(site_id: str, limit: int = 100, offset: int = 0):
        """Read local DNS policy summaries; excludes TXT values. No DNS changes."""
        return await dns_policies(get, site_id, limit, offset)

    @mcp.tool
    async def unifi_firewall_policies(site_id: str, limit: int = 100, offset: int = 0):
        """Read bounded firewall policy summaries; not a firewall reachability test."""
        return await firewall_policies(get, site_id, limit, offset)

    @mcp.tool
    async def unifi_address_observation(site_id: str, network_id: str, address: str):
        """Compare IPv4 address with configured subnet/DHCP range and connected clients. Never proves availability or changes settings."""
        return await address_observation(get, site_id, network_id, address)
