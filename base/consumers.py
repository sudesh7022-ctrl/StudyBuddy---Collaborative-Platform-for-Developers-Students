# base/consumers.py
import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model

from base.models import Message, Room
from studybud.utils.toxicity_checker import toxicity_checker

logger = logging.getLogger(__name__)
User = get_user_model()


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """
        Called when the websocket is handshaking as part of initial connection.
        """
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'chat_{self.room_id}'
        self.user = self.scope.get("user")  # Logged-in user (may be AnonymousUser)

        # Join room group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # Notify others this user joined (preserve original behavior)
        if self.user and getattr(self.user, "is_authenticated", False):
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "user_join",
                    "username": self.user.username,
                }
            )

    async def disconnect(self, close_code):
        """
        Called when the WebSocket closes for any reason.
        """
        # Notify others this user left
        if self.user and getattr(self.user, "is_authenticated", False):
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "user_leave",
                    "username": self.user.username,
                }
            )

        # Leave room group
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        """
        Receive message from WebSocket.
        Expects JSON payload with keys: message, username, room, temp_id (optional)
        """
        try:
            data = json.loads(text_data)
        except Exception:
            logger.exception("Failed to decode incoming websocket data: %s", text_data)
            return

        logger.debug("[WebSocket] Received: %s", data)

        message = data.get('message', '')
        if message is None:
            message = ''
        message = str(message).strip()

        username = data.get('username')
        room_id = data.get('room')
        temp_id = data.get('temp_id')

        if not message:
            # nothing to send
            return

        # ------------- TOXICITY SANITIZATION (ML + rules) -------------
        # sanitize() returns (filtered_text, was_toxic_bool)
        try:
            filtered_message, was_toxic = toxicity_checker.sanitize(message)
        except Exception as e:
            # In case of unexpected error in sanitizer, fall back to original message
            logger.exception("Error during toxicity sanitization: %s", e)
            filtered_message, was_toxic = message, False

        if was_toxic:
            # Send a blocked alert only to the sender, never include the original toxic message.
            # Include temp_id so frontend can match the alert to the pending message.
            try:
                await self.send(text_data=json.dumps({
                    'type': 'blocked',
                    'message': 'Your message contained toxic content and was blocked or censored.',
                    'temp_id': temp_id,
                    # optional: sanitized version (either masked or removal string)
                    'sanitized': filtered_message
                }))
            except Exception:
                logger.exception("Failed to send blocked alert to sender for temp_id=%s", temp_id)
            # Proceed to store/broadcast the sanitized content (so the room never sees toxic words)
            message_to_store = filtered_message
        else:
            message_to_store = filtered_message

        # Save to DB and broadcast sanitized message
        await self.save_message(username, room_id, message_to_store)

        # Broadcast message to group (sanitized)
        try:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message_to_store,
                    'username': username,
                    'temp_id': temp_id,
                }
            )
        except Exception:
            logger.exception("Failed to group_send message for room %s", self.room_group_name)

    async def chat_message(self, event):
        """
        Handler for messages sent to the room group.
        Broadcasts the message to the websocket client.
        """
        logger.debug("[WebSocket] Broadcasting to clients: %s", event)
        message = event.get('message', '')
        username = event.get('username')

        # Resolve avatar_url (best-effort; fall back to default)
        avatar_url = '/static/images/default.png'
        if username:
            try:
                user = await database_sync_to_async(User.objects.get)(username=username)
                avatar_url = user.avatar.url if getattr(user, 'avatar', None) else avatar_url
            except Exception:
                # Keep default avatar if user lookup fails
                logger.debug("Could not resolve avatar for username=%s", username)

        payload = {
            'type': 'message',
            'message': message,
            'username': username,
            'avatar_url': avatar_url,
        }

        try:
            await self.send(text_data=json.dumps(payload))
        except Exception:
            logger.exception("Failed to send chat message payload to client: %s", payload)

    async def user_join(self, event):
        """
        Send notification when a user joins the room group.
        """
        logger.debug("[WebSocket] Sending JOIN event for %s", event.get('username'))
        await self.send(text_data=json.dumps({
            "type": "user_join",
            "username": event.get("username")
        }))

    async def user_leave(self, event):
        """
        Send notification when a user leaves the room group.
        """
        logger.debug("[WebSocket] Sending LEAVE event for %s", event.get('username'))
        await self.send(text_data=json.dumps({
            "type": "user_leave",
            "username": event.get("username")
        }))

    @database_sync_to_async
    def save_message(self, username, room_id, message):
        """
        Save message to database. This runs in a threadpool via database_sync_to_async.
        """
        try:
            if not username or not room_id:
                logger.debug("save_message called with missing username or room_id. username=%s room_id=%s", username, room_id)
                return

            user = User.objects.get(username=username)
            room = Room.objects.get(id=room_id)
            Message.objects.create(user=user, room=room, body=message)
        except Exception as e:
            # keep function quiet in production but log the exception for debugging
            logger.exception("[WebSocket] Error saving message: %s", e)
