// SPDX-License-Identifier: MIT
//! 1 dB steps. The first detent returns at once. `poll` ends the 30 ms window.

pub const DB_MIN: i32 = -100;
pub const DB_MAX: i32 = 26;
const WINDOW_MS: u64 = 30;

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct VolumeGate {
    last_poll: u64,
    polled: bool,
    deadline: Option<u64>,
    pending: i32,
    commanded: Option<i8>,
}

impl VolumeGate {
    pub fn window_open(&self) -> bool {
        self.deadline.is_some()
    }

    pub fn on_snapshot(&mut self) {
        if !self.window_open() {
            self.commanded = None;
            self.pending = 0;
        }
    }

    /// Absolute dB for the first step, if the window was closed.
    pub fn detent(&mut self, detents: i8, base_db: i8) -> Option<i8> {
        if detents == 0 {
            return None;
        }
        if self.deadline.is_some() {
            self.pending += i32::from(detents);
            return None;
        }
        let step: i32 = if detents > 0 { 1 } else { -1 };
        self.pending += i32::from(detents) - step;
        let base = i32::from(self.commanded.unwrap_or(base_db));
        let db = clamp_db(base + step);
        self.commanded = Some(db);
        let anchor = if self.polled { self.last_poll } else { 0 };
        self.deadline = Some(anchor.saturating_add(WINDOW_MS));
        Some(db)
    }

    /// One summed absolute dB when the window ends and further detents are waiting.
    pub fn poll(&mut self, now_ms: u64) -> Option<i8> {
        self.last_poll = now_ms;
        self.polled = true;
        let deadline = self.deadline?;
        if now_ms < deadline {
            return None;
        }
        self.deadline = None;
        if self.pending == 0 {
            return None;
        }
        let base = i32::from(self.commanded.unwrap_or(0));
        let db = clamp_db(base + self.pending);
        self.pending = 0;
        self.commanded = Some(db);
        Some(db)
    }
}

pub fn clamp_db(db: i32) -> i8 {
    db.clamp(DB_MIN, DB_MAX) as i8
}

pub fn round_db(raw: f64) -> i8 {
    if raw.is_nan() {
        return 0;
    }
    if raw >= 127.5 {
        return 127;
    }
    if raw <= -128.5 {
        return -128;
    }
    let shifted = if raw >= 0.0 { raw + 0.5 } else { raw - 0.5 };
    let trunc = shifted.trunc();
    if trunc >= 127.0 {
        127
    } else if trunc <= -128.0 {
        -128
    } else {
        trunc as i8
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_half_away_from_zero() {
        assert_eq!(round_db(0.5), 1);
        assert_eq!(round_db(-0.5), -1);
        assert_eq!(round_db(0.4), 0);
        assert_eq!(round_db(-0.4), 0);
        assert_eq!(round_db(1.5), 2);
        assert_eq!(round_db(-1.5), -2);
        assert_eq!(round_db(f64::NAN), 0);
        assert_eq!(round_db(200.0), 127);
        assert_eq!(round_db(-200.0), -128);
    }

    #[test]
    fn clamp_stays_inside_obs_db() {
        assert_eq!(clamp_db(27), 26);
        assert_eq!(clamp_db(-101), -100);
        assert_eq!(clamp_db(0), 0);
    }
}
