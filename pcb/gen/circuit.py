# SPDX-License-Identifier: CERN-OHL-S-2.0
"""In-memory netlist. No pcbnew import. LCSC cells that were not fetched are UNVERIFIED."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Package pin for GPIO n. Donor RP2040 QFN-56 map. GPIO 0 and 1 stay off the named header.
GPIO_PIN = [
    2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17, 18, 27, 28, 29, 30, 31, 32, 34, 35, 36,
    37, 38, 39, 40, 41,
]

IOVDD = (1, 10, 22, 33, 42, 49)
DVDD = (23, 50)
USB_VDD = 48
ADC_AVDD = 43
VREG_VIN = 44
VREG_VOUT = 45

LOCKED_LCSC = {"C2040", "C97521", "C596730"}

# Planned routes. Lengths are the polyline, so moving a point can fail the contract.
USB_DP = ((0.0, 0.0), (12.0, 0.0))
USB_DM = ((0.0, 0.0), (11.0, 0.0))
QSPI = {
    "QSPI_SS": ((0.0, 0.0), (14.0, 0.0)),
    "QSPI_SCLK": ((0.0, 0.0), (10.0, 0.0)),
    "QSPI_SD0": ((0.0, 0.0), (12.0, 0.0)),
    "QSPI_SD1": ((0.0, 0.0), (11.0, 0.0)),
    "QSPI_SD2": ((0.0, 0.0), (13.0, 0.0)),
    "QSPI_SD3": ((0.0, 0.0), (9.0, 0.0)),
}
XIN = ((0.0, 0.0), (8.0, 0.0))
XOUT = ((0.0, 0.0), (8.0, 0.0))

SOCKET_HALF = 7.2
FH12_COURTYARD = (15.0, 5.0)  # MEASURE until the Hirose drawing is on the footprint
TACT_COURTYARD = (6.2, 4.2)
ENCODER_BODY = (12.4, 12.4)


@dataclass
class Part:
    designator: str
    comment: str
    footprint: str
    lcsc: str
    manufacturer: str
    mpn: str
    layer: str
    x: float
    y: float
    rotation: float
    hand: bool = False
    note: str = ""


@dataclass
class Board:
    parts: list[Part] = field(default_factory=list)
    nets: dict[str, set[tuple[str, str]]] = field(default_factory=dict)

    def add(self, part: Part) -> None:
        self.parts.append(part)

    def tie(self, net: str, designator: str, pin: str) -> None:
        self.nets.setdefault(net, set()).add((designator, pin))


def path_len(points: tuple[tuple[float, float], ...]) -> float:
    total = 0.0
    for start, end in zip(points, points[1:]):
        total += math.hypot(end[0] - start[0], end[1] - start[1])
    return total


def rect(cx: float, cy: float, width: float, height: float) -> tuple[float, float, float, float]:
    return (cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)


def circle_hits_rect(cx: float, cy: float, radius: float, box: tuple[float, float, float, float]) -> bool:
    x0, y0, x1, y1 = box
    nearest_x = min(max(cx, x0), x1)
    nearest_y = min(max(cy, y0), y1)
    dx = cx - nearest_x
    dy = cy - nearest_y
    return dx * dx + dy * dy <= radius * radius


def keepout_hits(board_toml: dict, radius: float) -> list[str]:
    """Names of features a keep-out circle touches. Boundary contact is a hit."""
    pcb = board_toml["pcb"]
    hits = []
    circles = [(x, y) for x, y in pcb["holes"]]
    boxes = []
    for x in pcb["key_x"]:
        for y in pcb["key_y"]:
            boxes.append((f"socket {x:.2f},{y:.2f}", rect(x, y, SOCKET_HALF * 2, SOCKET_HALF * 2)))
    kx, ky = pcb["knob"]
    boxes.append(("encoder", rect(kx, ky, ENCODER_BODY[0], ENCODER_BODY[1])))
    ox, oy = pcb["display_origin"]
    w, h = pcb["display_size"]
    boxes.append(("glass", (ox, oy, ox + w, oy + h)))
    fx, fy = pcb["fpc"]
    boxes.append(("fh12", rect(fx, fy, FH12_COURTYARD[0], FH12_COURTYARD[1])))
    for name, centre in (("boot", pcb["boot"]), ("reset", pcb["reset"])):
        boxes.append((name, rect(centre[0], centre[1], TACT_COURTYARD[0], TACT_COURTYARD[1])))
    for hx, hy in circles:
        for name, box in boxes:
            if circle_hits_rect(hx, hy, radius, box):
                hits.append(f"{name} @ ({hx}, {hy})")
    return hits


def _passives(board: Board) -> None:
    n = 1

    def cap(value: str, net_a: str, net_b: str, pin_a: str) -> None:
        nonlocal n
        des = f"C{n}"
        n += 1
        board.add(Part(des, value, "C_0402", "UNVERIFIED", "UNVERIFIED", value, "bottom", 0, 0, 0))
        board.tie(net_a, des, "1")
        board.tie(net_b, des, "2")
        board.tie(net_a, "U1", pin_a)

    for pin in IOVDD:
        cap("100 nF", "V3", "GND", str(pin))
    for pin in DVDD:
        cap("100 nF", "V1V1", "GND", str(pin))
    cap("100 nF", "V3", "GND", str(USB_VDD))
    cap("100 nF", "V3", "GND", str(ADC_AVDD))
    cap("1 uF", "V3", "GND", str(VREG_VIN))
    cap("1 uF", "V1V1", "GND", str(VREG_VOUT))
    board.add(Part("C20", "2.2 uF", "C_0603", "UNVERIFIED", "UNVERIFIED", "2.2 uF", "bottom", 0, 0, 0))
    board.tie("V5", "C20", "1")
    board.tie("GND", "C20", "2")
    board.add(Part("C21", "10 uF", "C_0805", "UNVERIFIED", "UNVERIFIED", "10 uF", "bottom", 0, 0, 0))
    board.tie("V3", "C21", "1")
    board.tie("GND", "C21", "2")
    board.add(Part("C22", "15 pF", "C_0402", "UNVERIFIED", "UNVERIFIED", "15 pF", "bottom", 0, 0, 0))
    board.add(Part("C23", "15 pF", "C_0402", "UNVERIFIED", "UNVERIFIED", "15 pF", "bottom", 0, 0, 0))
    board.tie("XIN", "C22", "1")
    board.tie("GND", "C22", "2")
    board.tie("XOUT", "C23", "1")
    board.tie("GND", "C23", "2")


def build(board_toml: dict) -> Board:
    pcb = board_toml["pcb"]
    keys = board_toml["keys"]["gpio"]
    knob = board_toml["knob"]
    disp = board_toml["display"]
    board = Board()
    board.add(
        Part(
            "U1",
            "RP2040",
            "QFN-56",
            "C2040",
            "Raspberry Pi",
            "RP2040",
            "bottom",
            44.0,
            40.0,
            0,
        )
    )
    board.add(
        Part(
            "U2",
            "W25Q128JVSIQ, SOIC-8 208 mil",
            "SOIC-8-208mil",
            "C97521",
            "Winbond",
            "W25Q128JVSIQ",
            "bottom",
            60.0,
            40.0,
            0,
        )
    )
    board.add(
        Part("J1", "USB-C", "USB-C-16P", "UNVERIFIED", "HRO", "TYPE-C-31-M-12", "bottom", pcb["usb_x"], 149.0, 0)
    )
    board.add(
        Part(
            "U3",
            "AP2112K-3.3",
            "SOT-23-5",
            "UNVERIFIED",
            "Diodes",
            "AP2112K-3.3TRG1",
            "bottom",
            20.0,
            130.0,
            0,
        )
    )
    board.add(
        Part("U4", "USBLC6-2SC6", "SOT-23-6", "UNVERIFIED", "ST", "USBLC6-2SC6", "bottom", 30.0, 140.0, 0)
    )
    board.add(Part("F1", "polyfuse 500 mA hold", "nSMD050", "UNVERIFIED", "UNVERIFIED", "nSMD050", "bottom", 40, 145, 0))
    board.add(
        Part("Y1", "12 MHz", "ABM8", "UNVERIFIED", "Abracon", "ABM8-272-T3", "bottom", 50.0, 36.0, 0)
    )
    board.add(Part("R1", "5.1 k", "R_0402", "UNVERIFIED", "UNVERIFIED", "5.1 k", "bottom", 0, 0, 0))
    board.add(Part("R2", "5.1 k", "R_0402", "UNVERIFIED", "UNVERIFIED", "5.1 k", "bottom", 0, 0, 0))
    board.add(Part("R3", "27", "R_0402", "UNVERIFIED", "UNVERIFIED", "27", "bottom", 0, 0, 0))
    board.add(Part("R4", "27", "R_0402", "UNVERIFIED", "UNVERIFIED", "27", "bottom", 0, 0, 0))
    board.add(Part("R5", "1 k", "R_0402", "UNVERIFIED", "UNVERIFIED", "1 k", "bottom", 0, 0, 0))
    board.add(Part("R6", "1 k", "R_0402", "UNVERIFIED", "UNVERIFIED", "1 k", "bottom", 0, 0, 0))
    board.add(Part("R20", "0", "R_0402", "UNVERIFIED", "UNVERIFIED", "0", "bottom", 0, 0, 0))
    board.add(Part("R21", "62", "R_1206", "UNVERIFIED", "UNVERIFIED", "62 1%", "bottom", 0, 0, 0))
    board.add(Part("R22", "100 k", "R_0402", "UNVERIFIED", "UNVERIFIED", "100 k", "bottom", 0, 0, 0))
    board.add(
        Part(
            "Q1",
            "N-channel, Rds(on) at Vgs=2.5 V, Id ≥ 200 mA, SOT-23",
            "SOT-23",
            "UNVERIFIED",
            "UNVERIFIED",
            "UNVERIFIED",
            "bottom",
            0,
            0,
            0,
        )
    )
    fx, fy = pcb["fpc"]
    board.add(
        Part(
            "J2",
            "FH12-20S-0.5SH(55)",
            "FH12-20S-0.5SH",
            "C596730",
            "Hirose",
            "FH12-20S-0.5SH(55)",
            "top",
            fx,
            fy,
            0,
        )
    )
    bx, by = pcb["boot"]
    rx, ry = pcb["reset"]
    board.add(
        Part("SW10", "TS-1187A", "TS-1187A", "UNVERIFIED", "UNVERIFIED", "TS-1187A-B-A-B", "bottom", bx, by, 0)
    )
    board.add(
        Part("SW11", "TS-1187A", "TS-1187A", "UNVERIFIED", "UNVERIFIED", "TS-1187A-B-A-B", "bottom", rx, ry, 0)
    )
    rotation = float(pcb["mx_rotation_deg"])
    n = 0
    for y in pcb["key_y"]:
        for x in pcb["key_x"]:
            gpio = keys[n]
            des = f"SW{n + 1}"
            n += 1
            board.add(
                Part(
                    des,
                    "MX hot-swap, Kailh CPG151101S11 class",
                    "MX-hotswap",
                    "UNVERIFIED",
                    "Kailh",
                    "CPG151101S11",
                    "bottom",
                    x,
                    y,
                    rotation,
                )
            )
            board.tie(f"GPIO{gpio}", des, "1")
            board.tie("GND", des, "2")
            board.tie(f"GPIO{gpio}", "U1", str(GPIO_PIN[gpio]))
    kx, ky = pcb["knob"]
    board.add(
        Part(
            "EN1",
            "Alps EC11E18244AU",
            "EC11",
            "UNVERIFIED",
            "Alps",
            "EC11E18244AU",
            "top",
            kx,
            ky,
            0,
            hand=True,
            note="through-hole, hand soldered",
        )
    )
    ox, oy = pcb["display_origin"]
    board.add(
        Part(
            "DS1",
            "Raystar RFJ240M-ALW-DNN",
            "glass",
            "UNVERIFIED",
            "Raystar",
            "RFJ240M-ALW-DNN",
            "top",
            ox,
            oy,
            0,
            hand=True,
            note="sourced glass, not machine placed",
        )
    )
    _passives(board)
    _power_and_io(board, knob, disp)
    return board


def _power_and_io(board: Board, knob: dict, disp: dict) -> None:
    for pin in IOVDD:
        board.tie("V3", "U1", str(pin))
    for pin in DVDD:
        board.tie("V1V1", "U1", str(pin))
    board.tie("V3", "U1", str(USB_VDD))
    board.tie("V3", "U1", str(ADC_AVDD))
    board.tie("V3", "U1", str(VREG_VIN))
    board.tie("V1V1", "U1", str(VREG_VOUT))
    board.tie("GND", "U1", "19")
    board.tie("GND", "U1", "57")
    board.tie("XIN", "U1", "20")
    board.tie("XOUT", "U1", "21")
    board.tie("XIN", "Y1", "1")
    board.tie("XOUT", "R5", "1")
    board.tie("Y1", "R5", "2")
    board.tie("USB_DM", "U1", "46")
    board.tie("USB_DP", "U1", "47")
    board.tie("USB_DM", "R3", "1")
    board.tie("USB_DP", "R4", "1")
    board.tie("USB_DM_C", "R3", "2")
    board.tie("USB_DP_C", "R4", "2")
    board.tie("USB_DM_C", "J1", "D-")
    board.tie("USB_DP_C", "J1", "D+")
    board.tie("USB_DM_C", "U4", "D-")
    board.tie("USB_DP_C", "U4", "D+")
    board.tie("GND", "U4", "GND")
    board.tie("VBUS", "J1", "VBUS")
    board.tie("VBUS", "F1", "1")
    board.tie("V5", "F1", "2")
    board.tie("V5", "U3", "IN")
    board.tie("V3", "U3", "OUT")
    board.tie("GND", "U3", "GND")
    board.tie("CC1", "J1", "CC1")
    board.tie("CC2", "J1", "CC2")
    board.tie("CC1", "R1", "1")
    board.tie("CC2", "R2", "1")
    board.tie("GND", "R1", "2")
    board.tie("GND", "R2", "2")
    board.tie("QSPI_SS", "U1", "56")
    board.tie("QSPI_SCLK", "U1", "52")
    board.tie("QSPI_SD0", "U1", "53")
    board.tie("QSPI_SD1", "U1", "55")
    board.tie("QSPI_SD2", "U1", "54")
    board.tie("QSPI_SD3", "U1", "51")
    board.tie("QSPI_SS", "U2", "1")
    board.tie("QSPI_SD1", "U2", "2")
    board.tie("QSPI_SD2", "U2", "3")
    board.tie("GND", "U2", "4")
    board.tie("QSPI_SD0", "U2", "5")
    board.tie("QSPI_SCLK", "U2", "6")
    board.tie("QSPI_SD3", "U2", "7")
    board.tie("V3", "U2", "8")
    board.tie("QSPI_SS", "R6", "1")
    board.tie("BOOT", "R6", "2")
    board.tie("BOOT", "SW10", "1")
    board.tie("GND", "SW10", "2")
    board.tie("RUN", "U1", "26")
    board.tie("RUN", "SW11", "1")
    board.tie("GND", "SW11", "2")
    board.tie("SWCLK", "U1", "24")
    board.tie("SWDIO", "U1", "25")
    for pad, net in (("A", "GPIO12"), ("B", "GPIO13"), ("C", "GND"), ("S1", "GPIO11"), ("S2", "GND")):
        board.tie(net, "EN1", pad)
    board.tie("GPIO12", "U1", str(GPIO_PIN[knob["gpio_a"]]))
    board.tie("GPIO13", "U1", str(GPIO_PIN[knob["gpio_b"]]))
    board.tie("GPIO11", "U1", str(GPIO_PIN[knob["gpio_push"]]))
    # FPC pins. Pin 14 IM3 is strapped to GND through R20. SDO and TE stay open.
    fpc = {
        "1": "GND",
        "2": "BL_A",
        "3": "BL_K",
        "4": "GND",
        "5": "V3",
        "6": "GPIO21",
        "7": "GPIO19",
        "8": "GPIO18",
        "9": "GPIO17",
        "10": "GPIO20",
        "11": "GND",
        "14": "IM3",
        "15": "GND",
        "20": "GND",
    }
    for pin, net in fpc.items():
        board.tie(net, "J2", pin)
    board.tie("IM3", "R20", "1")
    board.tie("GND", "R20", "2")
    board.tie("V5", "R21", "1")
    board.tie("BL_A", "R21", "2")
    board.tie("BL_K", "Q1", "D")
    board.tie("GND", "Q1", "S")
    board.tie("GPIO22", "Q1", "G")
    board.tie("GPIO22", "R22", "1")
    board.tie("GND", "R22", "2")
    board.tie("GPIO22", "U1", str(GPIO_PIN[disp["gpio_bl"]]))
    for gpio, pin_name in (
        (disp["gpio_sck"], "8"),
        (disp["gpio_mosi"], "7"),
        (disp["gpio_cs"], "9"),
        (disp["gpio_dc"], "10"),
        (disp["gpio_reset"], "6"),
    ):
        board.tie(f"GPIO{gpio}", "U1", str(GPIO_PIN[gpio]))
        board.tie(f"GPIO{gpio}", "J2", pin_name)


def forbidden_lcsc(board: Board) -> list[str]:
    banned = {"C165948", "C51118", "C7519", "C318884", "C49352235", "C202365"}
    return [part.designator for part in board.parts if part.lcsc in banned or (
        part.lcsc != "UNVERIFIED" and part.lcsc not in LOCKED_LCSC
    )]
