let meta = #{
    name: "case-apple-form",
    description: "Sculpt the wedge in the worxbend/macropad CNC language, then commit the pass on main",
    when_to_use: "One brainstorm, review, implement, review cycle. Form source is worxbend/macropad. The supervisor relaunches it until 21:00 Europe/Kyiv on 2026-11-16.",
    phases: [
        #{ title: "Brainstorm", detail: "three form moves" },
        #{ title: "Review", detail: "one brief that keeps the mechanical contract" },
        #{ title: "Implement", detail: "edit the case and export it" },
        #{ title: "Critique", detail: "judge the solid and the picture" },
        #{ title: "Commit", detail: "commit the accepted pass on main" },
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
let brief_schema = #{
    "type": "object",
    "required": ["brief", "reject"],
    "properties": #{
        "brief": #{ "type": "string" },
        "reject": #{ "type": "string" },
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
    "required": ["accept", "done", "stop_adding", "critique"],
    "properties": #{
        "accept": #{ "type": "boolean" },
        "done": #{ "type": "boolean" },
        "stop_adding": #{ "type": "boolean" },
        "critique": #{ "type": "string" },
    },
};
let commit_schema = #{
    "type": "object",
    "required": ["committed", "sha", "subject"],
    "properties": #{
        "committed": #{ "type": "boolean" },
        "sha": #{ "type": "string" },
        "subject": #{ "type": "string" },
    },
};

let prior = "Study /home/worxbend/Projects/macropad. Copy its CNC language onto this wedge: continuous-curvature corners, 45 degree chamfers, one key dish, a grooved dial in a well. Do not copy the square plan, the second knob, the light bar, or the lens.";
if args != () && type_of(args) == "map" && args.critique != () && args.critique != "" {
    prior = args.critique;
}

let fallback = "Form source: /home/worxbend/Projects/macropad, the CNC case, not the printed one. ";
fallback += "Read cad/README.md from the heading What the design is, solids.py case_outline _continuous_outline _corner_curve chamfered_slab, and small_parts.py knob _knob_grooves. Re-derive them on this wedge. Do not import that package. ";
fallback += "Order: (1) Replace the rounded-rectangle outline with a quintic Bezier corner whose curvature is zero on the straight sides. Reference setback is 10.935 mm and handles are 0.6 and 0.2 of that setback. ";
fallback += "(2) 45 degree chamfers only, no fillets. 0.5 mm on the outer top rim. 0.3 mm on the lower outer edge of the top. 1.7 mm on the base underside so the base recedes. The 1.5 mm key plate cannot take a 1.7 mm chamfer. ";
fallback += "(3) One dish, not nine square holes. Flat floor, 45 degree walls up to a raised rim. Keys and the glass stay coplanar on that floor. MX cuts stay 14 mm through the floor. The glass stays flush with the floor. No overlay lens. ";
fallback += "(4) Knob stays 22 mm. One band of 36 straight 90 degree V grooves, 0.35 mm deep, between two plain bands. Flat top. One radial pointer. A well about 0.7 mm deep. If the well hits a keycap, shrink the well. Do not move the knob. ";
fallback += "(5) USB mouth gets rounded corners and a 0.3 mm lead-in. The shadow gap stops 2 mm short of the mouth. ";
fallback += "Keep the 8 degree wedge, the vertical rear wall, the spans, and board.toml. No light bar, no second knob, no SK6812, no engraved worxbend wordmark, no text on the top face. ";
fallback += "Render graphite metal and a dark knob: top #8d9096, base #4a4c50, glass #121316, knob #2a2c30. ";
fallback += "Run python3 cad/build.py check and cad/.venv/bin/python cad/build.py export. Both must exit 0. ";
fallback += "If a later step throws, keep the earlier good step. If the file will not import, git checkout the files you touched. ";
fallback += "Update docs/design.md only where a shell sentence is now false.";

fn map_ok(result) {
    if result == () { return false; }
    if result.success != true { return false; }
    if type_of(result.output) != "map" { return false; }
    return true;
}

