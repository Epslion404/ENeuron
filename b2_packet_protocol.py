"""B2 外层 DMA 帧的冻结参考编码器/解码器。

帧内所有多字节字段均为 little-endian。该模块只负责外层完整性和固定 beat
边界，不解释 NPU 命令 opcode，也不替代核心的 8/10 beat 计数合同。
"""

from dataclasses import dataclass
from enum import IntEnum
import struct
from typing import Sequence
import zlib


MAGIC = int.from_bytes(b"ENB2", "little")
VERSION = 1
HEADER_FORMAT = "<IBBBBIIIIII"
HEADER_BYTES = struct.calcsize(HEADER_FORMAT)
CRC_BYTES = 4
MAX_FRAME_BYTES = 4096
MAX_PAYLOAD_BYTES = MAX_FRAME_BYTES - HEADER_BYTES - CRC_BYTES
HEADER_WORDS = HEADER_BYTES // 4


class MessageType(IntEnum):
    COMMAND = 1
    SAMPLE = 2
    RESPONSE = 3
    RESULT = 4


class PacketError(ValueError):
    """输入不是一个可交给下游的完整 B2 帧。"""


@dataclass(frozen=True)
class DecodedFrame:
    message_type: MessageType
    flags: int
    payload_length: int
    sequence: int
    sample_id: int
    model_id: int
    mask_epoch: int
    status: int
    payload: bytes
    words: tuple[int, ...] = ()
    beats: tuple[int, ...] = ()


def _uint32(value: int, label: str) -> int:
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
        raise ValueError(f"{label} must be a uint32")
    return value


def _pack_header(message_type: MessageType, payload_length: int, sequence: int,
                 sample_id: int, model_id: int, mask_epoch: int, status: int) -> bytes:
    if payload_length < 0 or payload_length > MAX_PAYLOAD_BYTES:
        raise ValueError("payload length exceeds 4096-byte DMA frame")
    if payload_length + HEADER_BYTES + CRC_BYTES > MAX_FRAME_BYTES:
        raise ValueError("frame length exceeds 4096 bytes")
    return struct.pack(
        HEADER_FORMAT,
        MAGIC,
        VERSION,
        int(message_type),
        0,
        HEADER_WORDS,
        payload_length,
        _uint32(sequence, "sequence"),
        _uint32(sample_id, "sample_id"),
        _uint32(model_id, "model_id"),
        _uint32(mask_epoch, "mask_epoch"),
        _uint32(status, "status"),
    )


def _finish(header: bytes, payload: bytes) -> bytes:
    frame_without_crc = header + payload
    return frame_without_crc + struct.pack("<I", zlib.crc32(frame_without_crc) & 0xFFFFFFFF)


def _encode_fixed(message_type: MessageType, values: Sequence[int], count: int,
                  sequence: int, sample_id: int, model_id: int, mask_epoch: int,
                  signed: bool = False, status: int = 0) -> bytes:
    if len(values) != count:
        raise ValueError(f"{message_type.name.lower()} requires exactly {count} beats")
    packed_values: list[int] = []
    for value in values:
        if type(value) is not int:
            raise ValueError("beat must be an integer")
        if signed:
            if not -(1 << 31) <= value < (1 << 31):
                raise ValueError("result beat must fit signed INT32")
            packed_values.append(value & 0xFFFFFFFF)
        else:
            packed_values.append(_uint32(value, "beat"))
    payload = struct.pack("<" + "I" * count, *packed_values)
    return _finish(
        _pack_header(message_type, len(payload), sequence, sample_id, model_id, mask_epoch, status),
        payload,
    )


def encode_command(words: Sequence[int], *, sequence: int, model_id: int, mask_epoch: int,
                   status: int = 0) -> bytes:
    if not words or len(words) * 16 > MAX_PAYLOAD_BYTES:
        raise ValueError("command payload must contain 1..253 128-bit words")
    payload = bytearray()
    for word in words:
        if type(word) is not int or not 0 <= word < (1 << 128):
            raise ValueError("command word must be an unsigned 128-bit integer")
        payload.extend(word.to_bytes(16, "little"))
    return _finish(
        _pack_header(MessageType.COMMAND, len(payload), sequence, 0, model_id, mask_epoch, status),
        bytes(payload),
    )


