import asyncio
import unittest
import errno
from unittest.mock import patch

import httpx

from sitesentry.core.checker import SiteChecker
from sitesentry.core.network_diagnostics import NetworkDiagnostics, validate_profile


class NetworkProfileTests(unittest.IsolatedAsyncioTestCase):
    def profile(self):
        return {"name": "Internal", "scope": "intranet_vpn", "enabled": True,
                "targets": [{"url": "https://reference.example.test/health", "method": "HEAD", "timeout_seconds": 2}]}

    def test_validation_rejects_sensitive_urls_and_unsafe_methods(self):
        for url in ["https://user:secret@example.test/", "https://example.test/?token=secret", "ftp://example.test/"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_profile({**self.profile(), "targets": [{"url": url, "method": "GET"}]})
        with self.assertRaises(ValueError):
            validate_profile({**self.profile(), "targets": [{"url": "https://example.test", "method": "POST"}]})
        with self.assertRaises(ValueError):
            validate_profile({**self.profile(), "targets": self.profile()["targets"] * 3})

    async def test_concurrent_probe_is_shared_cached_and_has_no_credentials(self):
        requests = []
        async def handler(request):
            requests.append(request)
            await asyncio.sleep(0.01)
            return httpx.Response(403)
        engine = NetworkDiagnostics(transport=httpx.MockTransport(handler))
        results = await asyncio.gather(*(engine.probe(self.profile()) for _ in range(5)))
        self.assertEqual(len(requests), 1)
        self.assertTrue(all(item["targets"][0]["reachable"] for item in results))
        self.assertNotIn("authorization", requests[0].headers)
        self.assertNotIn("cookie", requests[0].headers)
        self.assertEqual(requests[0].method, "HEAD")
        await engine.probe(self.profile())
        self.assertEqual(len(requests), 1)

    async def test_redirect_is_not_followed(self):
        requests = []
        async def handler(request):
            requests.append(str(request.url))
            return httpx.Response(302, headers={"Location": "https://unrelated.example.test/"})
        engine = NetworkDiagnostics(transport=httpx.MockTransport(handler))
        result = await engine.probe(self.profile())
        self.assertEqual(len(requests), 1)
        self.assertTrue(result["targets"][0]["reachable"])

    async def test_profile_edit_does_not_allow_two_probes_at_once(self):
        active = 0
        max_active = 0
        async def handler(request):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.02)
            active -= 1
            return httpx.Response(200)
        engine = NetworkDiagnostics(transport=httpx.MockTransport(handler))
        first = self.profile()
        second = {**first, "targets": [{"url": "https://different.example.test/", "method": "HEAD"}]}
        a, b = await asyncio.gather(engine.probe(first), engine.probe(second))
        self.assertEqual(max_active, 1)
        self.assertIn("reference.example.test", a["targets"][0]["url"])
        self.assertIn("different.example.test", b["targets"][0]["url"])

    async def test_no_profile_makes_no_reference_probe(self):
        requests = []
        async def handler(request):
            requests.append(str(request.url))
            raise httpx.ConnectError("refused", request=request)
        client = httpx.AsyncClient
        with patch("sitesentry.core.checker.httpx.AsyncClient", side_effect=lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs)):
            result = await SiteChecker().check_monitor({"url": "https://target.example.test/", "retry_count": 1})
        self.assertEqual(result.error_type, "target_unreachable")
        self.assertEqual(len(requests), 1)

    async def test_profile_evidence_is_attached_without_claiming_machine_is_offline(self):
        requests = []
        async def handler(request):
            requests.append(str(request.url))
            return httpx.Response(200)
        engine = NetworkDiagnostics(transport=httpx.MockTransport(handler))
        checker = SiteChecker(profile_resolver=lambda name: self.profile(), network_diagnostics=engine)
        from sitesentry.core.checker import CheckResult
        with patch.object(checker, "_check_once", return_value=CheckResult(False, "down", error="timeout", error_type="timeout")):
            result = await checker.check_monitor({"url": "https://target.example.test", "network_profile": "Internal", "retry_count": 1})
        self.assertEqual(result.error_type, "timeout")
        self.assertTrue(result.evidence["network_probe"]["targets"][0]["reachable"])
        self.assertEqual(len(requests), 1)

    async def test_internet_reference_is_checked_before_monitor_without_blocking_internal_target(self):
        order = []
        internet = {**self.profile(), "scope": "internet"}
        async def handler(request):
            order.append("reference")
            raise httpx.ConnectError("unreachable", request=request)
        engine = NetworkDiagnostics(transport=httpx.MockTransport(handler))
        checker = SiteChecker(internet_profile_resolver=lambda: internet, network_diagnostics=engine)
        from sitesentry.core.checker import CheckResult
        async def target(_monitor):
            order.append("target")
            return CheckResult(True, "up", status_code=200)
        with patch.object(checker, "_check_once", side_effect=target):
            result = await checker.check_monitor({"url": "https://intranet.example.test", "retry_count": 1})
        self.assertEqual(order, ["reference", "target"])
        self.assertTrue(result.ok)
        self.assertEqual(result.evidence["internet_check"]["state"], "reference_unreachable")

    async def test_successful_reference_and_unconfigured_are_distinct(self):
        profile = {**self.profile(), "scope": "internet"}
        engine = NetworkDiagnostics(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
        from sitesentry.core.checker import CheckResult
        checker = SiteChecker(internet_profile_resolver=lambda: profile, network_diagnostics=engine)
        with patch.object(checker, "_check_once", return_value=CheckResult(True, "up")):
            result = await checker.check_monitor({"url": "https://example.test", "retry_count": 1})
        self.assertEqual(result.evidence["internet_check"]["state"], "reachable")

    async def test_local_network_down_is_distinct_from_reference_failure(self):
        profile = {**self.profile(), "scope": "internet"}
        async def handler(request):
            try:
                raise OSError(errno.ENETDOWN, "network unavailable")
            except OSError as cause:
                raise httpx.ConnectError("network error", request=request) from cause
        engine = NetworkDiagnostics(transport=httpx.MockTransport(handler))
        from sitesentry.core.checker import CheckResult
        checker = SiteChecker(internet_profile_resolver=lambda: profile, network_diagnostics=engine)
        with patch.object(checker, "_check_once", return_value=CheckResult(True, "up")):
            result = await checker.check_monitor({"url": "https://intranet.example.test", "retry_count": 1})
        self.assertEqual(result.evidence["internet_check"]["state"], "network_offline")
        self.assertTrue(result.ok)
