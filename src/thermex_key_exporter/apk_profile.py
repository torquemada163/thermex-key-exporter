"""Read the non-user OEM profile from an official Thermex Home APK.

The desktop application deliberately does not bundle Thermex's application
credentials.  Instead, it reads the currently installed official APK selected
by the user and keeps the derived material in memory for the duration of one
export.  No account credentials, QR tokens, sessions, or local keys are read
from the APK or written by this module.
"""

from __future__ import annotations

import hashlib
import re
import struct
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Final
from xml.etree import ElementTree

from cryptography.hazmat.primitives.serialization import Encoding, pkcs7

from .profile import SdkProfile

_ANDROID_NAMESPACE: Final = "http://schemas.android.com/apk/res/android"
_APK_ASSET: Final = "assets/t_s.bmp"
_APP_INITIALIZER_DESCRIPTOR: Final = "Lcom/thingclips/smart/initializer/AppInitializer;"
_APP_INITIALIZER_METHOD: Final = "d"
_APP_ID_PATTERN: Final = re.compile(r"^[a-z0-9]{20}$")
_APP_SECRET_PATTERN: Final = re.compile(r"^[a-z0-9]{32}$")
_NO_INDEX: Final = 0xFFFFFFFF


class ProfileExtractionError(RuntimeError):
    """Raised when an APK cannot be used to derive an OEM profile safely."""


@dataclass(frozen=True, slots=True)
class ApkManifest:
    """The small subset of Android manifest data needed by the exporter."""

    package_name: str
    version_name: str


def load_thermex_profile(apk_path: Path) -> SdkProfile:
    """Build an in-memory SDK profile from an official Thermex Home APK.

    The branded SDK values that change with the APK are extracted at runtime.
    The remaining Android SDK version fields are the values used by the
    currently supported Thermex Home release.  They can be updated without
    exposing any app-level credential in source control.
    """
    apk_path = apk_path.expanduser()
    if not apk_path.is_file():
        raise ProfileExtractionError("the selected Thermex Home APK does not exist")

    try:
        with zipfile.ZipFile(apk_path) as archive:
            manifest = _read_manifest(archive)
            certificate_sha256 = _read_certificate_sha256(archive)
            bitmap = _read_required_entry(archive, _APK_ASSET)
            app_id, app_secret = _read_oem_identity(archive)
    except (OSError, zipfile.BadZipFile) as error:
        raise ProfileExtractionError("the selected file is not a readable Android APK") from error

    bitmap_tokens = _extract_bitmap_tokens(app_id, bitmap)
    if len(bitmap_tokens) != 1:
        raise ProfileExtractionError("the APK security bitmap did not yield one usable SDK token")

    return SdkProfile(
        app_id=app_id,
        app_secret=app_secret,
        certificate_sha256=certificate_sha256,
        bitmap_token=bitmap_tokens[0],
        package_name=manifest.package_name,
        app_version=manifest.version_name,
    )


def read_apk_manifest(apk_path: Path) -> ApkManifest:
    """Read package name and version from an APK without exposing credentials."""
    try:
        with zipfile.ZipFile(apk_path.expanduser()) as archive:
            return _read_manifest(archive)
    except (OSError, zipfile.BadZipFile) as error:
        raise ProfileExtractionError("the selected file is not a readable Android APK") from error


def _read_manifest(archive: zipfile.ZipFile) -> ApkManifest:
    data = _read_required_entry(archive, "AndroidManifest.xml")
    package_name, version_name = _parse_android_manifest(data)
    if not package_name or not version_name:
        raise ProfileExtractionError(
            "the APK manifest does not contain package and version information"
        )
    return ApkManifest(package_name, version_name)


def _read_required_entry(archive: zipfile.ZipFile, name: str) -> bytes:
    try:
        return archive.read(name)
    except KeyError as error:
        raise ProfileExtractionError(f"the APK is missing required entry: {name}") from error


