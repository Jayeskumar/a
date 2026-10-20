"""Document checklist: union of required documents across chosen schemes,
deduplicated to canonical document ids (so "Aadhaar card", "aadhar" and
"AADHAAR" become one line), each tagged with the schemes that need it.
"""
import re

_PUNCT = re.compile(r"[^0-9a-z஀-௿]+")


def _norm(s):
    return _PUNCT.sub(" ", (s or "").lower()).strip()


def alias_table(documents):
    """normalised name -> canonical id, from ids, English names and aliases."""
    table = {}
    for did, d in documents.items():
        for name in [did, did.replace("_", " "), d.get("en", ""), d.get("ta", "")] + list(d.get("aliases", [])):
            n = _norm(name)
            if n:
                table.setdefault(n, did)
    return table


def canonical_doc(name, documents, table=None):
    """Map any spelling of a document to its canonical id (or a slug if unknown)."""
    table = table or alias_table(documents)
    n = _norm(name)
    if n in table:
        return table[n]
    # tolerate a trailing generic word: "aadhaar card" -> "aadhaar"
    for tail in (" card", " certificate", " copy", " details"):
        if n.endswith(tail) and n[: -len(tail)] in table:
            return table[n[: -len(tail)]]
    return n.replace(" ", "_") or "unknown"


def build(scheme_ids, catalogue, extra=None):
    """Return the deduplicated checklist for the given schemes.

    extra: optional {scheme_id: [free-text document names]} merged in (e.g. a
    field worker's local additions) to exercise alias-based deduplication.
    """
    docs = catalogue.documents
    table = alias_table(docs)
    seen = {}
    order = []
    unknown = [sid for sid in scheme_ids if sid not in catalogue.by_id]
    for sid in scheme_ids:
        s = catalogue.by_id.get(sid)
        if not s:
            continue
        names = list(s["documents"]) + list((extra or {}).get(sid, []))
        for name in names:
            did = canonical_doc(name, docs, table)
            if did not in seen:
                d = docs.get(did, {"en": name, "ta": name})
                seen[did] = {"id": did, "name": {"en": d["en"], "ta": d["ta"]}, "schemes": []}
                order.append(did)
            if sid not in seen[did]["schemes"]:
                seen[did]["schemes"].append(sid)
    items = [seen[d] for d in order]
    items.sort(key=lambda x: (-len(x["schemes"]), order.index(x["id"])))
    total_mentions = sum(len(catalogue.by_id[s]["documents"]) for s in scheme_ids if s in catalogue.by_id)
    return {"items": items, "count": len(items), "mentions": total_mentions,
            "duplicates_removed": max(0, total_mentions - len(items)), "unknown_schemes": unknown}
