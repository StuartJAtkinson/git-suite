# Taxonomy — git-suite

Working state of the theme/category ontology. Supersedes the flat 32-category
list in `category_dividers.html` as it gets walked theme by theme.

**Status 2026-09-07:** Single Computer rung closed. Access rung is next.

## The ordering principle

Three layers, per Stuart's standing scheme:

1. **Tree of Knowledge** supplies the domains — an ascending order from raw
   compute to art. Stuart's phrasing: *"the import of those elements, the
   processing, the structure and the specialisation."*
2. **BFO** is the intended upper ontology the domains map onto.
3. **Wikidata Item-Property-Value** triples are the intended linking mechanism.

### The discriminators, in the order they were derived

Applied in this order when placing a repo:

1. **Domain-agnostic → domain-specific.** *The* axis. Generic sits low,
   specialised sits high. A filesystem doesn't care what the bytes are; Arr
   cares intensely that the thing is a consumable media item.
2. **File by what it does, not what it's packaged in.** Docker is delivery,
   not domain. Nearly everything ships as an image; treating that as signal
   makes Container swallow the corpus.
3. **File by function, not by object.** `ansible-linux-docker` is an Ansible
   role that installs Docker — it's configuration management, not
   containerization. An Ansible role that installs Postgres isn't a database.
4. **Engine vs dataset.** Software that stores and queries → Database.
   Content that happens to be stored → its subject's leaf. Test: *does it
   know what the data means?* `anime-offline-database`, `pc-part-dataset` and
   `multitudes` all failed this.
5. **Substrate vs application.** Hypervisors, orchestrators and config
   management are substrate → Homelab. Applications go to their domain leaf.
6. **Declarative desired-state** distinguishes real IaC (Ansible, Terraform)
   from one-shot imperative installers (ProxmoxVE helper scripts, Deployrr).

**Rejected discriminator:** "does it require more than one machine". Proposed
early, used to justify a Virtualization leaf, then abandoned — it disagreed
with the function test on ProxmoxVE and mislabels hypervisors, which are
homelab substrate regardless of node count.

## Rung 1 — Single Computer *(CLOSED)*

Leaves: **Operating Systems · Containerization · Storage · Database**

### Operating Systems *(new)*
OS distros, bare metal, single-box tweak/debloat tooling, OS emulation and
compat layers.

Members: windows95, winutil, linutil, GoAwayEdge, chromeos-apk, puter,
Windows11-3.0, dotnet9x, Windows-MCP, runwhenidle, netboot.xyz

Absorbs single-machine tooling currently misfiled in Homelab & Server
Administration.

### Containerization *(was "Container")*
Container runtimes and container lifecycle management.

Members: portainer, rancher¹, dockge, podman, watchtower, awesome-docker,
komodo, proxmox-lxc-autoscale², community-scripts/ProxmoxVE², Deployrr

¹ rancher is orchestration → Homelab.
² Open: does "runs on Proxmox" pull these to Homelab? Substrate-wins says yes.

Latent fault line, not split (leaf too thin): **runtimes** (docker, podman,
containerd, runc) vs **lifecycle management** (portainer, dockge, komodo,
watchtower). Revisit if the leaf grows.

**Virtualization is NOT a leaf** — hypervisors (Proxmox, VMware, KVM, Xen,
QEMU, libvirt) are homelab substrate. Stuart's call, 2026-09-07.

### Storage
Domain-agnostic persistence **and** organisation of files. Merged with the
briefly-proposed "File Management" leaf — Stuart's original gloss was
"Filesystems and the sort", which already meant this.

Members: minio, nextcloud/all-in-one (recovered from Business),
nextcloud/desktop, llama-fs, TagStudio, + a mime-type element still to land

The line that keeps it honest: **a mime-type sorter is Storage; a thing that
knows what a *season* or an *album* is, is Arr.** Generic type vs domain
semantics.

Consequence: organise-vs-serve is not a rung-level axis, it's a within-domain
one. Storage holds both (nextcloud serves, TagStudio organises).

