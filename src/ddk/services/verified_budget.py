"""Durable, case-serialized authorization for exactly one provider attempt."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import stat
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypeGuard
from urllib.parse import urlsplit

from ddk.adapters.llm.model_traits import known_model_names
from ddk.models.verified_change import (
    MAX_RECORD_BYTES,
    Record,
    canonical_json,
    decode_json,
    parse_record,
)
from ddk.services.durable_files import OwnedLock, read_regular
from ddk.services.verified_change_store import VerifiedChangeStore

_MAX_INTEGER = 2**53 - 1
_VERSION = "linear-tokens-v1"


class BudgetError(ValueError):
    """A request cannot be authorized without weakening its fixed limits."""


@dataclass(frozen=True)
class VerifiedPrice:
    """Explicit caller-verified maximum prices; no implicit price lookup occurs."""

    provider: str
    model: str
    input_micro_usd_per_million: int
    output_micro_usd_per_million: int
    extra_max_micro_usd: int
    source_url: str
    verified_at: str
    evaluator_sha256: str


@dataclass(frozen=True)
class ProviderUsage:
    """Observed usage; None means unobserved, including for extra charges."""

    input_tokens: int | None
    output_tokens: int | None
    extra_micro_usd: int | None


@dataclass(frozen=True)
class ProviderResult:
    value: Any
    usage: ProviderUsage | None
    provider: str
    model: str


@dataclass(frozen=True)
class BudgetCallOutcome:
    """blocked returns a final run_record; callers must not complete it again."""

    run_record: Record
    value: Any
    call_record: Record
    blocked: bool


def _now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _integer(value: object) -> TypeGuard[int]:
    return type(value) is int and 0 <= value <= _MAX_INTEGER


def _exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _cost(price: VerifiedPrice, input_tokens: int, output_tokens: int, extra: int) -> int:
    numerator = (
        input_tokens * price.input_micro_usd_per_million
        + output_tokens * price.output_micro_usd_per_million
    )
    return (numerator + 999_999) // 1_000_000 + extra


def _verify_price(price: VerifiedPrice, evaluator_sha256: str) -> None:
    try:
        url = urlsplit(price.source_url)
        verified = datetime.fromisoformat(price.verified_at.replace("Z", "+00:00"))
        valid = (
            price.provider == "anthropic"
            and price.model in known_model_names()
            and all(
                _integer(value)
                for value in (
                    price.input_micro_usd_per_million,
                    price.output_micro_usd_per_million,
                    price.extra_max_micro_usd,
                )
            )
            and url.scheme == "https"
            and bool(url.hostname)
            and url.username is None
            and url.password is None
            and not url.fragment
            and price.verified_at.endswith("Z")
            and verified.utcoffset() is not None
            and price.evaluator_sha256 == evaluator_sha256
        )
    except (AttributeError, TypeError, ValueError):
        valid = False
    if not valid:
        raise BudgetError("price_unavailable")


class RunBudget:
    """One fresh run's lifetime; never resume or reset its monotonic allowance."""

    _store: VerifiedChangeStore
    _run_id: str
    _case: Record
    _clock_ns: Callable[[], int]
    _last_ns: int
    _deadline_ns: int
    _started_ns: int
    _started_utc: datetime
    _code_sha256: str
    _poisoned: bool

    def __init__(self) -> None:
        raise TypeError("use_RunBudget_start")

    @classmethod
    def start(
        cls,
        store: VerifiedChangeStore,
        prepared_run: Record,
        *,
        clock_ns: Callable[[], int] = time.monotonic_ns,
        started_ns: int | None = None,
    ) -> RunBudget:
        now = clock_ns()
        started = now if started_ns is None else started_ns
        if type(started) is not int or not 0 <= started <= now:
            raise BudgetError("monotonic_clock_invalid")
        started_utc = datetime.now(UTC) - timedelta(microseconds=(now - started) // 1000)
        if prepared_run.get("operation") not in {"repair", "generation"} or prepared_run.get(
            "model_calls"
        ):
            raise BudgetError("fresh_model_run_required")
        record, created = store.claim_run(prepared_run)
        if not created:
            raise BudgetError("budget_resume_forbidden")
        value = object.__new__(cls)
        value._store = store
        value._run_id = record["run_id"]
        value._case = store.case(record["case_id"])
        value._clock_ns = clock_ns
        value._last_ns = now
        value._deadline_ns = started + value._case["limits"]["run_timeout_ms"] * 1_000_000
        value._started_ns = started
        value._started_utc = started_utc
        value._code_sha256 = hashlib.sha256(
            read_regular(Path(__file__).resolve(strict=True), MAX_RECORD_BYTES)
        ).hexdigest()
        value._poisoned = False
        return value

    @property
    def deadline_ns(self) -> int:
        """The fixed deadline shared by preparation, provider and verification."""
        return self._deadline_ns

    @property
    def record(self) -> Record:
        """Authoritative pending or final record, including engine-added rounds."""
        if _exists(self._store.path_for("run", self._run_id) / "run.json"):
            return self._store.run(self._run_id)
        return self._store.pending_run(self._run_id)

    def _time(self) -> int:
        now = self._clock_ns()
        if now < self._last_ns:
            raise BudgetError("monotonic_clock_invalid")
        self._last_ns = now
        return now

    def _remaining(self, step_deadline: int) -> float:
        now = self._time()
        if now >= self._deadline_ns:
            raise BudgetError("run_timeout")
        if now >= step_deadline:
            raise BudgetError("step_timeout")
        return (min(self._deadline_ns, step_deadline) - now) / 1_000_000_000

    def _load_history(self, directory: Path) -> Record:
        # A missing referenced file is corruption, never evidence of a missing manifest.
        completed_exists = _exists(directory / "run.json")
        pending_exists = _exists(directory / ".pending/run.json")
        if not completed_exists and not pending_exists:
            raise ValueError("orphan_run")
        pending = self._store.pending_run(directory.name) if pending_exists else None
        completed = self._store.run(directory.name) if completed_exists else None
        if completed is not None and pending is not None:
            immutable = ("case_id", "case_sha256", "request_sha256", "operation", "source_run_id")
            if any(completed[key] != pending[key] for key in immutable):
                raise ValueError("history_identity_changed")
            calls = {c["call_id"]: c for c in completed["model_calls"]}
            for previous in pending["model_calls"]:
                current = calls.get(previous["call_id"])
                if (
                    current is None
                    or any(
                        previous[key] != current[key]
                        for key in (
                            "attempt_no",
                            "provider",
                            "model",
                            "price_artifact_id",
                            "reserved_micro_usd",
                            "created_at",
                            "round_no",
                        )
                    )
                    or (previous["state"] != "reserved" and current != previous)
                ):
                    raise ValueError("history_reservation_changed")
            artifacts = {a["artifact_id"]: a for a in completed["artifacts"]}
            if any(artifacts.get(a["artifact_id"]) != a for a in pending["artifacts"]):
                raise ValueError("history_artifact_changed")
        record = completed if completed is not None else pending
        assert record is not None
        if record["case_id"] == self._case["case_id"]:
            self._audit_price_files(directory, record)
        return record

    def _artifact_json(self, record: Record, artifact_id: str) -> Record:
        artifact = next(a for a in record["artifacts"] if a["artifact_id"] == artifact_id)
        payload = read_regular(
            self._store.path_for("run", record["run_id"]) / artifact["path"],
            min(MAX_RECORD_BYTES, artifact["size_bytes"]),
        )
        value = decode_json(payload)
        if canonical_json(value) != payload:
            raise ValueError("noncanonical_budget_artifact")
        return value

    def _audit_price_files(self, directory: Path, record: Record) -> None:
        prices = directory / "artifacts/prices"
        if _exists(prices):
            if not stat.S_ISDIR(prices.lstat().st_mode):
                raise ValueError("invalid_price_directory")
            declared = {a["path"] for a in record["artifacts"] if a["kind"] == "price"}
            for path in prices.iterdir():
                if path.relative_to(directory).as_posix() not in declared:
                    raise ValueError("orphan_price")
        for call in record["model_calls"]:
            fixed = self._artifact_json(record, call["price_artifact_id"])
            price = VerifiedPrice(**fixed["price"])
            _verify_price(price, record["evaluator_sha256"])
            if (
                fixed["pricing_model"] != _VERSION
                or fixed["call_id"] != call["call_id"]
                or price.provider != call["provider"]
                or price.model != call["model"]
                or not all(_integer(fixed[key]) for key in ("input_limit", "output_limit"))
                or not isinstance(fixed["budget_code_sha256"], str)
                or len(fixed["budget_code_sha256"]) != 64
                or _cost(
                    price, fixed["input_limit"], fixed["output_limit"], price.extra_max_micro_usd
                )
                != call["reserved_micro_usd"]
            ):
                raise ValueError("invalid_price_reservation")
            if call["state"] == "settled":
                observed = self._artifact_json(record, "usage-" + call["call_id"])
                usage = ProviderUsage(**observed["usage"])
                assert usage.input_tokens is not None
                assert usage.output_tokens is not None
                assert usage.extra_micro_usd is not None
                if (
                    observed["call_id"] != call["call_id"]
                    or observed["provider"] != price.provider
                    or observed["model"] != price.model
                    or not all(_integer(v) for v in asdict(usage).values())
                    or usage.input_tokens != call["input_tokens"]
                    or usage.output_tokens != call["output_tokens"]
                    or observed["calculated_micro_usd"] != call["calculated_micro_usd"]
                    or _cost(price, usage.input_tokens, usage.output_tokens, usage.extra_micro_usd)
                    != call["calculated_micro_usd"]
                ):
                    raise ValueError("invalid_usage_settlement")

    def _audit(self) -> None:
        try:
            for directory in (self._store.base_path / "runs").iterdir():
                if not stat.S_ISDIR(directory.lstat().st_mode):
                    raise ValueError("invalid_run_directory")
                record = self._load_history(directory)
                if record["case_id"] == self._case["case_id"] and any(
                    c["state"] != "settled" for c in record["model_calls"]
                ):
                    raise BudgetError("cost_unknown")
        except BudgetError:
            raise
        except (ValueError, OSError, KeyError, TypeError, StopIteration) as error:
            raise BudgetError("budget_history_invalid") from error

    async def _acquire(self, deadline: int) -> OwnedLock:
        path = self._store.base_path / f"locks/model/{self._case['case_id']}.lock"
        while True:
            self._remaining(deadline)
            lock = OwnedLock(path, self._run_id)
            try:
                lock.acquire()
            except FileExistsError:
                try:
                    payload = read_regular(path, 4096)
                except FileNotFoundError:
                    continue
                try:
                    previous = parse_record(payload)
                    if (
                        previous["record_type"] != "lock"
                        or canonical_json(previous) != payload
                        or stat.S_IMODE(path.lstat().st_mode) != 0o600
                    ):
                        raise ValueError("invalid_model_lock")
                    owner_path = self._store.path_for("run", previous["owner_run_id"])
                    owner = self._load_history(owner_path)
                    if owner["case_id"] != self._case["case_id"]:
                        raise ValueError("lock_case_mismatch")
                except (ValueError, OSError, KeyError, TypeError, StopIteration) as error:
                    raise BudgetError("budget_history_invalid") from error
                await asyncio.sleep(min(0.01, self._remaining(deadline)))
                continue
            return lock

    def _payloads(self, record: Record) -> dict[str, bytes]:
        return {
            a["path"]: read_regular(
                self._store.path_for("run", self._run_id) / a["path"], a["size_bytes"]
            )
            for a in record["artifacts"]
        }

    @staticmethod
    def _artifact(artifact_id: str, kind: str, path: str, payload: bytes) -> Record:
        return {
            "artifact_id": artifact_id,
            "kind": kind,
            "path": path,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
            "sensitive": True,
            "public_export_allowed": False,
        }

    def _save(self, record: Record) -> None:
        record["duration_ms"] = max(0, (self._time() - self._started_ns) // 1_000_000)
        self._store.save_pending(record)

    @staticmethod
    def _block(record: Record, code: str) -> None:
        record["decision"] = "blocked"
        record["actions"].append(
            {"code": code, "target": None, "message": code, "retryable": False}
        )

    def _unknown(self, record: Record, call: Record) -> None:
        call["state"] = "unknown"
        call["completed_at"] = _now_utc()
        self._save(record)

    async def call(
        self,
        round_no: int,
        *,
        price: VerifiedPrice,
        input_limit: int,
        output_limit: int,
        provider: Callable[[], Awaitable[ProviderResult]],
    ) -> BudgetCallOutcome:
        """Reserve before one callback; blocked returns an already completed run.

        The callback must make one HTTP attempt and report explicit observed usage.
        Exceptions/cancellation preserve the reservation and are never retried here.
        """
        if self._poisoned:
            raise BudgetError("budget_history_invalid")
        deadline = self._time() + self._case["limits"]["step_timeout_ms"] * 1_000_000
        self._remaining(deadline)
        _verify_price(price, self._case["evaluator_sha256"])
        if not _integer(input_limit) or not _integer(output_limit):
            raise BudgetError("price_unavailable")
        reserved = _cost(price, input_limit, output_limit, price.extra_max_micro_usd)
        if not _integer(reserved):
            raise BudgetError("price_unavailable")
        lock = await self._acquire(deadline)
        uncertain = False
        try:
            self._audit()
            self._remaining(deadline)
            record = copy.deepcopy(self.record)
            if record["status"] not in {"prepared", "running"} or record["decision"] == "blocked":
                raise BudgetError("budget_blocked")
            limits = self._case["limits"]
            if (
                round_no not in {r["round_no"] for r in record["rounds"]}
                or not 0 <= round_no <= limits["max_fix_attempts"]
            ):
                raise BudgetError("fix_limit")
            if len(record["model_calls"]) >= limits["max_provider_requests"]:
                raise BudgetError("request_limit")
            held = sum(
                c["calculated_micro_usd"] if c["state"] == "settled" else c["reserved_micro_usd"]
                for c in record["model_calls"]
            )
            if held + reserved > limits["budget_micro_usd"]:
                raise BudgetError("cost_reservation_limit")
            call_id = str(uuid.uuid4())
            price_id = "price-" + call_id
            fixed = canonical_json(
                {
                    "pricing_model": _VERSION,
                    "call_id": call_id,
                    "price": asdict(price),
                    "input_limit": input_limit,
                    "output_limit": output_limit,
                    "budget_code_sha256": self._code_sha256,
                }
            )
            payloads = self._payloads(record)
            artifact = self._artifact(price_id, "price", f"artifacts/prices/{call_id}.json", fixed)
            record["artifacts"].append(artifact)
            payloads[artifact["path"]] = fixed
            call = {
                "call_id": call_id,
                "attempt_no": len(record["model_calls"]) + 1,
                "provider": price.provider,
                "model": price.model,
                "price_artifact_id": price_id,
                "state": "reserved",
                "reserved_micro_usd": reserved,
                "calculated_micro_usd": None,
                "input_tokens": None,
                "output_tokens": None,
                "created_at": _now_utc(),
                "completed_at": None,
                "round_no": round_no,
            }
            record["model_calls"].append(call)
            record["status"] = "running"
            self._remaining(deadline)
            uncertain = True
            self._store.stage_artifacts(record, payloads)
            self._save(record)
            # Read back the manifest and all referenced files before permitting HTTP.
            if self.record != record:
                raise ValueError("reservation_readback_mismatch")
            remaining = self._remaining(deadline)
            try:
                async with asyncio.timeout(remaining):
                    response = await provider()
            except TimeoutError as error:
                self._unknown(record, call)
                uncertain = False
                code = "run_timeout" if self._time() >= self._deadline_ns else "step_timeout"
                raise BudgetError(code) from error
            except (Exception, asyncio.CancelledError):
                self._unknown(record, call)
                uncertain = False
                raise
            usage = response.usage
            complete = (
                isinstance(usage, ProviderUsage)
                and all(_integer(v) for v in asdict(usage).values())
                and response.provider == price.provider
                and response.model == price.model
            )
            calculated: int | None = None
            if complete:
                assert usage is not None
                assert (
                    usage.input_tokens is not None
                    and usage.output_tokens is not None
                    and usage.extra_micro_usd is not None
                )
                calculated = _cost(
                    price, usage.input_tokens, usage.output_tokens, usage.extra_micro_usd
                )
                if not _integer(calculated):
                    self._block(record, "cost_reservation_exceeded")
                    call.update(
                        state="unknown",
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                        completed_at=_now_utc(),
                    )
                else:
                    call.update(
                        state="settled",
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                        calculated_micro_usd=calculated,
                        completed_at=_now_utc(),
                    )
                    if calculated > reserved:
                        self._block(record, "cost_reservation_exceeded")
            else:
                call.update(
                    state="unknown",
                    input_tokens=usage.input_tokens
                    if isinstance(usage, ProviderUsage) and _integer(usage.input_tokens)
                    else None,
                    output_tokens=usage.output_tokens
                    if isinstance(usage, ProviderUsage) and _integer(usage.output_tokens)
                    else None,
                    completed_at=_now_utc(),
                )
            if isinstance(usage, ProviderUsage) and any(
                _integer(value) and value > limit
                for value, limit in (
                    (usage.input_tokens, input_limit),
                    (usage.output_tokens, output_limit),
                    (usage.extra_micro_usd, price.extra_max_micro_usd),
                )
            ):
                self._block(record, "provider_request_limit_exceeded")
            observed = canonical_json(
                {
                    "call_id": call_id,
                    "provider": getattr(response, "provider", None),
                    "model": getattr(response, "model", None),
                    "calculated_micro_usd": calculated,
                    "usage": asdict(usage) if isinstance(usage, ProviderUsage) else None,
                }
            )
            usage_artifact = self._artifact(
                "usage-" + call_id, "log", f"artifacts/usage/{call_id}.json", observed
            )
            record["artifacts"].append(usage_artifact)
            payloads[usage_artifact["path"]] = observed
            if self._time() >= min(deadline, self._deadline_ns):
                self._block(
                    record, "run_timeout" if self._time() >= self._deadline_ns else "step_timeout"
                )
            if record["decision"] == "blocked":
                elapsed = self._time() - self._started_ns
                record.update(
                    status="completed",
                    duration_ms=elapsed // 1_000_000,
                    finished_at=(self._started_utc + timedelta(microseconds=elapsed // 1000))
                    .isoformat()
                    .replace("+00:00", "Z"),
                )
                self._store.publish_run(record, payloads)
            else:
                self._store.stage_artifacts(record, payloads)
                self._save(record)
            if self.record != record:
                raise ValueError("settlement_readback_mismatch")
            uncertain = False
            return BudgetCallOutcome(
                copy.deepcopy(record),
                getattr(response, "value", None),
                copy.deepcopy(call),
                record["decision"] == "blocked",
            )
        finally:
            if uncertain:
                self._poisoned = True
                lock.leave_locked()
            else:
                lock.release()