def _read_certificate_sha256(archive: zipfile.ZipFile) -> str:
    names = sorted(
        name
        for name in archive.namelist()
        if name.upper().startswith("META-INF/") and name.upper().endswith((".RSA", ".DSA", ".EC"))
    )
    if not names:
        raise ProfileExtractionError("the APK signing certificate was not found")
    for name in names:
        try:
            certificates = pkcs7.load_der_pkcs7_certificates(archive.read(name))
        except ValueError:
            continue
        if certificates:
            digest = hashlib.sha256(certificates[0].public_bytes(Encoding.DER)).digest()
            return ":".join(f"{byte:02X}" for byte in digest)
    raise ProfileExtractionError("the APK signing certificate could not be parsed")


def _read_oem_identity(archive: zipfile.ZipFile) -> tuple[str, str]:
    method_strings: list[str] = []
    dex_names = sorted(name for name in archive.namelist() if _is_dex_name(name))
    if not dex_names:
        raise ProfileExtractionError("the APK does not contain executable DEX code")
    for dex_name in dex_names:
        dex = _DexFile(archive.read(dex_name))
        method_strings.extend(dex.oem_initializer_strings())
    return _select_oem_identity(method_strings)


def _is_dex_name(name: str) -> bool:
    stem = name.rsplit("/", maxsplit=1)[-1]
    return bool(re.fullmatch(r"classes(?:[1-9][0-9]*)?\.dex", stem))


def _select_oem_identity(values: Iterable[str]) -> tuple[str, str]:
    app_ids = {value for value in values if _APP_ID_PATTERN.fullmatch(value)}
    app_secrets = {value for value in values if _APP_SECRET_PATTERN.fullmatch(value)}
    if len(app_ids) != 1 or len(app_secrets) != 1:
        raise ProfileExtractionError(
            "the APK does not contain an unambiguous Thermex OEM application profile"
        )
    return next(iter(app_ids)), next(iter(app_secrets))


def _parse_android_manifest(data: bytes) -> tuple[str, str]:
    stripped = data.lstrip()
    if stripped.startswith(b"<"):
        return _parse_plain_manifest(data)
    return _parse_binary_manifest(data)


def _parse_plain_manifest(data: bytes) -> tuple[str, str]:
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as error:
        raise ProfileExtractionError("the APK manifest is not valid XML") from error
    return (
        root.attrib.get("package", ""),
        root.attrib.get(f"{{{_ANDROID_NAMESPACE}}}versionName", ""),
    )


def _parse_binary_manifest(data: bytes) -> tuple[str, str]:
    if len(data) < 8:
        raise ProfileExtractionError("the APK manifest is truncated")
    chunk_type, header_size, total_size = _chunk_header(data, 0)
    if chunk_type != 0x0003 or header_size < 8 or total_size > len(data):
        raise ProfileExtractionError("the APK manifest has an unsupported binary XML header")

    strings: tuple[str, ...] | None = None
    offset = header_size
    while offset < total_size:
        chunk_type, chunk_header_size, chunk_size = _chunk_header(data, offset)
        if chunk_size < chunk_header_size or offset + chunk_size > total_size:
            raise ProfileExtractionError("the APK manifest contains an invalid XML chunk")
        if chunk_type == 0x0001:
            strings = _parse_string_pool(data, offset, chunk_header_size, chunk_size)
        elif chunk_type == 0x0102 and strings is not None:
            package_name, version_name = _manifest_start_element(data, offset, strings)
            if package_name:
                return package_name, version_name
        offset += chunk_size
    raise ProfileExtractionError("the APK manifest does not contain a manifest element")


def _manifest_start_element(data: bytes, offset: int, strings: tuple[str, ...]) -> tuple[str, str]:
    if offset + 36 > len(data):
        raise ProfileExtractionError("the APK manifest start element is truncated")
    name_index = _u32(data, offset + 20)
    if _string_at(strings, name_index) != "manifest":
        return "", ""
    attributes_start = _u16(data, offset + 24)
    attributes_size = _u16(data, offset + 26)
    attributes_count = _u16(data, offset + 28)
    if attributes_size < 20:
        raise ProfileExtractionError("the APK manifest has an invalid attribute size")
    cursor = offset + 16 + attributes_start
    package_name = ""
    version_name = ""
    for _ in range(attributes_count):
        if cursor + attributes_size > len(data):
            raise ProfileExtractionError("the APK manifest attributes are truncated")
        attribute_name = _string_at(strings, _u32(data, cursor + 4))
        value = _attribute_value(data, cursor, strings)
        if attribute_name == "package":
            package_name = value
        elif attribute_name == "versionName":
            version_name = value
        cursor += attributes_size
    return package_name, version_name


