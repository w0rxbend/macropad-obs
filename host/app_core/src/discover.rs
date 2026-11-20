// SPDX-License-Identifier: MIT
//! Finds the pad among the serial ports by USB VID/PID and serial string, not by a fixed path.
//! `serialport::available_ports` reads the USB fields through libudev on Linux.

use std::fmt;
use std::time::Duration;

use obs_core::{USB_PID, USB_VID};
use serialport::{SerialPort, SerialPortType};

/// The CDC port ignores the baud rate (`docs/protocol.md`); the OS still wants one.
const BAUD: u32 = 115_200;
/// Short, so `Link` checks its reply deadline often.
const READ_TIMEOUT: Duration = Duration::from_millis(20);

/// One USB serial port as the OS lists it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UsbPort {
    pub path: String,
    pub vid: u16,
    pub pid: u16,
    pub serial: Option<String>,
}

#[derive(Debug)]
pub enum DiscoverError {
    Serial(serialport::Error),
    /// No port has the pad's VID and PID, or none has the serial asked for.
    NoPad,
    /// More than one pad and no serial to choose: their serial strings.
    SeveralPads(Vec<Option<String>>),
}

impl fmt::Display for DiscoverError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Serial(err) => write!(f, "serial port: {err}"),
            Self::NoPad => f.write_str("no pad found"),
            Self::SeveralPads(serials) => write!(f, "{} pads found; choose one by serial", serials.len()),
        }
    }
}

impl std::error::Error for DiscoverError {}

impl From<serialport::Error> for DiscoverError {
    fn from(err: serialport::Error) -> Self {
        Self::Serial(err)
    }
}

/// Every USB serial port the OS lists, pad or not.
pub fn usb_ports() -> Result<Vec<UsbPort>, DiscoverError> {
    let ports = serialport::available_ports()?;
    Ok(ports
        .into_iter()
        .filter_map(|port| match port.port_type {
            SerialPortType::UsbPort(usb) => {
                Some(UsbPort { path: port.port_name, vid: usb.vid, pid: usb.pid, serial: usb.serial_number })
            }
            _ => None,
        })
        .collect())
}

/// The ports with the pad's VID and PID.
pub fn pads(ports: &[UsbPort]) -> Vec<UsbPort> {
    ports.iter().filter(|port| port.vid == USB_VID && port.pid == USB_PID).cloned().collect()
}

/// The pad with `serial`, or with no serial asked the only pad there is.
pub fn pick(ports: &[UsbPort], serial: Option<&str>) -> Result<UsbPort, DiscoverError> {
    let mut found = pads(ports);
    if let Some(serial) = serial {
        found.retain(|port| port.serial.as_deref() == Some(serial));
    }
    match found.len() {
        0 => Err(DiscoverError::NoPad),
        1 => Ok(found.remove(0)),
        _ => Err(DiscoverError::SeveralPads(found.into_iter().map(|port| port.serial).collect())),
    }
}

/// Opens the pad's port and asserts DTR: TinyUSB counts the CDC port as connected only then.
pub fn open(port: &UsbPort) -> Result<Box<dyn SerialPort>, DiscoverError> {
    let mut opened = serialport::new(&port.path, BAUD).timeout(READ_TIMEOUT).open()?;
    opened.write_data_terminal_ready(true)?;
    Ok(opened)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn port(path: &str, vid: u16, pid: u16, serial: Option<&str>) -> UsbPort {
        UsbPort { path: path.into(), vid, pid, serial: serial.map(str::to_owned) }
    }

    fn listed() -> Vec<UsbPort> {
        vec![
            port("/dev/ttyACM0", 0x303A, 0x1001, Some("boot")),
            port("/dev/ttyACM1", USB_VID, USB_PID, Some("A1")),
            port("/dev/ttyUSB0", 0x0403, 0x6001, None),
            port("/dev/ttyACM2", USB_VID, USB_PID, Some("B2")),
        ]
    }

    #[test]
    fn pads_keeps_only_the_pad_vid_and_pid() {
        let paths: Vec<_> = pads(&listed()).into_iter().map(|port| port.path).collect();
        assert_eq!(paths, ["/dev/ttyACM1", "/dev/ttyACM2"]);
    }

    #[test]
    fn a_serial_picks_its_pad_wherever_it_is() {
        assert_eq!(pick(&listed(), Some("B2")).expect("found").path, "/dev/ttyACM2");
    }

    #[test]
    fn a_serial_on_another_device_is_not_a_pad() {
        assert!(matches!(pick(&listed(), Some("boot")), Err(DiscoverError::NoPad)));
    }

    #[test]
    fn one_pad_needs_no_serial() {
        let one = vec![port("/dev/ttyACM5", USB_VID, USB_PID, None), port("/dev/ttyUSB0", 0x0403, 0x6001, None)];
        assert_eq!(pick(&one, None).expect("found").path, "/dev/ttyACM5");
    }

    #[test]
    fn two_pads_and_no_serial_names_both() {
        let Err(DiscoverError::SeveralPads(serials)) = pick(&listed(), None) else { panic!("two pads") };
        assert_eq!(serials, [Some("A1".to_owned()), Some("B2".to_owned())]);
    }

    #[test]
    fn no_pad_listed_is_no_pad() {
        assert!(matches!(pick(&[], None), Err(DiscoverError::NoPad)));
    }
}
