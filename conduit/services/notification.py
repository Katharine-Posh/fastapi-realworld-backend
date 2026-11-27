from sqlalchemy.ext.asyncio import AsyncSession

from conduit.dtos.domain.notification import NotificationDTO, NotificationsFeedDTO
from conduit.dtos.records.notification import NotificationFeedRecordDTO
from conduit.interfaces.repositories.notification import INotificationRepository
from conduit.interfaces.services.notification import INotificationService


class NotificationService(INotificationService):
    """Service to handle user notifications."""

    def __init__(self, notification_repo: INotificationRepository) -> None:
        self._notification_repo = notification_repo

    async def notify(
        self,
        session: AsyncSession,
        recipient_id: int,
        actor_id: int,
        notification_type: str,
        article_id: int | None = None,
    ) -> None:
        # Self-notifications are intentionally skipped.
        if recipient_id == actor_id:
            return
        await self._notification_repo.add(
            session=session,
            recipient_id=recipient_id,
            actor_id=actor_id,
            notification_type=notification_type,
            article_id=article_id,
        )

    async def get_notifications(
        self,
        session: AsyncSession,
        recipient_id: int,
        limit: int,
        offset: int,
        unread_only: bool = False,
    ) -> NotificationsFeedDTO:
        records = await self._notification_repo.list(
            session=session,
            recipient_id=recipient_id,
            limit=limit,
            offset=offset,
            unread_only=unread_only,
        )
        # Badge count is computed independently of the list filters.
        unread_count = await self._notification_repo.count(
            session=session, recipient_id=recipient_id
        )
        total_count = await self._notification_repo.count(
            session=session, recipient_id=recipient_id, unread_only=unread_only
        )
        return NotificationsFeedDTO(
            notifications=[self._to_dto(record) for record in records],
            unread_count=unread_count,
            notifications_count=total_count,
        )

    async def mark_as_read(
        self, session: AsyncSession, notif_id: int, recipient_id: int
    ) -> NotificationDTO:
        await self._notification_repo.mark_as_read(
            session=session, notification_id=notif_id, recipient_id=recipient_id
        )
        record = await self._notification_repo.get_feed_record(
            session=session, notification_id=notif_id
        )
        return self._to_dto(record)

    async def mark_all_as_read(self, session: AsyncSession, recipient_id: int) -> int:
        return await self._notification_repo.mark_all_as_read(
            session=session, recipient_id=recipient_id
        )

    @staticmethod
    def _to_dto(record: NotificationFeedRecordDTO) -> NotificationDTO:
        return NotificationDTO.from_record(record=record)
