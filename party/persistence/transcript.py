import json
import os
from party.models import Scene, TranscriptEntry
from party.config import settings
from party.log import get_logger

log = get_logger(__name__)


class TranscriptWriter:
    def __init__(self, path: str = ""):
        self._path = path or settings.transcript_path

    async def write(self, scene: Scene) -> None:
        entry = TranscriptEntry(
            trigger_id=scene.trigger.trigger_id,
            received_at=scene.trigger.received_at.isoformat(),
            type=scene.trigger.type.value,
            text=scene.trigger.text,
            characters=scene.characters,
            router_method=scene.router_method,
            responses=[r.model_dump() for r in scene.responses],
            total_latency_ms=scene.total_latency_ms,
            total_tokens_input=sum(r.tokens_input for r in scene.responses),
            total_tokens_output=sum(r.tokens_output for r in scene.responses),
            total_estimated_cost_usd=round(
                sum(r.estimated_cost_usd for r in scene.responses), 6
            ),
            total_repair_events=sum(1 for r in scene.responses if r.repaired),
            error=scene.error,
        )

        path = self._path
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(entry.model_dump_json() + "\n")
        except Exception as e:
            log.error("transcript.write_failed", reason=str(e))


# Module-level default writer
_default_writer = TranscriptWriter()


async def write_transcript(scene: Scene) -> None:
    """Convenience function using the default writer."""
    await _default_writer.write(scene)
