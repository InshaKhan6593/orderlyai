"""Proactive WhatsApp notifications to customers (order status updates).

The in-chat agent already confirms an order while the customer is messaging. This module
covers the *other* direction: when the owner advances an order in the dashboard (accepted →
preparing → ready/out_for_delivery → completed), tell the customer on WhatsApp.

Meta's rule: free-form messages are only allowed within 24h of the customer's last inbound
message. Inside that window we send plain text; outside it, only a pre-approved *template*
may be sent (configured via ``whatsapp_order_status_template`` — skipped with a log line if
unset). Notifications are best-effort and run in the background: a send failure (or a missing
WhatsApp connection) never affects the dashboard API response.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.crypto import decrypt_secret
from app.core.db import SessionLocal
from app.models.customer import Customer
from app.models.order import Order
from app.models.whatsapp import WhatsAppConnection
from app.services import whatsapp_service

logger = logging.getLogger(__name__)

# Customer-facing copy per status. `pending` is the initial state (no notification); the keys
# here mirror order_service.TRANSITIONS targets.
_STATUS_MESSAGES: dict[str, str] = {
    "accepted": "Good news! Your order #{no} has been accepted and will be prepared shortly.",
    "preparing": "Your order #{no} is now being prepared.",
    "ready": "Your order #{no} is ready for pickup!",
    "out_for_delivery": "Your order #{no} is out for delivery.",
    "completed": "Your order #{no} is complete. Thank you for ordering!",
    "rejected": "Sorry, we couldn't accept your order #{no}. Please message us for help.",
    "cancelled": "Your order #{no} has been cancelled.",
}


def _window_open(last_inbound_at: datetime | None) -> bool:
    """Whether we're still inside Meta's 24h free-form messaging window."""
    if last_inbound_at is None:
        return False
    if last_inbound_at.tzinfo is None:
        last_inbound_at = last_inbound_at.replace(tzinfo=timezone.utc)
    horizon = timedelta(hours=settings.whatsapp_customer_window_hours)
    return datetime.now(timezone.utc) - last_inbound_at <= horizon


async def _deliver(
    *,
    connection: WhatsAppConnection,
    to: str,
    in_window: bool,
    body: str,
    template_name: str | None,
    template_components: list | None,
) -> bool:
    """Send a free-form text inside the 24h window, else a template (if one is configured)."""
    token = decrypt_secret(connection.access_token)
    if in_window:
        result = await whatsapp_service.send_text(
            phone_number_id=connection.phone_number_id,
            access_token=token,
            to=to,
            body=body,
        )
        return bool(result)
    if template_name:
        result = await whatsapp_service.send_template(
            phone_number_id=connection.phone_number_id,
            access_token=token,
            to=to,
            template_name=template_name,
            components=template_components,
        )
        return bool(result)
    logger.info(
        "Skipping out-of-window notification to %s (no template configured)", to
    )
    return False


async def notify_order_status(business_id, order_id) -> bool:
    """Notify the customer that their order's status changed. Best-effort; opens its own session.

    Safe to call as a background task: returns False (no raise) when there's no WhatsApp
    connection, no message for the status, or the send fails.
    """
    try:
        async with SessionLocal() as db:
            order = await db.scalar(
                select(Order).where(Order.id == order_id, Order.business_id == business_id)
            )
            if order is None:
                return False
            body_tmpl = _STATUS_MESSAGES.get(order.status)
            if not body_tmpl:
                return False

            customer = await db.get(Customer, order.customer_id)
            if customer is None or not customer.wa_phone:
                return False

            connection = await db.scalar(
                select(WhatsAppConnection).where(
                    WhatsAppConnection.business_id == business_id
                )
            )
            if connection is None or not connection.access_token:
                return False

            body = body_tmpl.format(no=order.order_no)
            in_window = _window_open(customer.last_inbound_at)
            components = (
                [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": str(order.order_no)},
                            {"type": "text", "text": order.status.replace("_", " ")},
                        ],
                    }
                ]
                if settings.whatsapp_order_status_template
                else None
            )
            return await _deliver(
                connection=connection,
                to=customer.wa_phone,
                in_window=in_window,
                body=body,
                template_name=settings.whatsapp_order_status_template,
                template_components=components,
            )
    except Exception:  # noqa: BLE001 — notifications never break the calling request
        logger.exception("Order status notification failed for order %s", order_id)
        return False