def _attribute_value(data: bytes, offset: int, strings: tuple[str, ...]) -> str:
    raw_value_index = _u32(data, offset + 8)
    if raw_value_index != _NO_INDEX:
        return _string_at(strings, raw_value_index)
    value_type = data[offset + 15]
    value_data = _u32(data, offset + 16)
    return _string_at(strings, value_data) if value_type == 0x03 else ""


def _parse_string_pool(
    data: bytes, offset: int, header_size: int, chunk_size: int
) -> tuple[str, ...]:
    if header_size < 28 or offset + header_size > len(data):
        raise ProfileExtractionError("the APK manifest string pool is invalid")
    string_count = _u32(data, offset + 8)
    flags = _u32(data, offset + 16)
    strings_start = _u32(data, offset + 20)
    offsets_start = offset + header_size
    data_start = offset + strings_start
    if data_start > offset + chunk_size or offsets_start + string_count * 4 > len(data):
        raise ProfileExtractionError("the APK manifest string pool is truncated")
    utf8 = bool(flags & 0x100)
    values: list[str] = []
    for index in range(string_count):
        string_offset = _u32(data, offsets_start + index * 4)
        position = data_start + string_offset
        if position >= offset + chunk_size:
            raise ProfileExtractionError("the APK manifest string offset is invalid")
        values.append(_decode_pool_string(data, position, utf8, offset + chunk_size))
    return tuple(values)


def _decode_pool_string(data: bytes, position: int, utf8: bool, limit: int) -> str:
    if utf8:
        _, position = _decode_length8(data, position, limit)
        byte_length, position = _decode_length8(data, position, limit)
        end = position + byte_length
        if end >= limit:
            raise ProfileExtractionError("the APK manifest UTF-8 string is truncated")
        return data[position:end].decode("utf-8", errors="replace")
    char_length, position = _decode_length16(data, position, limit)
    end = position + char_length * 2
    if end >= limit:
        raise ProfileExtractionError("the APK manifest UTF-16 string is truncated")
    return data[position:end].decode("utf-16le", errors="replace")


def _decode_length8(data: bytes, position: int, limit: int) -> tuple[int, int]:
    if position >= limit:
        raise ProfileExtractionError("the APK manifest string length is truncated")
    first = data[position]
    position += 1
    if first & 0x80:
        if position >= limit:
            raise ProfileExtractionError("the APK manifest string length is truncated")
        return ((first & 0x7F) << 8) | data[position], position + 1
    return first, position


def _decode_length16(data: bytes, position: int, limit: int) -> tuple[int, int]:
    if position + 2 > limit:
        raise ProfileExtractionError("the APK manifest string length is truncated")
    first = _u16(data, position)
    position += 2
    if first & 0x8000:
        if position + 2 > limit:
            raise ProfileExtractionError("the APK manifest string length is truncated")
        return ((first & 0x7FFF) << 16) | _u16(data, position), position + 2
    return first, position


def _chunk_header(data: bytes, offset: int) -> tuple[int, int, int]:
    if offset + 8 > len(data):
        raise ProfileExtractionError("the APK manifest XML chunk is truncated")
    return _u16(data, offset), _u16(data, offset + 2), _u32(data, offset + 4)


def _string_at(strings: tuple[str, ...], index: int) -> str:
    if index == _NO_INDEX or index >= len(strings):
        return ""
    return strings[index]


def _u16(data: bytes, offset: int) -> int:
    if offset + 2 > len(data):
        raise ProfileExtractionError("APK data is truncated")
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    if offset + 4 > len(data):
        raise ProfileExtractionError("APK data is truncated")
    return struct.unpack_from("<I", data, offset)[0]


