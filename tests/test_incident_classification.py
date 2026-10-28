import asyncio
import errno
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx

from sitesentry.core.checker import CheckResult, SiteChecker
from sitesentry.core.database import Database
from sitesentry.core.email_rules import normalize_rule
from sitesentry.core.notifier import EmailNotifier
from sitesentry.core.security import SecurityManager


class ClassificationTests(unittest.TestCase):
    def run_check(self, handler, monitor=None):
        real_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        with patch("sitesentry.core.checker.httpx.AsyncClient", side_effect=lambda **kwargs: real_client(transport=transport, **kwargs)):
            return asyncio.run(SiteChecker().check_monitor({"url": "https://example.test", "retry_count": 1, **(monitor or {})}))

    def test_timeout_is_not_incorrect_password(self):
        def handler(request):
            raise httpx.ReadTimeout("read timed out", request=request)
        result = self.run_check(handler)
        self.assertEqual(result.error_type, "timeout")

    def test_auth_transport_failures_keep_network_category(self):
        def handler(request):
            raise httpx.ConnectError("connection refused", request=request)
        with patch("sitesentry.core.diagnostics.has_local_route", return_value=True):
            result = self.run_check(handler, {"monitor_type": "auth_web", "auth_login_url": "https://example.test/login"})
        self.assertEqual(result.error_type, "target_unreachable")
        self.assertIn("Login page failed", result.error)

    def test_network_down_requires_local_evidence(self):
        def handler(request):
            raise httpx.ConnectError("no route", request=request) from OSError(errno.ENETUNREACH, "Network unreachable")
        self.assertEqual(self.run_check(handler).error_type, "network_offline")

    def test_server_401_and_403_are_distinct(self):
        self.assertEqual(self.run_check(lambda req: httpx.Response(401)).error_type, "auth_credentials")
        self.assertEqual(self.run_check(lambda req: httpx.Response(403)).error_type, "http_error")

    def test_missing_text_is_an_assertion(self):
        result = self.run_check(lambda req: httpx.Response(200, text="Hello"), {"expected_text": "Dashboard"})
        self.assertEqual(result.error_type, "assertion_failed")

    def test_auth_login_rejection_is_not_retried(self):
        requests = []
        form = '<form><input name="username"><input name="password" type="password"></form>'
        def handler(request):
            requests.append(request.method)
            return httpx.Response(200, text=form + ("Invalid username or password" if request.method == "POST" else ""))
        result = self.run_check(handler, {"monitor_type": "auth_web", "auth_login_url": "https://example.test/login", "retry_count": 3})
        self.assertEqual(result.error_type, "auth_credentials")
        self.assertEqual(requests, ["GET", "POST"])

    def test_login_page_without_explicit_rejection_is_not_bad_password(self):
        form = '<form><input name="username"><input name="password" type="password"></form>'
        result = self.run_check(lambda req: httpx.Response(200, text=form), {"monitor_type": "auth_web", "auth_login_url": "https://example.test"})
        self.assertEqual(result.error_type, "auth_verification")

    def test_json_failure_has_category(self):
        result = self.run_check(lambda req: httpx.Response(200, json={"status": "bad"}), {"monitor_type": "api", "expected_json_path": "status", "expected_json_value": "ok"})
        self.assertEqual(result.error_type, "assertion_failed")


class IncidentPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db = Database(root / "db", SecurityManager(root / "key"))
        self.db.set_setting("smtp_enabled", "1")
        self.rule = self.db.list_email_rules()[0]
        self.db.save_email_rule({**self.rule, "batch_window_seconds": 15, "excluded_error_types": ["auth_credentials"]})
        self.monitors = [self.db.save_monitor({"name": f"Monitor {index}", "url": f"https://example.test/{index}", "monitor_type": kind}) for index, kind in enumerate(["simple_web", "auth_web", "api"])]

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def record(self, monitor_id, category="timeout", ok=False):
        result = CheckResult(ok, "up" if ok else "down", error_type="" if ok else category, error="test only")
        self.db.record_check_result(monitor_id, result)

    def test_exclusion_preserves_log_but_suppresses_down_and_recovery(self):
        self.record(self.monitors[0], "auth_credentials")
        self.record(self.monitors[0], ok=True)
        self.assertEqual(len(self.db.list_logs()), 2)
        self.assertEqual(self.db.list_logs()[-1]["error_type"], "auth_credentials")
        self.assertEqual(self.db.email_delivery_counts(), {})

    def test_excluded_error_becoming_eligible_while_still_down_alerts_once(self):
        self.record(self.monitors[0], "auth_credentials")
        self.record(self.monitors[0], "timeout")
        self.record(self.monitors[0], "timeout")
        self.assertEqual(self.db.email_delivery_counts(), {"pending": 1})

    def test_three_monitor_types_become_one_email_after_window(self):
        for monitor_id in self.monitors:
            self.record(monitor_id)
        self.assertEqual(self.db.pending_email_deliveries(), [])
        notifier = EmailNotifier(self.db)
        with patch.object(notifier, "_send", return_value=(True, "sent")) as send:
            notifier.process_pending(now=datetime.now() + timedelta(seconds=20))
        self.assertEqual(send.call_count, 1)
        for index in range(3):
            self.assertIn(f"Monitor {index}", send.call_args.args[1])
        self.assertEqual(self.db.email_delivery_counts(), {"sent": 3})
        with patch.object(notifier, "_send") as send:
            notifier.process_pending(now=datetime.now() + timedelta(minutes=2))
        send.assert_not_called()

    def test_batch_retry_and_recovery_order(self):
        for monitor_id in self.monitors:
            self.record(monitor_id)
        self.record(self.monitors[0], ok=True)
        notifier = EmailNotifier(self.db)
        now = datetime.now() + timedelta(seconds=20)
        with patch.object(notifier, "_send", return_value=(False, "offline")) as send:
            notifier.process_pending(now=now)
        self.assertEqual(send.call_count, 1)
        with patch.object(notifier, "_send", return_value=(True, "sent")) as send:
            notifier.process_pending(now=now + timedelta(minutes=2))
        self.assertEqual(send.call_count, 2)
        self.assertIn("DOWN", send.call_args_list[0].args[0])
        self.assertIn("UP", send.call_args_list[1].args[0])

    def test_validation_rejects_unknown_errors_and_unbounded_windows(self):
        for data in [{"excluded_error_types": ["typo"]}, {"batch_window_seconds": -1}, {"batch_window_seconds": 301}]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                normalize_rule({"name": "rule", **data})

    def test_exclusions_changed_during_grouping_apply_before_send(self):
        self.record(self.monitors[0], "timeout")
        self.record(self.monitors[1], "http_error")
        self.record(self.monitors[0], ok=True)
        self.db.save_email_rule({**self.db.get_email_rule(self.rule["id"]), "excluded_error_types": ["timeout"]})
        notifier = EmailNotifier(self.db)
        with patch.object(notifier, "_send", return_value=(True, "sent")) as send:
            notifier.process_pending(now=datetime.now() + timedelta(seconds=20))
        self.assertEqual(send.call_count, 1)
        self.assertNotIn("Monitor 0", send.call_args.args[1])
        self.assertIn("Monitor 1", send.call_args.args[1])
        self.assertEqual(self.db.email_delivery_counts(), {"sent": 1, "suppressed": 2})

    def test_batch_partial_delivery_retry_does_not_resend_accepted_addresses(self):
        self.db.set_setting("smtp_host", "smtp.example.test")
        self.db.set_setting("smtp_to", "one@example.test,two@example.test")
        self.db.set_setting("smtp_use_tls", "0")
        for monitor_id in self.monitors:
            self.record(monitor_id)
        notifier = EmailNotifier(self.db)
        with patch("sitesentry.core.notifier.smtplib.SMTP") as smtp_class:
            smtp = smtp_class.return_value.__enter__.return_value
            smtp.sendmail.side_effect = [{"two@example.test": (450, b"later")}, {}]
            notifier.process_pending(now=datetime.now() + timedelta(seconds=20))
            notifier.process_pending(now=datetime.now() + timedelta(minutes=2))
        self.assertEqual(smtp.sendmail.call_count, 2)
        self.assertEqual(smtp.sendmail.call_args_list[-1].args[1], ["two@example.test"])
        self.assertEqual(self.db.email_delivery_counts(), {"sent": 3})


if __name__ == "__main__":
    unittest.main()