def encode_response(words: Sequence[int], *, sequence: int, model_id: int = 0,
                    mask_epoch: int = 0, status: int = 0) -> bytes:
    if not words or len(words) * 16 > MAX_PAYLOAD_BYTES:
        raise ValueError("response payload must contain 1..253 128-bit words")
    payload = bytearray()
    for word in words:
        if type(word) is not int or not 0 <= word < (1 << 128):
            raise ValueError("response word must be an unsigned 128-bit integer")
        payload.extend(word.to_bytes(16, "little"))
    return _finish(
        _pack_header(MessageType.RESPONSE, len(payload), sequence, 0, model_id, mask_epoch, status),
        bytes(payload),
    )


def encode_sample(beats: Sequence[int], *, sequence: int, sample_id: int,
                  model_id: int, mask_epoch: int, status: int = 0) -> bytes:
    return _encode_fixed(
        MessageType.SAMPLE, beats, 8, sequence, sample_id, model_id, mask_epoch, status=status
    )


def encode_result(beats: Sequence[int], *, sequence: int, sample_id: int,
                  model_id: int, mask_epoch: int, status: int = 0) -> bytes:
    return _encode_fixed(
        MessageType.RESULT, beats, 10, sequence, sample_id, model_id, mask_epoch,
        signed=True, status=status,
    )


def _signed32(value: int) -> int:
    return value - (1 << 32) if value & (1 << 31) else value


def decode_frame(frame: bytes, *, tlast: bool) -> DecodedFrame:
    if not tlast:
        raise PacketError("TLAST is required at the DMA frame boundary")
    if not isinstance(frame, bytes):
        raise PacketError("frame must be bytes")
    if len(frame) < HEADER_BYTES + CRC_BYTES:
        raise PacketError("frame is shorter than the header and CRC")
    if len(frame) > MAX_FRAME_BYTES:
        raise PacketError("frame length exceeds 4096 bytes")

    (magic, version, type_value, flags, header_words, payload_length, sequence,
     sample_id, model_id, mask_epoch, status) = struct.unpack_from(HEADER_FORMAT, frame)
    if magic != MAGIC:
        raise PacketError("bad magic")
    if version != VERSION:
        raise PacketError("unsupported version")
    if flags != 0:
        raise PacketError("reserved flags must be zero")
    if header_words != HEADER_WORDS:
        raise PacketError("header length is not 32 bytes")
    expected_length = HEADER_BYTES + payload_length + CRC_BYTES
    if expected_length != len(frame):
        raise PacketError("frame length does not match payload length")
    if payload_length > MAX_PAYLOAD_BYTES:
        raise PacketError("payload length exceeds 4096-byte DMA frame")
    try:
        message_type = MessageType(type_value)
    except ValueError as exc:
        raise PacketError("unknown message type") from exc

    payload = frame[HEADER_BYTES:-CRC_BYTES]
    expected_crc = struct.unpack_from("<I", frame, len(frame) - CRC_BYTES)[0]
    actual_crc = zlib.crc32(frame[:-CRC_BYTES]) & 0xFFFFFFFF
    if expected_crc != actual_crc:
        raise PacketError("CRC mismatch")

    words: tuple[int, ...] = ()
    beats: tuple[int, ...] = ()
    if message_type in (MessageType.COMMAND, MessageType.RESPONSE):
        if payload_length == 0 or payload_length % 16:
            raise PacketError("command/response payload must be a nonzero 16-byte multiple")
        words = tuple(int.from_bytes(payload[offset:offset + 16], "little")
                      for offset in range(0, payload_length, 16))
    elif message_type is MessageType.SAMPLE:
        if payload_length != 32:
            raise PacketError("sample payload must be exactly 32 bytes")
        beats = struct.unpack("<8I", payload)
    elif message_type is MessageType.RESULT:
        if payload_length != 40:
            raise PacketError("result payload must be exactly 40 bytes")
        beats = tuple(_signed32(value) for value in struct.unpack("<10I", payload))

    return DecodedFrame(
        message_type=message_type,
        flags=flags,
        payload_length=payload_length,
        sequence=sequence,
        sample_id=sample_id,
        model_id=model_id,
        mask_epoch=mask_epoch,
        status=status,
        payload=payload,
        words=words,
        beats=beats,
    )