def _extract_bitmap_tokens(app_id: str, bitmap: bytes) -> list[str]:
    """Extract the SDK's per-app token from its bundled security bitmap."""
    pixels = bitmap[0x36:]
    if not pixels:
        raise ProfileExtractionError("the APK security bitmap does not contain pixel data")
    length = len(pixels)
    offset = (abs(_java_string_hash(app_id)) % length) // 2
    keys_count = pixels[(offset + 1) % length]
    coefficients_count = pixels[(offset + 2) % length]
    if not 1 <= keys_count <= 4 or coefficients_count == 0:
        raise ProfileExtractionError("the APK security bitmap has an unsupported token layout")

    magic = _signed32(
        int.from_bytes(bytes(pixels[(offset + index) % length] for index in range(3, 7)), "big")
    )
    current = _signed32(offset ^ magic)
    pairs: list[tuple[int, int]] = []
    for _ in range(coefficients_count * keys_count):
        first_offset = _c_remainder(current, length)
        first_length = pixels[first_offset]
        first = int.from_bytes(
            bytes(pixels[(first_offset + 1 + index) % length] for index in range(first_length)),
            "big",
        )
        second_offset = (first_offset + first_length + 1) % length
        second_length = pixels[second_offset]
        second = int.from_bytes(
            bytes(pixels[(second_offset + 1 + index) % length] for index in range(second_length)),
            "big",
        )
        next_offset = (second_offset + second_length + 1) % length
        next_magic = _signed32(
            int.from_bytes(
                bytes(pixels[(next_offset + index) % length] for index in range(4)), "big"
            )
        )
        current = _signed32(first_offset ^ next_magic)
        pairs.append((first, second))

    tokens: list[str] = []
    for token_index in range(keys_count):
        rows: list[list[Fraction]] = []
        for first, second in pairs[
            token_index * coefficients_count : (token_index + 1) * coefficients_count
        ]:
            rows.append(
                [Fraction(first) ** power for power in range(coefficients_count - 1, -1, -1)]
                + [Fraction(second)]
            )
        for row in range(coefficients_count):
            if rows[row][row] == 0:
                replacement = next(
                    (
                        candidate
                        for candidate in range(row + 1, coefficients_count)
                        if rows[candidate][row] != 0
                    ),
                    None,
                )
                if replacement is None:
                    raise ProfileExtractionError(
                        "the APK security bitmap coefficient matrix is singular"
                    )
                rows[row], rows[replacement] = rows[replacement], rows[row]
            if row < coefficients_count - 1:
                diagonal = rows[row][row]
                for below in range(row + 1, coefficients_count):
                    if rows[below][row] != 0:
                        ratio = diagonal / rows[below][row]
                        for column in range(row, coefficients_count + 1):
                            rows[below][column] = ratio * rows[below][column] - rows[row][column]
        result = rows[-1][-1] / rows[-1][-2]
        if result.denominator != 1:
            raise ProfileExtractionError("the APK security bitmap yielded a non-integer SDK token")
        encoded = format(result.numerator, "x")
        if len(encoded) % 2:
            encoded = "0" + encoded
        try:
            tokens.append(bytes.fromhex(encoded).decode("ascii"))
        except UnicodeDecodeError as error:
            raise ProfileExtractionError(
                "the APK security bitmap yielded a non-text SDK token"
            ) from error
    return tokens


def _signed32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def _java_string_hash(value: str) -> int:
    result = 0
    for character in value:
        result = _signed32(result * 31 + ord(character))
    return result


def _c_remainder(value: int, divisor: int) -> int:
    return value - int(value / divisor) * divisor


@dataclass(frozen=True, slots=True)
class _MethodReference:
    owner: str
    name: str


