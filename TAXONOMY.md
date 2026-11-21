# Taxonomy — git-suite

Working state of the theme/category ontology. Supersedes the flat 32-category
list in `category_dividers.html` as it gets walked theme by theme.

**Status 2026-11-21:** Single Computer rung closed — the single-node,
bare-metal material is done. The nine open calls are answered: the Access rung
was **split** — Monitoring now sits in a new **Rung 3 — Observability &
Security** with the newly-earned Security leaf — and Remote Access, Security
and Productivity are earned leaves. Rung 3 (Substrate) renumbered to **Rung 4**;
Data & Content to **Rung 5**; Data Input to **Rung 6**. Decisions and their
reasons are in `CONSIDERATIONS.md`'s history and `ISSUES.md`'s resolved list;
the questions themselves are annotated in "Open questions" below.

**Status 2026-09-11:** Single Computer rung closed — the single-node,
bare-metal material is done. Currently walking the device / homelab material:
Access rung walked but not closed (questions 7–11), Substrate rung walked but
not closed (questions 9, 12, 13, 14, 15 still hold; questions 1, 2, 4, 5
and 6 resolved on 2026-09-11 — Q1 implementation (LXC content stays in
Containerization) and Q2 implementation (file awesome-lists by subject)
landed on 2026-09-29, Q5 implementation on 2026-09-25, Q4 and Q6 by the
Media Acquisition + Homelab splits on 2026-09-25; question 17 opened
on 2026-09-25 to capture the deferred Productivity placement).

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
   management are substrate → the Rung 4 substrate leaves
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
(Rung 4 substrate).

### Containerization *(was "Container")*
Container runtimes and container lifecycle management.

Members: portainer, rancher¹, dockge, podman, watchtower, awesome-docker,
komodo, proxmox-lxc-autoscale, community-scripts/ProxmoxVE, Deployrr²

¹ rancher is orchestration → Rung 4 substrate (Orchestration &
   Infrastructure as Code).
ProxmoxVE and proxmox-lxc-autoscale stay here per question 1 — LXC content
is containerization regardless of the fact that the platform runs on Proxmox.
² Deployrr arrived here on 2026-11-21 (question 15): it ships Docker Compose,
   so its content is containerization — the same principle that put ProxmoxVE
   here, even though it automates home-server setup and so reads as substrate.

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
nextcloud/desktop, llama-fs, TagStudio, 3d-printed-nas (from Homelab —
question 13, resolved 2026-11-21: it stores files, and a NAS knows what its
files are), + a mime-type element still to land

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

## Rung 4 — Substrate *(WALKED, closed 2026-11-21)*

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
leaf at rung-4's natural granularity — stand up / automate / face — and
removes the "wait for the corpus to grow" risk.

### Virtualization & Server Platforms

Provision substrate: hypervisors and the platforms that *stand up the box*.
What runs *on* the box is out of scope for this leaf; only the platform
itself counts.

Members: cozystack/cozystack, Corsinvest/awesome-proxmox-ve
(meta index, file by subject per question 2). `community-scripts/ProxmoxVE`
stays in Containerization — see question 1 (LXC content is containerization,
so the repo belongs there even though it stands up Proxmox itself).

