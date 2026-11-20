// SPDX-License-Identifier: MIT
//! Firmware update (spec row 11b, R18 section 8, criterion 14): `BOOTLOADER`, the ROM port
//! 303a:1001 within 10 s, `espflash` writes the image and hard resets, then the pad is back within
//! 30 s with the image's git hash in `INFO` and no credential set.
//!
//! `Host` is the machine side (port listing, opening, flashing, clock), so the steps run against a
//! fake in the tests. `System` is the real one. The real run is task 4.9.

use std::borrow::Cow;
use std::error::Error;
use std::fmt;
use std::fs::File;
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::thread;
use std::time::{Duration, Instant};

use espflash::connection::{Connection, ResetAfterOperation, ResetBeforeOperation};
use espflash::flasher::Flasher;
use espflash::image_format::Segment as EspSegment;
use espflash::target::{Chip, DefaultProgressCallback};
use obs_core::protocol::{Info, Message, CRED_OK};
use serialport::{FlowControl, SerialPort, UsbPortInfo};

use crate::discover::{self, DiscoverError, UsbPort};
use crate::session::{Session, SessionError};

/// The ESP32-S3 ROM download port on the USB-Serial/JTAG (espflash `USB_SERIAL_JTAG_PID`).
pub const ROM_VID: u16 = 0x303A;
pub const ROM_PID: u16 = 0x1001;
/// From the `BOOTLOADER` reply to the ROM port listed (criterion 14).
pub const ROM_WAIT: Duration = Duration::from_secs(10);
/// From the end of the write to the pad answering `INFO` (criterion 14).
pub const BACK_WAIT: Duration = Duration::from_secs(30);
/// Between two port listings.
const POLL: Duration = Duration::from_millis(100);
/// The ROM sync rate; espflash connects at this rate.
const ROM_BAUD: u32 = 115_200;

/// Bytes for one flash address: the bootloader, the partition table, the app, or one merged image.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Segment {
    pub addr: u32,
    pub bytes: Vec<u8>,
}

/// What the update writes, and the git hash the new firmware puts in `INFO`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Image {
    pub segments: Vec<Segment>,
    pub git_hash: [u8; 4],
}

/// The first byte of an ESP image header: a merged image starts with the bootloader's.
const IMAGE_MAGIC: u8 = 0xE9;
/// The flash of the ESP32-S3-WROOM-1-N16R2 (16 MB).
const FLASH_BYTES: usize = 16 * 1024 * 1024;
/// The git hash file beside the image: `just firmware` writes the commit it built from.
const GIT_HASH_EXTENSION: &str = "git_hash";

/// Why an image file cannot be written to the pad.
#[derive(Debug)]
pub enum ImageError {
    Read {
        path: PathBuf,
        err: io::Error,
    },
    NotAnImage,
    TooBig,
    /// The git hash file does not hold 8 hex digits.
    BadHash,
}

impl fmt::Display for ImageError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Read { path, err } => write!(f, "cannot read {}: {err}", path.display()),
            Self::NotAnImage => f.write_str("the file is not an ESP32-S3 image (run `just firmware`)"),
            Self::TooBig => write!(f, "the image is larger than the {} MB flash", FLASH_BYTES >> 20),
            Self::BadHash => write!(f, "the .{GIT_HASH_EXTENSION} file beside the image does not hold 8 hex digits"),
        }
    }
}

impl Error for ImageError {}

impl Image {
    /// `just firmware`'s merged image at `path`, written from address 0 (bootloader, partition
    /// table, app), and the commit it was built from in the file beside it with the extension
    /// `git_hash`: the 8 hex digits the new firmware puts in `INFO`. The files are a trust
    /// boundary: an image is refused unless it starts with an ESP image header and fits the flash.
    pub fn load(path: &Path) -> Result<Self, ImageError> {
        let bytes = read_at_most(path, FLASH_BYTES + 1)?;
        if bytes.len() > FLASH_BYTES {
            return Err(ImageError::TooBig);
        }
        if bytes.first() != Some(&IMAGE_MAGIC) {
            return Err(ImageError::NotAnImage);
        }
        let hash_text = read_at_most(&path.with_extension(GIT_HASH_EXTENSION), 64)?;
        let git_hash = git_hash(&hash_text).ok_or(ImageError::BadHash)?;
        Ok(Self { segments: vec![Segment { addr: 0, bytes }], git_hash })
    }
}