phase("Brainstorm");
let axes = [
    "continuous-curvature corners and 45 degree chamfers, with the base receding under a 1.7 mm underside chamfer",
    "one key dish with 45 degree walls, keys and glass coplanar on the floor, no overlay lens",
    "one 22 mm dial: 36 V grooves in a single band, plain bands, a radial pointer, and a shallow well",
];
let jobs = [];
let n = 0;
for axis in axes {
    let bp = "You are designing the macropad-obs case. Read these files before you answer: ";
    bp += "/home/worxbend/Projects/macropad-obs/cad/obs_case/geometry.py, ";
    bp += "/home/worxbend/Projects/macropad-obs/cad/obs_case/render.py, ";
    bp += "/home/worxbend/Projects/macropad-obs/docs/images/case.png, ";
    bp += "and the Case section of /home/worxbend/Projects/macropad-obs/docs/design.md. ";
    bp += "Also read /home/worxbend/Projects/macropad/cad/README.md, docs/images/cad/hero_aluminium.png, docs/images/cad/knob_detail.png, and docs/images/cad/deck_detail.png. ";
    bp += "Use read_file. Do not edit. Propose one move for this axis only, taken from that CNC case: ";
    bp += axis;
    bp += ". This product stays an 8 degree wedge, 95.2 by 157.2 mm. Do not propose the 90 mm square, a second knob, a light bar, a lens, or a fillet. ";
    bp += "The glass stays flush with the key plate. Pocket stays 43.22 by 60.76 by 2.35. Knob diameter stays 22 mm. Rear wall stays vertical. ";
    bp += "Do not propose LEDs, paint, a red part, text on the top face, or a board.toml change. ";
    bp += "Prior critique, JSON: ";
    bp += json_encode(prior);
    jobs.push(#{
        prompt: bp,
        label: "brainstorm:" + n.to_string(),
        capability_mode: "read-only",
        output_schema: idea_schema,
    });
    n += 1;
}
let ideas = parallel(jobs);

let packed = "[]";
if ideas != () && type_of(ideas) == "array" {
    let rows = [];
    for idea in ideas {
        if map_ok(idea) {
            rows.push(idea.output);
        }
    }
    if rows.len() > 0 {
        packed = json_encode(rows);
    }
}

phase("Review");
let rp = "Read /home/worxbend/Projects/macropad-obs/cad/obs_case/geometry.py and /home/worxbend/Projects/macropad-obs/cad/obs_case/numbers.py before you answer. ";
rp += "Pick a buildable brief from these proposals: ";
rp += packed;
rp += ". Reject any move that changes tilt, spans, key coordinates, glass size, pocket size, hole diameters, or board.toml. Reject LEDs, a lens, a logo, and paint. ";
rp += "The brief must name the edit in geometry.py: Bezier outline, 45 degree chamfers, one dish, then the grooved dial in a well. ";
rp += "Reject a plain RectangleRounded, a fillet, a light bar, a second knob, and a lens. ";
rp += "If stop_adding is true in the prior critique, the brief may only fix the named defect. Prior critique, JSON: ";
rp += json_encode(prior);
rp += ". Return brief and reject. The brief is orders to a CAD editor, not an essay.";
let pick = agent(rp, #{
    label: "review:brief",
    capability_mode: "read-only",
    output_schema: brief_schema,
});

let brief = fallback;
if map_ok(pick) && pick.output.brief != () && pick.output.brief != "" {
    brief = pick.output.brief;
}
log("brief chosen");

phase("Implement");
let ip = "Edit the macropad-obs case in /home/worxbend/Projects/macropad-obs. Read geometry.py, render.py, numbers.py, and the Case section of docs/design.md first. ";
ip += "Read chamfer in cad/.venv/lib/python3.12/site-packages/build123d/operations_generic.py and call only that signature. Do not fillet. ";
ip += "Read /home/worxbend/Projects/macropad/cad/macropad_case/solids.py and small_parts.py before editing. Re-derive. Do not import them. ";
ip += "Standing orders: keep the CERN-OHL-S header. Do not edit firmware, host, app, pcb, or board.toml. ";
ip += "Do not change the numbers.py expectations. python3 cad/build.py check must stay green. ";
ip += "The show outline is a quintic Bezier corner, not RectangleRounded. Chamfers are 45 degrees: 0.5 top, 0.3 lower top edge, 1.7 on the base underside only. ";
ip += "One dish with 45 degree walls. Its floor holds the keys and the flush glass. Knob grooves are 36 V cuts in one band, as in small_parts.py _knob_grooves, on the 22 mm knob. ";
ip += "If a later operation throws, keep the last importing solid and say so. If the module will not import, git checkout -- cad/obs_case docs/images/case.png docs/design.md. ";
ip += "Run python3 cad/build.py check, then cad/.venv/bin/python cad/build.py export. Both exit 0, or ok is false. ";
ip += "Quote the last line of each command in evidence. Do not commit. Do not push. ";
ip += "Brief: ";
ip += brief;
let built = agent(ip, #{
    label: "implement:case",
    capability_mode: "all",
    output_schema: impl_schema,
});

