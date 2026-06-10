import time
import requests

def safe_get(url, params=None, headers=None, timeout=30):
    try:
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"请求失败：{url}, 错误：{e}")
        return None

def in_year_range(year, from_year=None, to_year=None):
    if year in [None, "", "None"]:
        return False
    try:
        y = int(year)
    except:
        return False
    if from_year and y < int(from_year):
        return False
    if to_year and y > int(to_year):
        return False
    return True

def search_openalex(query, per_page=50, from_year=None, to_year=None):
    url = "https://api.openalex.org/works"

    filters = []
    if from_year:
        filters.append(f"from_publication_date:{from_year}-01-01")
    if to_year:
        filters.append(f"to_publication_date:{to_year}-12-31")

    params = {
        "search": query,
        "per-page": min(int(per_page), 200),
        "sort": "cited_by_count:desc"
    }

    if filters:
        params["filter"] = ",".join(filters)

    data = safe_get(url, params=params)
    if not data:
        return []

    results = []
    for item in data.get("results", []):
        title = item.get("display_name") or ""
        authors = []
        for a in item.get("authorships", []):
            author = a.get("author", {})
            name = author.get("display_name")
            if name:
                authors.append(name)

        primary_location = item.get("primary_location") or {}
        source = primary_location.get("source") or {}

        doi = item.get("doi")
        if doi and doi.startswith("https://doi.org/"):
            doi = doi.replace("https://doi.org/", "")

        year = item.get("publication_year")
        if not in_year_range(year, from_year, to_year):
            continue

        results.append({
            "title": title,
            "authors": "; ".join(authors),
            "year": year,
            "venue": source.get("display_name") or "",
            "doi": doi or "",
            "abstract": "",
            "citation_count": item.get("cited_by_count"),
            "url": item.get("id") or "",
            "source": "OpenAlex"
        })

    return results

def search_crossref_by_title(title, mailto="your_email@example.com"):
    url = "https://api.crossref.org/works"
    params = {
        "query.title": title,
        "rows": 1,
        "mailto": mailto
    }

    data = safe_get(url, params=params)
    if not data:
        return None

    items = data.get("message", {}).get("items", [])
    if not items:
        return None

    item = items[0]

    crossref_title = item.get("title", [""])[0] if item.get("title") else ""
    container_title = item.get("container-title", [""])[0] if item.get("container-title") else ""

    year = None
    date_info = item.get("published-print") or item.get("published-online") or item.get("published")
    if date_info:
        date_parts = date_info.get("date-parts", [])
        if date_parts and date_parts[0]:
            year = date_parts[0][0]

    authors = []
    for a in item.get("author", []):
        name = f"{a.get('given','')} {a.get('family','')}".strip()
        if name:
            authors.append(name)

    return {
        "title": crossref_title,
        "authors": "; ".join(authors),
        "year": year,
        "venue": container_title,
        "doi": item.get("DOI", ""),
        "abstract": "",
        "citation_count": "",
        "url": item.get("URL", ""),
        "source": "Crossref"
    }

def enrich_with_crossref(papers, mailto="your_email@example.com", max_items=30):
    enriched = []

    for index, paper in enumerate(papers):
        new_paper = paper.copy()

        if new_paper.get("doi"):
            enriched.append(new_paper)
            continue

        if index >= max_items:
            enriched.append(new_paper)
            continue

        crossref_info = search_crossref_by_title(
            new_paper.get("title", ""),
            mailto=mailto
        )

        time.sleep(0.15)

        if crossref_info and crossref_info.get("doi"):
            new_paper["doi"] = crossref_info.get("doi", "")
            if not new_paper.get("venue"):
                new_paper["venue"] = crossref_info.get("venue", "")
            if not new_paper.get("url"):
                new_paper["url"] = crossref_info.get("url", "")
            new_paper["source"] = new_paper.get("source", "") + "+Crossref"

        enriched.append(new_paper)

    return enriched

def search_semantic_scholar(query, limit=50, api_key="", from_year=None, to_year=None):
    url = "https://api.semanticscholar.org/graph/v1/paper/search"

    params = {
        "query": query,
        "limit": min(int(limit), 100),
        "fields": "title,authors,year,venue,abstract,citationCount,externalIds,url"
    }

    if from_year and to_year:
        params["year"] = f"{from_year}-{to_year}"
    elif from_year:
        params["year"] = f"{from_year}-"
    elif to_year:
        params["year"] = f"-{to_year}"

    headers = {"x-api-key": api_key} if api_key else {}

    data = safe_get(url, params=params, headers=headers)
    if not data:
        return []

    results = []
    for item in data.get("data", []):
        year = item.get("year")
        if not in_year_range(year, from_year, to_year):
            continue

        authors = []
        for a in item.get("authors", []):
            name = a.get("name")
            if name:
                authors.append(name)

        external_ids = item.get("externalIds") or {}

        results.append({
            "title": item.get("title") or "",
            "authors": "; ".join(authors),
            "year": year,
            "venue": item.get("venue") or "",
            "doi": external_ids.get("DOI") or "",
            "abstract": item.get("abstract") or "",
            "citation_count": item.get("citationCount"),
            "url": item.get("url") or "",
            "source": "Semantic Scholar"
        })

    return results