fn read_at_most(path: &Path, limit: usize) -> Result<Vec<u8>, ImageError> {
    let failed = |err| ImageError::Read { path: path.to_owned(), err };
    let mut bytes = Vec::new();
    File::open(path).and_then(|file| file.take(limit as u64).read_to_end(&mut bytes)).map_err(failed)?;
    Ok(bytes)
}

/// `git rev-parse --short=8` output, a trailing newline allowed, as the `INFO` bytes.
fn git_hash(text: &[u8]) -> Option<[u8; 4]> {
    let digits = std::str::from_utf8(text).ok()?.trim_end();
    if digits.len() != 8 || !digits.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return None;
    }
    u32::from_str_radix(digits, 16).ok().map(u32::to_be_bytes)
}

/// An `espflash` error, or a fake one in the tests.
pub type FlashError = Box<dyn Error + Send + Sync>;

/// What the update needs from the machine.
pub trait Host {
    type Port: Read + Write;
    /// Every USB serial port listed now.
    fn ports(&mut self) -> Result<Vec<UsbPort>, DiscoverError>;
    /// Opens the pad's CDC port.
    fn open(&mut self, pad: &UsbPort) -> Result<Self::Port, DiscoverError>;
    /// Writes every segment over the ROM port, then hard resets the chip.
    fn flash(&mut self, rom: &UsbPort, image: &Image) -> Result<(), FlashError>;
    /// Time since the host was made, from a monotonic clock.
    fn elapsed(&self) -> Duration;
    fn sleep(&mut self, wait: Duration);
}

#[derive(Debug)]
pub enum UpdateError {
    Discover(DiscoverError),
    /// `BOOTLOADER` failed or was refused: the pad stays as it was.
    Session(SessionError),
    /// No ROM port within `ROM_WAIT`.
    NoRomPort,
    /// A new Espressif port that is not the USB-Serial/JTAG ROM port.
    WrongPid {
        pid: u16,
    },
    /// More than one new ROM port: the update cannot tell which is the pad.
    SeveralRomPorts,
    Flash(FlashError),
    /// The pad was not listed again within `BACK_WAIT`.
    NotBack,
    /// The pad came back with another git hash: the new firmware does not run.
    OldFirmware {
        git_hash: [u8; 4],
    },
    /// The pad came back with a credential set: `BOOTLOADER` did not erase them (R1).
    CredentialsKept,
}

impl fmt::Display for UpdateError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Discover(err) => err.fmt(f),
            Self::Session(err) => err.fmt(f),
            Self::NoRomPort => write!(f, "no ROM port {ROM_VID:04x}:{ROM_PID:04x} within {} s", ROM_WAIT.as_secs()),
            Self::WrongPid { pid } => write!(f, "the pad came up as {ROM_VID:04x}:{pid:04x}, not {ROM_PID:04x}"),
            Self::SeveralRomPorts => f.write_str("more than one ROM port appeared; unplug the other boards"),
            Self::Flash(err) => write!(f, "flash write: {err}"),
            Self::NotBack => write!(f, "the pad did not come back within {} s", BACK_WAIT.as_secs()),
            Self::OldFirmware { git_hash } => {
                write!(f, "the pad runs git {}, not the image's", git_hash.map(|b| format!("{b:02x}")).concat())
            }
            Self::CredentialsKept => f.write_str("the pad kept a credential through the update"),
        }
    }
}

impl Error for UpdateError {}

impl From<DiscoverError> for UpdateError {
    fn from(err: DiscoverError) -> Self {
        Self::Discover(err)
    }
}

impl From<SessionError> for UpdateError {
    fn from(err: SessionError) -> Self {
        Self::Session(err)
    }
}

impl<P: Read + Write> Session<P> {
    /// `BOOTLOADER`: the pad erases both credentials, answers, then leaves the CDC port for ROM
    /// download (spec 8.2). The session ends with it.
    pub fn enter_download(mut self) -> Result<(), SessionError> {
        match self.ask(&Message::Bootloader)? {
            Message::CredStatus { code: CRED_OK } => Ok(()),
            Message::CredStatus { code } => Err(SessionError::CredentialRefused { code }),
            _ => Err(SessionError::BadReply("BOOTLOADER answered without CRED_STATUS")),
        }
    }
}

