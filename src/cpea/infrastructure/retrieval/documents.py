from pathlib import Path
from langchain_core.documents import Document
from cpea.application.ports.catalog import CatalogProvider

def build_documents(catalog: CatalogProvider) -> list[Document]:
    """Return one semantic, table-preserving retrieval unit per view.

    The curated files are already organized by business-document
    sections. Keeping each schema contract intact prevents field tables
    and their column headings from being separated. Large sample-data
    tables are deliberately excluded from both retrieval and LLM context.
    """
    documents: list[Document] = []
    for definition in catalog.views():
        # Retrieval needs a compact semantic index. The full field
        # descriptions are loaded only after the view has been selected.
        columns = catalog.columns(definition.name)
        contract = "\n".join(
            [f"# View: {definition.name}", definition.summary, "", "欄位："]
            + [f"- {name}（{field_type}）" for name, field_type in columns.items()]
        )
        source = Path(definition.detail_path).as_posix()
        documents.append(
            Document(
                id=definition.name,
                page_content=(
                    f"# {definition.name}\n\n"
                    f"用途摘要：{definition.summary}\n\n{contract}"
                ),
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
                    "summary": definition.summary,
                },
            )
        )
    return documents
