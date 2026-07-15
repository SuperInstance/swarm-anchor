"""swarm-anchor core — file-based shared state for working animal swarms.

The simplest possible distributed state: a directory of files, one per
animal, plus a roster file. Each animal writes its own heartbeat. The
roster is rebuilt by listing the directory. Status decays by staleness.

No coordinator, no consensus, no consensus mechanism, no leader.
The shepherd (human) is the only authority. Animals make proposals,
shepherd decides. Animals that act without shepherd approval are
constrained to reversible actions.

This complements shepherds-console (Kennel view shows the roster).
swarm-anchor WRITES the state that shepherds-console reads.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Optional


SWARM_FILE = "SWARM.yaml"     # legacy / single-file mode
HB_SUFFIX = ".heartbeat.json" # per-animal heartbeat file


class HeartbeatStatus(str, Enum):
    """Lifecycle of an animal."""

    STARTING = "starting"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DRAINING = "draining"
    DEAD = "dead"


@dataclass
class Heartbeat:
    """One animal's view of itself, written by the animal itself."""

    animal: str                       # sheep, scout, fencer, herder, breeder
    model: str                        # e.g. "deepseek-ai/DeepSeek-V4-Flash"
    task: str                         # human-readable summary
    status: HeartbeatStatus = HeartbeatStatus.STARTING
    started_at: str = ""              # ISO-8601, set automatically
    last_seen: str = ""               # ISO-8601, refreshed on each heartbeat()
    pid: int = 0                      # process id (sanity check)
    proposals: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    extras: Dict[str, str] = field(default_factory=dict)

    def touch(self) -> None:
        """Update last_seen and return."""
        now = _dt.datetime.now(_dt.timezone.utc).isoformat()
        self.last_seen = now
        if not self.started_at:
            self.started_at = now

    def add_proposal(self, what: str) -> None:
        if what not in self.proposals:
            self.proposals.append(what)

    def add_warning(self, w: str) -> None:
        if w not in self.warnings:
            self.warnings.append(w)


@dataclass
class Roster:
    """A snapshot of all animals in the swarm at one moment."""

    animals: Dict[str, Heartbeat] = field(default_factory=dict)
    at: str = ""

    def active(self, stale_seconds: int = 30) -> List[Heartbeat]:
        """Animals whose heartbeat is fresher than stale_seconds."""
        cutoff = time.time() - stale_seconds
        out = []
        for hb in self.animals.values():
            if not hb.last_seen:
                continue
            try:
                dt = _dt.datetime.fromisoformat(hb.last_seen)
            except ValueError:
                continue
            if dt.timestamp() >= cutoff:
                out.append(hb)
        return out

    def by_status(self, status: HeartbeatStatus) -> List[Heartbeat]:
        return [hb for hb in self.animals.values() if hb.status == status]

    def count(self) -> int:
        return len(self.animals)


# ---------------------------------------------------------------------------
# Anchor — directory-backed shared state
# ---------------------------------------------------------------------------


class Anchor:
    """The shared-state directory.

    Each animal writes its own heartbeat file into the directory.
    Roster() reads all files and reports who is alive.
    """

    def __init__(self, root: str = ".swarm") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ----- Heartbeats --------------------------------------------------

    def heartbeat(self, hb: Heartbeat) -> Path:
        """Write an animal's heartbeat to disk."""
        hb.touch()
        if not hb.pid:
            hb.pid = os.getpid()
        path = self.root / f"{hb.animal}{HB_SUFFIX}"
        path.write_text(
            json.dumps(_to_json(hb), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def reap(self, animal: str) -> bool:
        """Remove a heartbeat (the animal is gone)."""
        path = self.root / f"{animal}{HB_SUFFIX}"
        if path.exists():
            path.unlink()
            return True
        return False

    # ----- Roster ------------------------------------------------------

    def roster(self, stale_seconds: int = 30) -> Roster:
        """Read all heartbeats and assemble a roster."""
        ros = Roster(at=_dt.datetime.now(_dt.timezone.utc).isoformat())
        for path in self.root.glob(f"*{HB_SUFFIX}"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                hb = _from_json(data)
                ros.animals[hb.animal] = hb
            except (json.JSONDecodeError, KeyError, ValueError):
                # Corrupt heartbeat — treat as warning
                ros.animals.setdefault("__corrupt__", Heartbeat(
                    animal="__corrupt__",
                    model="",
                    task=f"corrupt heartbeat: {path.name}",
                    warnings=[f"failed to parse {path.name}"],
                ))
        return ros

    def kill_stale(self, stale_seconds: int = 120) -> List[str]:
        """Reap animals whose heartbeat hasn't been seen in stale_seconds."""
        ros = self.roster(stale_seconds=stale_seconds)
        removed = []
        for hb in ros.animals.values():
            if hb.animal == "__corrupt__":
                continue
            if hb not in ros.active(stale_seconds=stale_seconds):
                self.reap(hb.animal)
                removed.append(hb.animal)
        return removed

    # ----- Single-file mode (legacy / simple) --------------------------

    def write_swarm_yaml(self, ros: Roster, path: Optional[str] = None) -> Path:
        """Write the roster to a single SWARM.yaml file (readable by humans)."""
        path = Path(path or self.root / SWARM_FILE)
        payload = {
            "swarm": {
                "at": ros.at,
                "count": ros.count(),
                "animals": {name: asdict(hb) for name, hb in ros.animals.items()},
            }
        }
        text = json.dumps(payload, indent=2, ensure_ascii=False)
        path.write_text(text, encoding="utf-8")
        return path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_json(hb: Heartbeat) -> Dict:
    d = asdict(hb)
    d["status"] = hb.status.value
    return d


def _from_json(d: Dict) -> Heartbeat:
    status_str = d.get("status", "starting")
    try:
        status = HeartbeatStatus(status_str)
    except ValueError:
        status = HeartbeatStatus.STARTING
    return Heartbeat(
        animal=d.get("animal", "anonymous"),
        model=d.get("model", ""),
        task=d.get("task", ""),
        status=status,
        started_at=d.get("started_at", ""),
        last_seen=d.get("last_seen", ""),
        pid=int(d.get("pid", 0) or 0),
        proposals=list(d.get("proposals", [])),
        warnings=list(d.get("warnings", [])),
        extras=dict(d.get("extras", {})),
    )


def make_animal(name: str, model: str, task: str) -> Heartbeat:
    """Convenience constructor with auto-stamping."""
    hb = Heartbeat(animal=name, model=model, task=task)
    hb.touch()
    return hb
