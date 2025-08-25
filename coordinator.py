#!/usr/bin/env python3
# coordinator.py
# Merge server_update.json and client_update.json into server_view.json and client_view.json.
# Maintains a simple pairing FSM and per-pair epoch counters. Polls files every 100ms.
#
# Usage:
#   python3 coordinator.py \
#     --server-update server_update.json \
#     --client-update client_update.json \
#     --server-view   server_view.json \
#     --client-view   client_view.json
#
# States: INIT -> CLAIMED -> BOTH_RTS -> READY
# - Client writes CLAIMED/READY in client_update.json.pairs[]
# - Server writes BOTH_RTS in server_update.json.pairs[] when server side QP is RTS and paired.
# - The coordinator lifts the state for both views based on the highest observed stage.
#
# Epoch handling:
# - For each pair id, if the state differs from the previous output view, epoch += 1; else keep previous epoch.
#
# Remote by-id view:
# - For each output view V (server_view/client_view), V["remote"].ids.QP[] will list the "id" fields of remote.QP[].
#   This supports runtime_resolver's rr_*_by_id lookups.
#
# This script uses only stdlib.

import argparse, json, os, time, sys
from typing import Dict, Any, Tuple

POLL_INTERVAL = 0.1  # seconds
CACHED_FILES = ["server_update.json", "client_update.json", "server_view.json", "client_view.json"]


def clean_cached_files():
    for f in CACHED_FILES:
        try:
            os.remove(f)
        except Exception:
            pass


def load_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def atomic_write_json(path: str, obj: Dict[str, Any]):
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def extract_pairs(obj: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out = {}
    pairs = obj.get("local", {}).get("pairs", [])
    # Also accept top-level "pairs" for client demo
    if not pairs and "pairs" in obj:
        pairs = obj.get("pairs", [])
    for p in pairs or []:
        pid = p.get("id")
        if pid:
            out[pid] = p
    return out


def max_state(state_a: str, state_b: str) -> str:
    order = {"INIT": 0, "CLAIMED": 1, "PARAMS_BOUND": 2, "BOTH_RTS": 3, "READY": 4}
    a = order.get((state_a or "INIT"), 0)
    b = order.get((state_b or "INIT"), 0)
    # Choose the higher (more advanced) state
    inv = {v: k for k, v in order.items()}
    return inv[max(a, b)]


def merge_states(
    cli_pairs: Dict[str, Any], srv_pairs: Dict[str, Any], prev_view: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    # previous epochs from last output to preserve epoch unless state changes
    prev_epochs = {}
    prev_state = {}
    for p in prev_view.get("pairs") or []:
        prev_epochs[p.get("id", "")] = p.get("epoch", 0)
        prev_state[p.get("id", "")] = p.get("state", "INIT")

    all_ids = set(cli_pairs.keys()) | set(srv_pairs.keys())
    merged = {}
    for pid in sorted(all_ids):
        c = cli_pairs.get(pid, {})
        s = srv_pairs.get(pid, {})
        st = max_state(c.get("state", "INIT"), s.get("state", "INIT"))
        epoch = prev_epochs.get(pid, 0) + (1 if st != prev_state.get(pid, "INIT") else 0)
        merged[pid] = {
            "id": pid,
            "cli_id": c.get("cli_id", ""),
            "srv_id": c.get("srv_id", s.get("srv_id", "")),  # client may hint srv_id
            "state": st,
            "epoch": epoch,
            "ts": max(c.get("ts", 0), s.get("ts", 0)),
        }
    return merged


def build_view(
    local_update: Dict[str, Any],
    remote_update: Dict[str, Any],
    merged_pairs: Dict[str, Dict[str, Any]],
    prev_view: Dict[str, Any],
) -> Dict[str, Any]:
    view = {}
    # local
    view["local"] = local_update.get("local", {})
    # remote
    view["remote"] = remote_update.get("local", {})
    if "QP" not in view["remote"]:
        view["remote"]["QP"] = []
    # derive remote.ids.QP[]
    rid_list = [q.get("id", "") for q in (view["remote"].get("QP") or []) if q.get("id")]
    view["remote"]["ids"] = {"QP": rid_list}
    # pairs (list)
    view["pairs"] = list(merged_pairs.values())
    # carry build info
    view["_coordinator"] = {
        "generated_at_ms": int(time.time() * 1000),
        "local_qp_count": len(view["local"].get("QP", [])),
        "remote_qp_count": len(view["remote"].get("QP", [])),
        "pair_count": len(view["pairs"]),
    }
    return view


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server-update", required=True)
    ap.add_argument("--client-update", required=True)
    ap.add_argument("--server-view", required=True)
    ap.add_argument("--client-view", required=True)
    ap.add_argument("--once", action="store_true", help="Run once and exit (no polling loop).")
    # ap.add_argument("--clean", action="store_false", help="Clean cached filesexit.")
    args = ap.parse_args()
    # if args.clean:

    clean_cached_files()

    prev_server_view = load_json(args.server_view)
    prev_client_view = load_json(args.client_view)

    def one_round(prev_sv, prev_cv) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        srv_u = load_json(args.server_update)
        cli_u = load_json(args.client_update)

        # extract pairs from both sides
        cli_pairs = extract_pairs(cli_u)
        srv_pairs = extract_pairs(srv_u)

        # merge states with previous epochs
        # For server view, use prev_sv to preserve epochs; for client view, use prev_cv
        merged_for_server = merge_states(cli_pairs, srv_pairs, prev_sv or {})
        merged_for_client = merge_states(cli_pairs, srv_pairs, prev_cv or {})

        # server view: local=srv_u.local, remote=cli_u.local
        server_view = build_view(srv_u, cli_u, merged_for_server, prev_sv or {})
        # client view: local=cli_u.local, remote=srv_u.local
        client_view = build_view(cli_u, srv_u, merged_for_client, prev_cv or {})

        # atomic write
        atomic_write_json(args.server_view, server_view)
        atomic_write_json(args.client_view, client_view)
        return server_view, client_view

    sv, cv = one_round(prev_server_view, prev_client_view)
    if args.once:
        return

    # Polling loop with mtime checks
    def mtime(path):
        try:
            return os.stat(path).st_mtime_ns
        except Exception:
            return 0

    last_srv_m = mtime(args.server_update)
    last_cli_m = mtime(args.client_update)

    while True:
        time.sleep(POLL_INTERVAL)
        srv_m = mtime(args.server_update)
        cli_m = mtime(args.client_update)
        if srv_m != last_srv_m or cli_m != last_cli_m:
            last_srv_m, last_cli_m = srv_m, cli_m
            prev_server_view, prev_client_view = sv, cv
            sv, cv = one_round(prev_server_view, prev_client_view)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
