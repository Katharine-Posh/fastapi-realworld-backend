from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.exceptions import NotificationNotFoundException
from conduit.dtos.records.notification import (
    NotificationFeedRecordDTO,
    NotificationRecordDTO,
)
from conduit.infrastructure.models import Article, Notification, User
from conduit.interfaces.repositories.notification import INotificationRepository


def _feed_select() -> Select[Any]:
    return (
        select(
            Notification.id.label("id"),
            Notification.recipient_id.label("recipient_id"),
            Notification.actor_id.label("actor_id"),
            Notification.article_id.label("article_id"),
            Notification.type.label("type"),
            Notification.read_at.label("read_at"),
            Notification.created_at.label("created_at"),
            User.username.label("actor_username"),
            User.image.label("actor_image"),
            Article.slug.label("article_slug"),
        )
        .join(User, Notification.actor_id == User.id)
        .outerjoin(Article, Notification.article_id == Article.id)
    )


class NotificationRepository(INotificationRepository):
    async def add(
        self,
        session: AsyncSession,
        recipient_id: int,
        actor_id: int,
        notification_type: str,
        article_id: int | None = None,
    ) -> NotificationRecordDTO:
        query = (
            insert(Notification)
            .values(
                recipient_id=recipient_id,
                actor_id=actor_id,
                type=notification_type,
                article_id=article_id,
                created_at=datetime.now(),
            )
            .returning(Notification)
        )
        result = await session.execute(query)
        return self._to_record(result.scalar_one())

    async def list(
        self,
        session: AsyncSession,
        recipient_id: int,
        limit: int,
        offset: int,
        unread_only: bool = False,
    ) -> list[NotificationFeedRecordDTO]:
        query = _feed_select().where(Notification.recipient_id == recipient_id)
        if unread_only:
            query = query.where(Notification.read_at.is_(None))
        query = query.order_by(Notification.created_at.desc(), Notification.id.desc())
        query = query.limit(limit).offset(offset)
        result = await session.execute(query)
        return [self._to_feed_record(row) for row in result]

    async def count(
        self, session: AsyncSession, recipient_id: int, unread_only: bool = False
    ) -> int:
        query = select(func.count(Notification.id)).where(
            Notification.recipient_id == recipient_id
        )
        if unread_only:
            query = query.where(Notification.read_at.is_(None))
        result = await session.execute(query)
        return int(result.scalar_one())

    async def get_feed_record(
        self, session: AsyncSession, notification_id: int
    ) -> NotificationFeedRecordDTO:
        query = _feed_select().where(Notification.id == notification_id)
        result = await session.execute(query)
        row = result.one_or_none()
        if row is None:
            raise NotificationNotFoundException()
        return self._to_feed_record(row)

    async def mark_as_read(
        self, session: AsyncSession, notification_id: int, recipient_id: int
    ) -> None:
        query = (
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.recipient_id == recipient_id,
            )
            .values(read_at=datetime.now())
        )
        result = await session.execute(query)
        if result.rowcount == 0:
            raise NotificationNotFoundException()

    async def mark_all_as_read(self, session: AsyncSession, recipient_id: int) -> int:
        query = (
            update(Notification)
            .where(
                Notification.recipient_id == recipient_id,
                Notification.read_at.is_(None),
            )
            .values(read_at=datetime.now())
        )
        result = await session.execute(query)
        return result.rowcount

    @staticmethod
    def _to_record(model: Notification) -> NotificationRecordDTO:
        return NotificationRecordDTO(
            id=model.id,
            recipient_id=model.recipient_id,
            actor_id=model.actor_id,
            article_id=model.article_id,
            type=model.type,
            read_at=model.read_at,
            created_at=model.created_at,
        )

    @staticmethod
    def _to_feed_record(row: Any) -> NotificationFeedRecordDTO:
        return NotificationFeedRecordDTO(
            id=row.id,
            recipient_id=row.recipient_id,
            actor_id=row.actor_id,
            article_id=row.article_id,
            type=row.type,
            read_at=row.read_at,
            created_at=row.created_at,
            actor_username=row.actor_username,
            actor_image=row.actor_image,
            article_slug=row.article_slug,
        )
