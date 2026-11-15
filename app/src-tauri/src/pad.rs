// SPDX-License-Identifier: MIT
//! Opens `/dev/macropad-obs`, asserts DTR, and shuttles bytes.

use std::io::{ErrorKind, Read, Write};
use std::time::Duration;

use tokio::sync::mpsc;

pub enum PadMsg {
    Opened,
    Bytes(Vec<u8>),
    Closed,
}

pub fn spawn() -> (mpsc::UnboundedReceiver<PadMsg>, std::sync::mpsc::Sender<Vec<u8>>) {
    let (in_tx, in_rx) = mpsc::unbounded_channel();
    let (out_tx, out_rx) = std::sync::mpsc::channel::<Vec<u8>>();
    std::thread::Builder::new()
        .name("cdc".into())
        .spawn(move || pad_loop(in_tx, out_rx))
        .expect("cdc thread");
    (in_rx, out_tx)
}

fn pad_loop(tx: mpsc::UnboundedSender<PadMsg>, rx: std::sync::mpsc::Receiver<Vec<u8>>) {
    loop {
        let Ok(mut port) = serialport::new("/dev/macropad-obs", 115200)
            .timeout(Duration::from_millis(30))
            .open()
        else {
            std::thread::sleep(Duration::from_secs(1));
            continue;
        };
        if port.write_data_terminal_ready(true).is_err() || tx.send(PadMsg::Opened).is_err() {
            return;
        }
        'device: loop {
            while let Ok(bytes) = rx.try_recv() {
                if port.write_all(&bytes).is_err() {
                    let _ = tx.send(PadMsg::Closed);
                    break 'device;
                }
            }
            let mut buf = [0u8; 64];
            match port.read(&mut buf) {
                Ok(0) => {}
                Ok(n) => {
                    if tx.send(PadMsg::Bytes(buf[..n].to_vec())).is_err() {
                        return;
                    }
                }
                Err(err) if err.kind() == ErrorKind::TimedOut => {}
                Err(_) => {
                    let _ = tx.send(PadMsg::Closed);
                    break 'device;
                }
            }
        }
    }
}
