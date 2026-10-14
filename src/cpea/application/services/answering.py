"""Grounded answer synthesis from bounded SQL results."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from cpea.infrastructure.llm.parsing import parse_model

from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate

from cpea.application.services.sql_execution import SQLExecutionResult
from cpea.infrastructure.llm.context_budget import ContextPacker
from cpea.workflows.text_to_sql.schemas import AnswerDraft
from cpea.application.models.query import AssistantQueryResponse, SourceReference
from cpea.config.settings import AssistantSettings

ANSWER_SYSTEM_PROMPT = """你是企業內部業務資料助手。

回答問題時：
1. 只能根據提供的 Context 回答。
2. 不得自行補充 Context 中不存在的公司資料。
3. 如果 Context 無法支持答案，明確回答資料不足。
4. 數字、日期、產品名稱、客戶名稱不可自行推測。
5. 如果不同來源存在衝突，指出衝突。
6. 回答重要結論時標示來源，例如 [Source 1]。
7. 優先整理成簡潔、可供業務人員閱讀的格式。

只回傳 JSON：answer、citations。citations 必須是實際使用的來源標籤陣列。"""


class AnswerSynthesisService:
    def __init__(
        self,
        llm: Any,
        settings: AssistantSettings | None = None,
        context_packer: ContextPacker | None = None,
    ) -> None:
        self.llm = llm
        self.settings = settings or AssistantSettings.from_env()
        self.context_packer = context_packer or ContextPacker(self.settings)

    def synthesize(
        self, question: str, execution: SQLExecutionResult
    ) -> AssistantQueryResponse:
        context, source, rows_in_context = self.build_context(question, execution)
        messages = self.build_messages(
            question, context, execution.generation.limitations
        )
        raw = self.llm.invoke(messages)
        draft = parse_model(raw, AnswerDraft)
        return self.build_response(draft, source, rows_in_context, execution)

    @staticmethod
    def build_messages(
        question: str, context: str, limitations: list[str]
    ) -> list[BaseMessage]:
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", ANSWER_SYSTEM_PROMPT),
                (
                    "human",
                    "問題：{question}\n\nContext：\n{context}\n\n查詢限制：{limitations}",
                ),
            ]
        )
        return prompt.invoke(
            {
                "question": question,
                "context": context,
                "limitations": limitations,
            }
        ).to_messages()

    @staticmethod
    def build_response(
        draft: AnswerDraft,
        source: SourceReference,
        rows_in_context: int,
        execution: SQLExecutionResult,
    ) -> AssistantQueryResponse:
        allowed = {"[Source 1]", "Source 1"}
        citations = [
            "[Source 1]" for citation in draft.citations if citation in allowed
        ]
        if "[Source 1]" in draft.answer and "[Source 1]" not in citations:
            citations.append("[Source 1]")
        return AssistantQueryResponse(
            answer=draft.answer,
            citations=list(dict.fromkeys(citations)),
            sources=[source],
            sql=execution.generation.sql or "",
            columns=execution.columns,
            rows=execution.rows,
            rows_truncated=(
                execution.rows_truncated or rows_in_context < len(execution.rows)
            ),
            generation=execution.generation,
        )

    def build_context(
        self, question: str, execution: SQLExecutionResult
    ) -> tuple[str, SourceReference, int]:
        header = (
            "[Source 1]\n"
            f"verified_views: {', '.join(execution.generation.selected_views)}\n"
            f"columns: {json.dumps(execution.columns, ensure_ascii=False)}\n"
            "rows:\n"
        )
        base_tokens = self.context_packer.token_counter.count_messages(
            [
                ("system", ANSWER_SYSTEM_PROMPT),
                ("user", f"問題：{question}\nContext：\n{header}"),
            ]
        )
        row_budget = max(
            0,
            self.settings.context_window
            - self.settings.output_token_reserve
            - self.settings.context_safety_tokens
            - base_tokens,
        )
        rendered_rows: list[str] = []
        used = 0
        for row in execution.rows:
            rendered = json.dumps(row, ensure_ascii=False, default=str)
            tokens = self.context_packer.token_counter.count(rendered)
            if used + tokens > row_budget:
                break
            rendered_rows.append(rendered)
            used += tokens
        if not rendered_rows:
            rendered_rows.append("（查無資料，或結果超出可用 context budget）")
        context = header + "\n".join(rendered_rows)
        source_seed = execution.generation.sql or question
        first_schema_source = (
            execution.generation.sources[0] if execution.generation.sources else None
        )
        source = SourceReference(
            document_id="+".join(execution.generation.selected_views),
            source=(first_schema_source.source if first_schema_source else "database"),
            filename=(
                first_schema_source.filename if first_schema_source else "database"
            ),
            section="query_result",
            chunk_id=f"query:{hashlib.sha256(source_seed.encode('utf-8')).hexdigest()[:16]}",
            metadata={
                "views": execution.generation.selected_views,
                "row_count": len(execution.rows),
                "rows_in_context": min(len(rendered_rows), len(execution.rows)),
                "rows_truncated": execution.rows_truncated,
            },
            retrieval_score=(
                first_schema_source.retrieval_score if first_schema_source else None
            ),
            reranker_score=(
                first_schema_source.reranker_score if first_schema_source else None
            ),
        )
        return context, source, min(len(rendered_rows), len(execution.rows))
