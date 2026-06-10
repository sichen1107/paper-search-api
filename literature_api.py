import time
import re
import html
from urllib.parse import quote

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
    except Exception:
        return False

    if from_year and y < int(from_year):
        return False

    if to_year and y > int(to_year):
        return False

    return True


def clean_abstract_text(text):
    """
    清理 Crossref / 期刊接口返回的摘要 HTML、JATS XML 标签。
    """
    if not text:
        return ""

    text = str(text)

    # 去掉常见 JATS / HTML 标签
    text = re.sub(r"<[^>]+>", " ", text)

    # HTML 实体还原
    text = html.unescape(text)

    # 压缩空白
    text = re.sub(r"\s+", " ", text).strip()

    return text


def reconstruct_openalex_abstract(inverted_index):
    """
    OpenAlex 的 abstract 经常不是直接字符串，而是 inverted_abstract。
    格式类似：
    {
      "word": [0, 4, 10],
      "another": [1, 2]
    }

    这个函数把它还原成普通摘要文本。
    """
    if not inverted_index or not isinstance(inverted_index, dict):
        return ""

    positions = []

    for word, indexes in inverted_index.items():
        if not isinstance(indexes, list):
            continue

        for index in indexes:
            try:
                positions.append((int(index), word))
            except Exception:
                pass

    if not positions:
        return ""

    positions.sort(key=lambda x: x[0])
    return " ".join(word for _, word in positions).strip()


def normalize_doi(doi):
    if not doi:
        return ""

    doi = str(doi).strip()

    if doi.startswith("https://doi.org/"):
        doi = doi.replace("https://doi.org/", "")

    if doi.startswith("http://dx.doi.org/"):
        doi = doi.replace("http://dx.doi.org/", "")

    if doi.startswith("doi:"):
        doi = doi.replace("doi:", "")

    return doi.strip()


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
        "sort": "cited_by_count:desc",
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

        doi = normalize_doi(item.get("doi"))

        year = item.get("publication_year")

        if not in_year_range(year, from_year, to_year):
            continue

        abstract = reconstruct_openalex_abstract(
            item.get("abstract_inverted_index")
        )

        results.append(
            {
                "title": title,
                "authors": "; ".join(authors),
                "year": year,
                "venue": source.get("display_name") or "",
                "doi": doi or "",
                "abstract": abstract,
                "citation_count": item.get("cited_by_count"),
                "url": item.get("id") or "",
                "source": "OpenAlex",
            }
        )

    return results


def search_crossref_by_title(title, mailto="your_email@example.com"):
    url = "https://api.crossref.org/works"

    params = {
        "query.title": title,
        "rows": 1,
        "mailto": mailto,
    }

    data = safe_get(url, params=params)

    if not data:
        return None

    items = data.get("message", {}).get("items", [])

    if not items:
        return None

    item = items[0]

    crossref_title = item.get("title", [""])[0] if item.get("title") else ""
    container_title = (
        item.get("container-title", [""])[0]
        if item.get("container-title")
        else ""
    )

    year = None
    date_info = (
        item.get("published-print")
        or item.get("published-online")
        or item.get("published")
    )

    if date_info:
        date_parts = date_info.get("date-parts", [])
        if date_parts and date_parts[0]:
            year = date_parts[0][0]

    authors = []

    for a in item.get("author", []):
        name = f"{a.get('given', '')} {a.get('family', '')}".strip()
        if name:
            authors.append(name)

    abstract = clean_abstract_text(item.get("abstract", ""))

    return {
        "title": crossref_title,
        "authors": "; ".join(authors),
        "year": year,
        "venue": container_title,
        "doi": normalize_doi(item.get("DOI", "")),
        "abstract": abstract,
        "citation_count": "",
        "url": item.get("URL", ""),
        "source": "Crossref",
    }


