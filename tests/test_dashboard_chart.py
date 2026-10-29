import unittest

from sitesentry.ui.dashboard_view import summarize_monitor_states


class DashboardChartTests(unittest.TestCase):
    def test_paused_monitors_are_counted_once_and_not_as_current_up(self):
        monitors = [{"enabled": 1, "last_status": "up"}, {"enabled": 1, "last_status": "down"},
                    {"enabled": 0, "last_status": "up"}, {"enabled": 1, "last_status": "unknown"}]
        self.assertEqual(summarize_monitor_states(monitors), {"up": 1, "down": 1, "unknown": 1, "paused": 1})

    def test_empty_dashboard_has_zero_counts(self):
        self.assertEqual(sum(summarize_monitor_states([]).values()), 0)
