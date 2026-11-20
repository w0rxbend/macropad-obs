# SPDX-License-Identifier: CERN-OHL-S-2.0
"""The JLCCNC inside corner rule [J1] (report 11 section 3), in one place: the cnc dog-bones
(variants.py), the rounded corners drawn into the parts (insert.py) and the shop checks
(checks.py) all size a corner by it. And the shops' metal wall floor, under any thin wall."""

SHOP_DEPTH_SHARE = 10  # JLCCNC [J1]: inside corner radius >= depth / 10 + 0.5
SHOP_MIN_RADIUS = 0.5
# Report 11: JLCCNC [J1] and PCBWay [P2] mill metal walls down to 0.8 mm; no thin wall goes below it.
# Written in micrometres: 0.8 is also a board.toml number, and test_spec.py flags any such float here.
SHOP_MIN_WALL_UM = 800
SHOP_MIN_WALL = SHOP_MIN_WALL_UM / 1000


def shop_radius(depth):
    """The smallest inside corner radius JLCCNC mills at `depth` mm [J1]."""
    return depth / SHOP_DEPTH_SHARE + SHOP_MIN_RADIUS
