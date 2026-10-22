"""Contract counterexamples: no model or database calls."""
import pytest

from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from evaluations import three_stage_view_selection as stage


REQUEST = '對照各店各商品目前庫存件數與2026年9月線上通路的折扣金額及淨銷售額，保留所有庫存商品。'
INV = 'demo_retail.v_inventory_status'
SALES = 'demo_retail.v_sales_detail'
MONTH = 'demo_retail.v_product_monthly'


@pytest.fixture
def catalog():
    return SchemaCatalog('projects/retail')


def recall(catalog):
    specs = [('stock', '目前庫存件數', 'metric', []),
             ('sales', '折扣金額及淨銷售額', 'metric', ['channel', 'period']),
             ('channel', '線上通路', 'filter', []),
             ('period', '2026年9月', 'filter', []),
             ('population', '保留所有庫存商品', 'population', []),
             ('grain', '各店各商品', 'grain', [])]
    return stage.RecallResult.model_validate({
        'requirements': [dict(requirement_id=i, quote=q, kind=k, business_object=q,
                              scope_ids=s, grain='店商品', population='庫存商品') for i, q, k, s in specs],
        'candidate_views': [dict(view=v.name, reason='全契約控制組') for v in catalog.views()]})


def evidence(catalog, view, path):
    value = next(v for v in catalog.views() if v.name == view).policy
    for part in path.lstrip('/').split('/'):
        value = value[part]
    return dict(path=path, quote=value)


def mapping(catalog, view, column, role, quote, **kwargs):
    return dict(column=column, role=role, source_quote=quote,
                contract_evidence=[evidence(catalog, view, '/columns/' + column + '/description')], **kwargs)


def coverage(catalog, view):
    policy = next(v for v in catalog.views() if v.name == view).policy
    rows = []
    for r in recall(catalog).requirements:
        maps = []
        if r.requirement_id == 'stock' and view == INV:
            maps = [mapping(catalog, view, 'stock_qty', 'metric', r.quote, aggregation='sum')]
        if r.requirement_id == 'sales' and view in (SALES, MONTH):
            maps = [mapping(catalog, view, c, 'metric', r.quote, aggregation='sum') for c in ['discount_amount', 'net_sales']]
        if r.requirement_id == 'channel' and view == SALES:
            maps = [mapping(catalog, view, 'sales_channel', 'filter', r.quote, operator='=', value='online')]
        if r.requirement_id == 'period' and view in (SALES, MONTH):
            col = 'order_date' if view == SALES else 'sales_month'
            maps = [mapping(catalog, view, col, 'filter', r.quote, operator=o, value=d)
                    for o, d in [('>=', '2026-09-01'), ('<', '2026-10-01')]]
        if r.requirement_id in ('grain', 'population') and view in (INV, SALES, MONTH):
            maps = [mapping(catalog, view, c, 'key', r.quote) for c in ['store_id', 'product_id']]
        status = 'supported' if maps else 'unsupported'
        if r.requirement_id == 'sales' and view == MONTH:
            status = 'partial'
        rows.append(dict(requirement_id=r.requirement_id, status=status, mappings=maps,
                         contract_evidence=[evidence(catalog, view, '/grain/description')],
                         missing_requirements=['缺少通路'] if status != 'supported' else []))
    return stage.ViewCoverage.model_validate(dict(view=view, entries=rows,
        grain=policy['grain']['description'], keys=policy['grain']['keys'],
        population='來源契約母體', contract_evidence=[evidence(catalog, view, '/summary')]))


def selection(catalog):
    tasks = [dict(task_id='stock', view=INV, required_columns=['store_id', 'product_id', 'stock_qty'],
                  metrics={'stock_qty': 'sum'}, group_by=['store_id', 'product_id'],
                  output_grain=['store_id', 'product_id'], request='取得各店商品庫存件數'),
             dict(task_id='sales', view=SALES,
                  required_columns=['store_id', 'product_id', 'discount_amount', 'net_sales', 'sales_channel', 'order_date'],
                  filters=[dict(column='sales_channel', operator='=', value='online'),
                           dict(column='order_date', operator='>=', value='2026-09-01'),
                           dict(column='order_date', operator='<', value='2026-10-01')],
                  metrics={'discount_amount': 'sum', 'net_sales': 'sum'},
                  group_by=['store_id', 'product_id'], output_grain=['store_id', 'product_id'],
                  request='取得九月線上店商品折扣及淨銷售額')]
    return stage.SelectionResult.model_validate(dict(selected_views=[INV, SALES],
        assignments=[dict(requirement_id=r.requirement_id, view=INV if r.requirement_id in ('stock','population','grain') else SALES,
                          task_id='stock' if r.requirement_id in ('stock','population','grain') else 'sales', reason='契約支持')
                     for r in recall(catalog).requirements],
        exclusions=[dict(view=v.name, reason='沒有必要分工') for v in catalog.views() if v.name not in (INV, SALES)],
        draft=dict(status='ready', strategy='multi_view', tasks=tasks,
                   integration=dict(anchor_task='stock', output_grain=['store_id','product_id'],
                     edges=[dict(left_task='stock', right_task='sales', left_keys=['store_id','product_id'],
                       right_keys=['store_id','product_id'], mode='left', cardinality='one_to_one', preserve_task='stock')]))))


