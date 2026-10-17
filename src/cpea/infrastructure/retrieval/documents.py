from pathlib import Path
import re
from langchain_core.documents import Document
from cpea.application.ports.catalog import CatalogProvider


def _without_column_names(text: str, names: list[str]) -> str:
    for name in sorted(names, key=len, reverse=True):
        text = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", "欄位", text)
    return text


def build_documents(catalog: CatalogProvider) -> list[Document]:
    """Index View and field descriptions without column names for retrieval."""
    documents: list[Document] = []
    for definition in catalog.views():
        columns = catalog.columns(definition.name)
        names = list(columns)
        summary = _without_column_names(definition.summary, names)
        descriptions = [
            f"- {_without_column_names(catalog.field_contract(definition.name, name)['description'], names)}"
            for name in names
        ]
        source = Path(definition.detail_path).as_posix()
        documents.append(
            Document(
                id=definition.name,
                page_content="\n".join([f"用途摘要：{summary}", "", "欄位說明：", *descriptions]),
                metadata={
                    "document_id": definition.name,
                    "source": source,
                    "filename": Path(source).name,
                    "section": "schema_contract",
                    "page": None,
                    "chunk_id": f"{definition.name}:schema_contract",
                    "schema": definition.name.split(".", 1)[0],
                    "document_type": "database_view",
                    "view_name": definition.name,
                    "summary": summary,
                },
            )
        )
    return documents