class _DexFile:
    """Minimal DEX reader for string constants in the OEM initializer method."""

    def __init__(self, data: bytes) -> None:
        if len(data) < 112 or not data.startswith(b"dex\n"):
            raise ProfileExtractionError("the APK contains an invalid DEX file")
        self.data = data
        self.strings = self._read_strings()
        self.types = self._read_types()
        self.methods = self._read_methods()

    def oem_initializer_strings(self) -> list[str]:
        values: list[str] = []
        for method, code_offset in self._encoded_methods():
            instructions = self._instructions(code_offset)
            if self._invokes_app_initializer(instructions):
                values.extend(self._string_constants(instructions))
        return values

    def _read_strings(self) -> tuple[str, ...]:
        count = _u32(self.data, 56)
        offset = _u32(self.data, 60)
        if offset + count * 4 > len(self.data):
            raise ProfileExtractionError("the APK DEX string table is truncated")
        return tuple(
            self._read_dex_string(_u32(self.data, offset + index * 4)) for index in range(count)
        )

    def _read_dex_string(self, offset: int) -> str:
        _, offset = self._read_uleb128(offset)
        end = self.data.find(b"\x00", offset)
        if end < 0:
            raise ProfileExtractionError("the APK DEX string data is truncated")
        return self.data[offset:end].decode("utf-8", errors="replace")

    def _read_types(self) -> tuple[str, ...]:
        count = _u32(self.data, 64)
        offset = _u32(self.data, 68)
        if offset + count * 4 > len(self.data):
            raise ProfileExtractionError("the APK DEX type table is truncated")
        types: list[str] = []
        for index in range(count):
            string_index = _u32(self.data, offset + index * 4)
            if string_index >= len(self.strings):
                raise ProfileExtractionError("the APK DEX type table references an invalid string")
            types.append(self.strings[string_index])
        return tuple(types)

    def _read_methods(self) -> tuple[_MethodReference, ...]:
        count = _u32(self.data, 88)
        offset = _u32(self.data, 92)
        if offset + count * 8 > len(self.data):
            raise ProfileExtractionError("the APK DEX method table is truncated")
        methods: list[_MethodReference] = []
        for index in range(count):
            entry = offset + index * 8
            owner_index = _u16(self.data, entry)
            name_index = _u32(self.data, entry + 4)
            if owner_index >= len(self.types) or name_index >= len(self.strings):
                raise ProfileExtractionError("the APK DEX method table references invalid data")
            methods.append(_MethodReference(self.types[owner_index], self.strings[name_index]))
        return tuple(methods)

    def _encoded_methods(self) -> Iterator[tuple[_MethodReference, int]]:
        count = _u32(self.data, 96)
        offset = _u32(self.data, 100)
        if offset + count * 32 > len(self.data):
            raise ProfileExtractionError("the APK DEX class table is truncated")
        for index in range(count):
            class_data_offset = _u32(self.data, offset + index * 32 + 24)
            if class_data_offset:
                yield from self._read_class_data(class_data_offset)

    def _read_class_data(self, offset: int) -> Iterator[tuple[_MethodReference, int]]:
        static_fields, offset = self._read_uleb128(offset)
        instance_fields, offset = self._read_uleb128(offset)
        direct_methods, offset = self._read_uleb128(offset)
        virtual_methods, offset = self._read_uleb128(offset)
        for _ in range(static_fields + instance_fields):
            _, offset = self._read_uleb128(offset)
            _, offset = self._read_uleb128(offset)
        for methods_count in (direct_methods, virtual_methods):
            method_index = 0
            for _ in range(methods_count):
                delta, offset = self._read_uleb128(offset)
                method_index += delta
                _, offset = self._read_uleb128(offset)
                code_offset, offset = self._read_uleb128(offset)
                if method_index >= len(self.methods):
                    raise ProfileExtractionError("the APK DEX code references an invalid method")
                if code_offset:
                    yield self.methods[method_index], code_offset

    def _instructions(self, code_offset: int) -> tuple[int, ...]:
        if code_offset + 16 > len(self.data):
            raise ProfileExtractionError("the APK DEX code item is truncated")
        count = _u32(self.data, code_offset + 12)
        start = code_offset + 16
        if start + count * 2 > len(self.data):
            raise ProfileExtractionError("the APK DEX instructions are truncated")
        return struct.unpack_from(f"<{count}H", self.data, start)

    def _invokes_app_initializer(self, instructions: tuple[int, ...]) -> bool:
        for offset, opcode in self._instruction_offsets(instructions):
            if opcode not in {*range(0x6E, 0x73), *range(0x74, 0x79)}:
                continue
            if offset + 1 >= len(instructions):
                raise ProfileExtractionError("the APK DEX invoke instruction is truncated")
            method_index = instructions[offset + 1]
            if method_index >= len(self.methods):
                raise ProfileExtractionError("the APK DEX invoke references an invalid method")
            method = self.methods[method_index]
            if (
                method.owner == _APP_INITIALIZER_DESCRIPTOR
                and method.name == _APP_INITIALIZER_METHOD
            ):
                return True
        return False

    def _string_constants(self, instructions: tuple[int, ...]) -> Iterator[str]:
        for offset, opcode in self._instruction_offsets(instructions):
            if opcode == 0x1A:
                if offset + 1 >= len(instructions):
                    raise ProfileExtractionError("the APK DEX string instruction is truncated")
                string_index = instructions[offset + 1]
            elif opcode == 0x1B:
                if offset + 2 >= len(instructions):
                    raise ProfileExtractionError(
                        "the APK DEX jumbo string instruction is truncated"
                    )
                string_index = instructions[offset + 1] | (instructions[offset + 2] << 16)
            else:
                continue
            if string_index >= len(self.strings):
                raise ProfileExtractionError(
                    "the APK DEX string instruction references invalid data"
                )
            yield self.strings[string_index]

    def _instruction_offsets(self, instructions: tuple[int, ...]) -> Iterator[tuple[int, int]]:
        offset = 0
        while offset < len(instructions):
            word = instructions[offset]
            opcode = word & 0xFF
            yield offset, opcode
            width = _instruction_width(instructions, offset)
            if width <= 0 or offset + width > len(instructions):
                raise ProfileExtractionError("the APK DEX contains an invalid instruction width")
            offset += width

    def _read_uleb128(self, offset: int) -> tuple[int, int]:
        value = 0
        shift = 0
        for _ in range(5):
            if offset >= len(self.data):
                raise ProfileExtractionError("the APK DEX ULEB128 value is truncated")
            byte = self.data[offset]
            offset += 1
            value |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return value, offset
            shift += 7
        raise ProfileExtractionError("the APK DEX ULEB128 value is invalid")