def test_partial_monthly_mapping_survives(catalog):
    mapped = coverage(catalog, MONTH)
    stage.validate_coverage(mapped, recall(catalog), REQUEST, catalog)
    row = next(e for e in mapped.entries if e.requirement_id == 'sales')
    assert row.status == 'partial' and {m.column for m in row.mappings} == {'discount_amount', 'net_sales'}


@pytest.mark.parametrize('path,quote,valid', [('/grain/keys/0', 'store_id', True),
    ('/grain/keys/1', 'sales_month', True), ('/grain/keys/2', 'product_id', True),
    ('/grain/keys/3', 'product_id', False), ('/grain/keys/-1', 'product_id', False),
    ('/grain/keys/01', 'sales_month', False), ('/grain/keys/word', 'store_id', False)])
def test_contract_pointer_array_index_is_resolved_strictly(catalog, path, quote, valid):
    data = coverage(catalog, MONTH).model_dump()
    data['contract_evidence'].append({'path': path, 'quote': quote})
    parsed = stage.ViewCoverage.model_validate(data)
    if valid:
        assert stage.validate_coverage(parsed, recall(catalog), REQUEST, catalog).view == MONTH
    else:
        with pytest.raises(ValueError, match='evidence path'):
            stage.validate_coverage(parsed, recall(catalog), REQUEST, catalog)


@pytest.mark.parametrize('mutation', ['invented_column', 'fake_quote', 'wrong_path', 'forbidden_aggregation', 'missing_requirement', 'wrong_keys'])
def test_invalid_mapping_is_rejected(catalog, mutation):
    data = coverage(catalog, MONTH).model_dump()
    m = data['entries'][1]['mappings'][0]
    if mutation == 'invented_column': m['column'] = 'sales_channel'
    if mutation == 'fake_quote': m['contract_evidence'][0]['quote'] = '本表包含線上通路'
    if mutation == 'wrong_path': m['contract_evidence'][0]['path'] = '/columns/net_sales/description'
    if mutation == 'forbidden_aggregation':
        m['column'] = 'product_name'
        m['contract_evidence'] = [evidence(catalog, MONTH, '/columns/product_name/description')]
        m['aggregation'] = 'sum'
    if mutation == 'missing_requirement': data['entries'].pop()
    if mutation == 'wrong_keys': data['keys'] = ['product_id']
    with pytest.raises(ValueError):
        stage.validate_coverage(stage.ViewCoverage.model_validate(data), recall(catalog), REQUEST, catalog)


def test_monthly_cannot_claim_full_scoped_sales(catalog):
    data = coverage(catalog, MONTH).model_dump()
    data['entries'][1].update(status='supported', missing_requirements=[])
    with pytest.raises(ValueError, match='scope'):
        stage.validate_coverage(stage.ViewCoverage.model_validate(data), recall(catalog), REQUEST, catalog)


@pytest.mark.parametrize('mutation', ['missing_candidate', 'fake_request_quote', 'unknown_scope', 'duplicate_id'])
def test_recall_rejects_invalid_references(catalog, mutation):
    data = recall(catalog).model_dump()
    if mutation == 'missing_candidate': data['candidate_views'].pop()
    if mutation == 'fake_request_quote': data['requirements'][0]['quote'] = '需求不存在'
    if mutation == 'unknown_scope': data['requirements'][1]['scope_ids'] = ['unknown']
    if mutation == 'duplicate_id': data['requirements'][1]['requirement_id'] = 'stock'
    with pytest.raises(ValueError):
        stage.validate_recall(stage.RecallResult.model_validate(data), REQUEST, catalog)


def test_valid_selection_prepares_requests(catalog):
    mapped = [coverage(catalog, v.name) for v in catalog.views()]
    result = stage.finish_selection(selection(catalog), recall(catalog), mapped, REQUEST, catalog)
    assert result.status == 'ready'
    assert [p.view for p in result.prepared_requests] == [INV, SALES]


