import bibtexparser

def import_cnki_bibtex(uploaded_file):
    if uploaded_file is None:
        return []
    try:
        content = uploaded_file.read().decode("utf-8")
    except UnicodeDecodeError:
        uploaded_file.seek(0)
        content = uploaded_file.read().decode("gbk", errors="ignore")
    bib_database = bibtexparser.loads(content)
    results = []
    for entry in bib_database.entries:
        results.append({
            "title": entry.get("title", ""),
            "authors": entry.get("author", "").replace(" and ", "; "),
            "year": entry.get("year", ""),
            "venue": entry.get("journal") or entry.get("booktitle") or "",
            "doi": entry.get("doi", ""),
            "abstract": entry.get("abstract", ""),
            "citation_count": "",
            "url": entry.get("url", ""),
            "source": "CNKI Imported"
        })
    return results
