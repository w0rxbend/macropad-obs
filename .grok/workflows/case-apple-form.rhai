let meta = #{
    name: "case-apple-form",
    description: "Sculpt the wedge toward an Apple unibody desk product, then commit the pass on main",
    when_to_use: "One brainstorm, review, implement, review cycle. The supervisor relaunches it until 21:00 Europe/Kyiv on 2026-11-16.",
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

let prior = "The case is a sharp slab. The base plan is a box under a rounded plate. Holes are square. The knob is a smooth cylinder. Nobody would put this on a desk next to an Apple product.";
if args != () && type_of(args) == "map" && args.critique != () && args.critique != "" {
    prior = args.critique;
}

let fallback = "Required form, in this order, in cad/obs_case/geometry.py. ";
fallback += "The base is a sharp box. The top plate is already a rounded rectangle. Make the wedge blank and the shadow-gap inset use that same rounded plan, centred on the outer span, inset by shadow_gap on every side. ";
fallback += "The rear wall stays vertical. Do not change tilt, spans, key positions, the 14 mm MX cuts, glass size, pocket plan, pocket depth, hole diameters, or board.toml. ";
fallback += "Then replace the smooth knob with a 22 mm dial: 30 straight flutes about 0.45 mm deep, flat top, one shallow indicator notch. Same axis and height. ";
fallback += "Then chamfer the top-face lips of the outer profile, the key cuts, and the glass pocket by 0.4 mm. plate_web is 1.5 mm, so do not use a larger chamfer. ";
fallback += "build123d chamfer(edges, length) is the installed call. Confirm it in cad/.venv before using it. ";
fallback += "In render.py set the metal to graphite, not a white slab: top #6e7074, base #3a3c40, glass #121316, knob #8a8d92. Draw a thin edge so the radius is visible. ";
fallback += "No LEDs, no lens, no logo, no paint, no second top surface. ";
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
    "unibody plan: the base must follow the top radius, with a uniform shadow gap, not a box under a rounded plate",
    "the knob as one machined metal dial, 30 flutes, no pointer cap and no logo",
    "opening lips and the USB mouth: a small machined edge break, openings staying at their contract size",
];
let jobs = [];
let n = 0;
for axis in axes {
    let bp = "You are designing the macropad-obs case. Read these files before you answer: ";
    bp += "/home/worxbend/Projects/macropad-obs/cad/obs_case/geometry.py, ";
    bp += "/home/worxbend/Projects/macropad-obs/cad/obs_case/render.py, ";
    bp += "/home/worxbend/Projects/macropad-obs/docs/images/case.png, ";
    bp += "and the Case section of /home/worxbend/Projects/macropad-obs/docs/design.md. ";
    bp += "Use read_file. Do not edit. Propose one Apple unibody move for this axis only: ";
    bp += axis;
    bp += ". Apple here means a quiet graphite aluminum desk object: one deck, continuous plan radius, precise shadow gap, no fastener on the top face, no lamp, no logo. ";
    bp += "The mechanical contract stays: 8 degree tilt, spans 95.2 by 157.2 mm, flush glass 42.72 by 60.26 in a 43.22 by 60.76 by 2.35 pocket, 14 mm key cuts, 22 mm knob, rear wall vertical. ";
    bp += "Do not propose LEDs, a lens, paint, a red part, or a board.toml change. ";
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
rp += "The brief must name the edit in geometry.py: rounded wedge plan, then the knurled dial, then a 0.4 mm top lip chamfer. ";
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
ip += "Read chamfer and fillet in cad/.venv/lib/python3.12/site-packages/build123d/operations_generic.py and call only signatures that are in that file. ";
ip += "Standing orders: keep the CERN-OHL-S header. Do not edit firmware, host, app, pcb, or board.toml. ";
ip += "Do not change the numbers.py expectations. python3 cad/build.py check must stay green. ";
ip += "The base today is a Box inset. Replace that plan with the same rounded rectangle as the top plate, centred, inset by shadow_gap, before you add decoration. ";
ip += "Chamfer only after the cuts. 0.4 mm on the 1.5 mm plate. Knob flutes are 30 subtracted edge cylinders, about 0.45 mm deep, not a texture image. ";
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
cp += "accept is true only when the check would pass, the base plan is rounded with the top, and at least one of knurl or lip chamfer is in the solid. ";
cp += "A colour-only render change is accept false. ";
cp += "done is true only when the picture reads as a machined graphite desk product: rounded body, shadow gap, machined dial, broken opening lips, and no new greeble left to add. ";
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