`jetkvm/kvm` was held here on the *what-it-acts-on* test (it is how you reach
a box once stood up) and **moved to Remote Access on 2026-11-21** (question 8)
— an IP-KVM is session transport, not a platform, and the doc had been filing
the same repo under two questions at once. Rung 1's footnote already settled
that a hypervisor is substrate regardless of node count; `cozystack` is two
layers down at once (Kubernetes is container orchestration, KubeVirt is
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
(Container) — kept in Containerization per question 1: LXC content is
containerization regardless of running on Proxmox, and VM autoscale is the
same shape (autoscaler, not stand-up tool — the stand-up helper ProxmoxVE
itself stays in Containerization for the same reason).

**Imperative installer, moved out 2026-11-21:** `SimpleHomelab/Deployrr` sat
here on the discriminator-5 reading (substrate wins), but question 15 settled
the other way: it ships Docker Compose, so its content is containerization and
it lives in **Containerization** beside ProxmoxVE. The leaf is declarative
(discriminator 6) — an imperative installer is not one.

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
  experience*; **resolved 2026-11-21 (question 14): it stays here** — it acts
  on the user's device and is installed to make every application look
  better, which is what "install, configure" means in this leaf. The
  device-side framing wins over the dev-experience one.
- `Install-Git`, `GitPortable`, `nodejs-portable` — single-tool installers,
  function is end-user IT
- `scrcpy` — *mobile device management* on Android, function beats the
  Networking misclassification; this is the only non-mobile-management
  member of a non-existent MDM leaf, so it's IT Support for now
- `timelinize` — Lifelogging (rung 2)
- `ThesauRex`, `ontologies` → Ontology (rung 5, not yet walked)
- `IAO`, `all-repos`, `lobehub`, `jira`, `atlassian-python-api` — small
  per-user IT utilities, stay
- `openhaystack` — Find My network; **resolved 2026-11-21 (question 13):
  IT Support**, filed by function. The leaf's own gloss is "help-desk,
  install, configure, repair, **find**", and a Find My network finds a lost
  device.
- `gsmarena-scraper` — device specs; **resolved 2026-11-21 (question 13):
  IT Support**, filed by function, beside `pc-part-dataset` (also device
  specs) already here.
- `federated-api-model` (the public-sector copy) → Civic & Public Affairs

**Out:**

- `federated-api-model` (gov copy) → Civic & Public Affairs
- `pc-part-dataset` → IT Support (per above)
- `EMailParseAI` × 2, `aw-import-ical`, `ClickTheseThings`, `portia`,
  `DoIHaveEverything` → **Productivity** (2026-11-21, question 17) — the
  input pipeline is mime-agnostic and fits no content leaf, so it earns one.
- `huginn` → **Productivity** — web automation that happens to watch pages
  (evicted from Monitoring to Productivity on 2026-09-07; the leaf it was
  waiting for now exists).
- The 17 misclassifications that landed here purely because their
  `it support`/`government it`/`public sector it` keywords matched —
  resolved by function, not by the keyword.

After this walk, and after the 2026-11-21 moves, IT Support & Device
Management holds ~16 members. Still small, still real.

## Rung 2 — Access *(WALKED, closed 2026-11-21)*

Leaves: **Networking · Authentication · Remote Access**

The rung's throughline: rung 1 was one box; this rung is *the box reached over
a wire*. Ascending inside the rung — move the bytes (Networking), decide who
may (Authentication), drive the session (Remote Access). All three are
domain-agnostic: none of them knows what the traffic means. That is what keeps
the whole rung low on the main axis.

**Monitoring left this rung on 2026-11-21** (open question 7): three of the
four leaves were about *reaching* a machine and Monitoring is about *watching*
one, so it was split out into **Rung 3 — Observability & Security** rather than
renaming the rung to cover both. The rung's own name is unchanged.

### Networking
Moving bytes between machines, plus the naming, routing and encryption that
makes it possible.

Recovered into it: **unbound** (from Authentication — DNS) · **tailscale**,
**headscale** · **docker-netbird** (from Productivity) · **gluetun** (from
Container — discriminator 2: it's a VPN client that happens to ship as an
image) · **ivpn/desktop-app** (from Authentication — a VPN client, not an
identity provider) · **zrok/openziti** (from Storage, per rung 1's eviction) ·
**zoraxy**, **traefik** (from Homelab — reverse proxy / ingress) ·
**certmate** (TLS lifecycle) ·
**network-sketcher** (from Productivity) · **alternative-internet**

`awesome-scapy` (packet analysis, from Authentication) moved out to
**Security** on 2026-11-21 — see § Security.

Evicted: Windows11-3.0 → Operating Systems (rung 1) · linkedin-api → Social
Media · streets-gl, free-map-genie → Geospatial / Games · discord-transcriber →
Social Media · langgraph-search-agents → AI ·
sonarr-radarr-lidarr-autosearch-browser-extension → Media Pipeline ·
infisical → Authentication

Two that resist the leaf, both by the function test:
- **kong** — an API gateway. Its function is API lifecycle management, not
  packet transport → Web & API Tooling. Substrate-vs-application agrees.
- **caddy** — cuts both ways: serving sites is Web & API Tooling, automatic
  ACME + reverse proxy is Networking. **Resolved 2026-11-21 (question 10):
  Web & API Tooling** — the kong precedent decides it, serving is the function
  and transport is the mechanism. It stays where the walk put it.

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

### Remote Access *(leaf — confirmed 2026-11-21)*
Reaching and driving a machine you aren't sitting at.

Members: **mRemoteNG**, **tigervnc**, **neko**, **jetkvm/kvm**

This is the single largest block currently inside Authentication and it isn't
authentication: the function is *transporting a session*, not *proving an
identity*. The cause was mechanical — the removed tag vocabulary put ten
remote-access terms (`Rdp`, `Vnc`, `Ssh`, `Novnc`, `Guacd`, `Putty`,
`Teamviewer`, `Remote Desktop`, `Remote Access`, `Remote Management`) in the
Authentication pool, so anything mentioning RDP or VNC was routed to identity
management. Placed by hand, these three go to session transport.

**Resolved 2026-11-21 (question 8): it earns the leaf.** `jetkvm/kvm` — the
IP-KVM the Homelab walk held open, and the doc's one place that filed the same
repo under two questions — joins it here: out-of-band fleet management is
reaching and driving a machine you aren't sitting at. Its earlier placement
under Virtualization & Server Platforms is withdrawn. Four members is still
thin, but the function is real and distinct from both identity and packet
transport, which is the same reason Authentication survives at four.

## Rung 3 — Observability & Security *(NEW, 2026-11-21)*

Leaves: **Monitoring · Security**

Split out of Rung 2 on 2026-11-21 (question 7): Networking, Authentication and
Remote Access are all about *reaching* a machine, Monitoring is about *watching*
one, and Security is about *proving* it is sound. The rung is domain-agnostic
like Access — none of it knows what the traffic means — so it stays low on the
main axis, but it watches and audits rather than reaches. It sits between Access
and Substrate: you watch a box before you stand up a fleet of them.

### Monitoring
Observing whether all of the above is healthy — metrics, uptime, alerting,
logs. Domain-agnostic instrumentation.

In: **uptime-kuma**, **netdata**, **Pulse** (from Homelab), **glances** (from
Homelab), **zabbix-docker-monitoring** (from Container — discriminator 2),
**holmesgpt** (from the AI leaf — resolved 2026-11-21, question 9)

Evicted — **19 of the current 24 members**, making this the noisiest category
in the corpus: games (xenia, WoWAnalyzer, FFXIVPlugin, xiv-resources,
Tetra-Master-Clone, graph-dungeon-generator, obababot, Pogo-Account-Checker,
card-collector) · Lifelogging (aw-watcher-netstatus, simklExporter,
Interests-network-graph) · Gource → Code & Build Tooling · sql_schema_visualizer,
QueryGraph → Database (rung 1) · elasticsearch-analysis-skos → Ontology ·
manami → Video · gpsbabel → Geospatial · lg-washer-dryer-card → Home
Automation · huginn → Productivity (web automation that happens to watch pages)
· tailslayer → Operating Systems

**holmesgpt** — AI incident response over observability data. Function says
Monitoring, implementation says AI; the two discriminators disagree. **Resolved
2026-11-21 (question 9): Monitoring**, on discriminator 2: "it's AI" is
implementation, not domain — the same rule that keeps Docker packaging out of
the signal. **homebutler** / **homelable** had already been resolved on
2026-09-11 into Self-Hosted Dashboards when the Homelab leaf split — see
§ Self-Hosted Dashboards.

### Security *(leaf earned 2026-11-21)*
Finding the weaknesses in a system: vulnerability scanning and packet analysis.
Domain-agnostic — a scanner does not know what it is scanning.

Members: **Jira-Lens** (vulnerability scanning), **awesome-scapy** (packet
analysis)

**Resolved 2026-11-21 (question 11): a Security leaf is earned.** It was
previously recorded as "not in this rung" — scanning is not access control,
which is still true, so it does not join Access. It sits beside Monitoring
instead: both inspect a running system, one for liveness and one for soundness.
A leaf of two survives the same test Authentication does — it is a real
function, not a size.

## New leaves earned so far

Each was one of Stuart's "might become relevant" placeholders; each turned out
to have repos already scattered across unrelated categories.

- **Lifelogging** — timelinize, timeliner, ActivityWatch, aw-watcher-ask,
  aw-watcher-netstatus, aw-watcher-media-player, awesome-quantified-self,
  simklExporter. Currently spread over 7 categories. Swallows the separate
  "Activity Watch?" placeholder — they're the same thing.
- **Ontology** — CommonCoreOntologies, ontologiesUK, skoseditor,
  sparql.anything, Ontologies, OpenMetadata. All stranded in Data & Systems
  Management. RDF folds in: it is the storage-and-query layer for the same
  semantic content, not a separate leaf.
- **Webcrawl** — twitterscraper, tweetext. Thin so far.
- **Media Acquisition** — the renamed Arr: input pipeline for media-for-leisure,
  mime-agnostic (acquisition + watch-state sync). Output lives in the
  Video/Music/Photos content leaves. See Q4 resolution.

## Leaves earned in the 2026-11-21 walk

Three leaves earned by answering the nine open questions (full reasoning in
`ISSUES.md`, resolved list; the questions are annotated in "Open questions"
below).

- **Remote Access** — mRemoteNG, tigervnc, neko, jetkvm/kvm. Session transport:
  reaching a machine, not proving an identity and not moving packets. Earned
  under question 8; see § Remote Access.
- **Security** — Jira-Lens, awesome-scapy. Finding weaknesses in a running
  system. Earned under question 11; sits beside Monitoring in
  § Rung 3 — Observability & Security.
- **Productivity** *(rung 6, Data Input)* — EMailParseAI, aw-import-ical,
  ClickTheseThings, DoIHaveEverything, portia, huginn. The second input
  pipeline, beside Media Acquisition: on the same argument that earned that
  leaf, its content is mime-agnostic and fits no content leaf — email and
  documents are outputs, the gathering is the thing. Earned under question 17.
  Its outputs still file under Documents.

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
   Containerization? —
   **Resolved 2026-09-11 (2026-09-29 implementation):** **LXC content wins
   — stay in Containerization**. LXCs are containers, so LXC tooling
   belongs in Containerization regardless of the fact that the platform
   runs on Proxmox. `community-scripts/ProxmoxVE` is now listed only under
   Containerization (it was previously duplicated under Homelab), and
   `proxmox-lxc-autoscale` and `proxmox-vm-autoscale` are kept in
   Containerization rather than escalated to Orchestration & IaC. The
   principle: a repo's content decides its leaf, not the platform it runs
   on.
2. **Awesome-lists** — file by subject (done so far: awesome-docker,
   awesome-proxmox-ve, awesome-supabase) or pool them in one leaf? —
   **Resolved 2026-09-11 (2026-09-29 implementation):** **File by subject**.
   The walk already routes every `awesome-*` repo to the leaf of the
   domain it curates (Containerization → `awesome-docker`; Business →
   `awesome-selfhosted`; Code & Build Tooling →
   `awesome-open-source-supporters`; Homelab → `awesome-proxmox-ve`;
   Web & API Tooling → `awesome-supabase`; Data & Systems Management →
   `awesome-neo4j`, `awesome-graph`; etc.) — pooling them into one leaf
   would force the feature-check step to dereference a meta index every
   time, and the end aim is to absorb each listed repo's *feature* into
   an owned primary, not to keep the meta index itself as a destination.
   If a listed repo's features diverge from its host leaf later, the
   absorb step can split it again on its own merits.
3. **RDF and Ontology** — one leaf or two? —
   **Resolved 2026-09-11 (2026-09-29 implementation):** **One**.
   RDF is the storage-and-query layer for the same semantic content, so it
   folds into Ontology rather than earning a separate leaf. Recorded against
   the "Ontology" entry in "New leaves earned so far" above.
4. **Media rung is two-dimensional** — mime-type (Video/Music/Photos) vs
   function (the Arr pipeline, which is mime-agnostic within media). Stuart
   leans mime-type for content + pipeline as its own leaf. Name for the
   pipeline leaf: Media Pipeline / Media Acquisition / Media Library? —
   **Resolved 2026-09-11 (2026-09-25 implementation):** **Media Acquisition**.
   Arr is one of two input pipelines — the other is Productivity (handles
   email + documents for the work-productivity pipeline). Both produce media
   outputs served by the user's normal computers. Arr's real content
   (acquisition: yt-dlp, qBittorrent; watch-state sync: Simkl/Trakt tooling)
   maps cleanly to "Media Acquisition" — the mime-typed leaves (Video,
   Music, Photos) capture the *outputs*, Media Acquisition captures the
   *throughput*. Productivity stays open: not yet a leaf, placement unclear
   (the work-productivity pipeline's outputs — email, documents — file under
   Documents today, but the pipeline itself isn't represented). New open
   question 17 captures that.
5. **venn.js exists under 3 keys in 3 categories** (Dashboards, Education &
   Research, Documents). Decide once: charting or maths-teaching? —
   **Resolved 2026-09-11 (2026-09-25 implementation):** **Data Systems**.
   venn.js is visualising data (the function), which the Dashboards leaf
   captures for *dashboards* but not for the broader set-relationship /
   comparative work that venn-style diagrams do for *data* — business,
   hobby, or academic. It lands in a new "Data Systems" leaf at Rung 5,
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
   as two rungs, or rename to something that covers both (Rung 2 = "The Wire"?). —
   **Resolved 2026-11-21: split.** Monitoring moves out into a new **Rung 3 —
   Observability & Security** (which also takes the newly-earned Security leaf);
   Rung 3 Substrate renumbers to Rung 4, Data & Content to Rung 5, Data Input
   to Rung 6. The rung keeps the name "Access" — renaming it to cover both was
   the alternative, and splitting keeps the name honest instead of blurring it.
8. **Does Remote Access earn a leaf?** Three members (mRemoteNG, tigervnc,
   neko) plus `jetkvm/kvm`, folded in from the Homelab walk (2026-09-07) as the
   strongest case for and against the leaf. Options: (a) its own leaf; (b) fold
   into Networking as session transport; (c) fold into Operating Systems, since
   what you're doing is driving a box. It is definitively *not* Authentication
   either way. —
   **Resolved 2026-11-21: (a), it earns the leaf**, and `jetkvm/kvm` joins it —
   an IP-KVM is session transport, not a platform. Four members; the function
   is real and distinct from identity and from packet transport.
9. **Where do observability dashboards go?** holmesgpt (Monitoring or AI?) and
   homebutler / homelable (Monitoring or Homelab?). The substrate discriminator
   and the function discriminator disagree here, which is the first time
   they've conflicted since ProxmoxVE. —
   **Partly resolved 2026-09-11:** `homebutler` / `homelable` landed in
   **Self-Hosted Dashboards** (the split made the function discriminator and
   the substrate discriminator agree). **holmesgpt** is still open: Monitoring
   by function, AI by implementation. —
   **Resolved 2026-11-21: holmesgpt → Monitoring**, on discriminator 2 —
   "it's AI" is implementation, not domain, the same rule that keeps Docker
   packaging out of the signal. The question is now closed.
10. **caddy** — automatic-TLS reverse proxy that is also a web server.
    Networking or Web & API Tooling? Same shape as the kong call, but kong
    resolved cleanly and this doesn't. —
    **Resolved 2026-11-21: Web & API Tooling**, on the kong precedent — serving
    is the function, transport is the mechanism. caddy stays where the walk put
    it; Networking keeps zoraxy / traefik / certmate as its proxy set.
11. **Does Security earn a leaf?** Jira-Lens (vulnerability scanning) has no
    home in the current 32 — it isn't Authentication. Either a Security leaf
    gets earned, or scanners file under the thing they scan (Jira-Lens → Code &
    Build Tooling / IT Support). —
    **Resolved 2026-11-21: a Security leaf is earned**, with Jira-Lens and
    awesome-scapy. It does not join Access (scanning is not access control) —
    it sits beside Monitoring in **Rung 3 — Observability & Security**, the
    other way of inspecting a running system. A two-member leaf survives the
    test Authentication does: a real function, not a size.
12. **Does IaC earn a leaf?** *(corrected 2026-09-07 — an earlier draft of
    this question claimed the corpus had zero IaC. It doesn't.)* Real
    desired-state members exist: `Peco602/ansible-linux-docker` (Ansible),
    `mirceanton/home-ops` (Kubernetes via GitOps), `khuedoan/homelab`
    (bare disk → cluster), and `bjeans/homelab-mcp` carries an Ansible
    inventory. Discriminator 6 cleanly separates these from the one-shot
    imperative installers (`community-scripts/ProxmoxVE`, `Deployrr`). So the
    question is live, not hypothetical: does declarative fleet config split
    off from Homelab, or stay as a within-leaf ordering? —
    **Resolved 2026-09-11:** IaC earns a leaf — **Orchestration & Infrastructure
    as Code**, shared with the fleet orchestrators (komodo, homelab-core,
    Olares). See § Orchestration & Infrastructure as Code.
13. **Does Hardware earn a leaf?** `openhaystack` (Find My), `3d-printed-nas`,
    `gsmarena-scraper` (device data) — each is a one-off in Homelab today
    (`jetkvm/kvm` was folded into question 8 instead). If three more arrive, a
    Hardware leaf becomes worth earning; until then they file by function
    (Home Automation for Find-My-style trackers, IT Support for specs scrapers). —
    **Resolved 2026-11-21: no Hardware leaf — file by function**, the walk's own
    provisional answer: `3d-printed-nas` → **Storage** (a NAS knows what its
    files are), `openhaystack` → **IT Support** (the leaf's gloss includes
    "find", and a Find My network finds a lost device), `gsmarena-scraper` →
    **IT Support** (device specs, beside `pc-part-dataset`). Revisit if three
    more device repos arrive.
14. **Where does nerd-fonts go?** Developer tooling (function: glyph/icons
    used in dev work) or device-side tooling (function: installed on the user's
    machine to *make every application look better*)? Same leaf, two
    framings. —
    **Resolved 2026-11-21: it stays in IT Support & Device Management.** The
    device-side framing wins — it acts on the user's device and is installed to
    make every application look better, which is what "install, configure"
    means in that leaf.
15. **`Deployrr` — imperative installer or substrate?** It automates home
    server setup via Docker Compose. Discriminator 6 says imperative (so not
    IaC, stays out of the declarative group); discriminator 5 says substrate
    (so Homelab, not Containerization). First clean disagreement between those
    two discriminators. Same shape as question 1 (`ProxmoxVE`), so both should
    probably be answered together. —
    **Resolved 2026-11-21: Containerization**, on question 1's principle — a
    repo's content decides its leaf, and Deployrr's content is Docker Compose.
    It leaves the declarative IaC leaf (discriminator 6) for the container
    leaf, beside ProxmoxVE and the other one-shot install helpers.
16. **Does Data Systems split into Visualising vs not?** Settled on 2026-09-11
    (Q5) that venn.js belongs in a new Data Systems leaf at Rung 5, distinct
    from the Data & Systems Management residue. The decision deferred the
    sub-split — Visualising (charting, diagrams, comparison) vs everything
    else Data Systems ends up holding — until the leaf has enough members to
    make the cut self-evident. With one member today, the split is premature;
    revisit when a fourth or fifth data-tools repo lands here.
17. **Does Productivity earn its own leaf, or does it fold into Documents?**
    Settled on 2026-09-11 (Q4) that Arr and Productivity are the two input
    pipelines. Arr got a leaf (Media Acquisition) because its contents are
    mime-agnostic and don't fit any content leaf; Productivity's outputs
    (email, documents) currently file under Documents — but the *pipeline*
    itself (the input side: email clients, doc tools) isn't represented.
    Decide whether Productivity earns a leaf in its own right, or whether
    the pipeline aspect stays implicit and only the output leaf matters. —
    **Resolved 2026-11-21: it earns a leaf**, on the same argument that earned
    Media Acquisition — the input side is mime-agnostic and fits no content
    leaf. It lands in Rung 6 (Data Input) beside Media Acquisition, with
    EMailParseAI, aw-import-ical, ClickTheseThings, DoIHaveEverything, portia
    and huginn. Outputs (email, documents) still file under Documents;
    `dnd-session-recorder` stays in Ingestion — it is a capture, not
    productivity.

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

**The nine open calls are answered** (2026-11-21). Rung 2 split — Monitoring
moved into the new **Rung 3 — Observability & Security** — and three leaves
were earned: Remote Access, Security and Productivity. Rung 3 Substrate is now
Rung 4; Data & Content Rung 5; Data Input Rung 6. Each decision is annotated
in "Open questions" above and recorded in `ISSUES.md`'s resolved list.

**Rung 4 — Substrate** is walked but not closed: the Homelab leaf split on
2026-09-11 (question 6) and IaC earned its leaf (question 12), and the
2026-11-21 answers closed the last of this rung's calls — Deployrr moved to
Containerization, nerd-fonts stayed put, the Hardware leaf was declined in
favour of filing by function. Likely target size: ~25 members, not 80+,
because much of what *was* in Homelab was misclassified single-machine tooling
that rung 1 evicts.

**Rung 5 — Data & Content** *(proposed)*: Knowledge Base · Dashboards ·
Data Systems · Data & Systems Management · AI · Photos · Music · Video ·
Documents. The substrate runs out here and the rung turns to *what lives on
the box*, not the box itself. **Data Systems** is the new leaf decided on
2026-09-11 (open question 5): venn.js lands here; it captures *what you do
with data* (visualising, comparing, querying, …) and is distinct from Data &
Systems Management, which is the *ops tooling that happens to touch data*
residue. The "Visualising vs not" sub-split is held until the leaf has
enough members to make the cut self-evident. **Media Acquisition** is the
new leaf decided on 2026-09-11 (open question 4): Arr is one of two input
pipelines and lands here as a *pipeline* leaf (distinct from the mime-typed
Video/Music/Photos content leaves that capture its outputs); the other
pipeline, **Productivity**, was settled on 2026-11-21 (question 17) and earns
a leaf beside it in **Rung 6 — Data Input**.
This is also where the tag-pool
issue logged in ISSUES.md hurts most — the "Analysis" / "Tracking" / "Manager"
tags send nearly every one of these to Monitoring right now, so the rung is
likely to be the loudest single correction in the whole walk.

**The hub-leaders table below predates the 2026-11-21 leaf decisions** — hub
candidacy (which owned leader absorbs a repo's features) is a different axis
from leaf placement (which leaf a repo files under), so it is left as decided
on 2026-10-11. But `EMailParseAI` (now Productivity), `Jira-Lens` (now
Security) and `Deployrr` (now Containerization) sit in different leaves than
when that table was drawn, and it is worth a pass now the leaves have moved.

**Rung 6 — Data Input** *(proposed)*: Ingestion · Media Acquisition ·
Productivity. The content rungs collect what lives on the box; this one is the
*throughput* — the pipelines that bring it in. Ingestion (social, calendar,
audio, web) and Media Acquisition (media for leisure) were decided earlier;
Productivity joins them on 2026-11-21 as the third and last of the input
pipelines, carrying the email/document/web-automation side.

## Hub leaders — atelier projects *(decided 2026-10-11, revised 2026-10-12)*

Manual promotion, per [[hubs-emerge-not-seeded]]: a leader is an owned, atelier-driven
repo that neighbouring repos in its leaf get feature-absorbed into. Leaves with no
owned project stay leaderless.

| Hub | Leader | Satellites (owned) | Absorb candidates (third-party) |
|---|---|---|---|
| Database | sql-schema-miner | — | SchemaCrawler · *sql_schema_visualizer* · cloudbeaver · bytebase |
| Homelab | homelab-designer | — | awesome-selfhosted · homelab-discovery · *homelab-mcp* · ProxmoxVE · Deployrr |
| IT Support & Device Mgmt | *belzona-tickets* | — | jira · atlassian-api/atlassian-python-api · Jira-Lens · EMailParseAI |
| Ingestion *(rung 6, Data Input)* | socialMediaArchiver | multitudes · dnd-session-recorder · aw-import-ical | YouTubeCommunityPosts · tweetext · twitterscraper |
| Code & Build Tooling | git-suite | — | StuartJAtkinson/astral · all-repos |
| Ai — agent tooling | Atelier-Harness | *ask-ai* | aider · OpenDevin · Archon · crewAI-examples |
| Ontology | *marvel-ontology* | — | CommonCoreOntologies · ontologiesUK · skoseditor · *sparql.anything* · IAO |
| Geospatial & Mapping | map-merch | — | streets-gl · gboeing/osmnx · kepler.gl |
| Business | *chemeter-data* | — | ZohoAPI · twenty |
| Civic & Public Affairs | organised-commons | canvassing-planner | *democracy-watcher* · federated-api-model |
| Lifelogging *(presentation)* | timelinize | Genealogy | ActivityWatch · aw-watcher-* · simklExporter · *timeliner* |
| Health | *traintenance* | — | — |
| Travel | *travel-planner* | — | — |
| Video | *video-autoeditor* | — | — |
| Games — TTRPG | FoundryVTT | *ddb-bridge* · swipe-vtt · dnd-aFirstStep | — |
| Games — library | Playnite *(local install, no remote)* | — | — |
| Games — in-game data | *game-across-the-obelisk* | *d4lf* | free-map-genie · AllaganTools · WoWAnalyzer · FFXIVPlugin · *xiv-resources* · *Memoria* |
| Games — collectibles | *card-collection* | — | card-collector |

Cross-hub feature flows (not membership):

| From | To | Feature |
|---|---|---|
| dnd-session-recorder | Ontology | entity resolution |
| sql-schema-miner | Business | business-object extraction from SQL |
| Ingestion | Lifelogging | ingest → present pipeline |

Decisions: Games splits four ways (TTRPG · library · in-game data · collectibles) ·
Playnite and card-collection stay separate · organised-commons leads Civic ·
git-suite and Atelier-Harness are separate hubs · marvel-ontology leads Ontology ·
Genealogy files under Lifelogging · ingestion is its own hub at rung 6, presentation
stays with timelinize.

*Italicised entries are aspirational — not yet published on GitHub (Stuart's
roadmap). `tools/bootstrap_lists.py` keeps them in its `ASPIRATIONAL` set and
silently skips them until they materialise.*
