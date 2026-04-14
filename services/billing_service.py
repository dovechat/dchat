"""BillingService — daily charge for active lines."""
import uuid
from datetime import date
from decimal import Decimal

from models.billing import LedgerOperationType
from models.lines import LineStatus
from repo.billing_repo import (
    BalanceRepository,
    BalanceLedgerRepository,
    TariffRepository,
)
from repo.line_repo import ChannelAccountRepository, LineRepository

import logging
log = logging.getLogger("uvicorn.error")


class BillingService:

    def __init__(
        self,
        line_repo: LineRepository,
        balance_repo: BalanceRepository,
        ledger_repo: BalanceLedgerRepository,
        tariff_repo: TariffRepository,
        channel_account_repo: ChannelAccountRepository | None = None,
    ) -> None:
        self.line_repo = line_repo
        self.balance_repo = balance_repo
        self.ledger_repo = ledger_repo
        self.tariff_repo = tariff_repo
        self.channel_account_repo = channel_account_repo

    async def charge_lines(self, period: date) -> dict:
        """
        Charge all active lines for the given period date.
        Idempotent: skips lines already charged for this date.
        """
        active_lines = await self.line_repo.get_active_lines()
        results = {"charged": 0, "skipped": 0, "blocked": 0, "blocked_lines": [], "no_tariff": 0, "errors": 0}

        for line in active_lines:
            try:
                await self._charge_line(line, period, results)
            except Exception as e:
                log.error(f"Error charging line {line.id}: {e}")
                results["errors"] += 1

        log.info(f"Billing complete for {period}: {results}")
        return results

    async def _charge_line(self, line, period: date, results: dict) -> None:
        already_charged = await self.ledger_repo.charge_exists(line.id, period)
        if already_charged:
            log.debug(f"Line {line.id} already charged for {period}, skipping")
            results["skipped"] += 1
            return

        tariff = await self.tariff_repo.get_active_by_channel_type(line.channel_type.value)
        if not tariff:
            log.warning(f"No active tariff for channel_type={line.channel_type}, line {line.id}")
            results["no_tariff"] += 1
            return

        daily_amount = (Decimal(str(tariff.price)) / Decimal(str(tariff.period_days))).quantize(Decimal("0.01"))

        balance = await self.balance_repo.get_or_create(line.tenant_id)
        if balance.main_balance < daily_amount:
            await self.line_repo.update(line, status=LineStatus.disabled)
            log.warning(f"Line {line.id} blocked: required {daily_amount}, available {balance.main_balance}")
            results["blocked"] += 1
            results["blocked_lines"].append(line)
            return

        await self.balance_repo.deduct(line.tenant_id, daily_amount)
        await self.ledger_repo.add_entry(
            tenant_id=line.tenant_id,
            amount=-daily_amount,
            operation_type=LedgerOperationType.charge,
            reference_id=line.id,
            description=f"Daily charge for line '{line.name}' ({line.channel_type}), period {period}",
        )
        log.info(f"Charged {daily_amount} for line {line.id} (tenant {line.tenant_id})")
        results["charged"] += 1

    async def get_low_balance_tenants(self, warn_days: list[int]) -> list[dict]:
        log.info("\n\n !!! ----------- get_low_balance_tenants ----------- \n\n")
    
        targets = []
        balances = await self.balance_repo.get_multi(limit=10000)
    
        for balance in balances:
            log.info("\n\n !!! ----------- for balance in balances ----------- \n\n")
            try:
                daily_cost = await self.tariff_repo.get_daily_cost_by_tenant(balance.tenant_id)
                log.info("\n\n !!! ----------- daily_cost {daily_cost} ----------- \n\n")
                if daily_cost <= Decimal("0"):
                    continue
    
                total = balance.main_balance + balance.bonus_balance
                days_left = int(total / daily_cost)
                log.info("\n\n !!! ----------- tenant {tenant} total {total} daily_cost {daily_cost} days_left {days_left}----------- \n\n")
                

                log.info("\n\n ----------- DEBUG tenant=%s total=%s daily_cost=%s days_left=%s ----------- \n\n", balance.tenant_id, total, daily_cost, days_left)

                if days_left in warn_days or days_left < min(warn_days):
                    targets.append({
                        "tenant_id": balance.tenant_id,
                        "balance": total,
                        "days_left": days_left,
                    })
            except Exception as e:
                log.error("\n\n !!! ERROR --- low_balance check failed for tenant %s: %s", balance.tenant_id, e)
    
        return targets

    async def charge_channels(self, period: date) -> dict:
        """
        Charge all active channel_accounts for the given period date.
        Idempotent: skips channels already charged for this date (via ledger reference_id=line_id).
        """
        from models.lines import LineStatus
        active_lines = await self.line_repo.get_active_lines()
        results = {"charged": 0, "skipped": 0, "blocked": 0, "blocked_lines": [], "no_tariff": 0, "errors": 0}

        for line in active_lines:
            channels = await self.channel_account_repo.get_by_line(line.id)
            if not isinstance(channels, list):
                channels = [channels] if channels else []
            for channel in channels:
                try:
                    await self._charge_channel(line, channel, period, results)
                except Exception as e:
                    log.error(f"Error charging channel {channel.id} line {line.id}: {e}")
                    results["errors"] += 1

        log.info(f"Channel billing complete for {period}: {results}")
        return results

    async def _charge_channel(self, line, channel, period: date, results: dict) -> None:
        already_charged = await self.ledger_repo.charge_exists(channel.id, period)
        if already_charged:
            log.debug(f"Channel {channel.id} already charged for {period}, skipping")
            results["skipped"] += 1
            return

        tariff = await self.tariff_repo.get_active_by_channel_type(channel.channel_type.value)
        if not tariff:
            log.warning(f"No active tariff for channel_type={channel.channel_type}, channel {channel.id}")
            results["no_tariff"] += 1
            return

        daily_amount = (Decimal(str(tariff.price)) / Decimal(str(tariff.period_days))).quantize(Decimal("0.01"))

        balance = await self.balance_repo.get_or_create(line.tenant_id)
        if balance.main_balance < daily_amount:
            await self.line_repo.update(line, status=LineStatus.disabled)
            log.warning(
                f"Channel {channel.id} line {line.id} blocked: required {daily_amount}, available {balance.main_balance}")
            results["blocked"] += 1
            results["blocked_lines"].append({"tenant_id": line.tenant_id, "line_name": line.name})
            return

        await self.balance_repo.deduct(line.tenant_id, daily_amount)
        await self.ledger_repo.add_entry(
            tenant_id=line.tenant_id,
            amount=-daily_amount,
            operation_type=LedgerOperationType.charge,
            reference_id=channel.id,
            description=f"Daily charge for channel {channel.channel_type} line '{line.name}', period {period}",
        )
        log.info(f"Charged {daily_amount} for channel {channel.id} line {line.id} (tenant {line.tenant_id})")
        results["charged"] += 1