def search_crossref_by_doi(doi, mailto="your_email@example.com"):
    doi = normalize_doi(doi)

    if not doi:
        return None

    encoded_doi = quote(doi, safe="")
    url = f"https://api.crossref.org/works/{encoded_doi}"

    params = {
        "mailto": mailto,
    }

    data = safe_get(url, params=params)

    if not data:
        return None

    item = data.get("message", {})

    if not item:
        return None

    title = item.get("title", [""])[0] if item.get("title") else ""
    container_title = (
        item.get("container-title", [""])[0]
        if item.get("container-title")
        else ""
    )

    year = None
    date_info = (
        item.get("published-print")
        or item.get("published-online")
        or item.get("published")
    )

    if date_info:
        date_parts = date_info.get("date-parts", [])
        if date_parts and date_parts[0]:
            year = date_parts[0][0]

    authors = []

    for a in item.get("author", []):
        name = f"{a.get('given', '')} {a.get('family', '')}".strip()
        if name:
            authors.append(name)

    abstract = clean_abstract_text(item.get("abstract", ""))

    return {
        "title": title,
        "authors": "; ".join(authors),
        "year": year,
        "venue": container_title,
        "doi": normalize_doi(item.get("DOI", "")),
        "abstract": abstract,
        "citation_count": "",
        "url": item.get("URL", ""),
        "source": "Crossref",
    }


