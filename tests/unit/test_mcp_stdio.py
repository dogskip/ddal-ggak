"""The byte guard bounds allocation before handing a frame to the SDK."""

import io

import pytest

from ddk.models.verified_change import MAX_RECORD_BYTES, ContractError
from ddk.security.mcp_stdio import BoundedStdin


class ObservedBytes(io.BytesIO):
    def __init__(self, payload):
        super().__init__(payload)
        self.sizes = []

    def readline(self, size=-1):
        self.sizes.append(size)
        return super().readline(size)


async def test_bounded_reader_accepts_exact_byte_limit_and_eof():
    body = b"{}" + b" " * (MAX_RECORD_BYTES - 2)
    source = ObservedBytes(body + b"\n")
    guard = BoundedStdin(source)
    assert await anext(guard) == body.decode() + "\n"
    with pytest.raises(StopAsyncIteration):
        await anext(guard)
    assert source.sizes == [MAX_RECORD_BYTES + 2, MAX_RECORD_BYTES + 2]


async def test_oversized_line_does_not_read_or_allocate_its_remaining_bytes():
    source = ObservedBytes(b"{}" + b" " * (MAX_RECORD_BYTES * 3) + b"\n")
    with pytest.raises(ContractError, match="record_size_limit"):
        await anext(BoundedStdin(source))
    assert source.tell() == MAX_RECORD_BYTES + 2
    assert source.sizes == [MAX_RECORD_BYTES + 2]
