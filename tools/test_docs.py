#!/usr/bin/env python3
"""Checks that the docs agree with the tree, the task list and each other."""
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = "docs/spec/spec-v2.md"
TODO = "tasks/todo.md"
PLAN_FILES = (TODO, "tasks/plan.md")
DECISIONS = "docs/spec/decisions-v2.md"
TASK_ID = r"\b[A-Z0-9]\.\d+[a-z]?\b"
GATE_NAME = r"\bG-[a-z]+\b"
MOVED_CORE = ("link.c", "link.h", "input.c", "input.h")
# Task 1.4b retires the old wedge. Each path stays gone until the task beside it writes it again.
# The v2 case never brings back the two wedge modules, so no task is named for them.
WEDGE_PATHS = {
    "pcb/gen": "5.1", "pcb/kicad": "5.6", "pcb/fab": "5.10", "cad/exports": "6.5",
    "cad/obs_case/geometry.py": None, "cad/obs_case/numbers.py": None,
}
WEDGE_RECIPES = {"pcb-test": "5.1", "cad-check": "6.1", "cad": "6.2a"}
CAD_STEPS = ("check", "geometry", "export")
# Task 1.6a: no PC process holds the OBS socket (D1), so the host crate keeps no v1 bridge.
HOST_SOURCE_SKIP = {"target", "Cargo.lock"}


def flat(relative_path):
    """File text with every run of whitespace as one space, so line wraps do not matter."""
    return " ".join((ROOT / relative_path).read_text(encoding="utf-8").split())


def between(text, start, end):
    """The part of text from start up to end. Raises ValueError if either is missing."""
    head = text.index(start)
    return text[head : text.index(end, head + len(start))]


def paragraph(relative_path, start):
    """The paragraph that opens with start, up to the first blank line, as one line."""
    text = (ROOT / relative_path).read_text(encoding="utf-8")
    return " ".join(between(text, start, "\n\n").split())


def card(task_id):
    """One task card of tasks/todo.md, from its id up to the next card or heading."""
    body = flat(TODO).split(f"**{task_id} ", 1)[1]
    return re.split(r" - \[[ x]\] \*\*| #+ ", body, maxsplit=1)[0]


def ticked_tasks():
    return set(re.findall(r"- \[x\] \*\*(\S+) ", flat(TODO)))


def approved_gates():
    return set(re.findall(r"\| (G-[a-z]+) \|[^|]*\| \*\*Approved", flat(DECISIONS)))


def retired_by_task_1_1():
    """The paths the 1.1 card says are gone. The card is the one place that names them."""
    return re.findall(r"`(firmware/[^`]+)`", between(card("1.1"), "Accept:", "Verify:"))


def task_1_1_grep_hits():
    """Runs the grep of the 1.1 Verify step: its pattern over justfile and every file in tools/."""
    grep = re.search(r"grep -rn '([^']+)' justfile tools/", card("1.1"))
    pattern = re.compile(grep.group(1).replace("\\|", "|"))
    searched = [ROOT / "justfile", *sorted(p for p in (ROOT / "tools").rglob("*") if p.is_file())]
    return [
        f"{path.relative_to(ROOT)}:{number}"
        for path in searched
        for number, line in enumerate(path.read_text(encoding="latin-1").splitlines(), 1)
        if pattern.search(line)
    ]


def claude_md_after_pending_edits():
    """CLAUDE.md as it reads once the main session applies each tasks/pending-claude-md-*.sed.
    Only the main session edits CLAUDE.md, so a task leaves its rule edit as a sed script."""
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    for script in sorted((ROOT / "tasks").glob("pending-claude-md-*.sed")):
        sed = ["sed", "-f", str(script)]
        text = subprocess.run(sed, input=text, capture_output=True, text=True, check=True).stdout
    return " ".join(text.split())


def rule_r1():
    """The R1 text of spec section 12: its quoted lines, joined as one line."""
    spec = (ROOT / SPEC).read_text(encoding="utf-8")
    quoted = re.findall(r"^\s*> (.+)$", between(spec, "- **R1 (D2", "- **R2 (LCSC)"), re.MULTILINE)
    return " ".join(quoted)


