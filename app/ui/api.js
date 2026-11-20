// SPDX-License-Identifier: MIT
// The window's commands (app/src-tauri/src/commands.rs), one function each. A failure rejects
// with the command's one-line `Failure` text.

const invoke = (command, args = {}) => window.__TAURI__.core.invoke(command, args);

export const listPads = () => invoke("list_pads");
export const connect = (serial) => invoke("connect", { serial });
export const disconnect = () => invoke("disconnect");
export const padInfo = () => invoke("pad_info");
export const readMapping = () => invoke("read_mapping");
export const writeMapping = (mapping) => invoke("write_mapping", { mapping });
export const obsList = (list) => invoke("obs_list", { list });
export const checkUrl = (url) => invoke("check_url", { url });
export const readLayout = () => invoke("read_layout");
export const writeLayout = (layout) => invoke("write_layout", { layout });
// An ArrayBuffer: the main frame, then the strip frame, big-endian RGB565.
export const preview = (layout) => invoke("preview", { layout });
export const readNetwork = () => invoke("read_network");
export const writeNetwork = (network, secrets) => invoke("write_network", { network, secrets });
export const clearCredentials = () => invoke("clear_credentials");
export const updateFirmware = (image) => invoke("update_firmware", { image });
