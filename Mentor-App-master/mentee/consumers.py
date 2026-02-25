import json
import time
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.serializers.json import DjangoJSONEncoder
from django.contrib.auth import get_user_model

from .models import Reply, Reaction, ReplySeen

User = get_user_model()


class ChatConsumer(AsyncWebsocketConsumer):
    """
    Production-grade WebSocket consumer for chat:
    - Authenticated users only
    - Conversation-level authorization
    - Presence, typing, reactions, seen
    - HTTP creates messages, WS broadcasts only
    """

    # -----------------------
    # CONNECT / DISCONNECT
    # -----------------------

    async def connect(self):
        self.accepted = False  # safety flag

        try:
            # --- AUTH CHECK ---
            user = self.scope.get("user")
            if not user or not user.is_authenticated:
                await self.close(code=4003)
                return

            # --- URL PARAM ---
            self.conv_id = self.scope["url_route"]["kwargs"].get("conv_id")
            if not self.conv_id:
                await self.close(code=4001)
                return

            # --- AUTHORIZATION CHECK ---
            allowed = await self.user_allowed_in_conversation(user.id, self.conv_id)
            if not allowed:
                await self.close(code=4003)
                return

            self.room_group_name = f"conversation_{self.conv_id}"

            # --- JOIN GROUP ---
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )

            # --- ACCEPT SOCKET ---
            await self.accept()
            self.accepted = True

            # --- PRESENCE JOIN ---
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "presence",
                    "user_id": user.id,
                    "username": getattr(user, "username", ""),
                    "joined": True,
                }
            )

        except Exception as e:
            print("WebSocket connect error:", e)
            await self.close(code=4002)

    async def disconnect(self, close_code):
        if not getattr(self, "accepted", False):
            return

        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

            user = self.scope.get("user")
            if user and user.is_authenticated:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "presence",
                        "user_id": user.id,
                        "username": getattr(user, "username", ""),
                        "joined": False,
                    }
                )

    # -----------------------
    # RECEIVE
    # -----------------------

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return

        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.close(code=4000)
            return

        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            return

        action = data.get("action")

        # ---- TYPING (throttled) ----
        if action == "typing":
            now = time.time()
            if hasattr(self, "_last_typing") and now - self._last_typing < 0.8:
                return
            self._last_typing = now

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "typing",
                    "user_id": user.id,
                    "username": getattr(user, "username", ""),
                    "typing": bool(data.get("typing", False)),
                }
            )

        # ---- SEEN ----
        elif action == "seen":
            reply_id = data.get("reply_id")
            if reply_id:
                saved = await self.mark_seen(reply_id, user.id)
                if saved:
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            "type": "seen_event",
                            "reply_id": reply_id,
                            "user_id": user.id,
                        }
                    )

        # ---- REACTION ----
        elif action == "reaction":
            reply_id = data.get("reply_id")
            emoji = data.get("emoji")

            if reply_id and emoji:
                reaction = await self.add_reaction(reply_id, user.id, emoji)
                if reaction:
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            "type": "reaction_event",
                            "reply_id": reply_id,
                            "user_id": user.id,
                            "emoji": emoji,
                        }
                    )

    # -----------------------
    # GROUP EVENT HANDLERS
    # -----------------------

    async def typing(self, event):
        await self.send_json({
            "action": "typing",
            "user_id": event["user_id"],
            "username": event["username"],
            "typing": event["typing"],
        })

    async def new_message(self, event):
        await self.send_json({
            "action": "new_message",
            "message": event["message"],
        })

    async def seen_event(self, event):
        await self.send_json({
            "action": "seen_event",
            "reply_id": event["reply_id"],
            "user_id": event["user_id"],
        })

    async def reaction_event(self, event):
        await self.send_json({
            "action": "reaction",
            "reply_id": event["reply_id"],
            "user_id": event["user_id"],
            "emoji": event["emoji"],
        })

    async def presence(self, event):
        await self.send_json({
            "action": "presence",
            "user_id": event["user_id"],
            "username": event["username"],
            "joined": event["joined"],
        })

    async def edited_message(self, event):
        await self.send_json({
            "action": "edited_message",
            "message": event["message"],
        })

    async def deleted_message(self, event):
        await self.send_json({
            "action": "deleted_message",
            "message": event["message"],
        })

    # -----------------------
    # DB HELPERS
    # -----------------------

    @database_sync_to_async
    def user_allowed_in_conversation(self, user_id, conv_id):
        """
        Authorization check.
        Adjust logic if you have a Conversation/Members table.
        """
        return Reply.objects.filter(
            conversation_id=conv_id,
            sender_id=user_id
        ).exists()

    @database_sync_to_async
    def mark_seen(self, reply_id, user_id):
        try:
            reply = Reply.objects.get(pk=reply_id)
            user = User.objects.get(pk=user_id)
            ReplySeen.objects.get_or_create(reply=reply, user=user)
            return True
        except Exception:
            return False

    @database_sync_to_async
    def add_reaction(self, reply_id, user_id, emoji):
        try:
            reply = Reply.objects.get(pk=reply_id)
            user = User.objects.get(pk=user_id)
            reaction, _ = Reaction.objects.update_or_create(
                reply=reply,
                user=user,
                defaults={"emoji": emoji}
            )
            return reaction
        except Exception:
            return None

    # -----------------------
    # SEND JSON HELPER
    # -----------------------

    async def send_json(self, payload):
        await self.send(
            text_data=json.dumps(payload, cls=DjangoJSONEncoder)
        )
