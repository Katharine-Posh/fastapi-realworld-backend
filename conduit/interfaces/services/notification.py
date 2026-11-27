import abc
from typing import Any

from conduit.dtos.domain.notification import NotificationDTO, NotificationsFeedDTO


class INotificationService(abc.ABC):
    @abc.abstractmethod
    async def notify(
        self,
        session: Any,
        recipient_id: int,
        actor_id: int,
        notification_type: str,
        article_id: int | None = None,
    ) -> None: ...

    @abc.abstractmethod
    async def get_notifications(
        self,
        session: Any,
        recipient_id: int,
        limit: int,
        offset: int,
        unread_only: bool = False,
    ) -> NotificationsFeedDTO: ...

    @abc.abstractmethod
    async def mark_as_read(
        self, session: Any, notif_id: int, recipient_id: int
    ) -> NotificationDTO: ...

    @abc.abstractmethod
    async def mark_all_as_read(self, session: Any, recipient_id: int) -> int: ...
