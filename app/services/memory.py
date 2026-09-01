"""
LLM Memory Extraction Service.
Extracts structured knowledge (decisions, commitments, action items, requirements, facts)
and meeting summaries from raw meeting transcripts.
"""
import json
import re
from typing import List, Dict, Any, Optional, Tuple
from app.config import settings
from app.models.database import MemoryType


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
    def __init__(self):
        self.provider = settings.LLM_PROVIDER.lower()

    async def extract_memories(
        self,
        transcript_text: str,
        meeting_title: Optional[str] = None,
        customer_name: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Invokes configured LLM to extract memories, action items, and summary.
        Includes a deterministic parser fallback if no LLM key is configured.
        """
        # Format user prompt
        user_prompt = f"Meeting Title: {meeting_title or 'Untitled Meeting'}\n"
        if customer_name:
            user_prompt += f"Customer: {customer_name}\n"
        if project_name:
            user_prompt += f"Project: {project_name}\n"
        user_prompt += f"\n--- TRANSCRIPT ---\n{transcript_text}\n--- END TRANSCRIPT ---"

        # Try LLM providers
        if settings.OPENAI_API_KEY and self.provider == "openai":
            try:
                return await self._call_openai(user_prompt)
            except Exception as e:
                print(f"[WARN] OpenAI extraction failed: {e}. Falling back to rule-based parser.")

        if settings.GROQ_API_KEY:
            try:
                return await self._call_groq(user_prompt)
            except Exception as e:
                print(f"[WARN] Groq extraction failed: {e}. Falling back to rule-based parser.")

        # Deterministic rule-based extraction fallback
        return self._heuristic_extract(transcript_text, meeting_title, customer_name, project_name)

    async def _call_openai(self, prompt: str) -> Dict[str, Any]:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)

    async def _call_groq(self, prompt: str) -> Dict[str, Any]:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        response = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)

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
