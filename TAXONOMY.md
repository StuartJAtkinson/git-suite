# Taxonomy — git-suite

Working state of the theme/category ontology. Supersedes the flat 32-category
list in `category_dividers.html` as it gets walked theme by theme.

**Status 2026-09-11:** Single Computer rung closed — the single-node,
bare-metal material is done. Currently walking the device / homelab material:
Access rung walked but not closed (questions 7–11), Substrate rung walked but
not closed (questions 1, 9, 12, 13, 14, 15 still hold; questions 5 and 6
resolved on 2026-09-11 — Q5 implementation landed on 2026-09-25, Q6 by the
Homelab split below).

**This is a manual walk, and stays one.** The scripted classifier
(`classify_repos.py`) and its borrowed tag vocabulary (`category_tags.json`,
lifted wholesale from homelab-designer and describing a different corpus) were
removed on 2026-09-11 along with their outputs `repo_categories.json` and
`repo_domain_dump.json`. They were producing confident nonsense — `3d Printing`
into Music, `Adblocking` into Storage, the whole remote-access vocabulary into
Authentication — and every count they emitted had to be overruled by hand
anyway. Nothing replaces them. This document is the record of the alignment,
rung by rung, and the discriminators below are the criteria to apply by hand
when placing a repo. Do not re-script this.

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
3. **File by function, not by object.** `ansible-linux-docker` ships Ansible
   *inside* a container so it can manage Linux/Windows/macOS hosts — it's
   configuration management, not containerization. (Earlier drafts of this
   line described it as "an Ansible role that installs Docker"; that was
   wrong about the repo, right about the conclusion.) An Ansible role that
   installs Postgres isn't a database either.
4. **Engine vs dataset.** Software that stores and queries → Database.
   Content that happens to be stored → its subject's leaf. Test: *does it
   know what the data means?* `anime-offline-database`, `pc-part-dataset` and
   `multitudes` all failed this.
5. **Substrate vs application.** Hypervisors, orchestrators and config
   management are substrate → the Rung 3 substrate leaves
   (Virtualization & Server Platforms, Orchestration & Infrastructure as
   Code, Self-Hosted Dashboards). Applications go to their domain leaf.
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

Absorbs single-machine tooling currently misfiled in the Homelab leaves
(Rung 3 substrate).

### Containerization *(was "Container")*
Container runtimes and container lifecycle management.

Members: portainer, rancher¹, dockge, podman, watchtower, awesome-docker,
komodo, proxmox-lxc-autoscale², community-scripts/ProxmoxVE², Deployrr

¹ rancher is orchestration → Rung 3 substrate (Orchestration &
   Infrastructure as Code).
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

## Rung 3 — Substrate *(WALKED, not closed)*

Leaves: **Virtualization & Server Platforms · Orchestration & Infrastructure as Code · Self-Hosted Dashboards · IT Support & Device Management**

Rung 1 was one box. Rung 2 was the wire between boxes. This rung is **the
fleet**: the systems that turn one box into a place you can run, manage and
support many boxes. Ascending inside the rung — stand up the box
(Virtualization), then automate the box (Orchestration & IaC), then put a
face on the box (Self-Hosted Dashboards), then keep the user's hands on the
box (IT Support).

Substrate-wins, as decided in rung 1: anything whose function is *creating and
running more boxes* belongs here, regardless of the host OS or hypervisor
underneath.

This rung was walked on 2026-09-07 as a single Homelab & Server
Administration leaf holding ~25 repos; the leaf split into three on
2026-09-11 once it was clear that hypervisors, orchestration, IaC and
self-hosted dashboards were four distinct sub-axes that would each grow
past 20 members on their own (open question 6). Splitting now keeps each
leaf at rung-3's natural granularity — stand up / automate / face — and
removes the "wait for the corpus to grow" risk.

### Virtualization & Server Platforms