def missing_claude_paths():
    """Paths that CLAUDE.md names, pending edits applied, and the tree lacks."""
    paths = re.findall(r"`([^`\s]*/[^`\s]*)`", claude_md_after_pending_edits())
    return [path for path in paths if not (ROOT / path).exists()]


class TaskListTest(unittest.TestCase):
    def test_next_action_names_a_task_or_gate_and_no_ticked_task(self):
        for plan_file in PLAN_FILES:
            next_action = paragraph(plan_file, "Next action:")
            tasks = set(re.findall(TASK_ID, next_action))
            gates = set(re.findall(GATE_NAME, next_action))
            self.assertNotEqual(tasks | gates, set(), plan_file)
            self.assertEqual(tasks & ticked_tasks(), set(), plan_file)

    def test_next_action_waits_on_no_gate_the_owner_approved(self):
        self.assertIn("G-rules", approved_gates())
        for plan_file in PLAN_FILES:
            gates = set(re.findall(GATE_NAME, paragraph(plan_file, "Next action:")))
            self.assertEqual(gates & approved_gates(), set(), plan_file)

    def test_task_1_1_verify_grep_is_empty_while_1_1_is_ticked(self):
        if "1.1" in ticked_tasks():
            self.assertEqual(task_1_1_grep_hits(), [])

    def test_rule_tasks_stay_open_while_claude_md_names_a_missing_path(self):
        if missing_claude_paths():
            self.assertEqual({"1.2", "1.10"} & ticked_tasks(), set(), missing_claude_paths())

    def test_task_1_2_fixes_every_stale_claude_md_path(self):
        self.assertIn("`check_pins.py` sentence", card("1.2"))
        self.assertIn("xargs -n1 test -e", card("1.2"))

    def test_task_1_2_layout_is_in_the_tree_while_1_2_is_ticked(self):
        if "1.2" not in ticked_tasks():
            return
        accept = between(card("1.2"), "Accept:", "Verify:")
        app_dependency = re.search(r"`(obs_core = [^`]+)`", accept).group(1)
        self.assertIn(app_dependency, flat("app/src-tauri/Cargo.toml"))
        members = re.search(r"members = \[([^\]]*)\]", flat("host/Cargo.toml")).group(1)
        self.assertIn('"obs_core"', members)  # 3.2 adds "app_core" beside it
        moved = ["host/obs_core/src/protocol.rs", *(f"firmware/core/{name}" for name in MOVED_CORE)]
        self.assertEqual([path for path in moved if not (ROOT / path).is_file()], [])
        self.assertEqual(missing_claude_paths(), [])

    def test_claude_md_carries_rule_r6_while_1_3_is_ticked(self):
        if "1.3" in ticked_tasks():
            rule_r6 = re.search(r'R6 \(check_pins\)\.\*\* "([^"]+)"', flat(SPEC)).group(1)
            self.assertIn(rule_r6, claude_md_after_pending_edits())
            self.assertFalse((ROOT / "firmware/pins.h").exists())

    def test_claude_md_carries_rule_r5_while_1_5_is_ticked(self):
        if "1.5" in ticked_tasks():
            rule_r5 = re.search(r'R5 \(source of truth\)\.\*\* Add: "([^"]+)"', flat(SPEC)).group(1)
            self.assertIn(rule_r5, claude_md_after_pending_edits())

    def test_claude_md_carries_rule_r3_while_1_9_is_ticked(self):
        if "1.9" in ticked_tasks():
            rule_r3 = re.search(r'R3 \(protocol and config\)\.\*\* "([^"]+)"', flat(SPEC)).group(1)
            self.assertIn("Config schema changes", rule_r3)
            self.assertIn(rule_r3, claude_md_after_pending_edits())

    def test_claude_md_carries_rules_r1_and_r2_while_1_10_is_ticked(self):
        if "1.10" not in ticked_tasks():
            return
        claude_md = flat("CLAUDE.md")
        rule_r2 = re.search(r'R2 \(LCSC\)\.\*\* "([^"]+)"', flat(SPEC)).group(1)
        self.assertIn("The OBS password and any Wi-Fi passphrase", rule_r1())
        self.assertIn(rule_r1(), claude_md)
        self.assertNotIn("No OBS password in a CDC frame", claude_md)
        self.assertIn(rule_r2, claude_md)
        self.assertNotIn("`UNVERIFIED` except", claude_md)

    def test_task_1_8_names_the_credential_exceptions_and_reject_vectors(self):
        task = card("1.8")
        self.assertNotIn("could carry a secret", task)
        for phrase in ("derived from a credential", "`INFO` git hash", "`CFG_DATA`",
                       "`bad_kind`", "`bad_len`", "`bad_value`", "7 and 65"):
            self.assertIn(phrase, task)

    def test_task_1_8_has_clear_credentials_vectors_and_no_mask(self):
        self.assertNotIn("CLEAR_CREDENTIALS{mask}", flat(TODO))
        for phrase in ("`CLEAR_CREDENTIALS` with no payload", "with one payload byte"):
            self.assertIn(phrase, card("1.8"))

    def test_task_1_9_covers_schema_range_and_migration(self):
        task = card("1.9")
        for phrase in ("`schema` missing", "too old", "too new", "migration round trip"):
            self.assertIn(phrase, task)

    def test_task_1_9_covers_a_pad_older_than_the_app(self):
        for phrase in ("pad max below the app's schema", "`update firmware`", "builds no `CFG_BEGIN`"):
            self.assertIn(phrase, card("1.9"))

    def test_store_and_device_tasks_cover_a_stored_schema_below_min(self):
        self.assertIn("stored `schema` below min", card("2.10"))
        self.assertIn("stored `schema` below min", card("2.11a"))
        self.assertIn("`CFG_READ` returns the stored bytes", card("2.11a"))

    def test_task_2_10_dumps_the_credential_model_after_clear(self):
        self.assertIn("a raw dump of the model holds no byte run of either", card("2.10"))

    def test_task_3_3_allows_secrets_only_in_set_credential(self):
        task = card("3.3")
        self.assertNotIn("holds no password or PSK byte", task)
        self.assertIn("other than the `SET_CREDENTIAL` payload", task)


