"""Outgoing email abstraction.

Stage 1 ships no email provider. In development and test the
``LogEmailSender`` writes messages to the application log so password reset can
be exercised locally. In production, without a configured provider, messages
are *not* logged (they contain secrets); a warning says delivery is unavailable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger("via_api.email")


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    body: str


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None: ...


class LogEmailSender:
    """Development sender: logs the full message (including reset links)."""

    def send(self, message: EmailMessage) -> None:
        logger.info(
            "EMAIL (development, not delivered)\nTo: %s\nSubject: %s\n\n%s", message.to, message.subject, message.body
        )


class DisabledEmailSender:
    """Production default until a provider is configured."""

    def send(self, message: EmailMessage) -> None:
        logger.warning(
            "Email delivery is not configured; message to a user was not sent (subject: %s)", message.subject
        )


@dataclass
class MemoryEmailSender:
    """Test helper: collects messages."""

    sent: list[EmailMessage] = field(default_factory=list)

    def send(self, message: EmailMessage) -> None:
        self.sent.append(message)
