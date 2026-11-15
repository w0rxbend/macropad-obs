# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Solids. build123d is imported only when a venv asks for a build."""


def build_solids():
    import build123d as bd

    # One wedge. The glass is not a second tilted face.
    plate = bd.Pos(0, 0, 6) * bd.Rot(0, -8, 0) * bd.Box(95.2, 157.2, 5.0)
    return plate