class SpecTest(unittest.TestCase):
    def test_criterion_12_agrees_with_rule_r1(self):
        criterion = between(flat(SPEC), " 12. No ", " 13. ")
        self.assertNotIn("any capture of USB traffic", criterion)
        self.assertIn("other than the `SET_CREDENTIAL` payload", criterion)

    def test_set_credential_states_bounds_and_status_codes(self):
        rule = between(flat(SPEC), "- `SET_CREDENTIAL{", "- `STATUS`")
        self.assertNotIn("likely", rule)
        for phrase in ("1..239", "8..63", "64 hex", "wifi_sta_config_t",
                       "`ok`", "`bad_kind`", "`bad_len`", "`bad_value`", "`store_fail`"):
            self.assertIn(phrase, rule)

    def test_clear_credentials_is_all_or_nothing_with_a_status_reply(self):
        spec = flat(SPEC)
        self.assertNotIn("CLEAR_CREDENTIALS{mask}", spec)
        rule = between(spec, "- `CLEAR_CREDENTIALS`: no payload", "- `STATUS`")
        for phrase in ('nvs_flash_erase_partition("cred")', "no one-credential clear",
                       "`ok`", "`bad_len`", "`store_fail`"):
            self.assertIn(phrase, rule)

    def test_stored_schema_below_min_is_kept_and_served(self):
        rule = between(flat(SPEC), "At boot, a stored document", "The app opens")
        for phrase in ("below the pad's min", "not erased", "`update config`",
                       "`CFG_READ` still serves the stored bytes", "`schema` and `seq`"):
            self.assertIn(phrase, rule)

    def test_app_newer_than_the_pad_refuses_to_write(self):
        spec = flat(SPEC)
        self.assertIn("pad's schema max is below the app's", spec)
        self.assertIn("`update firmware`", spec)
        self.assertIn("no downgrade migration", spec)

    def test_schema_outside_the_pad_range_is_refused(self):
        spec = flat(SPEC)
        self.assertIn("`RESULT invalid` with path `schema`", spec)
        self.assertIn("read-only when the pad's schema max is above its own", spec)


