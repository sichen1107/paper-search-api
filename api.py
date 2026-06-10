import io
import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from literature_api import search_openalex, search_semantic_scholar, enrich_with_crossref
from cnki_importer import import_cnki_bibtex
from deduplicate import merge_and_deduplicate


app = FastAPI(
    title="免费文献检索 API",
    description="OpenAlex + Crossref + Semantic Scholar + CNKI BibTeX 文献检索接口",
    version="1.0.0"
)

# 允许网页前端跨域调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    query: str
    from_year: Optional[int] = 2018
    to_year: Optional[int] = 2026
    openalex_count: Optional[int] = 80
    semantic_count: Optional[int] = 50
    use_crossref: Optional[bool] = True
    email: Optional[str] = "your_email@example.com"
    semantic_key: Optional[str] = ""


def papers_to_dataframe(papers):
    df = pd.DataFrame(papers)

    if df.empty:
        return df

    preferred_columns = [
        "title",
        "authors",
        "year",
        "venue",
        "doi",
        "citation_count",
        "abstract",
        "url",
        "source"
    ]

    existing_columns = [c for c in preferred_columns if c in df.columns]
    df = df[existing_columns]

    if "year" in df.columns:
        df["year"] = pd.to_numeric(df["year"], errors="coerce")

    if "citation_count" in df.columns:
        df["citation_count"] = pd.to_numeric(df["citation_count"], errors="coerce").fillna(0)

    return df


def search_papers_core(
    query,
    from_year=2018,
    to_year=2026,
    openalex_count=80,
    semantic_count=50,
    use_crossref=True,
    email="your_email@example.com",
    semantic_key="",
    cnki_file=None
):
    all_papers = []

    openalex_papers = search_openalex(
        query,
        per_page=openalex_count,
        from_year=from_year,
        to_year=to_year
    )
    all_papers.extend(openalex_papers)

    semantic_papers = search_semantic_scholar(
        query,
        limit=semantic_count,
        api_key=semantic_key,
        from_year=from_year,
        to_year=to_year
    )
    all_papers.extend(semantic_papers)

    cnki_count = 0

    if cnki_file is not None:
        cnki_papers = import_cnki_bibtex(cnki_file)

        filtered_cnki = []
        for p in cnki_papers:
            try:
                y = int(p.get("year", 0))
                if int(from_year) <= y <= int(to_year):
                    filtered_cnki.append(p)
            except:
                pass

        cnki_count = len(filtered_cnki)
        all_papers.extend(filtered_cnki)

    merged_papers = merge_and_deduplicate(all_papers)

    if use_crossref:
        merged_papers = enrich_with_crossref(
            merged_papers,
            mailto=email,
            max_items=30
        )

    return {
        "query": query,
        "from_year": from_year,
        "to_year": to_year,
        "openalex_count": len(openalex_papers),
        "semantic_scholar_count": len(semantic_papers),
        "cnki_count": cnki_count,
        "total_count": len(merged_papers),
        "papers": merged_papers
    }


@app.get("/")
def root():
    return {
        "message": "免费文献检索 API 已启动",
        "docs": "/docs",
        "search_api": "/api/search",
        "excel_api": "/api/search/excel",
        "upload_api": "/api/search-with-cnki"
    }


@app.post("/api/search")
def search_api(request: SearchRequest):
    """
    JSON 文献检索接口。
    不上传 CNKI 文件时用这个。
    """
    result = search_papers_core(
        query=request.query,
        from_year=request.from_year,
        to_year=request.to_year,
        openalex_count=request.openalex_count,
        semantic_count=request.semantic_count,
        use_crossref=request.use_crossref,
        email=request.email,
        semantic_key=request.semantic_key
    )

    return result


@app.post("/api/search/excel")
def search_excel_api(request: SearchRequest):
    """
    JSON 检索并直接返回 Excel 文件。
    """
    result = search_papers_core(
        query=request.query,
        from_year=request.from_year,
        to_year=request.to_year,
        openalex_count=request.openalex_count,
        semantic_count=request.semantic_count,
        use_crossref=request.use_crossref,
        email=request.email,
        semantic_key=request.semantic_key
    )

    df = papers_to_dataframe(result["papers"])

    excel_buffer = io.BytesIO()

    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="papers")

    excel_buffer.seek(0)

    filename = "papers.xlsx"

    return StreamingResponse(
        excel_buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@app.post("/api/search-with-cnki")
def search_with_cnki_api(
    query: str = Form(...),
    from_year: int = Form(2018),
    to_year: int = Form(2026),
    openalex_count: int = Form(80),
    semantic_count: int = Form(50),
    use_crossref: bool = Form(True),
    email: str = Form("your_email@example.com"),
    semantic_key: str = Form(""),
    cnki_file: UploadFile = File(None)
):
    """
    支持上传 CNKI BibTeX 文件的检索接口。
    前端 form-data 上传时用这个。
    """
    result = search_papers_core(
        query=query,
        from_year=from_year,
        to_year=to_year,
        openalex_count=openalex_count,
        semantic_count=semantic_count,
        use_crossref=use_crossref,
        email=email,
        semantic_key=semantic_key,
        cnki_file=cnki_file.file if cnki_file else None
    )

    return result


@app.post("/api/search-with-cnki/excel")
def search_with_cnki_excel_api(
    query: str = Form(...),
    from_year: int = Form(2018),
    to_year: int = Form(2026),
    openalex_count: int = Form(80),
    semantic_count: int = Form(50),
    use_crossref: bool = Form(True),
    email: str = Form("your_email@example.com"),
    semantic_key: str = Form(""),
    cnki_file: UploadFile = File(None)
):
    """
    支持上传 CNKI BibTeX 文件，并返回 Excel。
    """
    result = search_papers_core(
        query=query,
        from_year=from_year,
        to_year=to_year,
        openalex_count=openalex_count,
        semantic_count=semantic_count,
        use_crossref=use_crossref,
        email=email,
        semantic_key=semantic_key,
        cnki_file=cnki_file.file if cnki_file else None
    )

    df = papers_to_dataframe(result["papers"])

    excel_buffer = io.BytesIO()

    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="papers")

    excel_buffer.seek(0)

    return StreamingResponse(
        excel_buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=papers.xlsx"
        }
    )
