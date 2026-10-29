import asyncio
import errno
import json
import unittest
from unittest.mock import patch

import httpx

from sitesentry.core.checker import SiteChecker
from sitesentry.core.diagnostic_rules import validate_rules
from sitesentry.core.diagnostics import exception_category


def rule(value, *, identifier="failure", category="assertion_failed", priority=10, phase="response"):
    return {"id": identifier, "enabled": True, "priority": priority, "phase": phase,
            "conditions": [{"source": "json", "path": "success", "operator": "equals", "value": value}],
            "result": {"error_type": category, "reason_code": "business_rule_match"}}


class RuleTests(unittest.TestCase):
    def check(self, response, rules, **extra):
        client = httpx.AsyncClient
        transport = httpx.MockTransport(lambda request: response)
        with patch("sitesentry.core.checker.httpx.AsyncClient", side_effect=lambda **kwargs: client(transport=transport, **kwargs)):
            return asyncio.run(SiteChecker().check_monitor({"url": "https://example.test/", "monitor_type": "api", "retry_count": 1, "diagnostic_rules_json": json.dumps(rules), **extra}))

    def test_json_values_are_typed_including_false_zero_null_and_empty(self):
        for value in [False, 0, None, ""]:
            with self.subTest(value=value):
                result = self.check(httpx.Response(200, json={"success": value}), [rule(value)])
                self.assertFalse(result.ok)
                self.assertEqual(result.error_type, "assertion_failed")
                self.assertEqual(result.reason_code, "business_rule_match")
                self.assertEqual(result.classification_state, "confirmed")
                self.assertEqual(result.evidence["rule_id"], "failure")
        self.assertTrue(self.check(httpx.Response(200, json={"success": 0}), [rule(False)]).ok)

    def test_conflicting_rules_at_same_priority_remain_unknown(self):
        rules = [rule(False, identifier="a"), rule(False, identifier="b", category="auth_verification")]
        result = self.check(httpx.Response(200, json={"success": False}), rules)
        self.assertFalse(result.ok)
        self.assertEqual((result.error_type, result.classification_state, result.reason_code), ("unknown", "undetermined", "conflicting_evidence"))
        self.assertEqual(result.evidence["rule_ids"], ["a", "b"])

    def test_higher_priority_wins_and_http_503_cannot_become_bad_password(self):
        rules = [rule(False, identifier="a", priority=1), rule(False, identifier="b", category="auth_credentials", priority=2)]
        result = self.check(httpx.Response(200, json={"success": False}), rules)
        self.assertEqual(result.error_type, "auth_credentials")
        result = self.check(httpx.Response(503, json={"success": False}), rules)
        self.assertEqual(result.error_type, "http_error")
        self.assertEqual(result.reason_code, "http_503")

    def test_invalid_duplicate_or_unbounded_rules_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_rules([rule(False), rule(True)])
        with self.assertRaises(ValueError):
            validate_rules([rule(False)] * 21)
        with self.assertRaises(ValueError):
            validate_rules([rule(False, category="network_offline")])
        result = self.check(httpx.Response(200), [{"id": "broken"}])
        self.assertEqual(result.error_type, "configuration_error")

    def test_generic_route_failure_is_not_offline_for_entire_machine(self):
        try:
            raise httpx.ConnectError("route unavailable") from OSError(errno.ENETUNREACH, "Network unreachable")
        except httpx.ConnectError as exc:
            with patch("sitesentry.core.diagnostics.has_local_route", return_value=True):
                self.assertEqual(exception_category(exc), "target_unreachable")

    def test_hidden_text_does_not_match_visible_rule(self):
        text_rule = {"id": "captcha", "enabled": True, "priority": 1, "phase": "response",
                     "conditions": [{"source": "visible_text", "operator": "contains", "value": "captcha"}],
                     "result": {"error_type": "auth_verification", "reason_code": "captcha_required"}}
        self.assertTrue(self.check(httpx.Response(200, text='<p hidden>captcha</p>OK'), [text_rule]).ok)
        self.assertEqual(self.check(httpx.Response(200, text='<p>Captcha required</p>'), [text_rule]).reason_code, "captcha_required")

    def test_auth_login_submit_rule_and_http_401_require_specific_evidence(self):
        login_rule = {"id": "password", "enabled": True, "priority": 1, "phase": "login_submit",
                      "conditions": [{"source": "http_status", "operator": "equals", "value": 401}, {"source": "visible_text", "operator": "contains", "value": "password incorrect"}],
                      "result": {"error_type": "auth_credentials", "reason_code": "password_rejected"}}
        form = '<form><input name="username"><input name="password" type="password"></form>'
        client = httpx.AsyncClient
        transport = httpx.MockTransport(lambda request: httpx.Response(200, text=form) if request.method == "GET" else httpx.Response(401, text="Password incorrect"))
        with patch("sitesentry.core.checker.httpx.AsyncClient", side_effect=lambda **kwargs: client(transport=transport, **kwargs)):
            result = asyncio.run(SiteChecker().check_monitor({"url": "https://example.test/protected", "auth_login_url": "https://example.test/login", "monitor_type": "auth_web", "retry_count": 3, "diagnostic_rules_json": json.dumps([login_rule])}))
        self.assertEqual((result.error_type, result.reason_code, result.phase, result.attempts), ("auth_credentials", "password_rejected", "login_submit", 1))

    def test_assertion_phase_rule_and_invalid_retry_are_classified(self):
        result = self.check(httpx.Response(200, json={"success": False}), [rule(False, phase="assertion")])
        self.assertEqual((result.error_type, result.phase), ("assertion_failed", "assertion"))
        result = self.check(httpx.Response(200), [], retry_count="not-a-number")
        self.assertEqual((result.error_type, result.classification_state), ("configuration_error", "confirmed"))
