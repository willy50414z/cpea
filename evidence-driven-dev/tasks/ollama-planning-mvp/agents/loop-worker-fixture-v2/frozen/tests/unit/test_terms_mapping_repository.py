from concurrent.futures import ThreadPoolExecutor
import json

import pytest
from cpea.application.ports.term_mappings import MappingScope, MappingStoreError, MappingConflict, TermMapping, normalize_term
from cpea.infrastructure.terms_mapping import JsonTermMappingRepository


def record(term='含稅發票總額', column='amount', ident='one'):
    return TermMapping(id=ident, term=term, normalized_term=normalize_term(term), view='demo.v', column=column,
                       view_contract_fingerprint='f' * 64, confirmed_at='2026-10-16T00:00:00Z')


def repository(tmp_path):
    return JsonTermMappingRepository(tmp_path / 'terms_mapping.json', MappingScope(profile_id='test', datasource_id=None))


def test_missing_concurrent_merge_and_idempotence(tmp_path):
    repo = repository(tmp_path)
    assert repo.read().revision == 0
    values = [record(f'詞彙 {i}', ident=str(i)) for i in range(15)]
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(lambda m: repo.commit([m], used=[], replacements={}), values))
    assert len(repo.read().mappings) == 15
    revision = repo.read().revision
    assert repo.commit([values[0]], used=[], replacements={}) == [values[0]]
    assert repo.read().revision == revision
    assert not repo.path.read_bytes().startswith(b'\xef\xbb\xbf')


def test_replacement_is_bound_to_current_id_and_atomic(tmp_path):
    repo = repository(tmp_path)
    one, two, three = record(), record(column='net', ident='two'), record(column='other', ident='three')
    repo.commit([one], used=[], replacements={})
    with pytest.raises(MappingConflict):
        repo.commit([two], used=[], replacements={})
    repo.commit([two], used=[], replacements={one.key: one.id})
    with pytest.raises(MappingConflict):
        repo.commit([three], used=[], replacements={one.key: one.id})
    assert [m.status for m in repo.read().mappings] == ['revoked', 'active']
    with pytest.raises(MappingConflict):
        repo.commit([], used=[one], replacements={})


@pytest.mark.parametrize('payload', ['{bad', '{}', '\ufeff{}'])
def test_corrupt_file_never_becomes_empty(tmp_path, payload):
    repo = repository(tmp_path)
    repo.path.write_text(payload, encoding='utf-8')
    with pytest.raises(MappingStoreError):
        repo.read()
    assert repo.path.read_text(encoding='utf-8') == payload


def test_scope_crlf_and_failed_replace(tmp_path, monkeypatch):
    repo = repository(tmp_path)
    repo.commit([record()], used=[], replacements={})
    original = repo.path.read_text(encoding='utf-8').replace('\n', '\r\n')
    repo.path.write_bytes(original.encode('utf-8'))
    repo.commit([record('其他詞彙', ident='two')], used=[], replacements={})
    assert b'\r\n' in repo.path.read_bytes() and b'\n' not in repo.path.read_bytes().replace(b'\r\n', b'')
    different = JsonTermMappingRepository(repo.path, MappingScope(profile_id='other', datasource_id=None))
    with pytest.raises(MappingStoreError):
        different.read()
    before = repo.path.read_bytes()
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr('cpea.infrastructure.terms_mapping.os.replace', fail)
    with pytest.raises(MappingStoreError):
        repo.commit([record('新詞', ident='three')], used=[], replacements={})
    assert repo.path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [repo.path]


def test_normalization_retains_qualifiers():
    assert normalize_term('  USD含稅發票總額 ') == 'usd含稅發票總額'
    assert normalize_term('未稅發票總額') != normalize_term('含稅發票總額')
