// SPDX-License-Identifier: MIT
//! `BOOTLOADER` against padsim (task 3.5): the firmware core answers `CRED_STATUS ok`, leaves the
//! link, and holds no credential when it starts again on the same flash (criterion 14).

mod common;

use app_core::{Credential, Secret, Session};
use common::{Padsim, Scratch};

#[test]
fn bootloader_erases_the_credentials_and_leaves_the_link() {
    let scratch = Scratch::new("update");
    let nor = scratch.path("pad.nor");
    let pad = Padsim::start(&nor);
    let mut session = Session::start(pad.port()).expect("INFO");
    let mut field = Secret(b"Zq7!Xv#9Lm@2Pp".to_vec());
    session.set_credential(Credential::ObsPassword, &mut field).expect("the pad stores the password");
    assert!(session.info().obs_password_set, "INFO shows the password set");

    session.enter_download().expect("the pad takes BOOTLOADER");
    pad.finish();

    let again = Padsim::start(&nor);
    let session = Session::start(again.port()).expect("INFO after the restart");
    assert!(!session.info().obs_password_set && !session.info().wifi_psk_set, "no credential survives BOOTLOADER");
    drop(session);
    again.finish();
}
