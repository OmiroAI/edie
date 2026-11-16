import tempfile
import unittest
from edie.core import Store
from edie.tasks import Tasks


class QueueTest(unittest.TestCase):
    def test_idempotency_and_lease(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            queue = Tasks(store.db)
            task = queue.submit('job', 'request', {'revision': 'a'})
            self.assertEqual(task, queue.submit('job', 'request', {'revision': 'a'}))
            with self.assertRaises(ValueError):
                queue.submit('job', 'request', {'revision': 'b'})
            self.assertEqual(queue.claim('worker')['id'], task)
            self.assertIsNone(queue.claim('other'))
            with self.assertRaises(ValueError):
                queue.finish(task, 'other', {})
            queue.finish(task, 'worker', {'artifact': 'preview'})
            self.assertIsNone(queue.claim('worker'))
            store.db.close()
            reopened = Store(root)
            self.assertEqual(Tasks(reopened.db).get(task)['state'], 'completed')
            reopened.db.close()

    def test_expired_task_requires_explicit_recovery(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            queue = Tasks(store.db)
            task = queue.submit('job', 'key', {})
            queue.claim('worker')
            with store.db:
                store.db.execute('UPDATE tasks SET expires=0 WHERE id=?', (task,))
            self.assertIsNone(queue.claim('replacement'))
            with self.assertRaises(ValueError):
                queue.finish(task, 'worker', {})
            queue.control(task, 'recover')
            queue.control(task, 'pause')
            self.assertIsNone(queue.claim('replacement'))
            queue.control(task, 'resume')
            self.assertEqual(queue.claim('replacement')['id'], task)
            store.db.close()

    def test_running_control_requires_worker_acknowledgement(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            queue = Tasks(store.db)
            task = queue.submit('job', 'key', {})
            queue.claim('worker')
            self.assertEqual(queue.control(task, 'pause')['state'], 'pause_requested')
            with self.assertRaises(ValueError):
                queue.finish(task, 'worker', {})
            self.assertEqual(queue.heartbeat(task, 'worker'), 'pause_requested')
            queue.stopped(task, 'worker', 'paused')
            queue.control(task, 'resume')
            queue.claim('second')
            queue.control(task, 'cancel')
            queue.stopped(task, 'second', 'cancelled')
            with self.assertRaises(ValueError):
                queue.control(task, 'resume')
            store.db.close()

class CapabilityQueueTest(unittest.TestCase):
    def test_workers_only_claim_their_capability(self):
        import sqlite3
        db=sqlite3.connect(':memory:');tasks=Tasks(db)
        index=tasks.submit('job','index',{'action':'index','sources':[]})
        render=tasks.submit('job','render',{'action':'render','revision':'r'})
        self.assertEqual(tasks.claim('renderer',action='render')['id'],render)
        self.assertEqual(tasks.claim('indexer',action='index')['id'],index)
        db.close()