def search_semantic_scholar(query, limit=50, api_key="", from_year=None, to_year=None):
    url = "https://api.semanticscholar.org/graph/v1/paper/search"

    params = {
        "query": query,
        "limit": min(int(limit), 100),
        "fields": "title,authors,year,venue,abstract,citationCount,externalIds,url",
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

        results.append(
            {
                "title": item.get("title") or "",
                "authors": "; ".join(authors),
                "year": year,
                "venue": item.get("venue") or "",
                "doi": normalize_doi(external_ids.get("DOI") or ""),
                "abstract": clean_abstract_text(item.get("abstract") or ""),
                "citation_count": item.get("citationCount"),
                "url": item.get("url") or "",
                "source": "Semantic Scholar",
            }
        )

    return results


def search_semantic_scholar_by_doi(doi, api_key=""):
    doi = normalize_doi(doi)

    if not doi:
        return None

    paper_id = f"DOI:{doi}"
    encoded_paper_id = quote(paper_id, safe=":")

    url = f"https://api.semanticscholar.org/graph/v1/paper/{encoded_paper_id}"

    params = {
        "fields": "title,authors,year,venue,abstract,citationCount,externalIds,url",
    }

    headers = {"x-api-key": api_key} if api_key else {}

    data = safe_get(url, params=params, headers=headers)

    if not data:
        return None

    authors = []

    for a in data.get("authors", []):
        name = a.get("name")
        if name:
            authors.append(name)

    external_ids = data.get("externalIds") or {}

    return {
        "title": data.get("title") or "",
        "authors": "; ".join(authors),
        "year": data.get("year"),
        "venue": data.get("venue") or "",
        "doi": normalize_doi(external_ids.get("DOI") or doi),
        "abstract": clean_abstract_text(data.get("abstract") or ""),
        "citation_count": data.get("citationCount"),
        "url": data.get("url") or "",
        "source": "Semantic Scholar",
    }


def enrich_with_crossref(
    papers,
    mailto="your_email@example.com",
    max_items=30,
    semantic_key="",
    enrich_abstract=True,
):
    """
    原函数只在没有 DOI 时用 Crossref 补 DOI。

    新版逻辑：
    1. 没有 DOI：用 Crossref 标题检索补 DOI、venue、url、abstract
    2. 有 DOI 但没有 abstract：用 Semantic Scholar DOI 接口补 abstract
    3. Semantic Scholar 仍没有：用 Crossref DOI 接口补 abstract
    4. 有 title 但没有 abstract：用 Semantic Scholar 标题搜索补 abstract
    """
    enriched = []

    for index, paper in enumerate(papers):
        new_paper = paper.copy()

        if index >= max_items:
            enriched.append(new_paper)
            continue

        doi = normalize_doi(new_paper.get("doi", ""))
        title = new_paper.get("title", "")
        abstract = clean_abstract_text(new_paper.get("abstract", ""))

        new_paper["doi"] = doi
        new_paper["abstract"] = abstract

        # 1. 没有 DOI 时，先用 Crossref 标题补 DOI
        if not doi and title:
            crossref_info = search_crossref_by_title(
                title,
                mailto=mailto,
            )

            time.sleep(0.15)

            if crossref_info:
                if crossref_info.get("doi"):
                    new_paper["doi"] = crossref_info.get("doi", "")

                if not new_paper.get("venue") and crossref_info.get("venue"):
                    new_paper["venue"] = crossref_info.get("venue", "")

                if not new_paper.get("url") and crossref_info.get("url"):
                    new_paper["url"] = crossref_info.get("url", "")

                if not new_paper.get("abstract") and crossref_info.get("abstract"):
                    new_paper["abstract"] = crossref_info.get("abstract", "")

                if "Crossref" not in new_paper.get("source", ""):
                    new_paper["source"] = new_paper.get("source", "") + "+Crossref"

        if not enrich_abstract:
            enriched.append(new_paper)
            continue

        # 更新 DOI 和 abstract
        doi = normalize_doi(new_paper.get("doi", ""))
        abstract = clean_abstract_text(new_paper.get("abstract", ""))

        # 2. 有 DOI 但没有摘要时，用 Semantic Scholar DOI 精确补摘要
        if doi and not abstract:
            semantic_info = search_semantic_scholar_by_doi(
                doi,
                api_key=semantic_key,
            )

            time.sleep(0.15)

            if semantic_info:
                if semantic_info.get("abstract"):
                    new_paper["abstract"] = semantic_info.get("abstract", "")

                if not new_paper.get("citation_count") and semantic_info.get("citation_count") is not None:
                    new_paper["citation_count"] = semantic_info.get("citation_count")

                if not new_paper.get("url") and semantic_info.get("url"):
                    new_paper["url"] = semantic_info.get("url", "")

                if "Semantic Scholar" not in new_paper.get("source", ""):
                    new_paper["source"] = new_paper.get("source", "") + "+Semantic Scholar"

        # 3. Semantic Scholar 仍没有摘要，再用 Crossref DOI 补摘要
        abstract = clean_abstract_text(new_paper.get("abstract", ""))

        if doi and not abstract:
            crossref_doi_info = search_crossref_by_doi(
                doi,
                mailto=mailto,
            )

            time.sleep(0.15)

            if crossref_doi_info:
                if crossref_doi_info.get("abstract"):
                    new_paper["abstract"] = crossref_doi_info.get("abstract", "")

                if not new_paper.get("venue") and crossref_doi_info.get("venue"):
                    new_paper["venue"] = crossref_doi_info.get("venue", "")

                if not new_paper.get("url") and crossref_doi_info.get("url"):
                    new_paper["url"] = crossref_doi_info.get("url", "")

                if "Crossref" not in new_paper.get("source", ""):
                    new_paper["source"] = new_paper.get("source", "") + "+Crossref"

        # 4. 如果还是没有摘要，用标题再搜一次 Semantic Scholar
        abstract = clean_abstract_text(new_paper.get("abstract", ""))

        if title and not abstract:
            semantic_title_results = search_semantic_scholar(
                title,
                limit=1,
                api_key=semantic_key,
            )

            time.sleep(0.15)

            if semantic_title_results:
                candidate = semantic_title_results[0]

                if candidate.get("abstract"):
                    new_paper["abstract"] = candidate.get("abstract", "")

                if not new_paper.get("doi") and candidate.get("doi"):
                    new_paper["doi"] = candidate.get("doi", "")

                if not new_paper.get("url") and candidate.get("url"):
                    new_paper["url"] = candidate.get("url", "")

                if "Semantic Scholar" not in new_paper.get("source", ""):
                    new_paper["source"] = new_paper.get("source", "") + "+Semantic Scholar"

        enriched.append(new_paper)

    return enriched