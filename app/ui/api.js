// SPDX-License-Identifier: MIT
// The window's commands (app/src-tauri/src/commands.rs), one function each. A failure rejects
// with the command's one-line `Failure` text.

const invoke = (command, args = {}) => window.__TAURI__.core.invoke(command, args);

export const listPads = () => invoke("list_pads");
export const connect = (serial) => invoke("connect", { serial });
export const disconnect = () => invoke("disconnect");
export const readMapping = () => invoke("read_mapping");
export const writeMapping = (mapping) => invoke("write_mapping", { mapping });
export const obsList = (list) => invoke("obs_list", { list });
export const checkUrl = (url) => invoke("check_url", { url });
