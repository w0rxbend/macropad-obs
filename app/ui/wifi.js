// SPDX-License-Identifier: MIT
// The Wi-Fi page (task 3.8): the SSID and OBS auth mode from the document, and the Wi-Fi
// passphrase and OBS password, which are write-only (R1). A read never fills a secret field: the
// core's `NetworkPage` has no secret member, only whether each is set. Every write empties both
// fields, whatever its outcome; the core zeroes its copy (host/app_core/src/connection.rs).

import * as api from "./api.js";
import { $, onPad, say, sayWritten, step } from "./dom.js";

const SECRET_FIELDS = ["#passphrase", "#obs-password"];

function clearSecrets() {
  for (const field of SECRET_FIELDS) $(field).value = "";
}

function drawSetFlags(wifiPskSet, obsPasswordSet) {
  $("#passphrase").placeholder = wifiPskSet ? "set on the pad (type to replace)" : "not set";
  $("#obs-password").placeholder = obsPasswordSet ? "set on the pad (type to replace)" : "not set";
}

function drawPage(page) {
  $("#ssid").value = page.ssid;
  $("#auth-mode").value = page.auth_mode;
  drawSetFlags(page.wifi_psk_set, page.obs_password_set);
  clearSecrets();
  $("#wifi-page").hidden = false;
}

async function readNetwork() {
  drawPage(await api.readNetwork());
}

async function save() {
  const network = { ssid: $("#ssid").value, auth_mode: $("#auth-mode").value };
  const secrets = { wifi_passphrase: $("#passphrase").value, obs_password: $("#obs-password").value };
  try {
    const answer = await api.writeNetwork(network, secrets);
    drawPage(answer.page);
    sayWritten(answer.saved);
  } finally {
    clearSecrets();
  }
}

async function eraseSecrets() {
  const info = await api.clearCredentials();
  drawSetFlags(info.wifi_psk_set, info.obs_password_set);
  say("Both secrets are erased on the pad.");
}

onPad("pad:connected", readNetwork);
document.addEventListener("pad:disconnected", () => {
  clearSecrets();
  $("#wifi-page").hidden = true;
});
$("#wifi-form").addEventListener("submit", (event) => {
  event.preventDefault();
  step(save);
});
$("#wifi-read").addEventListener("click", () => step(readNetwork));
$("#erase-secrets").addEventListener("click", () => step(eraseSecrets));
