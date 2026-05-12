"""WAV iXML chunk writer for embedding key-value metadata."""
from __future__ import annotations

import struct
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, fromstring, tostring

IXML_CHUNK_ID = b"iXML"


def _build_ixml(metadata: dict[str, str]) -> bytes:
    root = Element("BWFXML")
    version = SubElement(root, "IXML_VERSION")
    version.text = "1.61"
    user = SubElement(root, "USER")
    for key, value in metadata.items():
        entry = SubElement(user, "ENTRY")
        entry.set("KEY", key)
        entry.text = value
    return (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        + tostring(root, encoding="unicode").encode("utf-8")
    )


def _parse_ixml(data: bytes) -> dict[str, str]:
    root = fromstring(data.decode("utf-8"))
    user = root.find("USER")
    if user is None:
        return {}
    result: dict[str, str] = {}
    for entry in user.findall("ENTRY"):
        key = entry.get("KEY", "")
        result[key] = entry.text or ""
    return result


def write_ixml(path: str | Path, metadata: dict[str, str]) -> None:
    """Append an iXML chunk with key-value metadata to an existing WAV file."""
    wav_path = Path(path)
    data = wav_path.read_bytes()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("not a valid WAV file")

    payload = _build_ixml(metadata)
    chunk_size = len(payload)
    chunk = IXML_CHUNK_ID + struct.pack("<I", chunk_size) + payload
    if chunk_size % 2 != 0:
        chunk += b"\x00"

    new_data = data + chunk
    riff_size = len(new_data) - 8
    new_data = new_data[:4] + struct.pack("<I", riff_size) + new_data[8:]
    wav_path.write_bytes(new_data)


def read_ixml(path: str | Path) -> dict[str, str]:
    """Read iXML metadata from a WAV file. Returns empty dict if no iXML chunk."""
    wav_path = Path(path)
    data = wav_path.read_bytes()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("not a valid WAV file")

    offset = 12
    while offset + 8 <= len(data):
        chunk_id = data[offset : offset + 4]
        chunk_size = struct.unpack("<I", data[offset + 4 : offset + 8])[0]
        if chunk_id == IXML_CHUNK_ID:
            return _parse_ixml(data[offset + 8 : offset + 8 + chunk_size])
        offset += 8 + chunk_size
        if chunk_size % 2 != 0:
            offset += 1
    return {}
