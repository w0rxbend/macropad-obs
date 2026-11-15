// SPDX-License-Identifier: MIT

use crate::config::KeyAction;

pub const KEYS: usize = 9;
pub const SCENE_CAP: usize = 64;
pub const INPUT_CAP: usize = 32;
pub const PROFILE_CAP: usize = 32;

pub fn scene_count(keys: &[KeyAction]) -> usize {
    keys.iter().filter(|action| **action == KeyAction::Scene).count()
}

pub fn fixed_label(action: KeyAction) -> Option<&'static str> {
    match action {
        KeyAction::Scene => None,
        KeyAction::Mute => Some("Mute"),
        KeyAction::Transition => Some("Trans"),
        KeyAction::Stream => Some("Live"),
        KeyAction::Record => Some("Rec"),
        KeyAction::ProfileNext => Some("Prof+"),
        KeyAction::ProfilePrev => Some("Prof-"),
    }
}

pub fn scene_slot(keys: &[KeyAction; KEYS], index: u8) -> Option<usize> {
    let index = usize::from(index);
    if index >= KEYS || keys[index] != KeyAction::Scene {
        return None;
    }
    Some(keys.iter().take(index).filter(|action| **action == KeyAction::Scene).count())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scene_slot_skips_fixed_keys() {
        let mut keys = [KeyAction::Scene; KEYS];
        keys[1] = KeyAction::Mute;
        assert_eq!(scene_slot(&keys, 0), Some(0));
        assert_eq!(scene_slot(&keys, 1), None);
        assert_eq!(scene_slot(&keys, 2), Some(1));
        assert_eq!(scene_count(&keys), 8);
    }
}
