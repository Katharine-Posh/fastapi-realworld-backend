import datetime
from dataclasses import dataclass

from conduit.dtos.records.notification import NotificationFeedRecordDTO


@dataclass(frozen=True)
class NotificationDTO:
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

    @staticmethod
    def from_record(record: NotificationFeedRecordDTO) -> "NotificationDTO":
        return NotificationDTO(
            id=record.id,
            recipient_id=record.recipient_id,
            actor_id=record.actor_id,
            article_id=record.article_id,
            type=record.type,
            read_at=record.read_at,
            created_at=record.created_at,
            actor_username=record.actor_username,
            actor_image=record.actor_image,
            article_slug=record.article_slug,
        )


@dataclass(frozen=True)
class NotificationsFeedDTO:
    notifications: list[NotificationDTO]
    unread_count: int
    notifications_count: int
