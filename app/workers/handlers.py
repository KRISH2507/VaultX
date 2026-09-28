import logging
from typing import Any, Dict
from app.models.outbox import OutboxEvent
from app.workers.outbox_processor import register_handler

logger = logging.getLogger("vaultx.audit")


@register_handler("TRANSACTION_COMMITTED")
async def handle_transaction_committed(payload: Dict[str, Any], event: OutboxEvent) -> None:
    """
    Consumer triggered when a double-entry transaction is successfully committed.
    Generates compliance audit record and prepares downstream webhook notifications.
    """
    logger.info(
        "[AUDIT TRAIL] Tx %s: Transferred %s %s from Account %s to Account %s. IdempotencyKey: %s",
        payload.get("transaction_id"),
        payload.get("amount"),
        payload.get("currency"),
        payload.get("source_account_id"),
        payload.get("destination_account_id"),
        payload.get("idempotency_key"),
    )


@register_handler("FUNDS_DEPOSITED")
async def handle_funds_deposited(payload: Dict[str, Any], event: OutboxEvent) -> None:
    """
    Consumer triggered when funds are deposited into an account.
    """
    logger.info(
        "[AUDIT TRAIL] Deposit %s: Credited %s to Account %s. New Balance: %s",
        payload.get("transaction_id"),
        payload.get("amount"),
        payload.get("account_id"),
        payload.get("balance_after"),
    )
