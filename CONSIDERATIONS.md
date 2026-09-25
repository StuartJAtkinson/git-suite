# Considerations — git-suite

Design decisions that need a human call (not guessed at). See `CONSIDERATIONS.html`
for a rendered worksheet — reply with e.g. `1a, 2b`.

## Taxonomy — open calls from the theme walk

See `TAXONOMY.md` for the decided structure and the discriminators these follow from.
Questions 1–6 predate the rung 2/3 walks; 7–15 came out of them.

1. **Proxmox LXC repos** — does "runs on Proxmox" pull `community-scripts/ProxmoxVE`
   and `proxmox-lxc-autoscale` up to Homelab, or does their LXC content keep them in
   Containerization?
2. **Awesome-lists** — file by subject (as done so far with awesome-docker,
   awesome-proxmox-ve, awesome-supabase) or pool them into one leaf?
3. **RDF and Ontology** — one leaf or two?
4. **Media rung is two-dimensional** — mime-type (Video/Music/Photos) vs function
   (the pipeline, which is mime-agnostic within media). If the pipeline gets its own
   leaf, what is it called?
5. **venn.js exists under 3 keys in 3 categories** (Dashboards, Education & Research,
   Documents) — charting or maths-teaching?
6. **Homelab & Server Administration will balloon** to ~80+ once hypervisors,
   orchestration and IaC land. Split it now, or after the whole tree is walked?
7. **Is "Access" the right rung name?** Networking, Authentication and Remote Access
   are about *reaching* a machine; Monitoring is about *watching* one.
8. **Does Remote Access earn a leaf?** mRemoteNG, tigervnc, neko — own leaf, fold into
   Networking, or fold into Operating Systems?
9. **Where do observability dashboards go?** holmesgpt (Monitoring or AI?) and
   homebutler / homelable (Monitoring or Homelab?).
10. **caddy** — automatic-TLS reverse proxy that is also a web server. Networking or
    Web & API Tooling?
11. **Does Security earn a leaf?** Jira-Lens (vulnerability scanning) has no home in
    the current 32.
12. **Does IaC earn a leaf?** ansible-linux-docker, home-ops, khuedoan/homelab,
    homelab-mcp are real declarative members. Split from Homelab or order within it?
13. **Does Hardware earn a leaf?** jetkvm/kvm, openhaystack, 3d-printed-nas,
    gsmarena-scraper are each one-offs in Homelab today.
14. **Where does nerd-fonts go?** Developer tooling or device-side tooling?
15. **`Deployrr` — imperative installer or substrate?** Discriminator 6 says
    imperative; discriminator 5 says substrate. Same shape as question 1.

## Moved from STYLE.md (2026-09-09 — one question file now)

## Open questions for Auto Continue

One line per question, `- ` prefixed — that is the only shape
`consideration_items` (atelier-harness `meta/markdown.rs:280`) recognises.
Answer them inline when atelier interviews this project.
