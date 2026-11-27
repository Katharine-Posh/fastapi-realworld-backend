import datetime
from dataclasses import dataclass


@dataclass(frozen=True)
class NotificationRecordDTO:
    id: int
    recipient_id: int
    actor_id: int
    article_id: int | None
    type: str
    read_at: datetime.datetime | None
    created_at: datetime.datetime


@dataclass(frozen=True)
class NotificationFeedRecordDTO:
    id: int
    recipient_id: int
    actor_id: int
    article_id: int | None
    type: str
    read_at: datetime.datetime | None
    created_at: datetime.datetime
    actor_username: str
    actor_image: str | None
    article_slug: str | None
