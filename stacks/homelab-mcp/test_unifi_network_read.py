import unittest
from unittest.mock import AsyncMock
import unifi_network_read as u

SITE = "00000000-0000-0000-0000-000000000001"
NET = "00000000-0000-0000-0000-000000000002"
ROW = {"id": NET, "name": "Test", "ipv4Configuration": {
    "hostIpAddress": "192.0.2.1", "prefixLength": 24,
    "dhcpConfiguration": {"mode": "SERVER", "ipAddressRange": {
        "start": "192.0.2.100", "stop": "192.0.2.200"},
        "option43Value": "secret", "dnsServerIpAddressesOverride": ["192.0.2.1"]}}}


class UniFiNetworkReadTests(unittest.IsolatedAsyncioTestCase):
    async def test_network_projection(self):
        get = AsyncMock(return_value=ROW)
        result = await u.network(get, SITE, NET)
        self.assertEqual(result["ipv4"]["subnet"], "192.0.2.0/24")
        self.assertEqual(result["ipv4"]["dhcp_range_start"], "192.0.2.100")
        self.assertNotIn("secret", str(result))
        get.assert_awaited_once_with(f"/v1/sites/{SITE}/networks/{NET}", params=None)

    async def test_observation_never_claims_address_free(self):
        get = AsyncMock(side_effect=[ROW, {"data": [], "totalCount": 0}])
        result = await u.address_observation(get, SITE, NET, "192.0.2.150")
        self.assertTrue(result["inside_dhcp_range"])
        self.assertFalse(result["safe_to_assign"])
        self.assertFalse(result["reservation_inventory_verified"])
        self.assertEqual(get.call_args.kwargs["params"]["filter"], "ipAddress.eq('192.0.2.150')")

    async def test_invalid_ids_and_bounds(self):
        get = AsyncMock()
        for site in ("../clients", "x", SITE + "/"):
            with self.assertRaises(ValueError):
                await u.networks(get, site)
        with self.assertRaises(ValueError):
            await u.networks(get, SITE, 201)
        get.assert_not_awaited()

    async def test_unknown_dhcp_range(self):
        self.assertIsNone(u._network({"id": NET})["ipv4"]["dhcp_range_start"])
        get = AsyncMock(return_value={"id": SITE})
        with self.assertRaises(RuntimeError):
            await u.network(get, SITE, NET)

    async def test_error_redaction_and_dns_txt(self):
        get = AsyncMock(side_effect=RuntimeError("secret"))
        with self.assertRaisesRegex(RuntimeError, "^UniFi read failed"):
            await u.networks(get, SITE)
        get = AsyncMock(return_value={"totalCount": 1, "data": [
            {"id": NET, "type": "TXT_RECORD", "domain": "test.invalid", "text": "secret"}]})
        self.assertNotIn("secret", str(await u.dns_policies(get, SITE)))
