#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""check_partitions passes on the tree and fails on one broken copy per rule."""

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_partitions

CSV_TEXT = check_partitions.PARTITIONS.read_text(encoding="utf-8")
SDKCONFIG_TEXT = check_partitions.SDKCONFIG_DEFAULTS.read_text(encoding="utf-8")


def csv_problems_after(old, new):
    text = CSV_TEXT.replace(old, new)
    assert text != CSV_TEXT, f"{old!r} is not in partitions.csv"
    return check_partitions.table_problems(check_partitions.parse_csv(text))


def row_line(name):
    return next(line for line in CSV_TEXT.splitlines() if line.startswith(name + ","))


def packed_table(rows):
    """A partition-table.bin as gen_esp32part.py writes it: 32-byte entries, then 0xFF."""
    entries = b"".join(
        struct.pack("<HBBII16sI", 0x50AA, row.type, row.subtype, row.offset, row.size,
                    row.name.encode(), row.flags)
        for row in rows
    )
    md5_entry = b"\xeb\xeb" + b"\xff" * 14 + bytes(16)
    return entries + md5_entry + b"\xff" * 32


class TreeTest(unittest.TestCase):
    def test_tree_table_has_no_problem(self):
        self.assertEqual(check_partitions.table_problems(check_partitions.parse_csv(CSV_TEXT)), [])

    def test_tree_sdkconfig_defaults_have_no_problem(self):
        self.assertEqual(check_partitions.sdkconfig_problems(SDKCONFIG_TEXT), [])

    def test_slot_minimum_is_store_slot_bytes(self):
        self.assertEqual(check_partitions.slot_min_bytes(), 4096 + 16384)

    def test_flash_size_comes_from_the_n16_module(self):
        self.assertEqual(check_partitions.flash_bytes(), 16 * 1024 * 1024)


class TableTest(unittest.TestCase):
    def test_missing_cred_is_rejected(self):
        found = csv_problems_after(row_line("cred") + "\n", "")
        self.assertTrue(any("cred" in line for line in found), found)

    def test_extra_data_partition_is_rejected(self):
        found = csv_problems_after(row_line("cfg_b"), row_line("cfg_b") + "\nspare, data, 0x41, 0xF00000, 0x1000,")
        self.assertTrue(any("spare" in line for line in found), found)

    def test_second_app_is_rejected(self):
        found = csv_problems_after(row_line("cfg_b"), row_line("cfg_b") + "\nota_0, app, ota_0, 0x800000, 0x100000,")
        self.assertTrue(any("app" in line for line in found), found)

    def test_cred_that_is_not_nvs_is_rejected(self):
        found = csv_problems_after(row_line("cred"), row_line("cred").replace(" nvs,", " 0x42,"))
        self.assertTrue(any("cred" in line and "nvs" in line for line in found), found)

    def test_cfg_slot_that_is_nvs_is_rejected(self):
        found = csv_problems_after(row_line("cfg_a"), row_line("cfg_a").replace(" 0x40,", " nvs,"))
        self.assertTrue(any("cfg_a" in line and "raw" in line for line in found), found)

    def test_cfg_slot_below_store_slot_bytes_is_rejected(self):
        line = row_line("cfg_b")
        size = line.split(",")[4]
        found = csv_problems_after(line, line.replace(size, " 0x4000"))
        self.assertTrue(any("cfg_b" in text and "size" in text for text in found), found)

    def test_encrypted_flag_is_rejected(self):
        found = csv_problems_after(row_line("cred"), row_line("cred").rstrip(",") + ", encrypted")
        self.assertTrue(any("encrypted" in line for line in found), found)

    def test_unaligned_data_offset_is_rejected(self):
        line = row_line("cfg_a")
        offset = line.split(",")[3]
        found = csv_problems_after(line, line.replace(offset, f" {int(offset, 0) + 0x800:#x}"))
        self.assertTrue(any("cfg_a" in text and "align" in text for text in found), found)

    def test_overlap_is_rejected(self):
        line = row_line("cfg_b")
        offset = row_line("cfg_a").split(",")[3]
        found = csv_problems_after(line, line.replace(line.split(",")[3], offset))
        self.assertTrue(any("overlap" in text for text in found), found)

    def test_partition_past_the_flash_end_is_rejected(self):
        line = row_line("cfg_b")
        found = csv_problems_after(line, line.replace(line.split(",")[3], " 0xFF8000"))
        self.assertTrue(any("flash" in text for text in found), found)

    def test_partition_over_the_table_is_rejected(self):
        line = row_line("nvs")
        found = csv_problems_after(line, line.replace(line.split(",")[3], " 0x8000"))
        self.assertTrue(any("table" in text for text in found), found)

    def test_sizes_with_k_and_m_suffixes_parse(self):
        rows = check_partitions.parse_csv("a, data, nvs, 0x9000, 24K,\nb, app, factory, 0x10000, 4M,\n")
        self.assertEqual([row.size for row in rows], [24 * 1024, 4 * 1024 * 1024])


