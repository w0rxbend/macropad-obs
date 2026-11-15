// SPDX-License-Identifier: MIT

pub fn wrap_index(len: usize, current: Option<usize>, delta: i8) -> Option<usize> {
    if len == 0 || delta == 0 {
        return None;
    }
    let next = match current {
        Some(index) => index as isize + isize::from(delta),
        None if delta > 0 => 0,
        None => (len as isize) - 1,
    };
    Some(next.rem_euclid(len as isize) as usize)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn profile_wraps_both_ways() {
        assert_eq!(wrap_index(3, Some(0), -1), Some(2));
        assert_eq!(wrap_index(3, Some(2), 1), Some(0));
        assert_eq!(wrap_index(0, Some(0), 1), None);
        assert_eq!(wrap_index(2, None, 1), Some(0));
        assert_eq!(wrap_index(2, None, -1), Some(1));
    }
}
