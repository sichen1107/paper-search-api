import io
import datetime
import pandas as pd
import streamlit as st

from literature_api import search_openalex, search_semantic_scholar, enrich_with_crossref
from cnki_importer import import_cnki_bibtex
from deduplicate import merge_and_deduplicate

st.set_page_config(page_title="免费文献检索工具", layout="wide")

st.title("免费文献检索工具")
st.caption("OpenAlex + Crossref + Semantic Scholar + 知网 BibTeX 导入")

current_year = datetime.datetime.now().year

query = st.text_input(
    "请输入检索关键词",
    placeholder="例如：oleic acid hydrogenation catalyst"
)

col1, col2 = st.columns(2)

with col1:
    from_year = st.number_input(
        "起始发表年份",
        min_value=1900,
        max_value=current_year,
        value=max(2018, current_year - 8),
        step=1
    )

with col2:
    to_year = st.number_input(
        "结束发表年份",
        min_value=1900,
        max_value=current_year,
        value=current_year,
        step=1
    )

col3, col4 = st.columns(2)

with col3:
    openalex_count = st.slider(
        "OpenAlex 检索篇数",
        min_value=10,
        max_value=200,
        value=80,
        step=10
    )

with col4:
    semantic_count = st.slider(
        "Semantic Scholar 检索篇数",
        min_value=10,
        max_value=100,
        value=50,
        step=10
    )

sort_method = st.selectbox(
    "结果排序方式",
    ["按引用量排序", "按年份新到旧", "按年份旧到新"]
)

cnki_file = st.file_uploader(
    "上传知网 BibTeX 文件（可选）",
    type=["bib"]
)

semantic_key = st.text_input(
    "Semantic Scholar API Key（可不填）",
    "",
    type="password"
)

use_crossref = st.checkbox(
    "使用 Crossref 补充 DOI",
    value=True
)

email = st.text_input(
    "Crossref 邮箱参数",
    value="your_email@example.com"
)

if st.button("一键检索", type="primary"):
    if not query:
        st.warning("请输入检索关键词。")
    elif int(from_year) > int(to_year):
        st.warning("起始年份不能大于结束年份。")
    else:
        all_papers = []

        with st.spinner("检索 OpenAlex..."):
            openalex_papers = search_openalex(
                query,
                per_page=openalex_count,
                from_year=int(from_year),
                to_year=int(to_year)
            )
            all_papers.extend(openalex_papers)

        st.success(f"OpenAlex 返回 {len(openalex_papers)} 篇")

        with st.spinner("检索 Semantic Scholar..."):
            semantic_papers = search_semantic_scholar(
                query,
                limit=semantic_count,
                api_key=semantic_key,
                from_year=int(from_year),
                to_year=int(to_year)
            )
            all_papers.extend(semantic_papers)

        st.success(f"Semantic Scholar 返回 {len(semantic_papers)} 篇")

        if cnki_file:
            with st.spinner("解析知网 BibTeX..."):
                cnki_papers = import_cnki_bibtex(cnki_file)

                filtered_cnki = []
                for p in cnki_papers:
                    try:
                        y = int(p.get("year", 0))
                        if int(from_year) <= y <= int(to_year):
                            filtered_cnki.append(p)
                    except:
                        pass

                all_papers.extend(filtered_cnki)

            st.success(f"知网导入并按年份筛选后 {len(filtered_cnki)} 篇")

        with st.spinner("合并去重..."):
            merged_papers = merge_and_deduplicate(all_papers)

        if use_crossref:
            with st.spinner("Crossref 补充 DOI..."):
                merged_papers = enrich_with_crossref(
                    merged_papers,
                    mailto=email,
                    max_items=30
                )

        df = pd.DataFrame(merged_papers)

        if df.empty:
            st.warning("没有检索到符合条件的文献。可以尝试：放宽年份范围、增加检索篇数、换英文关键词。")
        else:
            if "year" in df.columns:
                df["year"] = pd.to_numeric(df["year"], errors="coerce")

            if "citation_count" in df.columns:
                df["citation_count"] = pd.to_numeric(df["citation_count"], errors="coerce").fillna(0)

            if sort_method == "按引用量排序" and "citation_count" in df.columns:
                df = df.sort_values(by="citation_count", ascending=False)
            elif sort_method == "按年份新到旧" and "year" in df.columns:
                df = df.sort_values(by="year", ascending=False)
            elif sort_method == "按年份旧到新" and "year" in df.columns:
                df = df.sort_values(by="year", ascending=True)

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

            st.subheader(f"检索结果：共 {len(df)} 篇")
            st.dataframe(df, use_container_width=True)

            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="papers")

            st.download_button(
                "下载 Excel 文献表",
                excel_buffer.getvalue(),
                "papers.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
