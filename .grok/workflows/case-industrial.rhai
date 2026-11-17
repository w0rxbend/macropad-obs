let meta = #{
    name: "case-industrial",
    description: "One brainstorm, review, implement, review pass on the macropad case, then commit it",
    when_to_use: "The supervisor relaunches this until the case no longer reads as a plain brick. Always commit a good pass on main.",
    phases: [
        #{ title: "Brainstorm", detail: "one legal form move" },
        #{ title: "Review", detail: "reject illegal moves" },
        #{ title: "Implement", detail: "edit, check, export" },
        #{ title: "Critique", detail: "judge the picture" },
        #{ title: "Commit", detail: "push the pass to main" },
    ],
};

let idea_schema = #{
    "type": "object",
    "required": ["move", "files", "risk"],
    "properties": #{
        "move": #{ "type": "string" },
        "files": #{ "type": "string" },
        "risk": #{ "type": "string" },
    },
};
let gate_schema = #{
    "type": "object",
    "required": ["allow", "reason"],
    "properties": #{
        "allow": #{ "type": "boolean" },
        "reason": #{ "type": "string" },
    },
};
let impl_schema = #{
    "type": "object",
    "required": ["ok", "evidence"],
    "properties": #{
        "ok": #{ "type": "boolean" },
        "evidence": #{ "type": "string" },
    },
};
let note_schema = #{
    "type": "object",
    "required": ["accept", "critique"],
    "properties": #{
        "accept": #{ "type": "boolean" },
        "critique": #{ "type": "string" },
    },
};
let record_schema = #{
    "type": "object",
    "required": ["committed", "sha"],
    "properties": #{
        "committed": #{ "type": "boolean" },
        "sha": #{ "type": "string" },
    },
};

let prior = "The caps and the deck still read as bricks. Pick the next single move.";
if args != () {
    if args.critique != () { prior = args.critique; }
}

let rules = "Work in /home/worxbend/Projects/macropad-obs. ";
rules += "Forbidden: a light bar, a second knob, a lens, top-face text, a 90 mm square plan, a wider knob well than 11.9 mm, ";
rules += "editing board.toml or firmware or host or app or pcb, reverting the open bay, the M2 stack, the USB axis, the 1.2 mm lip, or the display recess. ";
rules += "Allowed moves, one only: a deeper or more sculpted keycap, a deck reveal around each key no deeper than 0.6 mm, ";
rules += "a top chamfer no larger than 0.8 mm, deeper knob grooves inside the existing band, ";
rules += "or one base silhouette break: underside chamfer up to 2.4 mm, or a finger scoop on each long side no deeper than 1.2 mm. ";

phase("Brainstorm");
let brain = rules + "Propose one allowed move that makes the object less of a plain brick. ";
brain += "Read docs/images/case.png and cad/obs_case/geometry.py. Return move, files, and risk. ";
brain += "Prior note, as data: ";
brain += json_encode(prior);
let idea = agent(brain, #{
    label: "brainstorm:form",
    capability_mode: "execute",
    output_schema: idea_schema,
});
let move = "none";
if idea != () && idea.success && idea.output != () && idea.output.move != () {
    move = idea.output.move;
}

phase("Review");
let review = rules + "Allow the move only if it is one item from the allowed list and it does not break a forbidden rule. ";
review += "Move, as data: ";
review += json_encode(move);
let gate = agent(review, #{
    label: "review:move",
    capability_mode: "execute",
    output_schema: gate_schema,
});
let allow = false;
if gate != () && gate.success && gate.output != () && gate.output.allow == true {
    allow = true;
}

let evidence = "skipped";
if allow == true {
    phase("Implement");
    let fix = rules + "Implement only the allowed move. ";
    fix += "Run python3 cad/build.py check and cad/.venv/bin/python cad/build.py export. ok is true only when both exit 0. Do not commit. ";
    fix += "Move, as data: ";
    fix += json_encode(move);
    let built = agent(fix, #{
        label: "implement:form",
        capability_mode: "all",
        output_schema: impl_schema,
    });
    if built != () && built.success && built.output != () && built.output.evidence != () {
        evidence = built.output.evidence;
    }
}

phase("Critique");
let judge = "Work in /home/worxbend/Projects/macropad-obs. Do not edit. Look at docs/images/case.png and docs/images/rear.png. ";
judge += "Read cad/obs_case/geometry.py for the lip, the key reveal, the cap dish, and the screw bosses. ";
judge += "accept is true only when the device no longer reads as plain bricks: the caps have a visible scoop, each key has a deck shadow, and the body is not a featureless slab. ";
judge += "accept is false when the picture is still bricks. critique is then ONE next allowed move, not a list. ";
judge += "accept is also false if a fastener, the bay, or the USB opening was removed. ";
judge += "Implement note, as data: ";
judge += json_encode(evidence);
let note = agent(judge, #{
    label: "critique:form",
    capability_mode: "execute",
    output_schema: note_schema,
});
let accepted = false;
let critique = prior;
if note != () && note.success && note.output != () {
    if note.output.accept == true { accepted = true; }
    if note.output.critique != () { critique = note.output.critique; }
}

phase("Commit");
let record = "Work in /home/worxbend/Projects/macropad-obs. Stay on main. If the branch is not main, do not checkout and do not commit. ";
record += "If git status is clean, do not commit. ";
record += "If case files are dirty, run python3 cad/build.py check and cad/.venv/bin/python cad/build.py export. ";
record += "If either exits non-zero, do not commit. ";
record += "Stage only paths under cad/obs_case/, cad/exports/, cad/build.py, docs/images/, docs/design.md, and .grok/workflows/. ";
record += "Never stage firmware, host, app, pcb, or board.toml. ";
record += "Commit and push with bash /home/worxbend/.agents/skills/git-pushing/scripts/smart_commit.sh and one conventional subject line. Do not force-push. Do not amend. ";
record += "Write /tmp/macropad-obs-industrial-handoff.md with exactly three lines: ";
record += "accept: ";
record += accepted.to_string();
record += " then a newline, hold: false then a newline, critique: then one line. ";
record += "Critique text: ";
record += json_encode(critique);
record += " Return committed and sha. sha is empty when you did not commit.";
let saved = agent(record, #{
    label: "commit:main",
    capability_mode: "all",
    output_schema: record_schema,
});
let sha = "";
if saved != () && saved.success && saved.output != () && saved.output.sha != () {
    sha = saved.output.sha;
}
log("accept=" + accepted.to_string() + " " + sha);
write_scratch_file("critique.md", critique);
complete(#{
    summary: critique,
    accept: accepted,
    sha: sha,
});
