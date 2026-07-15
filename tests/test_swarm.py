"""Tests for swarm-anchor.

Round-trips, freshness, reaping, CLI. Stdlib only.
"""

import datetime as _dt
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from swarm_anchor.core import (
    Anchor,
    Heartbeat,
    HeartbeatStatus,
    make_animal,
    HB_SUFFIX,
)


class TestHeartbeat(unittest.TestCase):
    def test_make_animal_stamps(self):
        hb = make_animal("scout", "model-x", "task-y")
        self.assertEqual(hb.animal, "scout")
        self.assertEqual(hb.model, "model-x")
        self.assertEqual(hb.task, "task-y")
        self.assertNotEqual(hb.started_at, "")
        self.assertNotEqual(hb.last_seen, "")

    def test_touch_updates_last_seen(self):
        hb = make_animal("scout", "m", "t")
        first = hb.last_seen
        time.sleep(0.01)
        hb.touch()
        self.assertGreaterEqual(hb.last_seen, first)

    def test_add_proposal_no_dupes(self):
        hb = make_animal("scout", "m", "t")
        hb.add_proposal("do X")
        hb.add_proposal("do X")
        self.assertEqual(hb.proposals, ["do X"])


class TestAnchor(unittest.TestCase):
    def test_heartbeat_writes_file(self):
        with tempfile.TemporaryDirectory() as d:
            a = Anchor(d)
            hb = make_animal("scout", "m1", "t1")
            hb.pid = 1234
            path = a.heartbeat(hb)
            self.assertTrue(path.exists())
            data = json.loads(path.read_text())
            self.assertEqual(data["animal"], "scout")
            self.assertEqual(data["pid"], 1234)

    def test_reap_removes(self):
        with tempfile.TemporaryDirectory() as d:
            a = Anchor(d)
            a.heartbeat(make_animal("scout", "m", "t"))
            self.assertTrue(a.reap("scout"))
            self.assertFalse(a.reap("scout"))  # already gone

    def test_roster_lists_all(self):
        with tempfile.TemporaryDirectory() as d:
            a = Anchor(d)
            a.heartbeat(make_animal("scout", "m1", "t1"))
            a.heartbeat(make_animal("fencer", "m2", "t2"))
            ros = a.roster()
            self.assertEqual(ros.count(), 2)
            self.assertIn("scout", ros.animals)
            self.assertIn("fencer", ros.animals)

    def test_active_filters_fresh(self):
        with tempfile.TemporaryDirectory() as d:
            a = Anchor(d)
            a.heartbeat(make_animal("fresh", "m", "t"))
            # Manually write a stale heartbeat
            from swarm_anchor.core import _to_json
            stale = make_animal("old", "m", "t")
            stale.last_seen = (
                _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(seconds=120)
            ).isoformat()
            import json as _json
            (Path(d) / f"old{HB_SUFFIX}").write_text(_json.dumps(_to_json(stale)))
            ros = a.roster(stale_seconds=30)
            self.assertEqual(len(ros.active(stale_seconds=30)), 1)
            self.assertEqual(ros.active(stale_seconds=30)[0].animal, "fresh")

    def test_kill_stale_removes(self):
        with tempfile.TemporaryDirectory() as d:
            a = Anchor(d)
            from swarm_anchor.core import _to_json
            import json as _json
            stale = make_animal("old", "m", "t")
            stale.last_seen = (
                _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(seconds=999)
            ).isoformat()
            (Path(d) / f"old{HB_SUFFIX}").write_text(_json.dumps(_to_json(stale)))

            a.heartbeat(make_animal("fresh", "m", "t"))
            removed = a.kill_stale(stale_seconds=60)
            self.assertIn("old", removed)

    def test_corrupt_heartbeat_handled(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "broken.heartbeat.json").write_text("{ not json")
            a = Anchor(d)
            ros = a.roster()
            # corrupted heartbeats don't crash the roster
            self.assertGreaterEqual(ros.count(), 1)


class TestCLI(unittest.TestCase):
    def test_start_then_roster(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.check_call(
                [
                    sys.executable, "-m", "swarm_anchor.cli",
                    "--root", d,
                    "start",
                    "--animal", "scout",
                    "--model", "deepseek",
                    "--task", "survey",
                ],
            )
            out = subprocess.check_output(
                [
                    sys.executable, "-m", "swarm_anchor.cli",
                    "--root", d, "roster",
                ],
            )
            data = json.loads(out)
            self.assertEqual(data["count"], 1)
            self.assertEqual(data["animals"][0]["animal"], "scout")

    def test_heartbeat_with_proposal(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.check_call(
                [
                    sys.executable, "-m", "swarm_anchor.cli",
                    "--root", d, "start",
                    "--animal", "scout",
                    "--model", "m",
                    "--task", "t",
                ],
            )
            subprocess.check_call(
                [
                    sys.executable, "-m", "swarm_anchor.cli",
                    "--root", d, "heartbeat",
                    "--animal", "scout",
                    "--add-proposal", "try X",
                    "--add-warning", "watch Y",
                ],
            )
            out = subprocess.check_output(
                [
                    sys.executable, "-m", "swarm_anchor.cli",
                    "--root", d, "roster",
                ],
            )
            data = json.loads(out)
            scout = next(a for a in data["animals"] if a["animal"] == "scout")
            self.assertEqual(scout["proposals"], ["try X"])
            self.assertEqual(scout["warnings"], ["watch Y"])

    def test_leave_removes(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.check_call(
                [
                    sys.executable, "-m", "swarm_anchor.cli",
                    "--root", d, "start",
                    "--animal", "scout", "--model", "m", "--task", "t",
                ],
            )
            subprocess.check_call(
                [
                    sys.executable, "-m", "swarm_anchor.cli",
                    "--root", d, "leave", "--animal", "scout",
                ],
            )
            out = subprocess.check_output(
                [
                    sys.executable, "-m", "swarm_anchor.cli",
                    "--root", d, "roster",
                ],
            )
            data = json.loads(out)
            self.assertEqual(data["count"], 0)


if __name__ == "__main__":
    unittest.main()