/// Updates the pad on `session`, listed as `pad`, to `image`. Returns the new firmware's `INFO`.
pub fn update<P: Read + Write, H: Host>(
    session: Session<P>,
    pad: &UsbPort,
    image: &Image,
    host: &mut H,
) -> Result<Info, UpdateError> {
    // Ports listed before are not the ROM port: another Espressif board may be plugged in.
    let before = host.ports()?;
    session.enter_download()?;
    let rom = wait_for_rom(host, &before)?;
    host.flash(&rom, image).map_err(UpdateError::Flash)?;
    let info = wait_for_pad(host, pad)?;
    if info.git_hash != image.git_hash {
        return Err(UpdateError::OldFirmware { git_hash: info.git_hash });
    }
    if info.obs_password_set || info.wifi_psk_set {
        return Err(UpdateError::CredentialsKept);
    }
    Ok(info)
}

fn wait_for_rom<H: Host>(host: &mut H, before: &[UsbPort]) -> Result<UsbPort, UpdateError> {
    let deadline = host.elapsed() + ROM_WAIT;
    loop {
        let ports = host.ports()?;
        let espressif: Vec<&UsbPort> =
            ports.iter().filter(|port| port.vid == ROM_VID && !before.contains(port)).collect();
        let roms: Vec<&UsbPort> = espressif.iter().copied().filter(|port| port.pid == ROM_PID).collect();
        match (roms.as_slice(), espressif.first()) {
            ([rom], _) => return Ok((*rom).clone()),
            ([], Some(other)) => return Err(UpdateError::WrongPid { pid: other.pid }),
            ([], None) => {}
            _ => return Err(UpdateError::SeveralRomPorts),
        }
        if host.elapsed() >= deadline {
            return Err(UpdateError::NoRomPort);
        }
        host.sleep(POLL);
    }
}

/// The pad listed again with its serial, opened, and its `INFO`. A pad listed but not yet open
/// (udev still applying the rule) is tried again; its last error is the result at the deadline.
fn wait_for_pad<H: Host>(host: &mut H, pad: &UsbPort) -> Result<Info, UpdateError> {
    let deadline = host.elapsed() + BACK_WAIT;
    let mut last = UpdateError::NotBack;
    loop {
        if let Ok(back) = discover::pick(&host.ports()?, pad.serial.as_deref()) {
            match host
                .open(&back)
                .map_err(UpdateError::from)
                .and_then(|port| Session::start(port).map_err(UpdateError::from))
            {
                Ok(session) => return Ok(session.info().clone()),
                Err(err) => last = err,
            }
        }
        if host.elapsed() >= deadline {
            return Err(last);
        }
        host.sleep(POLL);
    }
}

/// The real machine: serial ports through `serialport`, the write through `espflash`.
pub struct System {
    started: Instant,
}

impl System {
    pub fn new() -> Self {
        Self { started: Instant::now() }
    }
}

impl Default for System {
    fn default() -> Self {
        Self::new()
    }
}

impl Host for System {
    type Port = Box<dyn SerialPort>;

    fn ports(&mut self) -> Result<Vec<UsbPort>, DiscoverError> {
        discover::usb_ports()
    }

    fn open(&mut self, pad: &UsbPort) -> Result<Self::Port, DiscoverError> {
        discover::open(pad)
    }

    fn flash(&mut self, rom: &UsbPort, image: &Image) -> Result<(), FlashError> {
        flash_rom(rom, image).map_err(FlashError::from)
    }

    fn elapsed(&self) -> Duration {
        self.started.elapsed()
    }

    fn sleep(&mut self, wait: Duration) {
        thread::sleep(wait);
    }
}

/// The chip already waits in ROM download, so no reset before. The stub writes with verify on;
/// the hard reset after is espflash's own, at the end of the write.
fn flash_rom(rom: &UsbPort, image: &Image) -> Result<(), espflash::Error> {
    let serial = serialport::new(&rom.path, ROM_BAUD).flow_control(FlowControl::None).open_native()?;
    let info = UsbPortInfo {
        vid: rom.vid,
        pid: rom.pid,
        serial_number: rom.serial.clone(),
        manufacturer: None,
        product: None,
    };
    let connection =
        Connection::new(serial, info, ResetAfterOperation::HardReset, ResetBeforeOperation::NoReset, ROM_BAUD);
    let mut flasher = Flasher::connect(connection, true, true, false, Some(Chip::Esp32s3), None)?;
    let segments: Vec<EspSegment<'_>> = image
        .segments
        .iter()
        .map(|segment| EspSegment { addr: segment.addr, data: Cow::Borrowed(&segment.bytes) })
        .collect();
    flasher.write_bins_to_flash(&segments, &mut DefaultProgressCallback)
}

