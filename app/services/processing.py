"""
End-to-end background processing pipeline for meetings:
Transcript Retrieval -> Segment Storage -> Memory Extraction -> Action Item Tracking -> Vector Indexing.
"""
import uuid
from typing import Optional, List, Dict, Any
from app.config import settings
from app.database.connection import get_db_context
from app.database.repositories import (
    MeetingRepository, TranscriptRepository, MemoryRepository,
    ActionItemRepository, ProcessingJobRepository, ParticipantRepository
)
from app.services.meetstream import meetstream_client
from app.services.memory import memory_extractor
from app.rag.meeting_memory import meeting_memory_rag


class MeetingProcessingPipeline:
    def __init__(self):
        self.meetstream_client = meetstream_client
        self.memory_extractor = memory_extractor
        self.rag_engine = meeting_memory_rag

    async def process_meeting_transcript(
        self,
        meeting_id: uuid.UUID,
        transcript_id: Optional[str] = None,
        transcript_segments_input: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Executes the full pipeline for a meeting once transcript is ready.
        """
        async with get_db_context() as db:
            meeting_repo = MeetingRepository(db)
            transcript_repo = TranscriptRepository(db)
            memory_repo = MemoryRepository(db)
            action_repo = ActionItemRepository(db)
            job_repo = ProcessingJobRepository(db)
            participant_repo = ParticipantRepository(db)

            # 1. Fetch meeting - no org context available yet at webhook time,
            # so look it up unscoped and read its real organization_id off
            # the row itself for every downstream org-scoped call below.
            meeting = await meeting_repo.get_by_id_unscoped(meeting_id)
            if not meeting:
                raise ValueError(f"Meeting {meeting_id} not found")

            # Create tracking job
            job = await job_repo.create_job(meeting_id=meeting.id, job_type="process_meeting_memory")
            await job_repo.start_job(job.id)
            await meeting_repo.update_status(meeting.id, processing_status="processing")
            await db.commit()

            try:
                # 2. Retrieve transcript data
                raw_segments = transcript_segments_input
                if not raw_segments and transcript_id:
                    t_resp = await self.meetstream_client.get_transcript(transcript_id)
                    if isinstance(t_resp, list):
                        # Actual MeetStream get_transcript response: each list item is one
                        # participant's speech for the call, with a "participant" object
                        # (not a flat "speaker" string) and a "words" array of timestamped
                        # word-level fragments (no top-level "transcript"/"text" field).
                        raw_segments = []
                        for item in t_resp:
                            words = item.get("words") or []
                            text = " ".join(w.get("text", "") for w in words).strip()
                            if not text:
                                continue
                            participant = item.get("participant") or {}
                            start_time = words[0].get("start_timestamp", {}).get("relative") if words else None
                            end_time = words[-1].get("end_timestamp", {}).get("relative") if words else None
                            raw_segments.append({
                                "speaker": participant.get("name") or "Unknown",
                                "text": text,
                                "start_time": start_time,
                                "end_time": end_time,
                                "confidence": None,
                                "word_data": words,
                            })
                    elif isinstance(t_resp, dict) and "words" in t_resp:
                        # Single raw transcript object
                        raw_segments = [{
                            "speaker": "Speaker",
                            "text": t_resp.get("text", ""),
                            "start_time": 0.0,
                            "end_time": float(t_resp.get("audio_duration", 0)),
                            "confidence": t_resp.get("confidence"),
                        }]

                if not raw_segments:
                    # Check if already in DB
                    existing_segs = await transcript_repo.get_segments_by_meeting(meeting.id)
                    raw_segments = [
                        {
                            "speaker": s.speaker,
                            "text": s.text,
                            "start_time": s.start_time,
                            "end_time": s.end_time,
                            "confidence": s.confidence,
                        }
                        for s in existing_segs
                    ]

                if not raw_segments:
                    raise ValueError(f"No transcript content available for meeting {meeting_id}")

                # 3. Store transcript segments in database
                await transcript_repo.add_segments(meeting.id, raw_segments)
                await participant_repo.sync_from_speaker_names(
                    meeting.id,
                    [s.get("speaker", "") for s in raw_segments],
                )
                await db.commit()

                # 4. Format transcript text for LLM memory extraction
                transcript_text = "\n".join([
                    f"{s.get('speaker', 'Unknown')}: {s.get('text', '')}"
                    for s in raw_segments
                ])

                # 5. Extract structured memories and action items
                extraction_result = await self.memory_extractor.extract_memories(
                    transcript_text=transcript_text,
                    meeting_title=meeting.title,
                    customer_name=meeting.customer_name,
                    project_name=meeting.project_name,
                )

                extracted_memories_data = extraction_result.get("memories", [])
                extracted_actions_data = extraction_result.get("action_items", [])
                summary = extraction_result.get("summary", "")

                # 6. Save Memories to DB
                created_memories = await memory_repo.create_batch(
                    org_id=meeting.organization_id,
                    meeting_id=meeting.id,
                    memories_data=extracted_memories_data,
                )

                # 7. Save Action Items to DB
                for act in extracted_actions_data:
                    await action_repo.create(
                        org_id=meeting.organization_id,
                        meeting_id=meeting.id,
                        task=act.get("task", ""),
                        owner=act.get("owner"),
                        priority=act.get("priority", "medium"),
                    )

                # 8. Index into Meeting Memory RAG
                indexed_count = await self.rag_engine.index_meeting(
                    db=db,
                    org_id=meeting.organization_id,
                    meeting_id=meeting.id,
                    transcript_segments=raw_segments,
                    memories=created_memories,
                    meeting_metadata={
                        "title": meeting.title,
                        "customer_name": meeting.customer_name,
                        "project_name": meeting.project_name,
                    }
                )

                # 9. Finalize meeting record
                await meeting_repo.update_status(
                    meeting_id=meeting.id,
                    summary=summary,
                    processing_status="completed",
                )

                result_payload = {
                    "memories_extracted": len(created_memories),
                    "action_items_created": len(extracted_actions_data),
                    "vectors_indexed": indexed_count,
                }

                await job_repo.complete_job(job.id, result=result_payload)
                await db.commit()
                return result_payload

            except Exception as e:
                await job_repo.complete_job(job.id, error=str(e))
                await meeting_repo.update_status(
                    meeting_id=meeting.id,
                    processing_status="failed",
                    processing_error=str(e),
                )
                await db.commit()
                print(f"[ERROR] Pipeline execution failed for meeting {meeting_id}: {e}")
                raise


processing_pipeline = MeetingProcessingPipeline()
