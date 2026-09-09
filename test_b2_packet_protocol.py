import struct
import unittest
import zlib

from b2_packet_protocol import (
    HEADER_BYTES,
    MAGIC,
    MAX_FRAME_BYTES,
    MessageType,
    PacketError,
    decode_frame,
    encode_command,
    encode_result,
    encode_sample,
)


class B2PacketProtocolTests(unittest.TestCase):
    def test_command_round_trip_preserves_128_bit_words(self):
        words = (0x10000000000000000000000000000001, 0xE00000000000000000000000000009)
        frame = encode_command(words, sequence=7, model_id=3, mask_epoch=11)
        decoded = decode_frame(frame, tlast=True)
        self.assertEqual(decoded.message_type, MessageType.COMMAND)
        self.assertEqual(decoded.sequence, 7)
        self.assertEqual(decoded.model_id, 3)
        self.assertEqual(decoded.mask_epoch, 11)
        self.assertEqual(decoded.words, words)

    def test_sample_is_exactly_eight_little_endian_beats(self):
        beats = tuple(range(8))
        frame = encode_sample(beats, sequence=9, sample_id=42, model_id=3, mask_epoch=11)
        decoded = decode_frame(frame, tlast=True)
        self.assertEqual(decoded.message_type, MessageType.SAMPLE)
        self.assertEqual(decoded.beats, beats)
        self.assertEqual(decoded.payload_length, 32)

    def test_result_is_exactly_ten_little_endian_beats(self):
        beats = tuple(range(10))
        frame = encode_result(beats, sequence=10, sample_id=42, model_id=3, mask_epoch=11)
        decoded = decode_frame(frame, tlast=True)
        self.assertEqual(decoded.message_type, MessageType.RESULT)
        self.assertEqual(decoded.beats, beats)
        self.assertEqual(decoded.payload_length, 40)

    def test_rejects_missing_tlast_and_trailing_bytes(self):
        frame = encode_sample(range(8), sequence=1, sample_id=1, model_id=1, mask_epoch=1)
        with self.assertRaisesRegex(PacketError, "TLAST"):
            decode_frame(frame, tlast=False)
        with self.assertRaisesRegex(PacketError, "length"):
            decode_frame(frame + b"x", tlast=True)

    def test_rejects_crc_and_reserved_header_bits(self):
        frame = bytearray(encode_sample(range(8), sequence=1, sample_id=1, model_id=1, mask_epoch=1))
        frame[-1] ^= 0x01
        with self.assertRaisesRegex(PacketError, "CRC"):
            decode_frame(bytes(frame), tlast=True)

        frame = bytearray(encode_sample(range(8), sequence=1, sample_id=1, model_id=1, mask_epoch=1))
        frame[6] = 1
        with self.assertRaisesRegex(PacketError, "flags"):
            decode_frame(bytes(frame), tlast=True)

    def test_rejects_wrong_fixed_payload_length_and_oversize(self):
        original = encode_sample(range(8), sequence=1, sample_id=1, model_id=1, mask_epoch=1)
        frame = bytearray(original[:HEADER_BYTES + 28])
        struct.pack_into("<I", frame, 8, 28)
        crc = zlib.crc32(frame) & 0xFFFFFFFF
        frame.extend(struct.pack("<I", crc))
        with self.assertRaisesRegex(PacketError, "32 bytes"):
            decode_frame(bytes(frame), tlast=True)

        self.assertGreaterEqual(MAX_FRAME_BYTES, HEADER_BYTES + 4)
        self.assertRaises(
            ValueError,
            encode_command,
            [0] * ((MAX_FRAME_BYTES // 16) + 1),
            sequence=1,
            model_id=1,
            mask_epoch=1,
        )

    def test_magic_is_fixed_and_crc_covers_header_and_payload(self):
        frame = encode_sample(range(8), sequence=1, sample_id=1, model_id=1, mask_epoch=1)
        self.assertEqual(frame[:4], struct.pack("<I", MAGIC))
        expected = zlib.crc32(frame[:-4]) & 0xFFFFFFFF
        self.assertEqual(frame[-4:], struct.pack("<I", expected))


if __name__ == "__main__":
    unittest.main()