#[cfg(test)]
mod tests {
    use super::*;
    use obs_core::protocol::{self, Pulled, Size, CRED_STORE_FAIL};
    use obs_core::{LinkRx, USB_PID, USB_VID};
    use std::io::ErrorKind;

    const OLD_HASH: [u8; 4] = [0x00, 0xC0, 0xFF, 0xEE];
    const NEW_HASH: [u8; 4] = [0x51, 0xB0, 0xCD, 0x6E];

    fn info(git_hash: [u8; 4], credentials_set: bool) -> Info {
        Info {
            proto: 2,
            obs_password_set: credentials_set,
            wifi_psk_set: credentials_set,
            schema_min: 1,
            schema_max: 1,
            max_doc_bytes: 16384,
            keys: 9,
            buttons: 4,
            knobs: 3,
            main_display: Size { width: 320, height: 480 },
            strip_display: Size { width: 142, height: 428 },
            capabilities: 0,
            board_rev: 1,
            git_hash,
            unique_id: [0x02, 0, 0, 0, 0, 0x01],
            fw_version: "0.2.0".into(),
        }
    }

    /// The pad's CDC port: answers `INFO_GET` with `info` and `BOOTLOADER` with `bootloader`.
    struct FakePad {
        info: Info,
        bootloader: u8,
        rx: LinkRx,
        pending: Vec<u8>,
    }

    impl FakePad {
        fn new(info: Info, bootloader: u8) -> Self {
            Self { info, bootloader, rx: LinkRx::default(), pending: Vec::new() }
        }
    }

    impl Write for FakePad {
        fn write(&mut self, buf: &[u8]) -> io::Result<usize> {
            self.rx.push(buf);
            while let Some(Pulled::Frame(frame)) = self.rx.pull() {
                let reply = match Message::decode(&frame) {
                    Some(Message::InfoGet) => Message::Info(self.info.clone()),
                    Some(Message::Bootloader) => Message::CredStatus { code: self.bootloader },
                    other => panic!("the update sent {other:?}"),
                };
                let frame = reply.encode(frame.id).expect("reply encodes");
                self.pending.extend(protocol::encode(&frame).expect("reply fits"));
            }
            Ok(buf.len())
        }

        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    impl Read for FakePad {
        fn read(&mut self, buf: &mut [u8]) -> io::Result<usize> {
            if self.pending.is_empty() {
                return Err(ErrorKind::TimedOut.into());
            }
            let got = self.pending.len().min(buf.len());
            buf[..got].copy_from_slice(&self.pending[..got]);
            self.pending.drain(..got);
            Ok(got)
        }
    }

    fn port(path: &str, vid: u16, pid: u16, serial: &str) -> UsbPort {
        UsbPort { path: path.into(), vid, pid, serial: Some(serial.into()) }
    }

    fn pad() -> UsbPort {
        port("/dev/ttyACM0", USB_VID, USB_PID, "A1")
    }

    fn rom() -> UsbPort {
        port("/dev/ttyACM1", ROM_VID, ROM_PID, "f4:12:fa:00:00:01")
    }

    fn image() -> Image {
        Image { segments: vec![Segment { addr: 0x1_0000, bytes: vec![0xE9, 1, 2, 3] }], git_hash: NEW_HASH }
    }

    /// A machine on a fake clock. The first listing is the one before `BOOTLOADER`; then the
    /// listing is `during` from `rom_at` on, and after the write `after` from `back_at` past it.
    struct FakeHost {
        now: Duration,
        listings: usize,
        before: Vec<UsbPort>,
        during: Vec<UsbPort>,
        rom_at: Duration,
        after: Vec<UsbPort>,
        back_at: Duration,
        flash_fails: bool,
        flashed: Vec<(UsbPort, Image)>,
        flashed_at: Option<Duration>,
        back_info: Info,
    }

    impl FakeHost {
        fn new() -> Self {
            Self {
                now: Duration::ZERO,
                listings: 0,
                before: vec![pad()],
                during: vec![rom()],
                rom_at: Duration::from_secs(2),
                after: vec![pad()],
                back_at: Duration::from_secs(5),
                flash_fails: false,
                flashed: Vec::new(),
                flashed_at: None,
                back_info: info(NEW_HASH, false),
            }
        }
    }

    impl Host for FakeHost {
        type Port = FakePad;

        fn ports(&mut self) -> Result<Vec<UsbPort>, DiscoverError> {
            self.listings += 1;
            let listed = match self.flashed_at {
                _ if self.listings == 1 => &self.before,
                Some(at) if self.now >= at + self.back_at => &self.after,
                Some(_) => &self.during,
                None if self.now >= self.rom_at => &self.during,
                None => &Vec::new(),
            };
            Ok(listed.clone())
        }

