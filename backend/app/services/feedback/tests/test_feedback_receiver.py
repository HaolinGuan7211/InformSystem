from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.services.feedback.receiver import FeedbackReceiver


@pytest.mark.asyncio
async def test_feedback_receiver_uses_request_id_for_stable_feedback_id() -> None:
    receiver = FeedbackReceiver()
    payload = {
        "user_id": "stu_001",
        "event_id": "evt_001",
        "feedback_type": "useful",
        "metadata": {"request_id": "req-001"},
    }

    first = await receiver.receive(payload)
    second = await receiver.receive(payload)

    assert first.feedback_id == second.feedback_id
    assert first.feedback_id.startswith("fb_")


@pytest.mark.asyncio
async def test_feedback_receiver_validates_rating_range() -> None:
    receiver = FeedbackReceiver()

    with pytest.raises(ValidationError):
        await receiver.receive(
            {
                "user_id": "stu_001",
                "event_id": "evt_001",
                "feedback_type": "useful",
                "rating": 6,
                "metadata": {},
            }
        )