let impl_ok = false;
let evidence = "implement agent returned nothing";
if map_ok(built) {
    if built.output.ok == true { impl_ok = true; }
    if built.output.evidence != () { evidence = built.output.evidence; }
}

phase("Critique");
let cp = "Judge the macropad-obs case after this edit. Read the diff with git diff, read docs/images/case.png, and read cad/obs_case/geometry.py. ";
cp += "You may run python3 cad/build.py check. Do not edit files. Do not commit. ";
cp += "accept is true only when the check would pass, the outline is not a plain rounded rectangle, the keys sit in one dish, and the knob has one grooved band between plain bands. ";
cp += "A colour-only render change is accept false. A light bar or a lens is accept false. ";
cp += "done is true only when the picture reads as the macropad CNC case stretched into this wedge: continuous corners, receding base, one dish, grooved dial, and no light bar. ";
cp += "stop_adding is true when another feature would make it busier than an Apple desk object. ";
cp += "critique names the single next fix, or says no further change helps. ";
cp += "Implement evidence, JSON: ";
cp += json_encode(evidence);
let note = agent(cp, #{
    label: "review:form",
    capability_mode: "execute",
    output_schema: note_schema,
});

let accept = false;
let done = false;
let stop_adding = false;
let critique = prior;
if map_ok(note) {
    if note.output.accept == true { accept = true; }
    if note.output.done == true { done = true; }
    if note.output.stop_adding == true { stop_adding = true; }
    if note.output.critique != () && note.output.critique != "" {
        critique = note.output.critique;
    }
}
if impl_ok != true { accept = false; }

phase("Commit");
let gate = "REJECT";
if accept == true { gate = "ACCEPT"; }
let gp = "Work in /home/worxbend/Projects/macropad-obs on branch main. Gate word: ";
gp += gate;
gp += ". If the gate is not ACCEPT, do not commit. ";
gp += "If the gate is ACCEPT: run python3 cad/build.py check and cad/.venv/bin/python cad/build.py export. ";
gp += "If either exits non-zero, do not commit. Restore nothing that you did not edit. ";
gp += "Confirm git branch --show-current prints main. If it does not, do not checkout and do not commit. ";
gp += "Stage only paths this pass changed under cad/obs_case/, cad/exports/, docs/images/case.png, and docs/design.md. ";
gp += "Never stage firmware, host, app, pcb, or board.toml. If board.toml is dirty, do not commit. ";
gp += "Commit with git commit -F using a message file under /tmp. Subject like the repo log: feat: then why the form changed. ";
gp += "Do not push. Do not amend. Do not reset. ";
gp += "Always write /tmp/macropad-obs-apple-handoff.md with these lines: ";
gp += "done, accept, stop_adding, committed, sha, subject, and critique. ";
gp += "Use done ";
gp += done.to_string();
gp += ", accept ";
gp += accept.to_string();
gp += ", stop_adding ";
gp += stop_adding.to_string();
gp += ". Critique text: ";
gp += json_encode(critique);
gp += ". Return committed, sha, and subject. Empty sha if you did not commit.";
let saved = agent(gp, #{
    label: "commit:main",
    capability_mode: "all",
    output_schema: commit_schema,
});

let sha = "";
let subject = "";
let committed = false;
if map_ok(saved) {
    if saved.output.committed == true { committed = true; }
    if saved.output.sha != () { sha = saved.output.sha; }
    if saved.output.subject != () { subject = saved.output.subject; }
}
log(gate + " committed=" + committed.to_string() + " " + sha);

write_scratch_file("handoff.md", critique);
complete(#{
    summary: critique,
    accept: accept,
    done: done,
    stop_adding: stop_adding,
    committed: committed,
    sha: sha,
    subject: subject,
});