@pytest.mark.parametrize('mutation', ['scope_borrowing', 'drop_filter', 'new_column', 'inner_population', 'wrong_join_key', 'omit_assignment', 'erase_root_grain', 'zero_missing_values', 'unverified_preparation'])
def test_selection_cannot_add_or_drop_verified_capabilities(catalog, mutation):
    data = selection(catalog).model_dump()
    if mutation == 'scope_borrowing':
        data['assignments'][1]['view'] = MONTH
        data['draft']['tasks'][1]['view'] = MONTH
        data['selected_views'][1] = MONTH
    if mutation == 'drop_filter': data['draft']['tasks'][1]['filters'].pop(0)
    if mutation == 'new_column': data['draft']['tasks'][0]['required_columns'].append('snapshot_date')
    if mutation == 'inner_population': data['draft']['integration']['edges'][0].update(mode='inner', preserve_task=None)
    if mutation == 'wrong_join_key': data['draft']['integration']['edges'][0]['right_keys'] = ['product_id']
    if mutation == 'omit_assignment': data['assignments'].pop()
    if mutation == 'erase_root_grain':
        data['draft']['integration']['output_grain'] = ['product_id']
        data['draft']['integration']['preparation'] = [dict(task_id='stock', kind='aggregate', keys=['product_id'], description='跨店合計')]
    if mutation == 'zero_missing_values': data['draft']['integration']['missing_data_policy'] = '未匹配銷售金額一律補零'
    if mutation == 'unverified_preparation':
        data['draft']['integration']['preparation'] = [dict(task_id='stock', kind='aggregate', keys=['product_id'], description='跨店合計')]
    with pytest.raises(ValueError):
        stage.finish_selection(stage.SelectionResult.model_validate(data), recall(catalog),
            [coverage(catalog, v.name) for v in catalog.views()], REQUEST, catalog)


def pipeline_fixture(catalog):
    from evaluations.indexed_requirement_recall import IndexedRecallResult
    data = recall(catalog).model_dump()
    for requirement in data['requirements']:
        quote = requirement.pop('quote')
        start = REQUEST.index(quote)
        requirement.update(start=start, end=start + len(quote))
    generated = IndexedRecallResult.model_validate(data)
    return [generated, *[coverage(catalog, v.name) for v in catalog.views()], selection(catalog)]


def test_pipeline_persists_nine_nodes_and_prepares_requests(catalog):
    from langchain_core.messages import AIMessage
    from evaluations.three_stage_view_selection_runner import run_pipeline, Budget
    responses = iter(pipeline_fixture(catalog))
    saved = {}
    def invoke(messages, schema):
        return AIMessage(content=next(responses).model_dump_json())
    result = run_pipeline(REQUEST, catalog, invoke, saved.__setitem__, Budget())
    assert result.status == 'ready'
    assert len([n for n in saved if n.endswith('-call.json')]) == 9
    assert len(result.prepared_requests) == 2


def test_pipeline_stops_at_first_invalid_node_and_keeps_raw(catalog):
    from langchain_core.messages import AIMessage
    from evaluations.three_stage_view_selection_runner import run_pipeline, Budget
    saved = {}
    result = pipeline_fixture(catalog)[0].model_dump()
    result['candidate_views'].pop()
    with pytest.raises(ValueError):
        run_pipeline(REQUEST, catalog, lambda *args: AIMessage(content=__import__('json').dumps(result)),
                     saved.__setitem__, Budget())
    assert set(saved) >= {'recall-call.json', 'recall-error.json'}
    assert not any(n.startswith('map-') for n in saved)


@pytest.mark.parametrize('limit', ['calls', 'tokens', 'wall', 'context'])
def test_budget_stops_before_provider_construction(catalog, limit):
    from evaluations.three_stage_view_selection_runner import run_pipeline, Budget
    budget = Budget()
    if limit == 'calls': budget.calls_limit = 0
    if limit == 'tokens': budget.total_input_limit = 1
    if limit == 'wall': budget.wall_seconds = 0
    if limit == 'context': budget.context_window = 1
    def no_provider(*args):
        pytest.fail('provider invoked after exhausted budget')
    with pytest.raises(ValueError, match='budget'):
        run_pipeline(REQUEST, catalog, no_provider, lambda *args: None, budget)


def test_provider_error_stops_without_retry(catalog):
    from evaluations.three_stage_view_selection_runner import run_pipeline, Budget
    saved = {}
    budget = Budget()
    def unavailable(*args):
        raise RuntimeError('provider unavailable')
    with pytest.raises(RuntimeError):
        run_pipeline(REQUEST, catalog, unavailable, saved.__setitem__, budget)
    assert budget.calls == 1
    assert 'recall-provider-error.json' in saved