Provision substrate: hypervisors and the platforms that *stand up the box*.
What runs *on* the box is out of scope for this leaf; only the platform
itself counts.

Members: community-scripts/ProxmoxVE, cozystack/cozystack, jetkvm/kvm,
Corsinvest/awesome-proxmox-ve (meta index, file by subject per question 2)

`jetkvm/kvm` is a hardware IP-KVM, not a software hypervisor — kept here on
the *what-it-acts-on* test (it is how you reach a box once stood up) and
the rung's natural ordering. Rung 1's footnote already settled that a
hypervisor is substrate regardless of node count; `cozystack` is two layers
down at once (Kubernetes is container orchestration, KubeVirt is
virtualization) and lands here on the same shape as ProxmoxVE.

### Orchestration & Infrastructure as Code

Automate a fleet — declaratively (IaC) or imperatively (run-books) — but
*not* one-shot install helpers, which stay with the platforms they stand
up. Discriminators 5 and 6 both fire here; substrate-wins + declarative
desired-state.

**Container / fleet orchestration:** komodo, homelab-core, Olares
(platform on top of a fleet)

**IaC (declarative, discriminator 6):** Peco602/ansible-linux-docker (the
repo discriminator 3 is named after — moved out of Container on
2026-09-07), mirceanton/home-ops (Kubernetes via GitOps),
khuedoan/homelab (bare disk → cluster), bjeans/homelab-mcp (Ansible
inventory). Resolves open question 12 — IaC does earn a leaf, and it is
this one, sharing it with fleet orchestrators.

**Held pending question 1:** proxmox-vm-autoscale, proxmox-lxc-autoscale
(Container) — substrate-wins says they belong here; held in Container until
question 1 (does "runs on Proxmox" pull a repo out of Container) is
answered for ProxmoxVE itself.

**Imperative installer, same leaf:** SimpleHomelab/Deployrr (open question
15 — first clean disagreement between discriminators 5 and 6; landed here
because discriminator 5 wins, same shape as ProxmoxVE).

### Self-Hosted Dashboards

Application-layer UIs that aggregate or admin a homelab from the *outside*.
This leaf is application, not substrate — discriminators 1, 2 and 3 all
fire: the dashboard knows what it's looking at (Heimdall bookmarks,
Organizr service pages), the docker packaging is delivery not domain, the
function is aggregation not automation.

Members: Heimdall, Organizr, homebutler, homelable, lg-washer-dryer-card
(Home Assistant card specialised to laundry), homelab-discovery

`homebutler`/`homelable` were held as open question 9 against Monitoring
on 2026-09-07 (substrate vs function discriminators disagreed for the first
time). Splitting Homelab resolves it: the function discriminator lands them
in this leaf, and the substrate discriminator is *also* satisfied (they act
on the homelab itself), so the disagreement was only with the old
single-leaf framing.

### Walked against Stuart's actual Homelab list *(2026-09-07)*

Fifteen repos checked one at a time. Eleven hold, four don't.

**Confirmed Homelab — already there:** `community-scripts/ProxmoxVE` ·
`cozystack` · `homebutler` · `homelable` · `homelab-mcp` ·
`proxmox-vm-autoscale` · `khuedoan/homelab` · `mortennordbye/homelab` ·
`homelab-core` · `homelab-designer`

**Confirmed Homelab — moved in by this walk:**

- **`Peco602/ansible-linux-docker`** ← Container. Discriminator 2 and 3 both
  fire: the container is *delivery*, the function is config management across
  Linux/Windows/macOS hosts. This is the repo the discriminator-3 example is
  named after, and it was in the wrong leaf the whole time.
- **`mirceanton/home-ops`** ← Container. "Manage a home Kubernetes cluster
  using GitOps principles" — declarative desired state (discriminator 6),
  substrate (5). Not containerization.
- **`awesome-selfhosted`** ← **Business**. Plainly wrong before; its domain
  is literally `self-hosting`. Files by subject per open question 2.
