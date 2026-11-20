// SPDX-License-Identifier: MIT
//! The diff the app shows after `stale_seq`: every leaf where the pad's document and the app's
//! differ, by the paths of `docs/config.md` (`obs.url`, `keys[2].do`).

use serde::Serialize;
use serde_json::Value;

/// One leaf that differs. `None` on a side means the member or list entry is not there.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Change {
    pub path: String,
    pub pad: Option<Value>,
    pub app: Option<Value>,
}

/// The leaves where `pad` and `app` differ, in path order: object members sorted, list entries by
/// index. Objects and lists are walked; any other pair that differs is one change.
pub fn changes(pad: &Value, app: &Value) -> Vec<Change> {
    let mut found = Vec::new();
    walk(String::new(), Some(pad), Some(app), &mut found);
    found
}

fn walk(path: String, pad: Option<&Value>, app: Option<&Value>, found: &mut Vec<Change>) {
    match (pad, app) {
        (Some(Value::Object(pad)), Some(Value::Object(app))) => {
            let mut names: Vec<&String> = pad.keys().chain(app.keys()).collect();
            names.sort();
            names.dedup();
            for name in names {
                walk(member_path(&path, name), pad.get(name), app.get(name), found);
            }
        }
        (Some(Value::Array(pad)), Some(Value::Array(app))) => {
            for index in 0..pad.len().max(app.len()) {
                walk(format!("{path}[{index}]"), pad.get(index), app.get(index), found);
            }
        }
        _ if pad != app => found.push(Change { path, pad: pad.cloned(), app: app.cloned() }),
        _ => {}
    }
}

fn member_path(parent: &str, name: &str) -> String {
    if parent.is_empty() {
        name.to_owned()
    } else {
        format!("{parent}.{name}")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn equal_documents_give_no_change() {
        let doc = json!({"obs": {"url": "ws://192.168.1.2"}, "keys": [{"do": "none"}]});
        assert_eq!(changes(&doc, &doc), Vec::new());
    }

    #[test]
    fn a_changed_leaf_gives_its_dotted_and_indexed_path() {
        let pad = json!({"obs": {"url": "ws://192.168.1.2"}, "keys": [{"do": "none"}, {"do": "none"}]});
        let app = json!({"obs": {"url": "ws://192.168.1.3"}, "keys": [{"do": "none"}, {"do": "toggle_record"}]});
        let paths: Vec<_> = changes(&pad, &app).into_iter().map(|change| change.path).collect();
        assert_eq!(paths, ["keys[1].do", "obs.url"]);
    }

    #[test]
    fn a_change_carries_both_sides() {
        let found = changes(&json!({"ui": {"brightness": 80}}), &json!({"ui": {"brightness": 20}}));
        assert_eq!(found, [Change { path: "ui.brightness".into(), pad: Some(json!(80)), app: Some(json!(20)) }]);
    }

    #[test]
    fn a_member_on_one_side_only_has_none_on_the_other() {
        let found = changes(&json!({"x_note": 1}), &json!({"x_tag": "a"}));
        assert_eq!(
            found,
            [
                Change { path: "x_note".into(), pad: Some(json!(1)), app: None },
                Change { path: "x_tag".into(), pad: None, app: Some(json!("a")) },
            ]
        );
    }

    #[test]
    fn a_longer_list_gives_its_extra_entries() {
        let found = changes(&json!({"w": [1]}), &json!({"w": [1, 2, 3]}));
        let paths: Vec<_> = found.iter().map(|change| (change.path.as_str(), change.pad.is_none())).collect();
        assert_eq!(paths, [("w[1]", true), ("w[2]", true)]);
    }

    #[test]
    fn a_type_change_is_one_leaf_not_a_walk() {
        let found = changes(&json!({"input": null}), &json!({"input": {"uuid": "U_A", "label": "Mic"}}));
        assert_eq!(found.len(), 1);
        assert_eq!(found[0].path, "input");
        assert_eq!(found[0].pad, Some(Value::Null));
    }
}
