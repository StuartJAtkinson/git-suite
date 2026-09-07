"""Guards the relevance weighting in classify_repos.classify().

The bug this pins down: votes used to be scored `len(tag) * boost`, so the
longest matching tag won regardless of meaning. Run with:

    python -m pytest test_classify_repos.py
"""
from classify_repos import classify


def _rec(domain, purpose, entities=()):
    return {"domain": domain, "purpose": purpose, "entities": list(entities)}


def test_domain_field_outranks_prose():
    """`tv` in the domain beats `file` in the purpose, despite being shorter."""
    rec = _rec(
        "tv series tracking",
        "Exports Simkl data to a CSV file for easy importing elsewhere.",
        ["profile", "data"],
    )
    assert classify(rec) == "Video"


def test_domain_field_outranks_entities():
    """`infrastructure` in the domain beats `cloud storage` in the entities."""
    rec = _rec(
        "cloud infrastructure management",
        "Lets AI assistants run gcloud commands to manage and inspect "
        "Google Cloud infrastructure on a user's behalf.",
        ["Google Cloud project", "virtual machine", "cloud storage bucket"],
    )
    assert classify(rec) != "Storage"


def test_entities_alone_do_not_decide():
    """A bare noun in `entities` must not outvote a topical word in `purpose`."""
    rec = _rec(
        "computer hardware",
        "Stores PC parts information for enthusiasts",
        ["PC", "CPU", "GPU", "RAM", "Storage"],
    )
    assert classify(rec) != "Storage"


def test_multiword_tags_still_beat_single_words_in_the_same_field():
    """`file management` is a more specific match than `photo` — both in domain."""
    rec = _rec(
        "photo & file management",
        "Organizes and manages photos and files with metadata and tags",
        ["photos", "files", "metadata"],
    )
    assert classify(rec) == "Storage"


def test_tag_scores_once_at_its_strongest_field():
    """A tag repeated across all three fields must not stack three weights."""
    once = classify(_rec("media tracking", "unrelated prose", []))
    thrice = classify(_rec("media tracking", "media tracking", ["media"]))
    assert once == thrice == "Video"
