"""
Unit tests for memory extraction and heuristic parser.
"""
import pytest
from app.services.memory import MemoryExtractionService
from app.models.database import MemoryType


@pytest.mark.asyncio
async def test_heuristic_memory_extraction():
    service = MemoryExtractionService()
    transcript = """John: Acme requires SSO integration before launch.
Sarah: I will send the SOC 2 compliance documentation by tomorrow.
John: Let's target September 15 for the public release."""

    result = await service.extract_memories(
        transcript_text=transcript,
        meeting_title="Acme Architecture Review",
        customer_name="Acme Corp",
        project_name="SSO Integration",
    )

    assert "summary" in result
    assert "memories" in result
    assert "action_items" in result

    memories = result["memories"]
    assert len(memories) >= 3

    # Verify requirement extraction
    reqs = [m for m in memories if m["type"] == MemoryType.REQUIREMENT.value]
    assert len(reqs) >= 1
    assert "SSO" in reqs[0]["content"]

    # Verify commitment extraction
    comms = [m for m in memories if m["type"] == MemoryType.COMMITMENT.value]
    assert len(comms) >= 1
    assert "SOC 2" in comms[0]["content"]
    assert comms[0]["speaker"] == "Sarah"

    # Verify decision extraction
    decs = [m for m in memories if m["type"] == MemoryType.DECISION.value]
    assert len(decs) >= 1
    assert "September 15" in decs[0]["content"]

    # Verify action items
    actions = result["action_items"]
    assert len(actions) >= 1
    assert actions[0]["owner"] == "Sarah"
