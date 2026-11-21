# Considerations — git-suite

Design decisions that need a human call (not guessed at). See `CONSIDERATIONS.html`
for a rendered worksheet — reply with e.g. `1a, 2b`.

## Taxonomy — open calls from the theme walk

See `TAXONOMY.md` for the decided structure and the discriminators these follow from.
Each question names its visual: `CONSIDERATIONS.html` (generated, opened off disk)
shows every option side by side with the repos it moves. The `TAXONOMY.md` open-question
number is quoted on each so answers can be written back unambiguously. The option sets
below are the durable copy — the worksheet renders them.

1. **Is "Access" the right rung name?** *(TAXONOMY Q7)* — Rung 2 holds Networking,
   Authentication, Remote Access? and Monitoring. The first three are about *reaching*
   a machine; Monitoring is about *watching* one. Either the rung is named for
   three-quarters of itself, or Monitoring belongs elsewhere.
   a) Keep "Access" — Monitoring is the fourth band (reach it, drive it, watch it).
   b) Split Observability out as its own rung above Access — Monitoring alone, and
      rung 3 onward renumbers.
   c) Rename the rung to cover all four ("The Wire", "Reach & Watch") — nothing moves.

2. **Does Remote Access earn a leaf?** *(TAXONOMY Q8)* — mRemoteNG, tigervnc, neko,
   plus jetkvm/kvm, which the Homelab walk folded in and the doc currently places
   both ways ("still open, folded into Q8" and "stays → Virtualization & Server
   Platforms" — one of those is a contradiction to settle here).
   a) Own leaf "Remote Access" — session transport is distinct from identity and
      from packet transport.
   b) Fold into Networking — the three are session transport over a network
      (Networking 13 → 16).
   c) Fold into Operating Systems — what you're doing is driving a box (OS 11 → 14).

3. **Where does holmesgpt go?** *(TAXONOMY Q9)* — AI incident response over
   observability data. The last of the three: homebutler / homelable were resolved
   into Self-Hosted Dashboards by the 2026-09-11 split.
   a) Monitoring — the function is observing; "it's AI" is implementation, and
      discriminator 2 already says implementation is not domain.
   b) AI — the subject is AI incident response, and AI is an existing leaf.

4. **caddy** — automatic-TLS reverse proxy that is also a web server. *(TAXONOMY Q10)*
   Same shape as the kong call, but kong resolved cleanly and this doesn't.
   a) Web & API Tooling — matches the kong precedent (serving is the function,
      transport the mechanism); this is where it sits today.
   b) Networking — automatic ACME and reverse proxy, beside zoraxy / traefik /
      certmate.

5. **Does Security earn a leaf?** *(TAXONOMY Q11)* — Jira-Lens (vulnerability
   scanning) has no home in the current 32; it isn't Authentication. awesome-scapy
   (packet analysis) sits in Networking.
   a) Earn a Security leaf — a real function with two members; the tree goes to 33.
   b) No new leaf — file scanners under the thing they scan: Jira-Lens → Code &
      Build Tooling (or IT Support), awesome-scapy → Networking.

6. **Does Hardware earn a leaf?** *(TAXONOMY Q13)* — 3d-printed-nas, openhaystack,
   gsmarena-scraper are each one-offs today. The walk's own text: "If three more
   arrive, a Hardware leaf becomes worth earning; until then they file by function."
   a) Earn a Hardware leaf at rung 1 — all three, as the physical-device axis.
   b) No new leaf, file by function — 3d-printed-nas → Storage, openhaystack →
      Home Automation, gsmarena-scraper → IT Support.
   c) Split the difference — 3d-printed-nas + openhaystack earn the leaf,
      gsmarena-scraper → IT Support, jetkvm/kvm decided by question 2.

7. **Where does nerd-fonts go?** *(TAXONOMY Q14)* — dev font/icon aggregation.
   Function is *developer experience*; it is also installed on the user's machine to
   make every application look better. Same leaf, two framings. It sits in IT
   Support & Device Management today.
   a) Code & Build Tooling — file by function (discriminator 3): terminal, editor,
      tmux glyphs.
   b) IT Support & Device Management (stays) — file by what it acts on: the user's
      device, installed globally.

8. **`Deployrr` — imperative installer or substrate?** *(TAXONOMY Q15)* — automates
   home server setup via Docker Compose. Discriminator 6 says imperative (so not
   IaC); discriminator 5 says substrate (so not an application). First clean
   disagreement between those two, and the same shape as question 1, whose principle
   ("the content decides the leaf") answers it directly.
   a) Substrate wins — stays in Orchestration & IaC, beside the declarative IaC.
   b) Imperative wins — moves to Containerization, beside ProxmoxVE and the other
      one-shot install helpers, following Q1's settled principle.

9. **Does Productivity earn its own leaf, or fold into Documents?** *(TAXONOMY Q17)* —
   Arr and Productivity are the two input pipelines. Arr earned a leaf because its
   content is mime-agnostic; Productivity's outputs (email, documents) file under
   Documents, but the pipeline itself is not represented.
   a) Own leaf "Productivity" at rung 5 beside Media Acquisition — the input side
      (email clients, doc tools, web automation) becomes a destination.
   b) Fold into Documents — only outputs matter; the pipeline stays implicit.

Closed already, for reference: TAXONOMY Q1–Q6 and Q12 are resolved and recorded in
`ISSUES.md` (and in `TAXONOMY.md`'s own question list). Q16 — does Data Systems split
into Visualising vs not — is deferred until the leaf has a fourth or fifth member.

## Moved from STYLE.md (2026-09-09 — one question file now)

## Open questions for Auto Continue

One line per question, `- ` prefixed — that is the only shape
`consideration_items` (atelier-harness `meta/markdown.rs:280`) recognises.
Answer them inline when atelier interviews this project.

## Cosmetic drift
