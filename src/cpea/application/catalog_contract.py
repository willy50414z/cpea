from __future__ import annotations
import json
import re
from typing import Any
import yaml

class CatalogContract:
    """Existing deterministic view rules and prompt rendering; no filesystem or LLM dependencies."""

    def columns(self, view_name: str) -> dict[str, str]:
        definition = next((item for item in self.views() if item.name == view_name), None)
        if definition is None:
            raise ValueError(f"view is not in the verified catalogue: {view_name}")
        configured = definition.policy.get("columns")
        if not isinstance(configured, dict):
            raise ValueError(f"view {view_name} does not contain columns")
        columns = {
            name: spec["type"]
            for name, spec in configured.items()
            if isinstance(name, str) and isinstance(spec, dict) and isinstance(spec.get("type"), str)
        }
        if not columns:
            raise ValueError(f"view {view_name} does not contain a valid field table")
        return columns

    def validate_plan_contract(self, plan: Any, request: str) -> list[str]:
        """Return deterministic schema/policy violations for a query plan.

        Cross-view joins intentionally remain out of scope.  Every referenced
        column must exist in one of the plan's approved source views and every
        filter operator must be permitted by that view's declarative policy.
        """
        definitions = {item.name: item for item in self.views()}
        selected = [definitions[name] for name in plan.source_views if name in definitions]
        available = {column for definition in selected for column in self.columns(definition.name)}
        violations: list[str] = []
        unknown_views = sorted(set(plan.source_views) - set(definitions))
        if unknown_views:
            violations.append(f"未驗證的 View：{', '.join(unknown_views)}")
        for label, values in (("select_columns", plan.select_columns), ("group_by", plan.group_by), ("order_by", plan.order_by)):
            unknown = sorted(set(values) - available)
            if unknown:
                violations.append(f"{label} 包含 schema 不存在的欄位：{', '.join(unknown)}")
        unknown_directions = sorted(set(plan.order_directions) - set(plan.order_by))
        if unknown_directions:
            violations.append(f"order_directions 包含未排序的欄位：{', '.join(unknown_directions)}")
        if not set(plan.group_by) <= set(plan.select_columns):
            violations.append("GROUP BY 欄位必須包含在 select_columns")
        if not set(plan.aggregations) <= set(plan.select_columns):
            violations.append("aggregations 只能引用 select_columns")
        for label, values, capability in (
            ("select_columns", plan.select_columns, "select"),
            ("group_by", plan.group_by, "group_by"),
            ("order_by", plan.order_by, "order_by"),
        ):
            for column in values:
                if column in available and not any(
                    capability in self.field_contract(definition.name, column).get("capabilities", [])
                    for definition in selected if column in self.columns(definition.name)
                ):
                    violations.append(f"{label} 不允許欄位：{column}")
        for column, aggregation in plan.aggregations.items():
            if column in available and not any(
                aggregation in self.field_contract(definition.name, column).get("aggregations", [])
                for definition in selected if column in self.columns(definition.name)
            ):
                violations.append(f"aggregation 不允許：{column} {aggregation}")
        for item in plan.filters:
            matching = [definition for definition in selected if item.column in self.columns(definition.name)]
            if not matching:
                violations.append(f"filter 欄位不存在於 source_views：{item.column}")
                continue
            if not any("filter" in self.field_contract(definition.name, item.column).get("capabilities", []) for definition in matching):
                violations.append(f"filter 不允許欄位：{item.column}")
            permitted = set().union(*(self._operators_for(definition.name, item.column) for definition in matching))
            if item.operator not in permitted:
                violations.append(f"filter operator 不允許：{item.column} {item.operator}")
            if item.operator == "IN" and (
                not isinstance(item.value, list) or not item.value
            ):
                violations.append(f"IN filter 必須提供非空值陣列：{item.column}")
            if item.operator != "IN" and isinstance(item.value, list):
                violations.append(f"非 IN filter 不可使用值陣列：{item.column}")
        if plan.having and not plan.group_by:
            violations.append("HAVING 必須有 GROUP BY")
        for item in plan.having:
            matching = [definition for definition in selected if item.column in self.columns(definition.name)]
            if not matching:
                violations.append(f"HAVING 欄位不存在於 source_views：{item.column}")
                continue
            if not any("filter" in self.field_contract(definition.name, item.column).get("capabilities", [])
                       for definition in matching):
                violations.append(f"HAVING 不允許篩選欄位：{item.column}")
            if not any(item.aggregation in self.field_contract(definition.name, item.column).get("aggregations", [])
                       for definition in matching):
                violations.append(f"HAVING aggregation 不允許：{item.column} {item.aggregation}")
            if not any(item.operator in self._operators_for(definition.name, item.column)
                       for definition in matching):
                violations.append(f"HAVING operator 不允許：{item.column} {item.operator}")
            if item.aggregation in {"sum", "avg", "min", "max"} and not any(
                    self.columns(definition.name)[item.column] in {"number", "數值", "数值"} for definition in matching):
                violations.append(f"HAVING 聚合結果必須為數值：{item.column}")
        for definition in selected:
            for rule in definition.policy.get("scope_rules", []):
                if not any(re.search(pattern, request) for pattern in rule.get("request_patterns", [])):
                    continue
                dimension = rule["required_dimension"]
                if dimension not in plan.select_columns:
                    violations.append(f"{rule['name']} 必須選取維度：{dimension}")
                if rule.get("required_group_by") and dimension not in plan.group_by:
                    violations.append(f"{rule['name']} 必須依維度彙總：{dimension}")
                prohibited = set(rule.get("prohibited_filter_columns", []))
                narrowed = sorted({item.column for item in plan.filters} & prohibited)
                if narrowed:
                    violations.append(f"{rule['name']} 不得限定篩選：{', '.join(narrowed)}")
        return violations

    def mapped_filters(self, request: str, view_names: list[str]) -> list[dict[str, Any]]:
        """Return deterministic business filters declared by matching view terms."""
        definitions = {item.name: item for item in self.views()}
        filters: list[dict[str, Any]] = []
        for view_name in view_names:
            definition = definitions.get(view_name)
            if definition is None:
                continue
            prohibited = {
                column
                for rule in definition.policy.get("scope_rules", [])
                if any(re.search(pattern, request) for pattern in rule.get("request_patterns", []))
                for column in rule.get("prohibited_filter_columns", [])
            }
            for mapping in definition.policy.get("term_mappings", []):
                terms = mapping.get("terms", [])
                if not any(term in request for term in terms if isinstance(term, str)):
                    continue
                for item in mapping.get("filters", []):
                    if isinstance(item, dict) and {"column", "operator", "value"} <= item.keys() and item["column"] not in prohibited:
                        filters.append(item)
        return filters

    def matching_scope_rules(self, request: str, view_names: list[str]) -> list[tuple[str, dict[str, Any]]]:
        """Return declarative scope rules matching the request, with their View."""
        definitions = {item.name: item for item in self.views()}
        return [
            (view_name, rule)
            for view_name in view_names
            if view_name in definitions
            for rule in definitions[view_name].policy.get("scope_rules", [])
            if any(re.search(pattern, request) for pattern in rule.get("request_patterns", []))
        ]

    def field_contract(self, view_name: str, column: str) -> dict[str, Any]:
        definition = next((item for item in self.views() if item.name == view_name), None)
        if definition is None:
            raise ValueError(f"view is not in the verified catalogue: {view_name}")
        contract = definition.policy.get("columns", {}).get(column)
        if not isinstance(contract, dict):
            raise ValueError(f"column is not in view contract: {view_name}.{column}")
        if definition.policy.get('version') not in {3, 4}:
            return contract
        field_type = contract['type']
        capabilities = {'select', 'filter', 'group_by', 'order_by'} - set(contract.get('disallowed_capabilities', []))
        aggregations = ({'sum', 'count', 'count_distinct', 'avg', 'min', 'max'} if field_type == 'number'
                        else {'count', 'count_distinct', 'min', 'max'} if field_type in {'string', 'date'}
                        else {'count', 'count_distinct'})
        return {**contract, 'capabilities': sorted(capabilities),
                'aggregations': sorted(aggregations - set(contract.get('disallowed_aggregations', [])))}

    def validate_link(self, link: Any, allowed_views: set[str]) -> str | None:
        if link.view not in allowed_views:
            return f"schema link uses unselected view: {link.view}"
        try:
            contract = self.field_contract(link.view, link.column)
        except ValueError as exc:
            return str(exc)
        needed = "filter" if link.role in {"filter", "having"} else "select"
        if needed not in contract.get("capabilities", []):
            return f"schema link cannot {needed} column: {link.column}"
        if link.role in {"metric", "having"} and link.aggregation and link.aggregation not in contract.get("aggregations", []):
            return f"metric aggregation not allowed: {link.column} {link.aggregation}"
        if link.role == "dimension" and "group_by" not in contract.get("capabilities", []):
            return f"dimension link requires groupable column: {link.column}"
        if link.role in {"filter", "having"}:
            if link.operator is None or link.value is None:
                return f"filter link requires operator and value: {link.column}"
            operators = self._operators_for(link.view, link.column)
            if link.operator not in operators:
                return f"filter operator not allowed: {link.column} {link.operator}"
            if link.operator == "IN" and (not isinstance(link.value, list) or not link.value):
                return f"IN link requires nonempty values: {link.column}"
            if link.operator != "IN" and isinstance(link.value, list):
                return f"filter link uses unexpected values list: {link.column}"
            if link.role == "having":
                if link.aggregation not in {"sum", "count", "count_distinct", "avg", "min", "max"}:
                    return f"HAVING link requires aggregation: {link.column}"
                if link.operator not in {"=", "!=", "<>", ">", ">=", "<", "<="}:
                    return f"HAVING link uses unsupported operator: {link.column}"
                if not isinstance(link.value, (int, float)) or isinstance(link.value, bool):
                    return f"HAVING link requires numeric value: {link.column}"
                if link.aggregation in {"sum", "avg", "min", "max"} and self.columns(link.view)[link.column] not in {"number", "數值", "数值"}:
                    return f"HAVING aggregation requires numeric column: {link.column}"
        elif link.operator is not None or link.value is not None:
            return f"non-filter link contains filter condition: {link.column}"
        return None

    def _operators_for(self, view_name: str, column: str) -> set[str]:
        definition = next(item for item in self.views() if item.name == view_name)
        if definition.policy.get('version') in {3, 4}:
            spec = definition.policy['columns'][column]
            base = {'=', '!=', '<>', 'IN'}
            if spec['type'] in {'number', 'date'}:
                base.update({'>', '>=', '<', '<='})
            if spec['type'] == 'string':
                base.add('LIKE')
            return base - set(spec.get('disallowed_operators', []))
        policy = definition.policy.get("filter_operators", {})
        configured = policy.get("columns", {}).get(column)
        if configured is not None:
            return set(configured)
        field_type = self.columns(view_name)[column]
        if "日期" in field_type:
            return set(policy.get("date", policy.get("default", [])))
        if "數值" in field_type or "数值" in field_type:
            return set(policy.get("number", policy.get("default", [])))
        return set(policy.get("default", []))

    def detail(self, view_name: str) -> str:
        definition = next(
            (item for item in self.views() if item.name == view_name), None
        )
        if definition is None:
            raise ValueError(f"view is not in the verified catalogue: {view_name}")
        policy = definition.policy
        lines = [f"# View: {view_name}", "", "## 用途摘要", "", policy["summary"], "", "## 欄位說明", "", "| 欄位名稱 | 型別（推測） | 說明 | 權限 | 可用聚合 | 別名 |", "|---|---|---|---|---|---|"]
        for name, raw in policy["columns"].items():
            spec = self.field_contract(view_name, name)
            lines.append(f"| {name} | {spec['type']} | {spec['description']} | {', '.join(spec.get('capabilities', []))} | {', '.join(spec.get('aggregations', []))} | {', '.join(raw.get('aliases', []))} |")
        if policy.get("filter_operators"):
            lines.extend(["", "## 篩選運算子", "", yaml.safe_dump(policy["filter_operators"], allow_unicode=True, sort_keys=False)])
        if policy.get("data_scope"):
            lines.extend(["", "## 資料範圍說明", "", policy["data_scope"]])
        if policy.get("temporal_scope"):
            temporal_scope = policy["temporal_scope"]
            description = ("目前快照；『目前／現在』由 View 本身滿足，不需時間欄位或篩選條件。"
                           if temporal_scope == "current_snapshot" else temporal_scope)
            lines.extend(["", "## 時間語意（非欄位）", "", description])
        if policy.get("limitations"):
            lines.extend(["", "## 已知限制"])
            lines.extend(f"- {item}" for item in policy["limitations"])
        if policy.get('version') == 4:
            for key, label in (('grain', '資料粒度'), ('source', '來源證據'),
                               ('scope', '資料母體與範圍'), ('time', '時間規則'),
                               ('usage', '適用範圍'), ('metrics', '指標口徑')):
                lines.extend(['', f'## {label}', '', json.dumps(policy[key], ensure_ascii=False)])
            entities = {name: spec['entity'] for name, spec in policy['columns'].items() if 'entity' in spec}
            if entities:
                lines.extend(['', '## 欄位所屬實體', '', json.dumps(entities, ensure_ascii=False)])
        return "\n".join(lines) + "\n"

    def context(self, view_names: list[str]) -> str:
        parts = ["## Verified view catalogue\n", self.overview()]
        for view_name in dict.fromkeys(view_names):
            parts.append(f"\n## Detailed schema: {view_name}\n{self.detail(view_name)}")
        return "\n".join(parts)

    def model_schema_context(self, view_names: list[str]) -> str:
        """Return only the schema contract needed for planning/generation.

        Sample rows remain available in the source files for future retrieval,
        but sending them on every LLM call wastes the limited local context
        window and can push a structured response out of the model context.
        """
        parts: list[str] = []
        for view_name in dict.fromkeys(view_names):
            detail = self.detail(view_name)
            contract = re.split(
                r"^##\s+範例資料", detail, maxsplit=1, flags=re.MULTILINE
            )[0].rstrip()
            parts.append(f"## Detailed schema: {view_name}\n{contract}")
        return "\n\n".join(parts)
