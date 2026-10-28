"""Small compatibility helpers for python-telegram-bot API changes.

python-telegram-bot 21+ removed ``Message.forward_from_chat`` and
``Message.forward_from_message_id`` (replaced by ``Message.forward_origin``).
These helpers work on both old and new versions.
"""


def get_forward_chat(msg):
    """Return ``(chat, message_id)`` of the original forwarded channel/chat message.

    Both values are ``None`` when the message is not a forward from a chat/channel.
    """
    if msg is None:
        return None, None

    origin = getattr(msg, "forward_origin", None)
    if origin is not None:
        chat = getattr(origin, "chat", None) or getattr(origin, "sender_chat", None)
        return chat, getattr(origin, "message_id", None)

    # python-telegram-bot < 21 fallback
    return getattr(msg, "forward_from_chat", None), getattr(msg, "forward_from_message_id", None)