def _instruction_width(instructions: tuple[int, ...], offset: int) -> int:
    opcode = instructions[offset] & 0xFF
    if opcode == 0x00:
        identifier = instructions[offset] >> 8
        if identifier == 0x01:  # packed-switch-payload
            return 4 + instructions[offset + 1] * 2
        if identifier == 0x02:  # sparse-switch-payload
            return 2 + instructions[offset + 1] * 4
        if identifier == 0x03:  # fill-array-data-payload
            element_width = instructions[offset + 1]
            size = instructions[offset + 2] | (instructions[offset + 3] << 16)
            return 4 + (element_width * size + 1) // 2
        return 1
    if opcode in {
        0x02,
        0x05,
        0x08,
        0x13,
        0x15,
        0x16,
        0x19,
        0x1A,
        0x1C,
        0x1F,
        0x20,
        0x22,
        0x23,
        0x29,
    }:
        return 2
    if opcode in {0x03, 0x06, 0x09, 0x14, 0x17, 0x1B, 0x24, 0x25, 0x26, 0x2A}:
        return 3
    if opcode == 0x18:
        return 5
    if opcode in {0x2B, 0x2C} or 0x2D <= opcode <= 0x3D:
        return 2 if opcode >= 0x2D else 3
    if 0x44 <= opcode <= 0x6D:
        return 2
    if 0x6E <= opcode <= 0x78:
        return 3
    if 0x7B <= opcode <= 0x8F or 0xB0 <= opcode <= 0xCF:
        return 1
    if 0x90 <= opcode <= 0xAF:
        return 2
    if 0xD0 <= opcode <= 0xE2:
        return 2
    if opcode in {0xFA, 0xFB}:
        return 4
    if opcode in {0xFC, 0xFD}:
        return 3
    if opcode in {0xFE, 0xFF}:
        return 2
    return 1
