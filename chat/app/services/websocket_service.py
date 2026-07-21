import uuid
from typing import Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.messages import Conversation, Message, MessageDirection, MessageStatus
from models.lines import Line


class WebSocketService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.subscriptions: Dict[uuid.UUID, List[uuid.UUID]] = {}  # conversation_id -> [user_id]

    async def subscribe_to_conversation(
            self,
            conversation_id: uuid.UUID,
            tenant_id: uuid.UUID,
            user_id: uuid.UUID
    ):
        """Subscribe user to conversation updates"""
        # Verify conversation belongs to tenant
        stmt = select(Conversation).join(Line).where(
            Conversation.id == conversation_id,
            Line.tenant_id == tenant_id
        )
        result = await self.db.execute(stmt)
        conversation = result.scalar_one_or_none()

        if not conversation:
            raise ValueError("Conversation not found or access denied")

        if conversation_id not in self.subscriptions:
            self.subscriptions[conversation_id] = []

        if user_id not in self.subscriptions[conversation_id]:
            self.subscriptions[conversation_id].append(user_id)

    async def save_message(
            self,
            conversation_id: uuid.UUID,
            tenant_id: uuid.UUID,
            user_id: uuid.UUID,
            message: dict
    ) -> dict:
        """Save incoming WebSocket message to database"""
        # Verify conversation belongs to tenant
        stmt = select(Conversation).join(Line).where(
            Conversation.id == conversation_id,
            Line.tenant_id == tenant_id
        )
        result = await self.db.execute(stmt)
        conversation = result.scalar_one_or_none()

        if not conversation:
            raise ValueError("Conversation not found or access denied")

        # Create message record
        new_message = Message(
            conversation_id=conversation_id,
            direction=MessageDirection.outbound,
            status=MessageStatus.sent,
            text=message.get("text"),
            raw_content=message
        )

        self.db.add(new_message)
        await self.db.commit()
        await self.db.refresh(new_message)

        # Update conversation updated_at
        from sqlalchemy import update
        from datetime import datetime, timezone
        update_stmt = update(Conversation).where(
            Conversation.id == conversation_id
        ).values(updated_at=datetime.now(timezone.utc))
        await self.db.execute(update_stmt)
        await self.db.commit()

        return {
            "id": new_message.id,
            "conversation_id": str(new_message.conversation_id),
            "direction": new_message.direction.value,
            "status": new_message.status.value,
            "text": new_message.text,
            "created_at": new_message.created_at.isoformat(),
            "raw_content": new_message.raw_content
        }

    async def get_subscribed_users(self, conversation_id: uuid.UUID) -> List[uuid.UUID]:
        """Get list of users subscribed to conversation"""
        return self.subscriptions.get(conversation_id, [])

    async def unsubscribe_from_conversation(
            self,
            conversation_id: uuid.UUID,
            user_id: uuid.UUID
    ):
        """Unsubscribe user from conversation"""
        if conversation_id in self.subscriptions:
            if user_id in self.subscriptions[conversation_id]:
                self.subscriptions[conversation_id].remove(user_id)

            if not self.subscriptions[conversation_id]:
                del self.subscriptions[conversation_id]