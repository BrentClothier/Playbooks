from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import httpx
from psycopg.types.json import Jsonb
from tenacity import retry, stop_after_attempt, wait_exponential

from .db import connect, ensure_source, finish_run, start_run


LEGISTAR_CLIENT = "humboldt"
LEGISTAR_BASE = f"https://webapi.legistar.com/v1/{LEGISTAR_CLIENT}"
SOURCE_KEY = "humboldt-legistar"
USER_AGENT = "HumboldtGovernmentIntelligence/1.0 (+public-records-research)"


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _get_json(client: httpx.Client, path: str, params: dict[str, Any]) -> Any:
    response = client.get(path, params=params)
    response.raise_for_status()
    return response.json()


def _attachment_external_id(attachment: dict[str, Any], index: int) -> str:
    for key in (
        "MatterAttachmentId",
        "MatterAttachmentGuid",
        "MatterAttachmentHyperlink",
        "MatterAttachmentFileName",
        "MatterAttachmentName",
    ):
        value = attachment.get(key)
        if value not in (None, ""):
            return str(value)
    return f"attachment-{index}"


def sync_legistar(days_back: int = 730) -> dict[str, int]:
    cutoff = date.today() - timedelta(days=max(1, days_back))
    seen = 0
    written = 0

    conn = connect()
    try:
        source_id = ensure_source(
            conn,
            source_key=SOURCE_KEY,
            name="Humboldt County Legistar",
            agency="County of Humboldt",
            source_type="legistar",
            base_url=LEGISTAR_BASE,
        )
        conn.commit()
        run_id = start_run(
            conn,
            source_id,
            {"days_back": days_back, "cutoff": cutoff.isoformat()},
        )
        conn.commit()

        with httpx.Client(
            base_url=LEGISTAR_BASE,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=httpx.Timeout(45.0),
            follow_redirects=True,
        ) as client:
            offset = 0
            page_size = 250
            done = False

            while not done:
                events = _get_json(
                    client,
                    "/events",
                    {
                        "$top": page_size,
                        "$skip": offset,
                        "$orderby": "EventDate desc",
                    },
                )
                if not isinstance(events, list) or not events:
                    break

                for event in events:
                    event_date = _parse_date(event.get("EventDate"))
                    if event_date and event_date < cutoff:
                        done = True
                        continue

                    event_id = event.get("EventId")
                    if event_id is None:
                        continue

                    detail = _get_json(
                        client,
                        f"/events/{event_id}",
                        {
                            "EventItems": 1,
                            "AgendaNote": 1,
                            "MinutesNote": 1,
                            "EventItemAttachments": 1,
                        },
                    )
                    if not isinstance(detail, dict):
                        continue

                    seen += 1
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO gov.meetings (
                                event_id, source_id, event_guid, body_id, body_name,
                                event_date, event_time, location, agenda_status,
                                minutes_status, agenda_url, minutes_url, video_url,
                                insite_url, last_modified_at, retrieved_at, raw
                            )
                            VALUES (
                                %s, %s, %s, %s, %s,
                                %s, %s, %s, %s,
                                %s, %s, %s, %s,
                                %s, %s, now(), %s
                            )
                            ON CONFLICT (event_id) DO UPDATE
                            SET source_id = EXCLUDED.source_id,
                                event_guid = EXCLUDED.event_guid,
                                body_id = EXCLUDED.body_id,
                                body_name = EXCLUDED.body_name,
                                event_date = EXCLUDED.event_date,
                                event_time = EXCLUDED.event_time,
                                location = EXCLUDED.location,
                                agenda_status = EXCLUDED.agenda_status,
                                minutes_status = EXCLUDED.minutes_status,
                                agenda_url = EXCLUDED.agenda_url,
                                minutes_url = EXCLUDED.minutes_url,
                                video_url = EXCLUDED.video_url,
                                insite_url = EXCLUDED.insite_url,
                                last_modified_at = EXCLUDED.last_modified_at,
                                retrieved_at = now(),
                                raw = EXCLUDED.raw
                            """,
                            (
                                int(event_id),
                                source_id,
                                detail.get("EventGuid"),
                                detail.get("EventBodyId"),
                                detail.get("EventBodyName"),
                                _parse_date(detail.get("EventDate")),
                                detail.get("EventTime"),
                                detail.get("EventLocation"),
                                detail.get("EventAgendaStatusName"),
                                detail.get("EventMinutesStatusName"),
                                detail.get("EventAgendaFile"),
                                detail.get("EventMinutesFile"),
                                detail.get("EventVideoPath") or detail.get("EventMedia"),
                                detail.get("EventInSiteURL"),
                                _parse_datetime(detail.get("EventLastModifiedUtc")),
                                Jsonb(detail),
                            ),
                        )

                        cur.execute(
                            "DELETE FROM gov.agenda_items WHERE meeting_event_id = %s",
                            (int(event_id),),
                        )

                        items = detail.get("EventItems") or []
                        if not isinstance(items, list):
                            items = []

                        for item in items:
                            item_id = item.get("EventItemId")
                            if item_id is None:
                                continue

                            cur.execute(
                                """
                                INSERT INTO gov.agenda_items (
                                    event_item_id, meeting_event_id, event_item_guid,
                                    matter_id, agenda_number, agenda_sequence, title,
                                    agenda_note, minutes_note, action_name, action_text,
                                    last_modified_at, retrieved_at, raw
                                )
                                VALUES (
                                    %s, %s, %s,
                                    %s, %s, %s, %s,
                                    %s, %s, %s, %s,
                                    %s, now(), %s
                                )
                                """,
                                (
                                    int(item_id),
                                    int(event_id),
                                    item.get("EventItemGuid"),
                                    item.get("EventItemMatterId"),
                                    item.get("EventItemAgendaNumber"),
                                    item.get("EventItemAgendaSequence"),
                                    item.get("EventItemTitle"),
                                    item.get("EventItemAgendaNote"),
                                    item.get("EventItemMinutesNote"),
                                    item.get("EventItemActionName"),
                                    item.get("EventItemActionText"),
                                    _parse_datetime(item.get("EventItemLastModifiedUtc")),
                                    Jsonb(item),
                                ),
                            )

                            attachments = item.get("EventItemMatterAttachments") or []
                            if not isinstance(attachments, list):
                                attachments = []
                            for index, attachment in enumerate(attachments):
                                if not isinstance(attachment, dict):
                                    continue
                                cur.execute(
                                    """
                                    INSERT INTO gov.agenda_item_attachments (
                                        event_item_id, external_id, name, hyperlink,
                                        file_name, raw
                                    )
                                    VALUES (%s, %s, %s, %s, %s, %s)
                                    ON CONFLICT (event_item_id, external_id) DO UPDATE
                                    SET name = EXCLUDED.name,
                                        hyperlink = EXCLUDED.hyperlink,
                                        file_name = EXCLUDED.file_name,
                                        raw = EXCLUDED.raw
                                    """,
                                    (
                                        int(item_id),
                                        _attachment_external_id(attachment, index),
                                        attachment.get("MatterAttachmentName"),
                                        attachment.get("MatterAttachmentHyperlink"),
                                        attachment.get("MatterAttachmentFileName"),
                                        Jsonb(attachment),
                                    ),
                                )

                    conn.commit()
                    written += 1

                offset += page_size
                if len(events) < page_size:
                    break

        finish_run(
            conn,
            run_id,
            status="success",
            records_seen=seen,
            records_written=written,
        )
        conn.commit()
        return {"meetings_seen": seen, "meetings_written": written}

    except Exception as exc:
        conn.rollback()
        if "run_id" in locals():
            finish_run(
                conn,
                run_id,
                status="error",
                records_seen=seen,
                records_written=written,
                error_message=str(exc)[:2000],
            )
            conn.commit()
        raise
    finally:
        conn.close()