def still_retired(returns_with):
    """The names of a {name: task} table whose task is absent or not ticked yet."""
    return [name for name, task in returns_with.items() if task not in ticked_tasks()]


def justfile_recipes():
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    return set(re.findall(r"^([a-z][\w-]*)\b[^:\n]*:", justfile, re.MULTILINE))


class OldWedgeTest(unittest.TestCase):
    def test_wedge_paths_stay_gone_until_their_task_lands(self):
        present = [path for path in still_retired(WEDGE_PATHS) if (ROOT / path).exists()]
        self.assertEqual(present, [])

    def test_justfile_names_no_retired_recipe_or_dependency(self):
        justfile = (ROOT / "justfile").read_text(encoding="utf-8")
        test_dependencies = set(re.search(r"^test:(.*)$", justfile, re.MULTILINE).group(1).split())
        retired = set(still_retired(WEDGE_RECIPES))
        self.assertEqual(retired & (justfile_recipes() | test_dependencies), set())

    def test_cad_build_exits_2_on_every_step_until_the_body_returns(self):
        if "6.2a" in ticked_tasks():
            return
        for step in CAD_STEPS:
            build = subprocess.run(
                [sys.executable, str(ROOT / "cad/build.py"), step],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(build.returncode, 2, f"{step}: {build.stderr}")
            self.assertIn("no case body until 6.2a", build.stderr, step)

    def test_cad_sources_import_no_deleted_wedge_module(self):
        gone = [Path(path).stem for path in still_retired(WEDGE_PATHS) if path.endswith(".py")]
        for source in sorted((ROOT / "cad").glob("*.py")) + sorted((ROOT / "cad/obs_case").glob("*.py")):
            imports = re.findall(r"^\s*(?:from|import) +(\S+)", source.read_text(encoding="utf-8"), re.MULTILINE)
            named = [module for module in imports if module.rsplit(".", 1)[-1] in gone]
            self.assertEqual(named, [], source.name)


def host_sources():
    """Every file under host/ that is not a build product or the lock file."""
    host = ROOT / "host"
    files = (path for path in sorted(host.rglob("*")) if path.is_file())
    return [path for path in files if not HOST_SOURCE_SKIP & set(path.relative_to(host).parts)]


class V1BridgeTest(unittest.TestCase):
    def test_host_crate_has_no_bridge_file_and_names_none(self):
        named = [
            str(path.relative_to(ROOT))
            for path in host_sources()
            if "bridge" in path.name.lower() or "bridge" in path.read_text(encoding="utf-8").lower()
        ]
        self.assertEqual(named, [])


class ReadmeTest(unittest.TestCase):
    def test_every_just_command_is_a_recipe(self):
        justfile = (ROOT / "justfile").read_text(encoding="utf-8")
        # A recipe may take parameters (`pcb *STEP:`); `name := value` is a variable, not a recipe.
        recipes = set(re.findall(r"^([a-z][\w-]*)(?: [^:=\n]*)?:(?!=)", justfile, re.MULTILINE))
        named = set(re.findall(r"`just ([a-z][\w-]*)`", flat("README.md")))
        self.assertEqual(named - recipes, set())

    def test_readme_names_no_file_that_task_1_1_retired(self):
        readme = flat("README.md")
        self.assertEqual(len(retired_by_task_1_1()), 3)
        for retired_path in retired_by_task_1_1():
            self.assertNotIn(retired_path, readme)

    def test_design_doc_is_marked_as_the_retired_v1_design(self):
        opening = (ROOT / "docs/design.md").read_text(encoding="utf-8")[:400]
        self.assertIn("v1 design", opening)
        self.assertIn("docs/spec/spec-v2.md", opening)


if __name__ == "__main__":
    unittest.main()
