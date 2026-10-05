"""Behavioral checks with labeled fixtures, no network calls and no fake benchmark."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import lab19_runtime as lab
import lab19_support as support


@pytest.fixture(autouse=True)
def isolate_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(lab, 'OUTPUTS', tmp_path)
    monkeypatch.setattr(lab, 'CHECKPOINT', tmp_path / 'checkpoint.csv')
    monkeypatch.setattr(support, 'OUTPUTS', tmp_path)
    monkeypatch.setattr(support, 'CACHE', tmp_path / 'cache')
    return tmp_path


def test_unicode_dedup_keeps_all_source_rows():
    text = 'Microsoft invested in OpenAI. ' * 8
    raw = pd.DataFrame({'title': ['ＡＩ news', 'AI news'], 'text': [text, text],
                        'published_date': ['2023-01-01', '2023-01-01'], 'id': ['same', 'same']})
    standardized = lab.standardize_news(raw)
    assert len(standardized) == 1
    assert json.loads(standardized.iloc[0].source_row_ids_json) == [0, 1]
    chunks = lab.build_chunks(standardized)
    assert chunks.chunk_id.is_unique
    assert json.loads(chunks.iloc[0].source_row_ids_json) == [0, 1]


def test_repeated_source_id_does_not_collide():
    raw = pd.DataFrame({'id': ['same', 'same'], 'title': ['A', 'B'],
                        'text': ['Article A. ' * 20, 'Article B. ' * 20]})
    assert lab.standardize_news(raw).article_id.is_unique


def test_hackernoon_schema_keeps_headline_as_evidence():
    raw = pd.DataFrame({'title': ['Microsoft invested in OpenAI'],
                        'description': ['The companies announced a new partnership in January 2023.'],
                        'published_at': ['2023-01-23T12:00:00Z']})
    standardized = lab.standardize_news(raw)
    assert len(standardized) == 1
    assert standardized.iloc[0].text.startswith('Microsoft invested in OpenAI.')
    assert standardized.iloc[0].published_date == '2023-01-23'
    chunks = lab.build_chunks(standardized)
    assert 'Microsoft invested in OpenAI' in chunks.iloc[0].text
    stats = pd.read_csv(lab.OUTPUTS / 'preprocessing_stats.csv')
    assert stats.iloc[0].text_kind == 'title_and_description'


def test_chunk_overlap_and_end():
    words = [f'w{i}' for i in range(401)]
    chunks = lab.chunk_text(' '.join(words), 220, 40)
    assert len(chunks) == 3
    assert chunks[0].split()[-40:] == chunks[1].split()[:40]
    assert chunks[-1].split()[-1] == 'w400'


@pytest.mark.parametrize('size,overlap', [(0, 0), (20, 20), (20, -1)])
def test_invalid_chunk_parameters(size, overlap):
    with pytest.raises(ValueError):
        lab.chunk_text('example', size, overlap)


@pytest.mark.parametrize('left,right,typ,expected', [
    ('Microsoft Corporation', 'Microsoft', 'Company', True),
    ('Sam Altman', 'Steve Altman', 'Person', False),
    ('Apple', 'Apple Watch', 'Technology', False),
    ('Google', 'Google Cloud', 'Company', False),
])
def test_false_merge_guards(left, right, typ, expected):
    assert lab.merge_guard(left, right, typ) is expected


def test_source_row_number_is_not_identity():
    raw = pd.DataFrame({'title': ['Unrelated report', 'Actual source'],
                        'text': ['X', 'Y'], 'published_date': ['2023-01-01', '2023-02-02'],
                        'url': ['https://example.org/wrong', 'https://example.org/right']})
    golden = pd.DataFrame([{'id': 'fixture', 'evidence_row_ids_0based': '[0]',
                            'evidence_urls_json': '["https://example.org/right"]',
                            'reference_evidence': 'row 0 (2023-02-02 00:00:00): Actual source'}])
    matches = support.source_matches(raw, golden)
    assert json.loads(matches.iloc[0].matched_source_row_ids) == [1]
    assert matches.iloc[0].match_mode == 'url'


def test_unknown_source_is_missing():
    raw = pd.DataFrame({'title': ['Wrong'], 'text': ['Wrong'], 'date': ['2023-01-01']})
    golden = pd.DataFrame([{'id': 'fixture', 'evidence_row_ids_0based': '[0]',
                            'evidence_urls_json': '[]',
                            'reference_evidence': 'row 0 (2023-02-02): Actual source'}])
    assert not support.source_matches(raw, golden).iloc[0].matched


def test_coref_rejects_changed_numbers(monkeypatch):
    monkeypatch.setattr(lab, 'groq_json', lambda *a, **k: ({'items': [
        {'chunk_id': 'fixture', 'resolved_text': 'Microsoft invested 20 billion.',
         'unresolved_mentions': []}]}, {}))
    batch = pd.DataFrame([{'chunk_id': 'fixture', 'text': 'Microsoft invested 10 billion.'}])
    result, _ = lab.resolve_coref_batch(batch)
    assert result.iloc[0].resolved_text == batch.iloc[0].text
    assert result.iloc[0].coref_status == 'rejected'


@pytest.mark.parametrize('change', [
    {'confidence': float('nan')}, {'confidence': 1.5}, {'confidence': 'not-a-number'},
    {'evidence': 'Invented evidence.'}, {'relation': 'CONSIDERING'},
])
def test_extraction_rejects_invalid_triples(change, monkeypatch):
    relation = {'source': 'Microsoft', 'source_type': 'Company', 'relation': 'INVESTED_IN',
                'target': 'OpenAI', 'target_type': 'Company', 'confidence': .95,
                'evidence': 'Microsoft invested in OpenAI.'}
    relation.update(change)
    monkeypatch.setattr(lab, 'extract_batch', lambda *a, **k: (
        {'items': [{'chunk_id': 'fixture', 'relations': [relation]}]}, {}))
    source = pd.DataFrame([{'chunk_id': 'fixture', 'published_date': '2023-01-01',
                            'text': 'Microsoft invested in OpenAI.'}])
    triples, errors = lab.run_extraction(source)
    assert triples.empty
    assert not errors.empty


def test_empty_provenance_rejected_before_ingestion(monkeypatch):
    monkeypatch.setattr(lab, 'run_cypher', lambda *a, **k: pytest.fail('Must reject before Cypher'))
    triples = pd.DataFrame([{'source_chunk_id': 'fixture', 'published_date': '',
                             'evidence': 'Evidence', 'confidence': .9, 'relation': 'USES'}])
    with pytest.raises(ValueError, match='Empty edge provenance'):
        lab.bulk_insert_edges(triples)


def edge(i, source='seed', neighbor=None):
    return {'source_id': source, 'target_id': f't{i}', 'relation': 'USES',
            'source_name': source, 'target_name': f't{i}',
            'source_type': 'Company', 'target_type': 'Technology',
            'source_chunk_id': f'fixture::{i}', 'published_date': '2023-01-01',
            'evidence': 'Explicitly labeled test fixture.', 'neighbor_id': neighbor or f't{i}'}


def test_supernode_policy_uses_50_edge_cap(monkeypatch):
    calls = []
    monkeypatch.setattr(lab, 'match_seeds', lambda query: [{'id': 'seed'}])
    monkeypatch.setattr(lab, 'node_degree', lambda node: 101 if node == 'seed' else 0)
    def recent(node, limit):
        calls.append((node, limit))
        return [edge(i) for i in range(min(limit, 101))] if node == 'seed' else []
    monkeypatch.setattr(lab, 'recent_edges', recent)
    result = lab.retrieve_graph_context('fixture', edge_limit=1000, return_debug=True)
    assert calls[0] == ('seed', 50)
    assert len(result['edges']) == 50
    assert result['diagnostics']['supernode_events'][0]['degree'] == 101


def test_global_edge_cap_and_context_cap(monkeypatch):
    monkeypatch.setattr(lab, 'match_seeds', lambda query: [{'id': 'seed'}])
    monkeypatch.setattr(lab, 'node_degree', lambda node: 50)
    monkeypatch.setattr(lab, 'recent_edges', lambda node, limit: [
        edge(f'{node}-{i}', source=node) for i in range(limit)])
    result = lab.retrieve_graph_context('fixture', return_debug=True)
    assert len(result['edges']) == 250
    assert len(result['context']) <= 14000


def test_bfs_does_not_expand_beyond_two_hops(monkeypatch):
    calls = []
    monkeypatch.setattr(lab, 'match_seeds', lambda query: [{'id': 'n0'}])
    monkeypatch.setattr(lab, 'node_degree', lambda node: 1)
    def recent(node, limit):
        calls.append(node)
        return [edge(node, source=node, neighbor=f'n{int(node[1:])+1}')]
    monkeypatch.setattr(lab, 'recent_edges', recent)
    lab.retrieve_graph_context('fixture', max_hops=2)
    assert calls == ['n0', 'n1']


def test_no_seed_returns_explicit_diagnostic(monkeypatch):
    monkeypatch.setattr(lab, 'match_seeds', lambda query: [])
    result = lab.retrieve_graph_context('fixture', return_debug=True)
    assert result['context'] == ''
    assert result['diagnostics']['reason'] == 'NO_SEED'


def test_golden_requires_all_groups_and_unique_ids():
    golden = pd.DataFrame({'id': ['a', 'b', 'c', 'd', 'e'],
                           'group': ['factoid', 'multi-hop', 'multi-hop', 'cross-doc', 'cross-doc'],
                           'question': ['Question'] * 5, 'reference_answer': ['Reference'] * 5})
    assert lab.validate_golden(golden)
    golden.loc[4, 'id'] = 'a'
    with pytest.raises(ValueError, match='unique'):
        lab.validate_golden(golden)


def test_invalid_judge_score_is_not_silently_clamped(monkeypatch):
    monkeypatch.setattr(lab, 'judge_json', lambda *a, **k: {
        'comprehensiveness': 6, 'faithfulness': 3, 'multi_hop_reasoning': 3, 'rationale': 'Fixture'})
    with pytest.raises(ValueError, match='Invalid Judge score'):
        lab.judge_answer('Q', 'R', 'A', 'C')


def test_checkpoints_change_with_payload_and_prompt(tmp_path):
    calls = []
    def compute():
        calls.append(1)
        return {'actual': 'fixture result'}
    support.cached_json('fixture', {'prompt': 'v1'}, compute)
    support.cached_json('fixture', {'prompt': 'v1'}, compute)
    support.cached_json('fixture', {'prompt': 'v2'}, compute)
    assert len(calls) == 2


def test_hybrid_online_tokens_include_seed_and_total_latency(monkeypatch):
    monkeypatch.setattr(lab, 'USAGE_LOG', [])
    def graph(*a, **k):
        lab.USAGE_LOG.append({'total_tokens': 25})
        return {'context': 'Graph fixture', 'diagnostics': {'supernode_events': []}}
    monkeypatch.setattr(lab, 'retrieve_graph_context', graph)
    monkeypatch.setattr(lab, 'retrieve_flat_context', lambda *a, **k: ('Vector fixture', pd.DataFrame()))
    monkeypatch.setattr(lab, 'generate_answer', lambda *a, **k: {'answer': 'Fixture', 'latency_s': 0., 'total_tokens': 100})
    result = lab.answer_graph_rag('Fixture question')
    assert result['online_total_tokens'] == 125
    assert result['seed_extraction_tokens'] == 25
    assert result['latency_s'] == result['end_to_end_latency_s']


def test_placeholders_are_not_credentials():
    assert not support.is_configured('gsk_...')
    assert not support.is_configured('your-neo4j-password')
    assert not support.is_configured('neo4j+s://<your-instance>.databases.neo4j.io')


def evaluation_fixture(tmp_path, monkeypatch):
    support.write_json(tmp_path / 'corpus_manifest.json',
                       {'chunks_fingerprint': 'fixture-v1', 'extraction_fingerprint': 'fixture-v1'})
    golden = pd.DataFrame({'id': ['f1', 'f2', 'f3', 'f4', 'f5'],
                           'group': ['factoid', 'multi-hop', 'multi-hop', 'cross-doc', 'cross-doc'],
                           'question': ['Fixture question'] * 5, 'reference_answer': ['Fixture reference'] * 5})
    calls = []
    def answer(question):
        calls.append(question)
        return {'answer': 'Fixture answer', 'context': 'Fixture context',
                'latency_s': 1.0, 'retrieval_latency_s': .2, 'generation_latency_s': .8,
                'total_tokens': 20, 'online_total_tokens': 25, 'seed_extraction_tokens': 5,
                'graph_debug': {'diagnostics': {'supernode_events': []}}}
    monkeypatch.setattr(lab, 'answer_flat_rag', answer)
    monkeypatch.setattr(lab, 'answer_graph_rag', answer)
    monkeypatch.setattr(lab, 'judge_answer', lambda *a: {
        'comprehensiveness': 3, 'faithfulness': 3, 'multi_hop_reasoning': 3, 'rationale': 'Test fixture'})
    return golden, calls


def test_evaluation_resumes_only_matching_configuration(tmp_path, monkeypatch):
    golden, calls = evaluation_fixture(tmp_path, monkeypatch)
    first = lab.run_evaluation(golden)
    assert len(first) == 5 and len(calls) == 10
    second = lab.run_evaluation(golden)
    assert len(second) == 5 and len(calls) == 10
    support.write_json(tmp_path / 'corpus_manifest.json',
                       {'chunks_fingerprint': 'changed-fixture-v2', 'extraction_fingerprint': 'fixture-v1'})
    changed = lab.run_evaluation(golden)
    assert len(calls) == 20
    assert changed.run_id.iloc[0] != first.run_id.iloc[0]


def test_judge_failure_retains_answers_for_resume(tmp_path, monkeypatch):
    golden, calls = evaluation_fixture(tmp_path, monkeypatch)
    attempted = []
    def judge(*args):
        attempted.append(1)
        if len(attempted) == 1:
            raise RuntimeError('Labeled transient test failure')
        return {'comprehensiveness': 3, 'faithfulness': 3, 'multi_hop_reasoning': 3, 'rationale': 'Test fixture'}
    monkeypatch.setattr(lab, 'judge_answer', judge)
    with pytest.raises(RuntimeError, match='1 Golden queries failed'):
        lab.run_evaluation(golden)
    assert len(calls) == 10
    assert not (tmp_path / 'graphrag_eval_results.csv').exists()
    result = lab.run_evaluation(golden)
    assert len(result) == 5
    assert len(calls) == 10  # No duplicate answer requests after the Judge failure.


def test_entity_ann_candidates_still_obey_guard(monkeypatch):
    class FixtureEmbedder:
        def encode(self, names, **kwargs):
            return np.array([[1., 0.] for _ in names], dtype='float32')
    monkeypatch.setattr(lab, 'get_embedder', lambda: FixtureEmbedder())
    raw = pd.DataFrame([
        {'source_raw': 'Sam Altman', 'source_type': 'Person', 'target_raw': 'OpenAI', 'target_type': 'Company'},
        {'source_raw': 'Steve Altman', 'source_type': 'Person', 'target_raw': 'Microsoft Corp', 'target_type': 'Company'},
    ])
    mapping, audit = lab.build_resolution_map(raw)
    assert mapping[('Person', 'sam altman')] != mapping[('Person', 'steve altman')]
    assert mapping[('Company', 'microsoft corp')] == 'Microsoft'
    assert 'REJECT_GUARD' in set(audit.decision)
    assert 'MERGE_MANUAL' in set(audit.decision)


def test_unknown_node_type_cannot_reach_cypher(monkeypatch):
    monkeypatch.setattr(lab, 'run_cypher', lambda *a, **k: pytest.fail('Must reject before Cypher'))
    with pytest.raises(ValueError, match='Node type outside allowlist'):
        lab.bulk_insert_nodes(pd.DataFrame([{'type': 'InjectedLabel'}]))


@pytest.mark.parametrize('provider,expected_host,key_name', [
    ('gemini', 'generativelanguage.googleapis.com', 'GEMINI_API_KEY'),
    ('openai', 'api.openai.com', 'OPENAI_API_KEY'),
])
def test_judge_routes_to_selected_provider_with_its_key(monkeypatch, provider, expected_host, key_name):
    import httpx
    import openai
    monkeypatch.delenv('OPENAI_BASE_URL', raising=False)
    monkeypatch.setattr(lab, 'JUDGE_PROVIDER', provider)
    monkeypatch.setattr(lab, 'JUDGE_MODEL', 'gemini-2.5-flash' if provider == 'gemini' else 'gpt-4o-mini')
    monkeypatch.setattr(lab, 'GEMINI_API_KEY', 'fixture-gemini-key')
    monkeypatch.setattr(lab, 'OPENAI_API_KEY', 'fixture-openai-key')
    monkeypatch.setattr(lab, 'USAGE_LOG', [])
    scores = {'comprehensiveness': 3, 'faithfulness': 4, 'multi_hop_reasoning': 2,
              'rationale': 'Labeled HTTP fixture, not a benchmark.'}
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={
            'id': 'fixture', 'object': 'chat.completion', 'created': 0, 'model': lab.JUDGE_MODEL,
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': json.dumps(scores)},
                         'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30},
        })
    original_client = openai.OpenAI
    monkeypatch.setattr(openai, 'OpenAI', lambda **kwargs: original_client(
        **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(respond))))
    assert lab.judge_answer('Fixture Q', 'Fixture reference', 'Fixture answer', 'Fixture context') == scores
    assert requests[0].url.host == expected_host
    assert requests[0].headers['authorization'] == f'Bearer {getattr(lab, key_name)}'
    payload = json.loads(requests[0].content)
    assert payload['model'] == lab.JUDGE_MODEL
    if provider == 'gemini':
        assert requests[0].url.path == '/v1beta/openai/chat/completions'
        assert payload['response_format']['type'] == 'json_schema'
        assert set(payload['response_format']['json_schema']['schema']['required']) == set(scores)
    assert lab.USAGE_LOG == [{'provider': provider, 'model': lab.JUDGE_MODEL, 'purpose': 'judge',
                              'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30}]


@pytest.mark.parametrize('key', ['', 'your-gemini-api-key'])
def test_missing_gemini_key_does_not_fall_back_to_other_credentials(monkeypatch, key):
    import openai
    monkeypatch.setattr(lab, 'JUDGE_PROVIDER', 'gemini')
    monkeypatch.setattr(lab, 'JUDGE_MODEL', 'gemini-2.5-flash')
    monkeypatch.setattr(lab, 'GEMINI_API_KEY', key)
    monkeypatch.setattr(lab, 'GROQ_API_KEY', 'fixture-groq-key')
    monkeypatch.setattr(lab, 'OPENAI_API_KEY', 'fixture-openai-key')
    monkeypatch.setattr(openai, 'OpenAI', lambda **kwargs: pytest.fail('Missing key must block the request'))
    with pytest.raises(RuntimeError, match='GEMINI_API_KEY'):
        lab.judge_json('JSON only', 'Fixture')


@pytest.mark.parametrize('provider,key_name', [('gemini', 'GEMINI_API_KEY'), ('groq', 'GROQ_API_KEY')])
def test_preflight_requires_the_selected_judge_key(tmp_path, monkeypatch, provider, key_name):
    monkeypatch.setattr(lab, 'JUDGE_PROVIDER', provider)
    monkeypatch.setattr(lab, 'GEMINI_API_KEY', '')
    monkeypatch.setattr(lab, 'OPENAI_API_KEY', '')
    monkeypatch.setattr(lab, 'GROQ_API_KEY', 'fixture-groq-key')
    monkeypatch.setattr(lab, 'connect_neo4j', lambda: None)
    monkeypatch.setattr(lab, 'setup_graph_schema', lambda: None)
    monkeypatch.setattr(lab, 'run_cypher', lambda *args, **kwargs: [{'ok': 1, 'nodes': 0}])
    status = lab.preflight(check_llm=False).set_index('check')
    assert 'OPENAI_API_KEY' not in status.index
    assert status.loc[key_name, 'status'] == ('missing_or_placeholder' if provider == 'gemini' else 'configured')


def test_gemini_key_is_redacted_from_errors(monkeypatch):
    monkeypatch.setattr(lab, 'LOCAL_CONFIG', {'GEMINI_API_KEY': 'fixture-secret-local'})
    monkeypatch.setenv('GEMINI_API_KEY', 'fixture-secret-env')
    message = lab.safe_error(RuntimeError('fixture-secret-local / fixture-secret-env'))
    assert message == 'RuntimeError: [REDACTED] / [REDACTED]'