def saved_run(tmp_path, catalog, provider_error=False, calls_limit=9):
    import json
    from hashlib import sha256
    from langchain_core.messages import AIMessage
    from evaluations.three_stage_view_selection_runner import run_pipeline, Budget, fingerprint
    budget = Budget(calls_limit=calls_limit)
    def save(name, value):
        (tmp_path / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    responses = iter(pipeline_fixture(catalog))
    def invoke(*args):
        if provider_error:
            raise RuntimeError('rate limited; no retry')
        return AIMessage(content=next(responses).model_dump_json())
    stopped = None
    try:
        run_pipeline(REQUEST, catalog, invoke, save, budget)
    except (RuntimeError, ValueError) as exc:
        stopped = dict(error_type=type(exc).__name__, error=str(exc))
    case = {'case_id': 'offline-control', 'request': REQUEST}
    save('run.json', dict(frozen=fingerprint(catalog, case), stopped=stopped, calls=budget.calls,
                          artifact_hashes={p.name: sha256(p.read_bytes()).hexdigest() for p in tmp_path.iterdir()}))
    return case


def test_replay_preserves_provider_stop_without_network(tmp_path, catalog):
    from evaluations.three_stage_view_selection_runner import replay
    case = saved_run(tmp_path, catalog, provider_error=True)
    result = replay(tmp_path, catalog, case)
    assert result['result'] == 'PASS' and result['raw_replays'] == 0
    assert result['stopped'] == {'error_type': 'RuntimeError', 'error': 'rate limited; no retry'}


def test_replay_rejects_unlisted_injected_artifact(tmp_path, catalog):
    from evaluations.three_stage_view_selection_runner import replay
    case = saved_run(tmp_path, catalog)
    assert replay(tmp_path, catalog, case) == {'result': 'PASS', 'raw_replays': 9, 'stopped': None}
    (tmp_path / 'injected-call.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='artifact'):
        replay(tmp_path, catalog, case)


def test_provider_usage_over_budget_stops_before_next_node(catalog):
    from langchain_core.messages import AIMessage
    from evaluations.three_stage_view_selection_runner import run_pipeline, Budget
    saved = {}
    def invoke(*args):
        return AIMessage(content=pipeline_fixture(catalog)[0].model_dump_json(),
                         usage_metadata={'input_tokens': 150001, 'output_tokens': 100, 'total_tokens': 150101})
    budget = Budget()
    with pytest.raises(ValueError, match='usage budget'):
        run_pipeline(REQUEST, catalog, invoke, saved.__setitem__, budget)
    assert budget.calls == 1
    assert 'recall-call.json' in saved and not any(n.startswith('map-') for n in saved)


def test_continuation_reuses_prefix_without_repeating_provider_calls(tmp_path, catalog):
    from langchain_core.messages import AIMessage
    from evaluations.three_stage_view_selection_runner import load_cached_prefix, Continuation, run_pipeline, Budget
    case = saved_run(tmp_path, catalog, calls_limit=2)
    records, meta = load_cached_prefix(tmp_path, catalog, case)
    remaining = iter(pipeline_fixture(catalog)[2:])
    def live(*args):
        return AIMessage(content=next(remaining).model_dump_json())
    continuation = Continuation(records, live)
    saved = {}
    response = run_pipeline(REQUEST, catalog, continuation, saved.__setitem__, Budget())
    assert response.status == 'ready'
    assert continuation.cached_calls == 2 and continuation.live_calls == 7
    assert saved['recall-call.json']['origin'] == 'cached_raw'
    assert saved['selection-call.json']['origin'] == 'live'


def test_continuation_refuses_provider_failure_retry(tmp_path, catalog):
    from evaluations.three_stage_view_selection_runner import load_cached_prefix
    case = saved_run(tmp_path, catalog, provider_error=True)
    with pytest.raises(ValueError, match='provider failure'):
        load_cached_prefix(tmp_path, catalog, case)


def test_continuation_rejects_changed_prompt_before_live_call(tmp_path, catalog):
    from evaluations.three_stage_view_selection_runner import load_cached_prefix, Continuation
    case = saved_run(tmp_path, catalog, calls_limit=2)
    records, _ = load_cached_prefix(tmp_path, catalog, case)
    continuation = Continuation(records, lambda *args: pytest.fail('must not invoke live'))
    with pytest.raises(ValueError, match='cached input'):
        continuation([], stage.RecallResult)