- **`homelab-discovery`** ← Home Automation. Documents/manages home server
  infrastructure; the smart-home entities pulled it sideways.

**Do NOT hold — these four are in the list but fail the discriminators:**

- **`nevalang/neva`** → **Code & Build Tooling**. It's a dataflow
  *programming language* (`domain='programming'`, Go). Nothing about it is
  substrate. This looks like a homelab repo only because it's self-hosted
  infrastructure-adjacent in spirit; by "what does it act upon", it acts on
  source code.
- **`zabbix-docker-monitoring`** → **Monitoring**. Rung 2 already claimed it.
  Discriminator 2: Docker is the *target*, not the domain; the function is
  observability. Keeping it in Homelab would re-open question 9 in the
  opposite direction from `homebutler`/`homelable` — those *are* the homelab,
  this *watches* one.
- **`11notes/docker-netbird`** → **Networking**. Rung 2 claimed it. A VPN
  overlay client that happens to ship as an image (discriminator 2).
- **`awesome-open-source-supporters`** → **Code & Build Tooling**. "Curates
  companies offering free services to open-source projects" — the subject is
  OSS funding, not infrastructure. Its `it support` domain string is the
  classifier's doing, not the repo's.

**Still open: `jetkvm/kvm`.** Substrate (out-of-band fleet management) vs
Remote Access (rung 2's proposed leaf — its function is literally "remotely
control any computer's keyboard, video and mouse"). It's the strongest case
for Remote Access earning a leaf, and the strongest case against. Folded into
open question 8.

**Also surfaced: `SimpleHomelab/Deployrr`** sits in Containerization but
"automates the setup of home servers using Docker Compose". Discriminator 6
calls it imperative (so not IaC); discriminator 5 calls it substrate (so
Homelab). Those two disagree — open question 15.

**Evictions from the old Homelab & Server Administration leaf (63 → ~25 staying):**

- `glances` → Monitoring (it is observability of a single machine)
- `Pulse` → Monitoring (observability of a fleet is still observability)
- `linutil`, `winutil` × 3 → Operating Systems (rung 1: single-machine
  debloat/tweak tooling)
- `Windows-MCP` → Operating Systems (rung 1; the `Windows administration`
  domain string is what scored it wrong here)
- `mRemoteNG`, `neko`, `tigervnc` → Remote Access (rung 2 — currently still
  in Authentication, but the Remote Access leaf pulls them up)
- `headscale`, `zoraxy`, `traefik` → Networking (rung 2)
- `infisical`, `desktop-app` (ivpn), `awesome-scapy`, `unbound` → already
  moved in rung 2
- `homebutler`, `homelable` → *stays* → now lands in **Self-Hosted Dashboards**
  (open question 9 resolved by the 2026-09-11 split)
- `gsmarena-scraper` → *out*: device specs scraping, function is
  data-aggregation about phones. Open question 13 (Devices? Webscrawl? or
  Data & Systems Management for now).
- `free-for-dev` → Code & Build Tooling (developer cloud-service index;
  function is developer productivity, not infrastructure)
- `playwright-tampermonkey-mcp` → Web & API Tooling (userscript
  management, per its domain)
- `twenty` → Business (CRM)
- `astral` → Code & Build Tooling (GitHub starred-repo manager)
- `democracy-watcher` → Civic & Public Affairs (already a leaf)
- `crewAI-examples`, `federated-api-model` (the *other* copy), `graphhopper`
  → already in old Homelab but misclassified by their domain strings;
  `graphhopper` is OSM *routing* — its function is geospatial, its `it
  support` match is from the entities list. Should land on Geospatial &
  Mapping.
- `ZohoAPI` → Business (Zoho sync)
- `bloop` → Code & Build Tooling (codebase search)
- `ossapps` → Wearables/Home Automation (Fitbit clock faces; per its domain
  `wearable technology` — already a rung-1 eviction target)
- `chromeos-apk` → Operating Systems (rung 1: it's an OS compat layer)
- `pc-part-dataset` → IT Support (device specs, see rung-2 discussion; the
  dataset function beats the Storage misclassification)
- `windows95` → Operating Systems (rung 1)
- `proxmox-vm-autoscale`, `proxmox-lxc-autoscale` (Container) → **Orchestration & IaC**
  per open question 1 once decided; held here under "stays in current
  bucket until question 1 is answered"
- `3d-printed-nas` → Hardware (open question 13)
- `openhaystack` → Hardware (Find My network; per its domain `hardware
  hacking` — open question 13)
- `nodejs-portable` → IT Support (single-tool portable installer)
- `awesome-clean-tech`, `awesome-open-source-supporters` → Civic & Public
  Affairs / Code & Build Tooling (awesome-list-by-subject per question 2)
- `xpipe` → Code & Build Tooling (server connection manager, function is
  developer tooling)
- `kvm` (jetkvm) → *stays* → now lands in **Virtualization & Server Platforms**
  per the substrate argument above

**Migration of the ~25 staying (2026-09-11 split):** the
hypervisor/platform members → Virtualization & Server Platforms (4);
fleet orchestrators + IaC + held-proxmox-scalers + Deployrr →
Orchestration & Infrastructure as Code (9); self-hosted dashboards →
Self-Hosted Dashboards (6); the remaining ~6 are named in the walked list
above and stay in the leaf they're already listed under.

### IT Support & Device Management
End-user IT and per-device tooling. The rung's "user-facing" band:
*help-desk, install, configure, repair, find*. The corpus here is mostly
sysadmin resource lists and small utilities, and that is exactly what the
leaf is.

**In (after eviction):**

- `awesome-sysadmin` — resource index, file by subject
- `UniGetUI` — Windows package-manager GUI; function is software
  management, fits
- `nerd-fonts` — dev font/icon aggregation. Function is *developer
  experience*; **open question 14**: developer tooling or device-side
  tooling? It's both.
- `Install-Git`, `GitPortable`, `nodejs-portable` — single-tool installers,
  function is end-user IT
- `scrcpy` — *mobile device management* on Android, function beats the
  Networking misclassification; this is the only non-mobile-management
  member of a non-existent MDM leaf, so it's IT Support for now
- `timelinize` — Lifelogging (rung 2)
- `ThesauRex`, `ontologies` → Ontology (rung 4, not yet walked)
- `IAO`, `aw-import-ical`, `EMailParseAI` × 2, `ClickTheseThings`,
  `all-repos`, `lobehub`, `jira`, `atlassian-python-api`, `portia`,
  `DoIHaveEverything` — small per-user IT utilities, stay
- `federated-api-model` (the public-sector copy) → Civic & Public Affairs

**Out:**

- `federated-api-model` (gov copy) → Civic & Public Affairs
- `pc-part-dataset` → IT Support (per above)
- The 17 misclassifications that landed here purely because their
  `it support`/`government it`/`public sector it` keywords matched —
  resolved by function, not by the keyword.

After this walk, IT Support & Device Management holds ~20 members. Still
small, still real.

## Rung 2 — Access *(WALKED, not closed)*

Leaves: **Networking · Authentication · Remote Access?¹ · Monitoring**

The rung's throughline: rung 1 was one box; this rung is *the box reached over
a wire*. Ascending inside the rung — move the bytes (Networking), decide who
may (Authentication), drive the session (Remote Access), watch it stay up
(Monitoring). All four are domain-agnostic: none of them knows what the traffic
means. That is what keeps the whole rung low on the main axis.

¹ Proposed, not earned — see open question 8.

### Networking
Moving bytes between machines, plus the naming, routing and encryption that
makes it possible.

Recovered into it: **unbound** (from Authentication — DNS) · **tailscale**,
**headscale** · **docker-netbird** (from Productivity) · **gluetun** (from
Container — discriminator 2: it's a VPN client that happens to ship as an
image) · **ivpn/desktop-app** (from Authentication — a VPN client, not an
identity provider) · **zrok/openziti** (from Storage, per rung 1's eviction) ·
**zoraxy**, **traefik** (from Homelab — reverse proxy / ingress) ·
**certmate** (TLS lifecycle) · **awesome-scapy** (from Authentication) ·
**network-sketcher** (from Productivity) · **alternative-internet**

Evicted: Windows11-3.0 → Operating Systems (rung 1) · linkedin-api → Social
Media · streets-gl, free-map-genie → Geospatial / Games · discord-transcriber →
Social Media · langgraph-search-agents → AI ·
sonarr-radarr-lidarr-autosearch-browser-extension → Media Pipeline ·
infisical → Authentication

Two that resist the leaf, both by the function test:
- **kong** — an API gateway. Its function is API lifecycle management, not
  packet transport → Web & API Tooling. Substrate-vs-application agrees.
- **caddy** — cuts both ways: serving sites is Web & API Tooling, automatic
  ACME + reverse proxy is Networking. Currently Web & API Tooling. Open
  question 10.

Latent fault line, not split: **transport** (VPN, overlay, DNS, proxy) vs
**security appliance** (firewall, WAF, adblock). The corpus has essentially no
firewall repos, so the second half doesn't exist yet. Revisit if it fills.

### Authentication
Proving who someone is and what they may reach.

In: **authelia**, **keycloak**, **awesome-iam**, **infisical** (from
Networking — privileged access + secret custody; note it exists under two keys
in two categories, see the key-normalisation issue in ISSUES.md)

Evicted: **openbr** → AI/vision. It is a face-recognition SDK; discriminator 3
says file it by function (recognition), not by one of its applications
(authentication). · **Jira-Lens** → security scanning, see below · **unbound**,
**awesome-scapy**, **desktop-app** → Networking · **puter** → Operating Systems
(rung 1) · the remote-access block → next leaf.

Secret management (infisical, and Vault/Bitwarden if they ever land) sits here
rather than Storage on the engine-vs-dataset test: a password vault *does* know
what its data means, so it's domain-specific, not generic persistence.

Leaf is thin — 4 members. It survives because it's a real function, not because
of its size.

### Remote Access *(proposed leaf)*
Reaching and driving a machine you aren't sitting at.

Members: **mRemoteNG**, **tigervnc**, **neko**

This is the single largest block currently inside Authentication and it isn't
authentication: the function is *transporting a session*, not *proving an
identity*. The cause was mechanical — the removed tag vocabulary put ten
remote-access terms (`Rdp`, `Vnc`, `Ssh`, `Novnc`, `Guacd`, `Putty`,
`Teamviewer`, `Remote Desktop`, `Remote Access`, `Remote Management`) in the
Authentication pool, so anything mentioning RDP or VNC was routed to identity
management. Placed by hand, these three go to session transport.

Three members is thin, and it has two plausible homes instead. Open question 8.

### Monitoring
Observing whether all of the above is healthy — metrics, uptime, alerting,
logs. Domain-agnostic instrumentation.

In: **uptime-kuma**, **netdata**, **Pulse** (from Homelab), **glances** (from
Homelab), **zabbix-docker-monitoring** (from Container — discriminator 2)

Evicted — **19 of the current 24 members**, making this the noisiest category
in the corpus: games (xenia, WoWAnalyzer, FFXIVPlugin, xiv-resources,
Tetra-Master-Clone, graph-dungeon-generator, obababot, Pogo-Account-Checker,
card-collector) · Lifelogging (aw-watcher-netstatus, simklExporter,
Interests-network-graph) · Gource → Code & Build Tooling · sql_schema_visualizer,
QueryGraph → Database (rung 1) · elasticsearch-analysis-skos → Ontology ·
manami → Video · gpsbabel → Geospatial · lg-washer-dryer-card → Home
Automation · huginn → Productivity (web automation that happens to watch pages)
· tailslayer → Operating Systems

Unresolved members: **holmesgpt** (AI incident response over observability data
— function says Monitoring, implementation says AI) and **homebutler** /
**homelable** (homelab status dashboards — discriminator 5 sends them to
Homelab, function says Monitoring). Open question 9.

### Security scanning is NOT in this rung
**Jira-Lens** is a vulnerability scanner and **awesome-scapy** is packet
analysis; neither is access control. There is no Security leaf among the
current 32. Open question 11.

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

- **Data & Systems Management (26)** — not a theme, a residue. It was the
  fallback bucket for the removed classifier's coarse Development /
  Infrastructure labels. Nothing in it shares a domain with anything else in
  it; the members need placing by hand as the walk reaches them.
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
   Research, Documents). Decide once: charting or maths-teaching? —
   **Resolved 2026-09-11 (2026-09-25 implementation):** **Data Systems**.
   venn.js is visualising data (the function), which the Dashboards leaf
   captures for *dashboards* but not for the broader set-relationship /
   comparative work that venn-style diagrams do for *data* — business,
   hobby, or academic. It lands in a new "Data Systems" leaf at Rung 4,
   alongside Data & Systems Management (the residue bucket that Q5 was
   actually about) but with a clear differentiator: Data Systems is *what
   you do with data*, the residue bucket was *ops tooling that happens to
   touch data*. The split into "Visualising" vs "not-Visualising" stays open
   (open question 16) until the leaf has enough members to make the cut
   self-evident; today it has one.
6. **Homelab & Server Administration will balloon** — ~~49 today, plus
   hypervisors, orchestration and IaC, minus single-box tooling leaving for
   Operating Systems. Likely 80+. Will need splitting later on grounds
   internal to itself, best judged after the whole tree is walked.~~
   **Resolved 2026-09-11:** split now, into Virtualization & Server Platforms,
   Orchestration & Infrastructure as Code, and Self-Hosted Dashboards. The
   "judge after the whole tree" caveat was set when the leaf was one bucket;
   the sub-axes (stand up / automate / face) are already obvious without
   the tree walk, so the wait was costing nothing but the risk of
   absorbing 30 more repos before splitting. Side effect: open questions 9
   (dashboard vs Monitoring) and 12 (does IaC earn a leaf) resolved in the
   same move.
7. **Is "Access" the right rung name?** Networking, Authentication and Remote
   Access are all about *reaching* a machine; Monitoring is about *watching*
   one. Either the rung is named for three-quarters of itself, or Monitoring
   belongs somewhere else. Alternatives: split into "Access" + "Observability"
   as two rungs, or rename to something that covers both (Rung 2 = "The Wire"?).
8. **Does Remote Access earn a leaf?** Three members (mRemoteNG, tigervnc,
   neko). Options: (a) its own leaf; (b) fold into Networking as session
   transport; (c) fold into Operating Systems, since what you're doing is
   driving a box. It is definitively *not* Authentication either way.
9. **Where do observability dashboards go?** holmesgpt (Monitoring or AI?) and
   homebutler / homelable (Monitoring or Homelab?). The substrate discriminator
   and the function discriminator disagree here, which is the first time
   they've conflicted since ProxmoxVE.
10. **caddy** — automatic-TLS reverse proxy that is also a web server.
    Networking or Web & API Tooling? Same shape as the kong call, but kong
    resolved cleanly and this doesn't.
11. **Does Security earn a leaf?** Jira-Lens (vulnerability scanning) has no
    home in the current 32 — it isn't Authentication. Either a Security leaf
    gets earned, or scanners file under the thing they scan (Jira-Lens → Code &
    Build Tooling / IT Support).
12. **Does IaC earn a leaf?** *(corrected 2026-09-07 — an earlier draft of
    this question claimed the corpus had zero IaC. It doesn't.)* Real
    desired-state members exist: `Peco602/ansible-linux-docker` (Ansible),
    `mirceanton/home-ops` (Kubernetes via GitOps), `khuedoan/homelab`
    (bare disk → cluster), and `bjeans/homelab-mcp` carries an Ansible
    inventory. Discriminator 6 cleanly separates these from the one-shot
    imperative installers (`community-scripts/ProxmoxVE`, `Deployrr`). So the
    question is live, not hypothetical: does declarative fleet config split
    off from Homelab, or stay as a within-leaf ordering?
13. **Does Hardware earn a leaf?** `jetkvm/kvm` (IP-KVM), `openhaystack`
    (Find My), `3d-printed-nas`, `gsmarena-scraper` (device data) — each is a
    one-off in Homelab today. If three more arrive, a Hardware leaf becomes
    worth earning; until then they file by function (Networking for KVM, Home
    Automation for Find-My-style trackers, IT Support for specs scrapers).
14. **Where does nerd-fonts go?** Developer tooling (function: glyph/icons
    used in dev work) or device-side tooling (function: installed on the user's
    machine to *make every application look better*)? Same leaf, two
    framings.
15. **`Deployrr` — imperative installer or substrate?** It automates home
    server setup via Docker Compose. Discriminator 6 says imperative (so not
    IaC, stays out of the declarative group); discriminator 5 says substrate
    (so Homelab, not Containerization). First clean disagreement between those
    two discriminators. Same shape as question 1 (`ProxmoxVE`), so both should
    probably be answered together.
16. **Does Data Systems split into Visualising vs not?** Settled on 2026-09-11
    (Q5) that venn.js belongs in a new Data Systems leaf at Rung 4, distinct
    from the Data & Systems Management residue. The decision deferred the
    sub-split — Visualising (charting, diagrams, comparison) vs everything
    else Data Systems ends up holding — until the leaf has enough members to
    make the cut self-evident. With one member today, the split is premature;
    revisit when a fourth or fifth data-tools repo lands here.

## Caveat on all counts

**Every count below the closed rungs is a historical number from a tool that no
longer exists.** They came out of length-weighted keyword voting over LLM-written
prose, against a tag vocabulary describing homelab-designer's corpus rather than
this one. Assignments were close to arbitrary for any repo whose description
lacked a long matching tag.

Treat them as a rough sense of volume — "Homelab is too big", "Monitoring has
eaten things it shouldn't" — and nothing more. A count is not evidence that a
repo belongs where it currently sits. Each rung's real membership is settled by
hand, by applying the discriminators above, and recorded here as the rung closes.
The counts disappear from this document rung by rung as that happens.

## Next

**Rung 3 — Substrate** is walked but not closed: open questions 1, 6, 9, 12,
13, 14 still hold. The structural one is question 6 — Homelab will still
balloon once the deferred substrate categories (hypervisors already in,
IaC/Hardware pending, status dashboards staying) all land. Likely target
size after this walk: ~25 members, not 80+, because much of what *was* in
Homelab was misclassified single-machine tooling that rung 1 evicts.

**Rung 4 — Data & Content** *(proposed)*: Knowledge Base · Dashboards ·
Data Systems · Data & Systems Management · AI · Photos · Music · Video ·
Documents. The substrate runs out here and the rung turns to *what lives on
the box*, not the box itself. **Data Systems** is the new leaf decided on
2026-09-11 (open question 5): venn.js lands here; it captures *what you do
with data* (visualising, comparing, querying, …) and is distinct from Data &
Systems Management, which is the *ops tooling that happens to touch data*
residue. The "Visualising vs not" sub-split is held until the leaf has
enough members to make the cut self-evident. This is also where the tag-pool
issue logged in ISSUES.md hurts most — the "Analysis" / "Tracking" / "Manager"
tags send nearly every one of these to Monitoring right now, so the rung is
likely to be the loudest single correction in the whole walk.
