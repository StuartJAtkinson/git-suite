# Taxonomy — git-suite

Working state of the theme/category ontology. Supersedes the flat 32-category
list in `category_dividers.html` as it gets walked theme by theme.

**Status 2026-09-07:** Single Computer rung closed. Access rung walked —
leaves drafted and membership recovered, but four calls are Stuart's and the
rung is **not closed** until they land (open questions 7–11).

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
identity*. The mechanism is visible in `category_tags.json` — the Authentication
pool carries ten remote-access tags (`Rdp`, `Vnc`, `Ssh`, `Novnc`, `Guacd`,
`Putty`, `Teamviewer`, `Remote Desktop`, `Remote Access`, `Remote Management`),
so anything mentioning RDP or VNC is routed to identity management.

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

## Caveat on all counts

Every category count here is the output of length-weighted keyword voting over
LLM-written prose (`classify_repos.py:99`). See ISSUES.md — assignments are
close to arbitrary for any repo whose description lacks a long matching tag,
and the tag vocabulary describes a *different corpus* (homelab-designer's).
Treat app placements as suggestions to overrule, not evidence.

## Next

**Rung 2 — Access** is walked but open on questions 7–11; those are Stuart's
calls, not derivable from the corpus.

**Rung 3 — Substrate** *(proposed)*: Homelab & Server Administration · IT
Support & Device Management. Earned by default — both rungs so far have been
deferring things into Homelab (hypervisors, orchestration, IaC, and now
possibly the status dashboards), and open question 6 says that leaf has to be
faced eventually. It is the natural next step up the axis: rung 1 was one box,
rung 2 was the wire between boxes, rung 3 is the fleet.
