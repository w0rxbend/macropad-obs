# OBS client

`obs_core` returns `ObsRequest`. The shell in `app/src-tauri` performs the websocket call with `obws` 0.15. The core does not link that crate.

On connect the shell reads, in order: `GetSceneList`, `GetCurrentProgramScene`, `GetProfileList`, `GetCurrentProfile`, `GetStreamStatus`, `GetRecordStatus`, `GetStudioModeEnabled`, `GetInputList`, then `GetInputMute` and `GetInputVolume` for each input. An input whose volume request fails is dropped. The cap of 32 applies after that drop. `round_db` runs on every volume before `apply_snapshot`. `GetInputList` does not carry mute or dB.

`obws` 0.15 `StreamStatus` and `RecordStatus` have `outputActive` and no `outputState`. The shell does not treat `outputActive` as on. Stream and record stay off until `StreamStateChanged` or `RecordStateChanged` carries `outputState` `OBS_WEBSOCKET_OUTPUT_STARTED` or `OBS_WEBSOCKET_OUTPUT_RECONNECTED`. `STARTING`, `STOPPING`, `STOPPED`, `RECONNECTING`, `PAUSED`, and `RESUMED` are off.

Events that update the snapshot: `CurrentProgramSceneChanged`, `SceneListChanged`, `InputMuteStateChanged`, `InputVolumeChanged`, `StreamStateChanged`, `RecordStateChanged`, `CurrentProfileChanged`, `StudioModeStateChanged`, `InputCreated`, `InputRemoved`, `InputNameChanged`. After `CurrentProfileChanged` the shell repeats the scene reads and the input reads. Bursts coalesce for 50 ms, then one `PAGE_VIEW` and one `INPUT` go out.

`SetInputVolume` uses `Volume::Db` only. Mute uses the selected input. Studio mode off emits `Notice("studio off")` and no OBS request. The password stays in the XDG file. BIND does not carry it. `get_state` returns `password_set` and does not echo the password. The non-loopback checkbox only calls `save`.
