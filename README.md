# swarm-anchor

> **File-based shared state for multi-agent swarms.** No coordinator. No consensus. Just a directory where working animals write their heartbeats and a roster that anyone can read.

---

## The problem

When several agents run in parallel, who knows who else is alive, what model each is using, and what they're working on? The natural answer is a central orchestrator — but central orchestrators become the single point of failure and the bottleneck.

**swarm-anchor** inverts the model. Each agent writes its own heartbeat to a shared directory. The roster is whatever heartbeat files exist. No registry, no master process, no leader.

This complements:

- **shepherds-console** — reads state, doesn't write it. swarm-anchor WRITES the state the Kennel view renders.
- **breed-registry** — picks the model, swarm-anchor reports which model each animal is using.
- **baton-protocol** — handles session handoff. swarm-anchor handles simultaneous multi-agent runtime.

## The model

```
/path/to/swarm-root/
├── scout.heartbeat.json
├── fencer.heartbeat.json
├── herder.heartbeat.json
└── SWARM.yaml         # (optional) exported roster view
```

Each file is one line:

```json
{
  "animal": "scout",
  "model": "deepseek-ai/DeepSeek-V4-Flash",
  "task": "survey new repos",
  "status": "healthy",
  "started_at": "2026-07-15T16:00:00Z",
  "last_seen": "2026-07-15T16:05:00Z",
  "pid": 12345,
  "proposals": ["found 12 new repos"],
  "warnings": ["rate limit approaching"]
}
```

That's it. No schemas, no migrations. Read the directory, see who's alive.

## Usage

### Python

```python
from swarm_anchor import Anchor, Heartbeat, make_animal

a = Anchor(root="/tmp/my-swarm")

# Each agent writes its own heartbeat
hb = make_animal(
    name="scout",
    model="deepseek-ai/DeepSeek-V4-Flash",
    task="survey new repos",
)
hb.add_proposal("found 12 new repos to tag")
a.heartbeat(hb)

# Later, the lead or another animal reads the roster
ros = a.roster()
print(f"{ros.count()} animals in swarm")
for animal in ros.active(stale_seconds=30):
    print(animal.animal, animal.status, animal.task)
```

### CLI

```bash
# Start an animal
swarm-anchor start --animal scout --model deepseek --task "survey new repos"

# Refresh the heartbeat from inside a long-running task
swarm-anchor heartbeat --animal scout \
    --add-proposal "tagged 12 repos" \
    --add-warning "approaching rate limit"

# Run a long ping in tmux (refreshes every 10 seconds)
swarm-anchor ping --animal fencer --model kimi --task "audit compliance" --interval 10

# Show the roster
swarm-anchor roster

# Reap stale heartbeats (animals that fell silent 2 min ago)
swarm-anchor reap --stale-seconds 120

# Leave the swarm gracefully
swarm-anchor leave --animal scout
```

## Design decisions

### Why not a database?

Files are easy to inspect (`cat` the directory), easy to back up (`tar -czf swarm.tar.gz /tmp/swarm/`), and easy to delete (`rm -rf .swarm/`). They survive crashes. The format is JSON. They work over NFS. A database gives you transactional guarantees we don't need.

### Why not a central coordinator?

A central coordinator is the shepherd, and the shepherd is the human (Casey). Animals don't need a coordinator — they need to be able to find each other's state.

### Why no consensus?

Multiple animals might write heartbeats simultaneously. The filesystem serializes writes at the inode level (last-writer-wins per file). That's "consensus enough" for heartbeat data — if you read a heartbeat, it represents the most recent write. No need for Raft or Paxos for a freshness signal.

### Why no schema validation?

JSON schemas add ceremony. The schema is 6 fields + 2 collections. If a field is missing, it defaults to a sensible empty value. Corrupt heartbeats are quarantined, not fatal.

## Use case: she's watching 4 agents in tmux

```bash
# Session 1 — Scout
swarm-anchor ping --animal scout --model deepseek --task "survey repos" --interval 10

# Session 2 — Fencer
swarm-anchor ping --animal fencer --model kimi --task "audit compliance" --interval 15

# Session 3 — Herder
swarm-anchor ping --animal herder --model seed-pro --task "write reading guides" --interval 30

# Session 4 — Lead (checks the roster)
watch -n 30 swarm-anchor roster
```

Four windows, one shared ground truth, no central coordination.

## Use case: integration with shepherds-console

shepherds-console reads its roster from a configured directory. Point it at your swarm-anchor root and the Kennel view lights up with the actual animals running, not a mock configuration.

```python
# shepherds-console integration (when wired)
from shepherds_console import Console
from swarm_anchor import Anchor

a = Anchor(root="/var/run/superinstance-swarm")
ros = a.roster()
kennel = {"animals": [{hb.animal: hb.__dict__} for hb in ros.animals.values()]}
Console().render(kennel=kennel)
```

## Testing

```bash
python3 -m unittest tests.test_swarm -v
```

12 tests cover heartbeats, reaping, freshness filtering, corrupt-file handling, and CLI.

---

*Built by MiniMax-M3, 2026-07-15. The swarm is a design problem, not a technology problem.*
