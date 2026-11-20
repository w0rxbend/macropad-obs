#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fail if the ESP32-S3 partition table or sdkconfig breaks spec section 10 or D8.

No argument checks firmware/esp32s3/partitions.csv and sdkconfig.defaults.
`--built DIR` also checks what `just firmware` built: DIR/partition_table/partition-table.bin
must hold the CSV's rows, and DIR/sdkconfig must pass the same sdkconfig rules."""

import re
import struct
import sys
import tomllib
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / "firmware" / "esp32s3"
PARTITIONS = PROJECT / "partitions.csv"
SDKCONFIG_DEFAULTS = PROJECT / "sdkconfig.defaults"
BOARD = ROOT / "board.toml"
CORE = ROOT / "firmware" / "core"

TYPES = {"app": 0x00, "data": 0x01}
SUBTYPES = {0x00: {"factory": 0x00, "ota_0": 0x10, "ota_1": 0x11}, 0x01: {"nvs": 0x02}}
FLAGS = {"encrypted": 0x1, "readonly": 0x2}
NVS = 0x02
RAW_SUBTYPES = range(0x40, 0xFF)  # IDF leaves data subtypes 0x40-0xFE to the application
DATA_NAMES = {"nvs", "cred", "cfg_a", "cfg_b"}  # spec 10
SECTOR = 0x1000
APP_ALIGN = 0x10000
TABLE_END = 0x9000  # the table sits at IDF's default 0x8000 and takes one sector
ENTRY = struct.Struct("<HBBII16sI")
ENTRY_MAGIC = 0x50AA
END_MAGICS = {0xEBEB, 0xFFFF}  # the MD5 entry, then erased flash
SDKCONFIG_REQUIRED = (
    'CONFIG_IDF_TARGET="esp32s3"',
    "CONFIG_PARTITION_TABLE_CUSTOM=y",
    'CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions.csv"',
)
SDKCONFIG_FORBIDDEN = ("CONFIG_NVS_ENCRYPTION", "CONFIG_SECURE_FLASH_ENC_ENABLED", "CONFIG_SECURE_BOOT")


class Partition(NamedTuple):
    name: str
    type: int
    subtype: int
    offset: int
    size: int
    flags: int


def parse_number(text):
    text = text.strip()
    scale = {"K": 1024, "M": 1024 * 1024}.get(text[-1:].upper(), 1)
    return int(text[:-1] if scale > 1 else text, 0) * scale


def parse_row(line):
    fields = [field.strip() for field in line.split(",")]
    name, type_name, subtype_name, offset, size = fields[:5]
    kind = TYPES[type_name]
    subtype = SUBTYPES[kind].get(subtype_name)
    flags = sum(FLAGS[flag] for flag in fields[5:] if flag)
    return Partition(name, kind, parse_number(subtype_name) if subtype is None else subtype,
                     parse_number(offset), parse_number(size), flags)


def parse_csv(text):
    lines = (line.strip() for line in text.splitlines())
    return [parse_row(line) for line in lines if line and not line.startswith("#")]


def parse_binary(blob):
    """Rows of a partition-table.bin, up to the MD5 entry. ValueError on a bad entry."""
    rows = []
    for start in range(0, len(blob) - ENTRY.size + 1, ENTRY.size):
        magic, kind, subtype, offset, size, label, flags = ENTRY.unpack_from(blob, start)
        if magic in END_MAGICS:
            return rows
        if magic != ENTRY_MAGIC:
            raise ValueError(f"partition entry at byte {start}: magic {magic:#06x}")
        rows.append(Partition(label.rstrip(b"\0").decode(), kind, subtype, offset, size, flags))
    raise ValueError("partition table has no end entry")


def header_define(header, name):
    return int(re.search(rf"^#define {name} (\d+)$", (CORE / header).read_text(), re.MULTILINE).group(1))


def slot_min_bytes():
    """STORE_SLOT_BYTES of firmware/core/store.h: one header sector plus CONFIG_MAX_BYTES."""
    return header_define("store.h", "STORE_SECTOR_BYTES") + header_define("config.h", "CONFIG_MAX_BYTES")


