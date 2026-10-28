import gc
import threading
import unittest
import weakref
from unittest.mock import Mock

from sitesentry.ui.lifecycle import TkGarbageCollector


class TkLifecycleTests(unittest.TestCase):
    def test_worker_allocations_cannot_finalize_tk_cycles(self):
        root = Mock()
        collector = TkGarbageCollector(root)
        finalized_on = []

        class Resource:
            def __del__(self):
                finalized_on.append(threading.get_ident())

        try:
            resource = Resource()
            resource.cycle = resource
            reference = weakref.ref(resource)
            del resource
            worker = threading.Thread(target=lambda: [[] for _ in range(10000)])
            worker.start()
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
            self.assertIsNotNone(reference())
            self.assertEqual(finalized_on, [])
            root.after.call_args.args[1]()
            self.assertIsNone(reference())
            self.assertEqual(finalized_on, [threading.get_ident()])
        finally:
            collector.close()

    def test_close_restores_collection_and_cancels_timer_once(self):
        before = gc.isenabled()
        root = Mock()
        collector = TkGarbageCollector(root)
        self.assertFalse(gc.isenabled())
        collector.close()
        collector.close()
        self.assertEqual(gc.isenabled(), before)
        root.after_cancel.assert_called_once_with(root.after.return_value)

    def test_preserves_an_already_disabled_collector(self):
        before = gc.isenabled()
        gc.disable()
        try:
            collector = TkGarbageCollector(Mock())
            collector.close()
            self.assertFalse(gc.isenabled())
        finally:
            if before:
                gc.enable()
