import re
from rapidfuzz import fuzz

def normalize_title(title):
    if not title:
        return ""
    title = title.lower()
    title = re.sub(r"[^a-z0-9\u4e00-\u9fff ]", " ", title)
    title = re.sub(r"\s+", " ", title)
    return title.strip()

def normalize_doi(doi):
    if not doi:
        return ""
    doi = doi.strip().lower()
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").replace("doi:", "")
    return doi.strip()

def merge_and_deduplicate(papers, title_threshold=92):
    merged = []
    seen_dois = set()
    for paper in papers:
        title = paper.get("title", "")
        doi = normalize_doi(paper.get("doi", ""))
        if not title:
            continue
        if doi:
            if doi in seen_dois:
                continue
            seen_dois.add(doi)
        norm_title = normalize_title(title)
        duplicate_found = False
        for existing in merged:
            existing_title = normalize_title(existing.get("title", ""))
            score = fuzz.ratio(norm_title, existing_title)
            if score >= title_threshold:
                duplicate_found = True
                for key, value in paper.items():
                    if not existing.get(key) and value:
                        existing[key] = value
                if paper.get("source") and paper.get("source") not in existing.get("source", ""):
                    existing["source"] = existing.get("source", "") + "+" + paper.get("source", "")
                break
        if not duplicate_found:
            merged.append(paper)
    return merged