def flash_bytes():
    """Flash size from the module ordering code in board.toml: -N16R2 is 16 MB."""
    part = tomllib.loads(BOARD.read_text(encoding="utf-8"))["mcu"]["part"]
    return int(re.search(r"-N(\d+)R\d+$", part).group(1)) * 1024 * 1024


def name_problems(rows):
    apps = [row.name for row in rows if row.type == TYPES["app"]]
    data = sorted(row.name for row in rows if row.type == TYPES["data"])
    found = [] if len(apps) == 1 else [f"app partitions {apps}: expected exactly one"]
    if sorted(DATA_NAMES) != data:
        found.append(f"data partitions {data}: expected {sorted(DATA_NAMES)}")
    return found


def kind_problems(row, slot_min):
    found = []
    if row.name in ("nvs", "cred") and row.subtype != NVS:
        found.append(f"{row.name}: subtype {row.subtype:#x}, expected nvs")
    if row.name in ("cfg_a", "cfg_b"):
        if row.subtype not in RAW_SUBTYPES:
            found.append(f"{row.name}: subtype {row.subtype:#x}, expected raw (0x40-0xfe)")
        if row.size < slot_min:
            found.append(f"{row.name}: size {row.size:#x}, below STORE_SLOT_BYTES {slot_min:#x}")
    if row.flags & FLAGS["encrypted"]:
        found.append(f"{row.name}: encrypted flag, D8 has no flash encryption")
    return found


def place_problems(row, flash):
    align = APP_ALIGN if row.type == TYPES["app"] else SECTOR
    found = []
    if row.offset % align or row.size % align:
        found.append(f"{row.name}: offset {row.offset:#x} size {row.size:#x} not {align:#x} aligned")
    if row.offset < TABLE_END:
        found.append(f"{row.name}: offset {row.offset:#x} is under the partition table")
    if row.offset + row.size > flash:
        found.append(f"{row.name}: ends at {row.offset + row.size:#x}, past the {flash:#x} flash")
    return found


def overlap_problems(rows):
    ordered = sorted(rows, key=lambda row: row.offset)
    return [
        f"{low.name} and {high.name} overlap"
        for low, high in zip(ordered, ordered[1:])
        if low.offset + low.size > high.offset
    ]


def table_problems(rows):
    slot_min = slot_min_bytes()
    flash = flash_bytes()
    found = name_problems(rows) + overlap_problems(rows)
    for row in rows:
        found += kind_problems(row, slot_min) + place_problems(row, flash)
    return found


def sdkconfig_problems(text):
    lines = set(text.splitlines())
    flash_line = f"CONFIG_ESPTOOLPY_FLASHSIZE_{flash_bytes() // (1024 * 1024)}MB=y"
    found = [f"missing {line}" for line in (*SDKCONFIG_REQUIRED, flash_line) if line not in lines]
    found += [f"{name}=y, spec 10 and D8 forbid it" for name in SDKCONFIG_FORBIDDEN if f"{name}=y" in lines]
    return found


def built_table_problems(blob, rows):
    built = parse_binary(blob)
    if built == rows:
        return []
    return [f"built table differs from partitions.csv: built {built}, csv {rows}"]


def main(argv):
    rows = parse_csv(PARTITIONS.read_text(encoding="utf-8"))
    found = table_problems(rows) + sdkconfig_problems(SDKCONFIG_DEFAULTS.read_text(encoding="utf-8"))
    if argv[:1] == ["--built"]:
        build = Path(argv[1])
        blob = (build / "partition_table" / "partition-table.bin").read_bytes()
        found += built_table_problems(blob, rows)
        found += [f"built sdkconfig: {line}" for line in sdkconfig_problems((build / "sdkconfig").read_text())]
    for line in found:
        print(line, file=sys.stderr)
    if found:
        return 1
    print(f"partitions: {len(rows)} rows match spec 10 ({', '.join(row.name for row in rows)})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
