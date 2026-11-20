// SPDX-License-Identifier: MIT
// The firmware page (task 3.8, criterion 14): the pad's firmware and the update from the merged
// image `just firmware` writes, with its `.git_hash` beside it. The steps (BOOTLOADER, ROM port,
// espflash, the new git hash in INFO) are host/app_core/src/update.rs. BOOTLOADER erases both
// secrets, so the page asks for that to be confirmed first.

import * as api from "./api.js";
import { $, announce, onPad, say, step } from "./dom.js";

function drawInfo(info) {
  $("#firmware-now").textContent = `Firmware ${info.fw_version}, git ${info.git_hash}, board rev ${info.board_rev}.`;
  $("#update-page").hidden = false;
}

async function showInfo() {
  drawInfo(await api.padInfo());
}

// A failure before BOOTLOADER (a bad image file) leaves the session open.
async function stillConnected() {
  try {
    await api.padInfo();
    return true;
  } catch {
    return false;
  }
}

async function update() {
  const button = $("#update");
  button.disabled = true;
  say("Updating. Do not unplug the pad.");
  try {
    const info = await api.updateFirmware($("#image").value);
    announce("pad:disconnected");
    say(`Updated: firmware ${info.fw_version}, git ${info.git_hash}. Connect again, then set the secrets.`);
  } catch (failure) {
    if (!(await stillConnected())) announce("pad:disconnected");
    say(`Update: ${failure}`);
  } finally {
    button.disabled = !$("#erase-ok").checked;
  }
}

onPad("pad:connected", showInfo);
document.addEventListener("pad:disconnected", () => {
  $("#update-page").hidden = true;
});
$("#erase-ok").addEventListener("change", () => {
  $("#update").disabled = !$("#erase-ok").checked;
});
$("#update").addEventListener("click", () => step(update));
