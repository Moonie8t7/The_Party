import json
from pathlib import Path
from party.config import settings

def load_transcript(path: str = "", date_filter: str = None) -> list[dict]:
    transcript_path = Path(path or settings.transcript_path)
    if not transcript_path.exists():
        return []
    
    entries = []
    with open(transcript_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    if date_filter:
                        # entry["received_at"] is ISO-8601: 2026-04-02T19:51:48...
                        if not entry.get("received_at", "").startswith(date_filter):
                            continue
                    entries.append(entry)
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
