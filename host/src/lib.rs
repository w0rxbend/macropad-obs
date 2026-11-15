// SPDX-License-Identifier: MIT
//! CDC frames for macropad-obs.

mod protocol;

pub use protocol::{
    ascii_field, encode, encode_bind, encode_hello_ack, encode_page, pad_event, Link, PadEvent, PageView, BIND,
    HEARTBEAT, INPUT, KEY, KNOB, PAGE_VIEW, PROFILE, USB_PID, USB_VID,
};