Evicted: pc-part-dataset → IT Support; zrok → Networking; gcloud-mcp →
Homelab/AI; timelinize + simklExporter → Lifelogging

### Database
Database engines and generic database tooling. **Not split by model** —
Stuart's call. Relational → multi-model → graph is ordered *within* the leaf.

In: neo4j, arangodb, supabase, nocodb, rel8, opteryx, SchemaCrawler,
cloudbeaver (from Knowledge Base), sql_schema_visualizer (from Monitoring),
bytebase + sql-schema-miner (from Data & Systems Management), awesome-supabase
(from Web & API Tooling), neo4J-SQL-Graphs, awesome-neo4j, awesome-graph

Out: system-design-101 → Education; multitudes → Knowledge Base/Webcrawl;
anime-offline-database → Video; pandas-ai + vanna + huggingface/datasets → AI;
airbyte + vectorflow → AI or Data Input (Stuart had them in AI); pyvenn →
Dashboards; sparql.anything → Ontology

Graph stays inside Database — a storage model, not a semantic commitment. RDF
is where edges carry meaning, and that's the specialisation threshold.

## New leaves earned so far

Each was one of Stuart's "might become relevant" placeholders; each turned out
to have repos already scattered across unrelated categories.

- **Lifelogging** — timelinize, timeliner, ActivityWatch, aw-watcher-ask,
  aw-watcher-netstatus, aw-watcher-media-player, awesome-quantified-self,
  simklExporter. Currently spread over 7 categories. Swallows the separate
  "Activity Watch?" placeholder — they're the same thing.
- **Ontology** — CommonCoreOntologies, ontologiesUK, skoseditor,
  sparql.anything, Ontologies, OpenMetadata. All stranded in Data & Systems
  Management. Open: is **RDF** a separate leaf or does it fold in?
- **Webcrawl** — twitterscraper, tweetext. Thin so far.
- **Media Pipeline** *(name undecided)* — the renamed Arr. See below.

## Leaves being dissolved

- **Data & Systems Management (26)** — not a theme, a residue. It's the
  fallback for `classify_repos.py`'s coarse Development/Infrastructure labels
  (lines 70, 80). Nothing in it shares a domain with anything else in it.
- **Arr (17)** — a suffix, not a domain, and it names software not in the
  corpus (no Sonarr/Radarr/Prowlarr anywhere). Real content is acquisition
  (yt-dlp, qBittorrent) + watch-state sync (Simkl/Trakt tooling). Rename.

## Open questions

1. **Proxmox LXC repos** — does "runs on Proxmox" pull `ProxmoxVE` and
   `proxmox-lxc-autoscale` up to Homelab, or does LXC content keep them in
   Containerization?
2. **Awesome-lists** — file by subject (done so far: awesome-docker,
   awesome-proxmox-ve, awesome-supabase) or pool them in one leaf?
3. **RDF and Ontology** — one leaf or two?
4. **Media rung is two-dimensional** — mime-type (Video/Music/Photos) vs
   function (the Arr pipeline, which is mime-agnostic within media). Stuart
   leans mime-type for content + pipeline as its own leaf. Name for the
   pipeline leaf: Media Pipeline / Media Acquisition / Media Library?
5. **venn.js exists under 3 keys in 3 categories** (Dashboards, Education &
   Research, Documents). Decide once: charting or maths-teaching?
6. **Homelab & Server Administration will balloon** — 49 today, plus
   hypervisors, orchestration and IaC, minus single-box tooling leaving for
   Operating Systems. Likely 80+. Will need splitting later on grounds
   internal to itself, best judged after the whole tree is walked.

## Caveat on all counts

Every category count here is the output of length-weighted keyword voting over
LLM-written prose (`classify_repos.py:99`). See ISSUES.md — assignments are
close to arbitrary for any repo whose description lacks a long matching tag,
and the tag vocabulary describes a *different corpus* (homelab-designer's).
Treat app placements as suggestions to overrule, not evidence.

## Next

**Rung 2 — Access:** Authentication · Networking · Monitoring
