// SPDX-License-Identifier: MIT

use crate::config::KeyAction;
use crate::keymap::{fixed_label, scene_count, KEYS};
use crate::protocol::{ascii_field, PageView, SlotView};

pub fn page_count(scenes: usize, page_size: usize) -> usize {
    if page_size == 0 {
        return 1;
    }
    scenes.div_ceil(page_size).max(1)
}

pub fn step_page(page: usize, delta: i8, pages: usize) -> usize {
    if pages == 0 {
        return 0;
    }
    let next = page as isize + isize::from(delta);
    next.rem_euclid(pages as isize) as usize
}

pub struct PageFlags {
    pub studio: bool,
    pub streaming: bool,
    pub recording: bool,
}

pub fn build_page(
    keys: &[KeyAction; KEYS],
    scenes: &[String],
    program: Option<&str>,
    page: usize,
    flags: PageFlags,
    notice: Option<String>,
) -> PageView {
    let page_size = scene_count(keys);
    let pages = page_count(scenes.len(), page_size);
    let page = if pages == 0 { 0 } else { page % pages };
    let mut slots = Vec::with_capacity(KEYS);
    let mut scene_i = 0usize;
    for action in keys {
        if *action == KeyAction::Scene {
            let ordinal = page * page_size + scene_i;
            scene_i += 1;
            match scenes.get(ordinal) {
                Some(name) => slots.push(SlotView {
                    occupied: true,
                    program: program == Some(name.as_str()),
                    name: ascii_field(name, 16),
                }),
                None => slots.push(SlotView { occupied: false, program: false, name: String::new() }),
            }
        } else {
            slots.push(SlotView {
                occupied: true,
                program: false,
                name: fixed_label(*action).unwrap_or("").to_string(),
            });
        }
    }
    PageView {
        page: u8::try_from(page).unwrap_or(0),
        page_count: u8::try_from(pages).unwrap_or(255),
        studio: flags.studio,
        streaming: flags.streaming,
        recording: flags.recording,
        slots,
        notice,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn flags() -> PageFlags {
        PageFlags { studio: false, streaming: false, recording: false }
    }

    #[test]
    fn page_wraps_and_empty_slot_is_clear() {
        let keys = [KeyAction::Scene; KEYS];
        assert_eq!(step_page(0, -1, 2), 1);
        assert_eq!(step_page(1, 1, 2), 0);
        let scenes = vec!["Only".to_string()];
        let view = build_page(&keys, &scenes, Some("Only"), 0, flags(), None);
        assert!(view.slots[0].occupied);
        assert!(view.slots[0].program);
        assert!(!view.slots[1].occupied);
        let long = "0123456789abcdefXYZ".to_string();
        let cut = build_page(&keys, &[long], None, 0, flags(), None);
        assert_eq!(cut.slots[0].name, "0123456789abcde.");
    }
}
