"""Free research-paper search. Uses OpenAlex and arXiv public APIs (no API key required)."""
import re
import xml.etree.ElementTree as ET
from itertools import zip_longest
import requests
import streamlit as st

HEADERS = {"User-Agent": "SmartAITutor/2.0 (educational project)"}

def _abstract(inv):
    """OpenAlex stores abstracts as an inverted index; rebuild the text."""
    if not inv:
        return ""
    pos = {i: w for w, idxs in inv.items() for i in idxs}
    return " ".join(pos[i] for i in sorted(pos))

@st.cache_data(ttl=3600, show_spinner=False)
def openalex(query, n, year_from, oa_only, sort):
    flt = [f"from_publication_date:{int(year_from)}-01-01"]
    if oa_only:
        flt.append("is_oa:true")
    params = {"search": query, "per-page": n, "filter": ",".join(flt)}
    try:
        email = st.secrets.get("CONTACT_EMAIL", "")
    except Exception:
        email = ""
    if email:
        params["mailto"] = email                      # optional: faster "polite pool"
    if sort == "cited":
        params["sort"] = "cited_by_count:desc"
    elif sort == "newest":
        params["sort"] = "publication_date:desc"
    r = requests.get("https://api.openalex.org/works", params=params, headers=HEADERS, timeout=20)
    r.raise_for_status()
    out = []
    for w in r.json().get("results", []):
        auth = w.get("authorships") or []
        names = [a["author"]["display_name"] for a in auth[:6] if a.get("author")]
        if len(auth) > 6:
            names.append("et al.")
        oa = w.get("open_access") or {}
        src = ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
        out.append({"title": w.get("display_name") or "Untitled", "authors": ", ".join(names),
                    "year": w.get("publication_year"), "venue": src,
                    "citations": w.get("cited_by_count") or 0,
                    "abstract": _abstract(w.get("abstract_inverted_index")),
                    "url": w.get("doi") or w.get("id") or "", "pdf": oa.get("oa_url") or "",
                    "open_access": bool(oa.get("is_oa")), "source": "OpenAlex"})
    return out

@st.cache_data(ttl=3600, show_spinner=False)
def arxiv(query, n, year_from, sort):
    words = re.findall(r"\w+", query)[:8]
    if not words:
        return []
    params = {"search_query": " AND ".join(f"all:{w}" for w in words), "start": 0,
              "max_results": n, "sortBy": "submittedDate" if sort == "newest" else "relevance",
              "sortOrder": "descending"}
    r = requests.get("https://export.arxiv.org/api/query", params=params, headers=HEADERS, timeout=20)
    r.raise_for_status()
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for e in ET.fromstring(r.content).findall("a:entry", ns):
        year = int((e.findtext("a:published", "0000", ns) or "0000")[:4])
        if year < int(year_from):
            continue
        link = e.findtext("a:id", "", ns)
        pdf = next((l.get("href") for l in e.findall("a:link", ns) if l.get("title") == "pdf"),
                   link.replace("/abs/", "/pdf/"))
        out.append({"title": " ".join((e.findtext("a:title", "", ns) or "").split()),
                    "authors": ", ".join(a.findtext("a:name", "", ns) for a in e.findall("a:author", ns)[:6]),
                    "year": year, "venue": "arXiv preprint", "citations": None,
                    "abstract": " ".join((e.findtext("a:summary", "", ns) or "").split()),
                    "url": link, "pdf": pdf, "open_access": True, "source": "arXiv"})
    return out

def search(query, source="OpenAlex + arXiv", sort="Relevance", year_from=2018, oa_only=False, n=10):
    """Returns (results, errors). One source failing never breaks the other."""
    sk = {"Relevance": "relevance", "Most cited": "cited", "Newest": "newest"}[sort]
    lists, errs = [], []
    if source in ("OpenAlex + arXiv", "OpenAlex"):
        try:
            lists.append(openalex(query, n, year_from, oa_only, sk))
        except Exception as e:
            errs.append(f"OpenAlex unavailable ({type(e).__name__})")
    if source in ("OpenAlex + arXiv", "arXiv"):
        try:
            lists.append(arxiv(query, n, year_from, sk))
        except Exception as e:
            errs.append(f"arXiv unavailable ({type(e).__name__})")
    merged, seen = [], set()
    for group in zip_longest(*lists):                 # interleave sources
        for p in group:
            key = re.sub(r"\W+", "", (p or {}).get("title", "").lower()) if p else ""
            if p and key and key not in seen:
                seen.add(key); merged.append(p)
    if sk == "cited":
        merged.sort(key=lambda p: p["citations"] or 0, reverse=True)
    elif sk == "newest":
        merged.sort(key=lambda p: p["year"] or 0, reverse=True)
    return merged, errs
