# Considerations — git-suite

Design decisions that need a human call (not guessed at). See `CONSIDERATIONS.html`
for a rendered worksheet — reply with e.g. `1a, 2b`.

## Taxonomy — open calls from the theme walk

See `TAXONOMY.md` for the decided structure and the discriminators these follow from.

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