        fn open(&mut self, pad: &UsbPort) -> Result<FakePad, DiscoverError> {
            assert!(self.flashed_at.is_some(), "the pad opens only after the write: {pad:?}");
            Ok(FakePad::new(self.back_info.clone(), CRED_OK))
        }

        fn flash(&mut self, rom: &UsbPort, image: &Image) -> Result<(), FlashError> {
            self.flashed.push((rom.clone(), image.clone()));
            self.flashed_at = Some(self.now);
            if self.flash_fails {
                return Err("flash write failed at 0x10000".into());
            }
            Ok(())
        }

        fn elapsed(&self) -> Duration {
            self.now
        }

        fn sleep(&mut self, wait: Duration) {
            self.now += wait;
        }
    }

    fn run(host: &mut FakeHost, bootloader: u8) -> Result<Info, UpdateError> {
        let session = Session::start(FakePad::new(info(OLD_HASH, true), bootloader)).expect("session starts");
        update(session, &pad(), &image(), host)
    }

    #[test]
    fn the_update_writes_the_image_on_the_rom_port_and_checks_the_new_hash() {
        let mut host = FakeHost::new();
        let back = run(&mut host, CRED_OK).expect("updated");
        assert_eq!(back.git_hash, NEW_HASH);
        assert_eq!(host.flashed, [(rom(), image())]);
    }

    #[test]
    fn a_rom_port_just_inside_ten_seconds_and_a_pad_just_inside_thirty_pass() {
        let mut host = FakeHost::new();
        host.rom_at = ROM_WAIT - POLL;
        host.back_at = BACK_WAIT - POLL;
        run(&mut host, CRED_OK).expect("updated");
        assert_eq!(host.now, ROM_WAIT - POLL + BACK_WAIT - POLL);
    }

    #[test]
    fn no_rom_port_in_ten_seconds_times_out_and_writes_nothing() {
        let mut host = FakeHost::new();
        host.rom_at = ROM_WAIT + POLL;
        assert!(matches!(run(&mut host, CRED_OK), Err(UpdateError::NoRomPort)));
        assert_eq!(host.now, ROM_WAIT);
        assert!(host.flashed.is_empty());
    }

    #[test]
    fn a_new_espressif_port_with_another_pid_is_refused() {
        let mut host = FakeHost::new();
        host.during = vec![port("/dev/ttyACM1", ROM_VID, 0x0002, "0")];
        assert!(matches!(run(&mut host, CRED_OK), Err(UpdateError::WrongPid { pid: 0x0002 })));
        assert!(host.flashed.is_empty());
    }

    #[test]
    fn an_espressif_board_plugged_in_before_is_not_the_rom_port() {
        let devkit = port("/dev/ttyACM7", ROM_VID, ROM_PID, "devkit");
        let wrong_pid_devkit = port("/dev/ttyACM8", ROM_VID, 0x0002, "s2");
        let mut host = FakeHost::new();
        host.before = vec![pad(), devkit.clone(), wrong_pid_devkit.clone()];
        host.during = vec![devkit, wrong_pid_devkit, rom()];
        run(&mut host, CRED_OK).expect("updated");
        assert_eq!(host.flashed[0].0, rom());
    }

    #[test]
    fn two_new_rom_ports_are_refused() {
        let mut host = FakeHost::new();
        host.during = vec![rom(), port("/dev/ttyACM2", ROM_VID, ROM_PID, "other")];
        assert!(matches!(run(&mut host, CRED_OK), Err(UpdateError::SeveralRomPorts)));
        assert!(host.flashed.is_empty());
    }

    #[test]
    fn a_refused_bootloader_stops_before_any_wait() {
        let mut host = FakeHost::new();
        let got = run(&mut host, CRED_STORE_FAIL);
        assert!(matches!(got, Err(UpdateError::Session(SessionError::CredentialRefused { code: CRED_STORE_FAIL }))));
        assert_eq!((host.now, host.listings), (Duration::ZERO, 1));
    }

    #[test]
    fn a_flash_error_is_the_result_and_the_pad_is_not_awaited() {
        let mut host = FakeHost::new();
        host.flash_fails = true;
        let Err(UpdateError::Flash(err)) = run(&mut host, CRED_OK) else { panic!("a flash error") };
        assert_eq!(err.to_string(), "flash write failed at 0x10000");
        assert_eq!(host.now, host.rom_at);
    }

