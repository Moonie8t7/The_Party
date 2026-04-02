"""
Minimal analytics server for The Party.
Run with: python analytics/server.py
Then open analytics/index.html in a browser.
"""

import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

TRANSCRIPT_PATH = Path("logs/transcript.jsonl")
PORT = 8787


def load_transcript() -> list[dict]:
    if not TRANSCRIPT_PATH.exists():
        return []
    entries = []
    with open(TRANSCRIPT_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def compute_stats(entries: list[dict]) -> dict:
    if not entries:
        return {
            "total_triggers": 0,
            "total_scenes": 0,
            "character_speak_counts": {},
            "router_method_counts": {},
            "avg_latency_ms": 0,
            "total_estimated_cost_usd": 0.0,
            "total_tokens_input": 0,
            "total_tokens_output": 0,
            "repair_events": 0,
            "avg_responses_per_scene": 0,
            "recent_triggers": [],
        }

    character_counts = {}
    router_counts = {}
    total_latency = 0
    total_cost = 0.0
    total_input_tokens = 0
    total_output_tokens = 0
    total_repairs = 0
    total_responses = 0

    for entry in entries:
        # Router method
        method = entry.get("router_method", "unknown")
        router_counts[method] = router_counts.get(method, 0) + 1

        # Latency
        total_latency += entry.get("total_latency_ms", 0)

        # Cost and tokens
        total_cost += entry.get("total_estimated_cost_usd", 0.0)
        total_input_tokens += entry.get("total_tokens_input", 0)
        total_output_tokens += entry.get("total_tokens_output", 0)
        total_repairs += entry.get("total_repair_events", 0)

        # Per-character counts
        for response in entry.get("responses", []):
            name = response.get("name", "unknown")
            character_counts[name] = character_counts.get(name, 0) + 1
            total_responses += 1

    n = len(entries)
    recent = sorted(entries, key=lambda e: e.get("received_at", ""), reverse=True)[:10]

    return {
        "total_triggers": n,
        "total_scenes": n,
        "character_speak_counts": character_counts,
        "router_method_counts": router_counts,
        "avg_latency_ms": round(total_latency / n) if n else 0,
        "total_estimated_cost_usd": round(total_cost, 4),
        "total_tokens_input": total_input_tokens,
        "total_tokens_output": total_output_tokens,
        "repair_events": total_repairs,
        "avg_responses_per_scene": round(total_responses / n, 1) if n else 0,
        "recent_triggers": [
            {
                "trigger_id": e.get("trigger_id", "")[:8],
                "type": e.get("type", ""),
                "text": e.get("text", "")[:60],
                "characters": e.get("characters", []),
                "latency_ms": e.get("total_latency_ms", 0),
                "cost": e.get("total_estimated_cost_usd", 0.0),
                "received_at": e.get("received_at", ""),
            }
            for e in recent
        ],
    }


class AnalyticsHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress request logs

    def do_GET(self):
        if self.path == "/api/stats":
            entries = load_transcript()
            stats = compute_stats(entries)
            body = json.dumps(stats).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    server = HTTPServer(("localhost", PORT), AnalyticsHandler)
    print(f"Analytics server running at http://localhost:{PORT}")
    print(f"Reading from: {TRANSCRIPT_PATH.absolute()}")
    print("Open analytics/index.html in your browser.")
    print("Ctrl+C to stop.")
    server.serve_forever()