class SdkconfigTest(unittest.TestCase):
    def test_nvs_encryption_is_rejected(self):
        found = check_partitions.sdkconfig_problems(SDKCONFIG_TEXT + "CONFIG_NVS_ENCRYPTION=y\n")
        self.assertTrue(any("CONFIG_NVS_ENCRYPTION" in line for line in found), found)

    def test_flash_encryption_is_rejected(self):
        found = check_partitions.sdkconfig_problems(SDKCONFIG_TEXT + "CONFIG_SECURE_FLASH_ENC_ENABLED=y\n")
        self.assertTrue(any("CONFIG_SECURE_FLASH_ENC_ENABLED" in line for line in found), found)

    def test_secure_boot_is_rejected(self):
        found = check_partitions.sdkconfig_problems(SDKCONFIG_TEXT + "CONFIG_SECURE_BOOT=y\n")
        self.assertTrue(any("CONFIG_SECURE_BOOT" in line for line in found), found)

    def test_not_set_comment_passes(self):
        found = check_partitions.sdkconfig_problems(SDKCONFIG_TEXT + "# CONFIG_SECURE_BOOT is not set\n")
        self.assertEqual(found, [])

    def test_missing_custom_table_is_rejected(self):
        text = SDKCONFIG_TEXT.replace("CONFIG_PARTITION_TABLE_CUSTOM=y\n", "")
        found = check_partitions.sdkconfig_problems(text)
        self.assertTrue(any("CONFIG_PARTITION_TABLE_CUSTOM=y" in line for line in found), found)

    def test_wrong_flash_size_is_rejected(self):
        text = SDKCONFIG_TEXT.replace("FLASHSIZE_16MB", "FLASHSIZE_4MB")
        found = check_partitions.sdkconfig_problems(text)
        self.assertTrue(any("FLASHSIZE_16MB" in line for line in found), found)


class BuiltTableTest(unittest.TestCase):
    def test_binary_reads_back_as_the_csv_rows(self):
        rows = check_partitions.parse_csv(CSV_TEXT)
        self.assertEqual(check_partitions.parse_binary(packed_table(rows)), rows)

    def test_binary_that_differs_from_the_csv_is_reported(self):
        rows = check_partitions.parse_csv(CSV_TEXT)
        moved = [row._replace(size=row.size * 2) if row.name == "cred" else row for row in rows]
        found = check_partitions.built_table_problems(packed_table(moved), rows)
        self.assertTrue(any("cred" in line for line in found), found)

    def test_binary_with_a_bad_entry_magic_is_rejected(self):
        with self.assertRaises(ValueError):
            check_partitions.parse_binary(b"\x00\x00" + b"\x00" * 30)


if __name__ == "__main__":
    unittest.main()
