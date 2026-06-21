from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from runtime.events.change_watcher import ChangeWatcher
from runtime.events.sources import DataVersionSource
from runtime.node.store import NodeStore


class DataVersionSourceTest(unittest.TestCase):
    def test_read_signal_changes_after_commit_on_observer_connection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "node.sqlite3"
            store = NodeStore.from_file(db_path)
            store.db.commit()
            source = DataVersionSource()
            before = source.read_signal(db_path)
            store.db.execute(
                "INSERT INTO workspaces (workspace_id, canonical_link, name) VALUES (?, ?, ?)",
                ("ws_test", "workspace://test", "Test"),
            )
            store.db.commit()
            after = source.read_signal(db_path)
            source.close()
            store.close()
            self.assertIsNotNone(before)
            self.assertIsNotNone(after)
            self.assertNotEqual(before, after)


class ChangeWatcherTest(unittest.IsolatedAsyncioTestCase):
    async def test_watcher_emits_after_external_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "node.sqlite3"
            seed = NodeStore.from_file(db_path)
            seed.db.commit()
            seed.close()

            watcher = ChangeWatcher(poll_interval_seconds=0.05, debounce_seconds=0.05)
            queue = watcher.bus.create_subscription()
            task = asyncio.create_task(watcher.run([db_path]))
            await asyncio.sleep(0.1)

            writer = NodeStore.from_file(db_path)
            writer.db.execute(
                "INSERT INTO workspaces (workspace_id, canonical_link, name) VALUES (?, ?, ?)",
                ("ws_evt", "workspace://evt", "Evt"),
            )
            writer.db.commit()
            writer.close()

            change = await asyncio.wait_for(queue.get(), timeout=2.0)
            self.assertEqual(change.db_path.resolve(), db_path.resolve())

            watcher.stop()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

    async def test_notify_local_write_emits_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "node.sqlite3"
            seed = NodeStore.from_file(db_path)
            seed.db.commit()
            seed.close()

            watcher = ChangeWatcher()
            queue = watcher.bus.create_subscription()
            task = asyncio.create_task(watcher.run([db_path]))
            await asyncio.sleep(0.05)

            watcher.notify_local_write(db_path)
            change = await asyncio.wait_for(queue.get(), timeout=1.0)
            self.assertEqual(change.db_path.resolve(), db_path.resolve())

            watcher.stop()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