    #[test]
    fn a_pad_not_back_in_thirty_seconds_times_out() {
        let mut host = FakeHost::new();
        host.back_at = BACK_WAIT + POLL;
        assert!(matches!(run(&mut host, CRED_OK), Err(UpdateError::NotBack)));
        assert_eq!(host.now, host.rom_at + BACK_WAIT);
    }

    #[test]
    fn another_pad_coming_back_is_not_this_pad() {
        let mut host = FakeHost::new();
        host.after = vec![port("/dev/ttyACM0", USB_VID, USB_PID, "B2")];
        assert!(matches!(run(&mut host, CRED_OK), Err(UpdateError::NotBack)));
    }

    #[test]
    fn the_old_git_hash_after_the_write_is_an_error() {
        let mut host = FakeHost::new();
        host.back_info = info(OLD_HASH, false);
        assert!(matches!(run(&mut host, CRED_OK), Err(UpdateError::OldFirmware { git_hash: OLD_HASH })));
    }

    /// A directory of its own under the system temp dir, removed on drop.
    struct ImageDir(std::path::PathBuf);

    impl ImageDir {
        fn new(name: &str) -> Self {
            let dir = std::env::temp_dir().join(format!("app-core-image-{}-{name}", std::process::id()));
            let _ = std::fs::remove_dir_all(&dir);
            std::fs::create_dir_all(&dir).expect("image directory");
            Self(dir)
        }

        /// Writes `macropad-obs-merged.bin` and, when given, its `.git_hash`; the image's path.
        fn write(&self, image: &[u8], git_hash: Option<&str>) -> std::path::PathBuf {
            let path = self.0.join("macropad-obs-merged.bin");
            std::fs::write(&path, image).expect("image writes");
            if let Some(text) = git_hash {
                std::fs::write(self.0.join("macropad-obs-merged.git_hash"), text).expect("hash writes");
            }
            path
        }
    }

    impl Drop for ImageDir {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn a_merged_image_loads_as_one_segment_at_zero_with_the_git_hash_beside_it() {
        let dir = ImageDir::new("good");
        let path = dir.write(&[0xE9, 0x03, 0x02, 0x4F], Some("51b0cd6e\n"));
        let image = Image::load(&path).expect("loads");
        assert_eq!(image.segments, [Segment { addr: 0, bytes: vec![0xE9, 0x03, 0x02, 0x4F] }]);
        assert_eq!(image.git_hash, NEW_HASH);
    }

    #[test]
    fn a_file_that_is_not_an_esp_image_is_refused() {
        let dir = ImageDir::new("magic");
        assert!(matches!(
            Image::load(&dir.write(&[0x7F, b'E', b'L', b'F'], Some("51b0cd6e"))),
            Err(ImageError::NotAnImage)
        ));
        assert!(matches!(Image::load(&dir.write(&[], Some("51b0cd6e"))), Err(ImageError::NotAnImage)));
    }

    #[test]
    fn an_image_larger_than_the_flash_is_refused() {
        let dir = ImageDir::new("big");
        let mut bytes = vec![0; FLASH_BYTES + 1];
        bytes[0] = 0xE9;
        assert!(matches!(Image::load(&dir.write(&bytes, Some("51b0cd6e"))), Err(ImageError::TooBig)));
        bytes.pop();
        assert!(Image::load(&dir.write(&bytes, Some("51b0cd6e"))).is_ok(), "exactly the flash size fits");
    }

    #[test]
    fn a_missing_or_malformed_git_hash_is_refused() {
        let dir = ImageDir::new("hash");
        assert!(matches!(Image::load(&dir.write(&[0xE9], None)), Err(ImageError::Read { .. })));
        for bad in ["51b0cd6", "51b0cd6e0", "51b0cd6g", "", "0"] {
            assert!(matches!(Image::load(&dir.write(&[0xE9], Some(bad))), Err(ImageError::BadHash)), "{bad:?}");
        }
    }

    #[test]
    fn a_missing_image_names_its_path() {
        let dir = ImageDir::new("missing");
        let err = Image::load(&dir.0.join("none.bin")).expect_err("no file");
        assert!(err.to_string().contains("none.bin"), "{err}");
    }

    #[test]
    fn a_credential_still_set_after_the_update_is_an_error() {
        let mut host = FakeHost::new();
        host.back_info = info(NEW_HASH, true);
        assert!(matches!(run(&mut host, CRED_OK), Err(UpdateError::CredentialsKept)));
    }
}
