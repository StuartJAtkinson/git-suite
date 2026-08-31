"""
git-suite's own flat repo category list. Self-contained — no dependency on
homelab-designer; category_tags.json is a one-time snapshot of the tag
vocabulary Stuart curated there, owned by git-suite from here on.

Axis: what does the repo act upon (or represent), not "software" (every repo
is software — that's not a distinguishing property). Categories are single-
rank: no category here is a subtype of another category in this list.
"""
import json, re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent
tag_rows = json.load(open(ROOT / "category_tags.json", encoding="utf-8"))
tag_to_group = {r["tag"].lower(): r["group"] for r in tag_rows}
tags_sorted = sorted(tag_to_group.keys(), key=len, reverse=True)

# Generic English words that double as tags (fragments of self-hosted app
# names) but collide with plain-English usage across git-suite's much wider
# corpus. Length is not a proxy for specificity ("gaming" is fine at 6
# chars, "custom" is not) so this is blocklist-only, no length gate.
GENERIC_BLOCKLIST = {
    "custom", "assistant", "master", "sessions", "relationships", "manage",
    "updates", "windows", "engine", "remote", "secure", "gravity", "browser",
    "desktops", "tools", "design", "inventory", "server", "passwords",
    "recipes", "interface", "system", "systems", "network", "networks",
    "application", "applications", "platform", "service", "services",
    "client", "clients", "host", "hosts", "admin", "role", "roles", "book",
    "books", "chat", "voice", "images", "image", "learning", "machine",
    "tracking", "analysis", "information", "collaboration", "project",
    "projects", "data", "time", "discovery", "install",
    "action", "admin", "agent", "alert", "alerts", "answer", "app", "audio",
    "backup", "blog", "acct",
}

tag_patterns = []
for t in tags_sorted:
    if t in GENERIC_BLOCKLIST:
        continue
    tag_patterns.append((t, re.compile(r"\b" + re.escape(t) + r"\b"), 2 if " " in t else 1))

# Entities with no home in the tag vocabulary at all — new git-suite-only
# categories, same object-acted-upon rule, checked only when no tag matched.
LOCAL_EXTRA_RULES = [
    ("Games", r"\b(tabletop role-?playing|heraldic|virtual hunting|mmorpg|pok[eé]mon|rpg battle|game play|game master|final fantasy xiv community|mythical zoology)\b"),
    ("Homelab & Server Administration", r"\b(it support|government it|\btechnology\b|hardware hacking|codebases?)\b"),
    ("Ai", r"\b(data processing|data analysis|computer vision)\b"),
    ("Social Media", r"\b(virtual youtubing|online communit\w*|content creation)\b"),
    ("Finance", r"\baccounts payable\b"),
    ("Home Automation", r"\bwearable technology\b"),
    ("Health", r"\bculinary planning\b"),
    ("Documents", r"^design$"),
    ("Code & Build Tooling", r"\baccessibility\b"),
    ("Geospatial & Mapping", r"\b(navigation planning|urban planning|cartography|earth observation)\b"),
    ("Education & Research", r"\b(physics( and)? simulation|physics education|geometry|mathematics education|geoscience|biomedical research|human research|user research|academic research|histor(y|ical) education|political education|literature and education|\bliterature\b)\b"),
    ("Civic & Public Affairs", r"\b(democracy|political campaigning|uk politics|\bpolitics\b|parliamentary support|civic-tech|public transportation|solidarity economics|environmental conservation)\b"),
    ("Hobbies & Crafts", r"\b(handweaving|artistic ontology)\b"),
]

