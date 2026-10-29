from datetime import datetime, timedelta
import os
from pathlib import Path
import tempfile
import time
import threading
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.environ.get("SITESENTRY_GUI_TEST") == "1", "Native display required")
class NativeUISmokeTests(unittest.TestCase):
    def test_views_dialogs_and_date_selection(self) -> None:
        from PIL import ImageGrab
        from sitesentry.ui.main_window import SiteSentryApp
        from sitesentry.ui.monitor_dialog import MonitorDialog
        from sitesentry.core.checker import CheckResult

        with tempfile.TemporaryDirectory() as directory:
            config = {"database_path": f"{directory}/app.db", "fernet_key_path": f"{directory}/key", "appearance": "Light"}
            with patch("sitesentry.ui.main_window.load_config", return_value=config), patch.object(SiteSentryApp, "_should_enable_tray", return_value=False), patch("sitesentry.ui.main_window.MonitorScheduler.start"):
                app = SiteSentryApp()
            errors = []
            app.report_callback_exception = lambda *args: errors.append(args)
            monitor_id = app.db.save_monitor({"name": "Portal QA", "url": "https://example.test", "monitor_type": "auth_web", "language": "PHP", "web_server": "Apache", "auth_login_url": "https://example.test/login", "auth_username": "demo", "auth_password": "test-only"})
            app.db.record_check_result(monitor_id, CheckResult(False, "down"))
            app.db.record_check_result(monitor_id, CheckResult(True, "up"))
            app.db.save_email_rule({"name": "Daily dashboard", "rule_type": "daily_summary", "weekdays": "mon,tue,wed,thu,fri,sat,sun"})

            def pump(until=lambda: True) -> None:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    app.update()
                    if errors:
                        self.fail(f"UI callback error: {errors[-1][1]}")
                    if until():
                        for _ in range(8):
                            app.update()
                            time.sleep(0.02)
                        return
                    time.sleep(0.02)
                self.fail("UI callback timed out")

            def screenshot(widget, name: str) -> None:
                folder = os.environ.get("SITESENTRY_QA_DIR")
                if folder:
                    Path(folder).mkdir(parents=True, exist_ok=True)
                    widget.lift()
                    widget.focus_force()
                    deadline = time.monotonic() + 0.4
                    while time.monotonic() < deadline:
                        app.update()
                        time.sleep(0.02)
                    pump()
                    x, y = widget.winfo_rootx(), widget.winfo_rooty()
                    ImageGrab.grab(bbox=(x, y, x + widget.winfo_width(), y + widget.winfo_height())).save(Path(folder) / f"{name}.png")

            try:
                app.geometry("980x640+40+60")
                app.show_view("Logs")
                logs = app._current_view
                pump(lambda: not logs._busy)
                self.assertEqual(len(logs.table.get_children()), 2)
                screenshot(app, "logs")
                logs.start_picker.set(datetime(2026, 1, 31, 12, 30, 15))
                logs.start_picker._open()
                popup = logs.start_picker._popup
                pump()
                popup._shift(1)
                popup._apply()
                self.assertEqual(logs.start_picker.get(), datetime(2026, 2, 28, 12, 30, 15))
                logs.start_picker._open()
                pump()
                screenshot(logs.start_picker._popup, "datetime")
                logs.start_picker._popup._clear()
                self.assertIsNone(logs.start_picker.get())
                app.show_view("Statistics")
                reports = app._current_view
                pump(lambda: not reports._busy)
                self.assertEqual(len(reports.table.get_children()), 1)
                screenshot(app, "statistics")
                app.show_view("Settings")
                settings = app._current_view
                pump()
                screenshot(app, "settings-smtp")
                settings.tabs.set("Email schedules")
                pump()
                screenshot(app, "settings-schedules")
                settings._edit_rule(app.db.list_email_rules()[-1])
                dialog = settings._dialog
                pump()
                screenshot(dialog, "email-schedule")
                self.assertTrue(dialog.schedule.winfo_ismapped())
                dialog.name.set("Updated digest")
                dialog._save()
                self.assertEqual(app.db.list_email_rules()[-1]["name"], "Updated digest")
                settings._edit_rule(app.db.list_email_rules()[0])
                pump()
                self.assertFalse(settings._dialog.schedule.winfo_ismapped())
                settings._dialog.destroy()
                monitor = MonitorDialog(app, app.db.get_monitor(monitor_id))
                pump()
                screenshot(monitor, "auth-monitor")
                self.assertEqual(monitor.language_var.get(), "PHP")
                self.assertEqual(monitor.web_server_var.get(), "Apache")
                monitor._open_diagnostics()
                diagnostics = monitor._diagnostic_dialog
                pump()
                diagnostics._manage_profiles()
                profiles = diagnostics._profiles_dialog
                profiles._edit_profile(None)
                profile = profiles._profile_dialog
                profile.name_var.set("VPN QA")
                profile.scope_var.set("intranet_vpn")
                profile.target_vars[0][0].set("https://reference.example.test/health")
                profile._save()
                self.assertEqual(app.db.get_network_profile("VPN QA")["scope"], "intranet_vpn")
                profiles.destroy()
                diagnostics.profile_var.set("VPN QA")
                diagnostics._edit_rule(None)
                diagnostics._rule_dialog._save()
                self.assertEqual(len(diagnostics.rules), 1)
                diagnostics._save()
                self.assertEqual(monitor._payload()["network_profile"], "VPN QA")
                self.assertIn("api-failure", monitor._payload()["diagnostic_rules_json"])
                from unittest.mock import AsyncMock
                with patch.object(app.checker, "check_monitor", new=AsyncMock(return_value=CheckResult(False, "down", error="Read timed out", error_type="timeout"))):
                    monitor._test_run()
                    pump(lambda: monitor.test_button.cget("state") == "normal")
                    self.assertIn("Website not responding", monitor.result_label.cget("text"))
                callback_ran = threading.Event()
                worker_finished = threading.Event()
                async def slow_check(_data):
                    import asyncio
                    await asyncio.sleep(3)
                    worker_finished.set()
                    return CheckResult(True, "up")
                with patch.object(app.checker, "check_monitor", new=AsyncMock(side_effect=slow_check)):
                    monitor._test_run()
                    app.after(200, callback_ran.set)
                    pump(callback_ran.is_set)
                    self.assertFalse(worker_finished.is_set())
                    monitor.destroy()
                    pump(worker_finished.is_set)
                app.show_view("Dashboard")
                dashboard = app._current_view
                pump(lambda: not dashboard._busy)
                self.assertEqual(len(dashboard.table.get_children()), 1)
                dashboard.table.selection_set(str(monitor_id))
                dashboard.refresh()
                pump(lambda: not dashboard._busy)
                self.assertEqual(dashboard.table.selection(), (str(monitor_id),))
                dashboard.search.set("missing monitor")
                self.assertEqual(len(dashboard.table.get_children()), 0)
                dashboard.search.set("Portal QA")
                self.assertEqual(len(dashboard.table.get_children()), 1)
                for name in ["QA website", "QA API"]:
                    kind = "api" if "API" in name else "simple_web"
                    new_id = app.db.save_monitor({"name": name, "url": "https://example.test", "monitor_type": kind})
                    editor = MonitorDialog(app, app.db.get_monitor(new_id))
                    pump()
                    self.assertEqual(editor._payload()["monitor_type"], kind)
                    editor._open_diagnostics()
                    pump()
                    editor._diagnostic_dialog.destroy()
                    editor.destroy()
                dashboard.refresh()
                pump(lambda: not dashboard._busy)
                dashboard.search.set("")
                dashboard.monitor_type.set("API")
                dashboard._render()
                self.assertEqual(len(dashboard.table.get_children()), 1)
                dashboard.monitor_type.set("All types")
                dashboard._render()
                self.assertEqual(len(dashboard.table.get_children()), 3)
                before_widgets = len(dashboard.winfo_children())
                for index in range(500):
                    app.db.save_monitor({"name": f"Bulk monitor {index:03d}", "url": "https://example.test"})
                dashboard.refresh()
                pump(lambda: not dashboard._busy)
                self.assertEqual(len(dashboard.table.get_children()), 503)
                self.assertEqual(len(dashboard.winfo_children()), before_widgets)
                app.show_view("Settings")
                settings = app._current_view
                settings._edit_rule(app.db.list_email_rules()[0])
                pump()
                dialog = settings._dialog
                dialog.geometry("640x570+60+80")
                dialog.excluded["auth_credentials"].set(True)
                dialog.batch_window.set("30")
                dialog._save()
                rule = app.db.list_email_rules()[0]
                self.assertEqual(rule["batch_window_seconds"], 30)
                self.assertIn("auth_credentials", rule["excluded_error_types_json"])
                app.db.set_setting("smtp_enabled", "1")
                app.db.record_check_result(monitor_id, CheckResult(False, "down", status_code=503))
                pending = app.db.pending_email_deliveries(now=datetime.now() + timedelta(seconds=31))
                self.assertTrue(pending)
                delivery_id = pending[0]["delivery_id"]
                app.db.mark_delivery_attempt(delivery_id)
                app.db.finish_email_delivery(delivery_id, False, "delivery_uncertain: synthetic")
                settings._show_queue()
                queue_dialog = settings._queue_dialog
                queue_dialog.table.selection_set(str(delivery_id))
                with patch("sitesentry.ui.settings_view.messagebox.askyesno", return_value=True):
                    queue_dialog._retry()
                self.assertEqual(app.db.email_delivery_counts().get("pending"), 1)
                queue_dialog.destroy()
                app.db.set_setting("smtp_enabled", "0")
                app.geometry("1160x760+40+60")
                settings.theme_var.set("Dark")
                self.assertTrue(settings._save())
                app.show_view("Statistics")
                pump(lambda: not app._current_view._busy)
                screenshot(app, "statistics-dark")
                self.assertFalse(errors, errors)
            finally:
                app._closing = True
                app.scheduler.stop()
                app.update_idletasks()
                app.destroy()
                app.db.close()
