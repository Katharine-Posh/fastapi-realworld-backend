import datetime

from pydantic import BaseModel, ConfigDict, Field

from conduit.core.utils.date import convert_datetime_to_realworld
from conduit.dtos.domain.notification import NotificationDTO, NotificationsFeedDTO


class NotificationActorData(BaseModel):
    username: str
    image: str | None


class NotificationData(BaseModel):
    id: int
    type: str
    actor: NotificationActorData
    article_slug: str | None = Field(default=None, alias="articleSlug")
    read_at: datetime.datetime | None = Field(default=None, alias="readAt")
    created_at: datetime.datetime = Field(alias="createdAt")

    model_config = ConfigDict(
        json_encoders={datetime.datetime: convert_datetime_to_realworld}
    )


class NotificationResponse(BaseModel):
    notification: NotificationData

    @classmethod
    def from_dto(cls, dto: NotificationDTO) -> "NotificationResponse":
        notification = NotificationData(
            id=dto.id,
            type=dto.type,
            actor=NotificationActorData(
                username=dto.actor_username, image=dto.actor_image
            ),
            articleSlug=dto.article_slug,
            readAt=dto.read_at,
            createdAt=dto.created_at,
        )
        return NotificationResponse(notification=notification)


class NotificationsFeedResponse(BaseModel):
    notifications: list[NotificationData]
    unread_count: int = Field(alias="unreadCount")
    notifications_count: int = Field(alias="notificationsCount")

    @classmethod
    def from_dto(cls, dto: NotificationsFeedDTO) -> "NotificationsFeedResponse":
        notifications = [
            NotificationResponse.from_dto(dto=notification_dto).notification
            for notification_dto in dto.notifications
        ]
        return NotificationsFeedResponse(
            notifications=notifications,
            unreadCount=dto.unread_count,
            notificationsCount=dto.notifications_count,
        )
