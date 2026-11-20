// SPDX-License-Identifier: MIT
//! Provisioning (spec 8.2): `SET_CREDENTIAL` from a `Secret`, `CLEAR_CREDENTIALS`, the pad's
//! `STATUS`, and the export. A secret crosses the link only in a `SET_CREDENTIAL` payload (R1).

use std::io::{Read, Write};
use std::mem;

use obs_core::document::Rejected;
use obs_core::protocol::{
    credential_status, Frame, Message, Secret, CREDENTIAL_OBS_PASSWORD, CREDENTIAL_WIFI_PASSPHRASE, CRED_OK,
    SET_CREDENTIAL,
};
use serde_json::Value;

use crate::session::{Session, SessionError, Stored};

/// Which secret a `SET_CREDENTIAL` carries.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Credential {
    ObsPassword,
    WifiPassphrase,
}

impl Credential {
    fn kind(self) -> u8 {
        match self {
            Self::ObsPassword => CREDENTIAL_OBS_PASSWORD,
            Self::WifiPassphrase => CREDENTIAL_WIFI_PASSPHRASE,
        }
    }
}

/// The last `STATUS` the pad sent. States are the `OBS_*` and `WIFI_*` values of `protocol`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Status {
    pub obs_state: u8,
    pub wifi_state: u8,
    pub rssi_dbm: i8,
    pub ip: [u8; 4],
}

impl<P: Read + Write> Session<P> {
    /// Sends the secret in `field`, then leaves `field` empty and its old bytes zeroed, whatever
    /// the outcome. A secret the pad would refuse is refused here with the pad's code and never
    /// sent. On `ok` the session asks `INFO` again, so its set flags are current.
    pub fn set_credential(&mut self, credential: Credential, field: &mut Secret) -> Result<(), SessionError> {
        let (kind, secret) = (credential.kind(), Secret(mem::take(&mut field.0)));
        let code = precheck(kind, &secret.0);
        let message = Message::SetCredential { kind, secret };
        let outcome =
            if code == CRED_OK { self.ask_credential(&message) } else { Err(SessionError::CredentialRefused { code }) };
        if let Message::SetCredential { secret, .. } = message {
            wipe(secret.0);
        }
        outcome
    }

    /// Erases both secrets on the pad, then asks `INFO` again.
    pub fn clear_credentials(&mut self) -> Result<(), SessionError> {
        self.ask_credential(&Message::ClearCredentials)
    }

    fn ask_credential(&mut self, message: &Message) -> Result<(), SessionError> {
        match self.ask(message)? {
            Message::CredStatus { code: CRED_OK } => self.reload_info(),
            Message::CredStatus { code } => Err(SessionError::CredentialRefused { code }),
            _ => Err(SessionError::BadReply("a credential request answered without CRED_STATUS")),
        }
    }
}

/// The `CRED_STATUS` code the pad would answer, from the codec's own rule.
fn precheck(kind: u8, secret: &[u8]) -> u8 {
    let frame = Frame { kind: SET_CREDENTIAL, id: 0, payload: [&[kind][..], secret].concat() };
    let code = credential_status(&frame);
    wipe(frame.payload);
    code
}

/// Zeroes a copy of a secret before its memory goes back to the allocator.
fn wipe(mut bytes: Vec<u8>) {
    bytes.fill(0);
    // Keeps the zeroing from being dropped as a dead store.
    std::hint::black_box(&bytes);
}

/// The stored document as pretty JSON for a file. The document has no secret field and the pad
/// never serves a secret, so the export holds none (spec 8.2). An empty pad has nothing to export.
pub fn export(stored: &Stored) -> Result<Vec<u8>, Rejected> {
    let not_an_object = || Rejected::Invalid { path: String::new() };
    let json: Value = serde_json::from_slice(&stored.bytes).map_err(|_| not_an_object())?;
    if !json.is_object() {
        return Err(not_an_object());
    }
    Ok(serde_json::to_vec_pretty(&json).expect("a JSON value serialises"))
}