# Development/Infrastructure were the two biggest buckets and both were
# "software acting on other software" catch-alls — too coarse on their own.
# Split by what they act on, then fold any subgroup that duplicates an
# existing top-level category (AI, Games, IT support) back into it instead
# of keeping three near-identical "AI-ish" piles.
DEV_SUBGROUPS = [
    ("Web & API Tooling", r"\b(web develop\w*|web scraping|web navigation|api develop\w*|api documentation|web design|semantic web|web content|cross-platform develop\w*|data access|technology and development|mobile gaming|payments|mmo development)\b"),
    ("Ai", r"\b(ai develop\w*|ai research and develop\w*|natural language|ai-assisted|ai and programming|ai and conversational|data science|computer science research|language education|art creation|api client development)\b"),
    ("Games", r"\b(game develop\w*|video game develop\w*|pok[eé]mon develop\w*|mmorpg develop\w*|pok[eé]mon training|tabletop role-?playing|tabletop rpg)\b"),
    ("Data & Systems Management", r"\b(knowledge engineering|data processing|data integration|gis develop\w*|media processing|computer graphics|computer hardware|energy policy|public policy)\b"),
    ("Code & Build Tooling", r"\b(programming|developer tools|code review|software engineering|software develop\w*|accessibility|api design|commonwealth develop\w*|github curator|github management|userscript management|application develop\w*|desktop develop\w*|personal develop\w*|software distribution|developer entertainment|development education|android rom customization|cloud computing|browser customization|devops)\b"),
    ("IT Support & Device Management", r"\b(it support|public sector it|web research)\b"),
]

INFRA_SUBGROUPS = [
    ("Homelab & Server Administration", r"\b(home server administration|home server self-hosting|homelab administration|homelab (management|self-hosting)|linux( system)? administration|windows administration|server administration|system administration|server virtualization|network administration|home computing|it administration|it infrastructure (management|administration)|it infrastructure and service management|infrastructure design|cloud operations|operating system|computer hardware management)\b"),
    ("IT Support & Device Management", r"\b(it support|government it|mobile device management|metadata management|personal data management|information management|email management|software management|calendar management|wearable technology|technology|hardware hacking)\b"),
    ("Games", r"\b(tabletop role-?playing|tabletop rpg support|game management|mmorpg character management|pok[eé]mon (trainer|go management)|gaming administration|mmo game administration|gaming addon management|media analysis|social-web)\b"),
    ("Ai", r"\b(ai development|ai assistant|ai agent administration|ai research|quantum computing|research management|conceptual knowledge management|knowledge management|graphics design)\b"),
    ("Data & Systems Management", r"\b(data management|database administration|devops|business process automation|api management|event management|diabetes management|healthcare|codebases|urban planning)\b"),
]

def _text(rec):
    return " ".join([rec.get("domain", ""), rec.get("purpose", ""), " ".join(rec.get("entities", []))]).lower()

def _sub(text, domain, subgroups, fallback):
    for label, pat in subgroups:
        if re.search(pat, text):
            return label
    if domain == "development":
        return "Code & Build Tooling"
    return fallback

def classify(rec):
    text = _text(rec)
    votes = Counter()
    for tag, pat, boost in tag_patterns:
        if pat.search(text):
            votes[tag_to_group[tag]] += len(tag) * boost
    label = votes.most_common(1)[0][0] if votes else None
    if label is None:
        domain = rec.get("domain", "").lower().strip()
        for group, pat in LOCAL_EXTRA_RULES:
            haystack = domain if pat == r"^design$" else text
            if re.search(pat, haystack):
                label = group
                break
        else:
            label = "UNCLASSED"
    if label == "Development":
        label = _sub(text, rec.get("domain", "").lower().strip(), DEV_SUBGROUPS, "Code & Build Tooling")
    elif label == "Infrastructure":
        label = _sub(text, rec.get("domain", "").lower().strip(), INFRA_SUBGROUPS, "Homelab & Server Administration")
    return label

if __name__ == "__main__":
    data = json.load(open(ROOT / "repo_domain_dump.json", encoding="utf-8"))
    assignment = {r["repo"]: classify(r) for r in data}
    counts = Counter(assignment.values())
    for label, n in counts.most_common():
        print(f"{n:4d}  {label}")
    print("\ntotal:", len(assignment), " categories:", len(counts))
    json.dump(assignment, open(ROOT / "repo_categories.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
