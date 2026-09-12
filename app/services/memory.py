"""
LLM Memory Extraction Service.
Extracts structured knowledge (decisions, commitments, action items, requirements, facts)
and meeting summaries from raw meeting transcripts.
"""
from typing import Any, Dict, Optional

from app.models.database import MemoryType
from app.providers.llm import ChatMessage, LLMError
from app.services.llm import try_get_llm_provider


EXTRACTION_SYSTEM_PROMPT = """You are an expert AI meeting analyst. Your job is to extract high-value persistent knowledge and structured action items from the provided meeting transcript.

Extract memories in these specific categories:
1. "decision": Architectural, product, timeline, or business decisions agreed upon.
2. "commitment": Explicit promises or commitments made by specific individuals (e.g. "I will send X tomorrow").
3. "action_item": Actionable tasks that need completion, with owner and deadline if mentioned.
4. "requirement": Technical, security, compliance, or business requirements specified by any participant.
5. "concern": Significant risks, hesitations, or blockers raised.
6. "fact": Key facts, metrics, or statements of reality shared during the meeting.
7. "unresolved_question": Critical questions that were left unanswered.

Output valid JSON ONLY with the following structure:
{
  "summary": "Concise 2-3 paragraph executive summary of the meeting discussions and outcomes.",
  "memories": [
    {
      "type": "decision|commitment|action_item|requirement|concern|preference|fact|project_update|relationship_context|unresolved_question",
      "content": "Clear, standalone statement capturing the memory with all necessary context.",
      "speaker": "Name of the person who said or committed to it, or null if general consensus",
      "importance": 1-10 (10 being critical business/technical blocker or top decision)
    }
  ],
  "action_items": [
    {
      "task": "Specific actionable description of the task",
      "owner": "Name of the assigned person, or null if unassigned",
      "due_date": "YYYY-MM-DD or null if no deadline specified",
      "priority": "low|medium|high|critical"
    }
  ]
}
"""


class MemoryExtractionService:
    """
    Turns a raw transcript into structured memories, action items and a summary.

    Runs against whichever LLM provider the user configured. When no provider
    is configured or the call fails, a deterministic rule-based parser keeps
    the pipeline working rather than losing the meeting entirely.
    """

    async def extract_memories(
        self,
        transcript_text: str,
        meeting_title: Optional[str] = None,
        customer_name: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        provider = try_get_llm_provider()
        if provider is not None:
            messages = [
                ChatMessage(role="system", content=EXTRACTION_SYSTEM_PROMPT),
                ChatMessage(
                    role="user",
                    content=self._build_prompt(
                        transcript_text, meeting_title, customer_name, project_name
                    ),
                ),
            ]
            try:
                return await provider.complete_json(messages)
            except (LLMError, OSError) as exc:
                print(
                    f"[WARN] Memory extraction via {provider.label} failed: {exc}. "
                    "Falling back to rule-based parser."
                )

        return self._heuristic_extract(transcript_text, meeting_title, customer_name, project_name)

    @staticmethod
    def _build_prompt(
        transcript_text: str,
        meeting_title: Optional[str],
        customer_name: Optional[str],
        project_name: Optional[str],
    ) -> str:
        prompt = f"Meeting Title: {meeting_title or 'Untitled Meeting'}\n"
        if customer_name:
            prompt += f"Customer: {customer_name}\n"
        if project_name:
            prompt += f"Project: {project_name}\n"
        prompt += f"\n--- TRANSCRIPT ---\n{transcript_text}\n--- END TRANSCRIPT ---"
        return prompt

    def _heuristic_extract(
        self,
        transcript_text: str,
        meeting_title: Optional[str] = None,
        customer_name: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Deterministic extraction for offline testing or when API keys are not provided.
        Parses common patterns like 'requires', 'will send', 'target', 'decided', etc.
        """
        lines = transcript_text.strip().split("\n")
        memories = []
        action_items = []

        for line in lines:
            if not line.strip():
                continue

            speaker = None
            text = line
            if ":" in line:
                parts = line.split(":", 1)
                speaker = parts[0].strip()
                text = parts[1].strip()

            text_lower = text.lower()

            # Requirements
            if "require" in text_lower or "must have" in text_lower or "need" in text_lower:
                memories.append({
                    "type": MemoryType.REQUIREMENT.value,
                    "content": text,
                    "speaker": speaker,
                    "importance": 8,
                })

            # Commitments & Action items
            if "i will" in text_lower or "i'll" in text_lower or "will send" in text_lower or "will do" in text_lower:
                memories.append({
                    "type": MemoryType.COMMITMENT.value,
                    "content": text,
                    "speaker": speaker,
                    "importance": 7,
                })
                action_items.append({
                    "task": text,
                    "owner": speaker,
                    "due_date": None,
                    "priority": "high" if "soc" in text_lower or "security" in text_lower else "medium",
                })

            # Decisions
            if "target" in text_lower or "decided" in text_lower or "agreed" in text_lower or "let's" in text_lower:
                memories.append({
                    "type": MemoryType.DECISION.value,
                    "content": text,
                    "speaker": speaker,
                    "importance": 9,
                })

            # Facts / Updates
            if not any(m["content"] == text for m in memories):
                memories.append({
                    "type": MemoryType.FACT.value,
                    "content": text,
                    "speaker": speaker,
                    "importance": 5,
                })

        summary = f"Meeting summary for {meeting_title or 'Discussion'}. Key topics included requirements, timeline targets, and action assignments."

        return {
            "summary": summary,
            "memories": memories,
            "action_items": action_items,
        }


memory_extractor = MemoryExtractionService()
