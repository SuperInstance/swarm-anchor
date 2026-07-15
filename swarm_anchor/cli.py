"""CLI for swarm-anchor.

    swarm-anchor start    --animal scout --model deepseek/... --task "..."
    swarm-anchor heartbeat --animal scout --model ... --task ...
    swarm-anchor roster
    swarm-anchor reap --stale-seconds 120
    swarm-anchor leave    --animal scout
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from swarm_anchor.core import Anchor, HeartbeatStatus, make_animal


def _read_existing(root: str, animal: str):
    """Read an existing heartbeat if present, return new one initialized."""
    from pathlib import Path
    from swarm_anchor.core import _from_json  # noqa
    import json as _json

    path = Path(root) / f"{animal}.heartbeat.json"
    if path.exists():
        try:
            return _from_json(_json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass
    return None


def _cmd_start(args: argparse.Namespace) -> int:
    a = Anchor(args.root)
    existing = _read_existing(args.root, args.animal)
    if existing:
        existing.status = HeartbeatStatus.HEALTHY
        existing.task = args.task
        existing.model = args.model
        a.heartbeat(existing)
    else:
        hb = make_animal(name=args.animal, model=args.model, task=args.task)
        hb.status = HeartbeatStatus.HEALTHY
        a.heartbeat(hb)
    print(f"{args.animal}: started ({args.model})")
    return 0


def _cmd_heartbeat(args: argparse.Namespace) -> int:
    a = Anchor(args.root)
    hb = _read_existing(args.root, args.animal)
    if not hb:
        hb = make_animal(name=args.animal, model=args.model or "?", task=args.task or "")
    if args.model:
        hb.model = args.model
    if args.task:
        hb.task = args.task
    if args.add_proposal:
        for p in args.add_proposal:
            hb.add_proposal(p)
    if args.add_warning:
        for w in args.add_warning:
            hb.add_warning(w)
    a.heartbeat(hb)
    print(f"{args.animal}: heartbeat fresh (last_seen={hb.last_seen})")
    return 0


def _cmd_leave(args: argparse.Namespace) -> int:
    a = Anchor(args.root)
    removed = a.reap(args.animal)
    print("left" if removed else "no heartbeat to remove")
    return 0


def _cmd_roster(args: argparse.Namespace) -> int:
    a = Anchor(args.root)
    ros = a.roster(stale_seconds=args.stale_seconds)
    payload = {
        "at": ros.at,
        "count": ros.count(),
        "active": len(ros.active(stale_seconds=args.stale_seconds)),
        "animals": [
            {
                "animal": hb.animal,
                "status": hb.status.value,
                "model": hb.model,
                "task": hb.task,
                "last_seen": hb.last_seen,
                "proposals": hb.proposals,
                "warnings": hb.warnings,
            }
            for hb in ros.animals.values()
        ],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _cmd_reap(args: argparse.Namespace) -> int:
    a = Anchor(args.root)
    removed = a.kill_stale(stale_seconds=args.stale_seconds)
    print(json.dumps({"removed": removed, "stale_seconds": args.stale_seconds}))
    return 0


def _cmd_ping(args: argparse.Namespace) -> int:
    """Long-running heartbeat pinger (every args.interval seconds)."""
    a = Anchor(args.root)
    interval = max(1, int(args.interval))
    while True:
        hb = _read_existing(args.root, args.animal)
        if hb:
            a.heartbeat(hb)
        else:
            hb = make_animal(name=args.animal, model=args.model, task=args.task)
            a.heartbeat(hb)
        time.sleep(interval)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="swarm-anchor")
    p.add_argument("--root", default=".swarm", help="swarm state directory")
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("start", help="start an animal in the swarm")
    ps.add_argument("--animal", required=True)
    ps.add_argument("--model", required=True)
    ps.add_argument("--task", required=True)
    ps.set_defaults(func=_cmd_start)

    ph = sub.add_parser("heartbeat", help="refresh an animal's heartbeat")
    ph.add_argument("--animal", required=True)
    ph.add_argument("--model", default="")
    ph.add_argument("--task", default="")
    ph.add_argument("--add-proposal", action="append", help="add a proposal (repeatable)")
    ph.add_argument("--add-warning", action="append", help="add a warning (repeatable)")
    ph.set_defaults(func=_cmd_heartbeat)

    pl = sub.add_parser("leave", help="remove an animal's heartbeat")
    pl.add_argument("--animal", required=True)
    pl.set_defaults(func=_cmd_leave)

    pr = sub.add_parser("roster", help="show all animals")
    pr.add_argument("--stale-seconds", type=int, default=30)
    pr.set_defaults(func=_cmd_roster)

    pkr = sub.add_parser("reap", help="remove stale animals")
    pkr.add_argument("--stale-seconds", type=int, default=120)
    pkr.set_defaults(func=_cmd_reap)

    pp = sub.add_parser("ping", help="long-running heartbeat (for tmux)")
    pp.add_argument("--animal", required=True)
    pp.add_argument("--model", required=True)
    pp.add_argument("--task", required=True)
    pp.add_argument("--interval", type=int, default=10)
    pp.set_defaults(func=_cmd_ping)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
