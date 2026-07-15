"""swarm-anchor: file-based shared state for multi-agent swarms.

Multiple agents writing and reading the same ground truth without
going through a central orchestrator. Each agent has a heartbeat file.
The swarm has a roster file. Conflicts are resolved last-writer-wins
(LWW) with a freshness check.

This complements shepherds-console (which reads state but doesn't write it),
breed-registry (which selects models), and baton-protocol (which handles
session handoff). swarm-anchor fills the runtime slot: who's alive, what
model each is using, what they're working on.

Usage:
    from swarm_anchor import Anchor, Roster, Heartbeat

    # Each agent writes a heartbeat
    hb = Heartbeat(animal="scout", model="deepseek-ai/DeepSeek-V4-Flash",
                   task="survey new repos")
    a = Anchor("/tmp/swarm")
    a.heartbeat(hb)

    # The lead reads the roster
    roster = a.roster()
    for animal, hb in roster.active():
        print(hb.animal, hb.task)
"""

from swarm_anchor.core import (
    Anchor,
    Heartbeat,
    Roster,
    SWARM_FILE,
    HeartbeatStatus,
)

__version__ = "0.1.0"
__all__ = ["Anchor", "Heartbeat", "Roster", "SWARM_FILE", "HeartbeatStatus"]
