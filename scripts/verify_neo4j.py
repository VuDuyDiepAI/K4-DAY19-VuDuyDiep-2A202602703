"""Real Neo4j integration check using a labeled, scoped and cleaned-up fixture."""
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
import lab19_runtime as lab
from lab19_support import write_json

lab.connect_neo4j()
before = lab.run_cypher('MATCH (n) RETURN count(n) AS n')[0]['n']
original_namespace, original_match_seeds = lab.LAB_NAMESPACE, lab.match_seeds
lab.LAB_NAMESPACE = 'day19-test-fixture-' + uuid.uuid4().hex
hub_id = lab.LAB_NAMESPACE + ':hub'
nodes = [{'id': hub_id, 'name': 'LAB19 TEST HUB', 'name_norm': 'lab19 test hub',
          'type': 'Company', 'aliases': [], 'aliases_norm': []}]
triples = []
for i in range(120):
    target_id = f'{lab.LAB_NAMESPACE}:target:{i}'
    nodes.append({'id': target_id, 'name': f'LAB19 TEST TECHNOLOGY {i}',
                  'name_norm': f'lab19 test technology {i}', 'type': 'Technology',
                  'aliases': [], 'aliases_norm': []})
    triples.append({'source_id': hub_id, 'target_id': target_id, 'relation': 'USES',
                    'source_chunk_id': f'fixture::{i}', 'published_date': (datetime(2023, 1, 1) + timedelta(days=i)).date().isoformat(),
                    'evidence': 'Explicit synthetic fixture for integration testing, not a corpus fact.',
                    'confidence': 1.0})
result = {'data_kind': 'synthetic fixture in a real local Neo4j connection', 'status': 'failed'}
try:
    nodes_df, triples_df = pd.DataFrame(nodes), pd.DataFrame(triples)
    lab.bulk_insert_nodes(nodes_df)
    lab.bulk_insert_edges(triples_df)
    lab.bulk_insert_nodes(nodes_df)
    lab.bulk_insert_edges(triples_df)
    count = lab.run_cypher('MATCH ()-[r]->() WHERE r.lab_namespace=$namespace RETURN count(r) AS n')[0]['n']
    assert count == 120, f'Rerun duplicated edges: {count}'
    assert lab.node_degree(hub_id) == 120
    lab.match_seeds = lambda question: [{'id': hub_id, 'name': 'LAB19 TEST HUB', 'type': 'Company'}]
    graph = lab.retrieve_graph_context('Integration fixture', max_hops=2, edge_limit=1000, return_debug=True)
    assert len(graph['edges']) == 50
    expected_dates = {r['published_date'] for r in triples[-50:]}
    assert set(graph['edges'].published_date) == expected_dates
    assert len(graph['context']) <= lab.MAX_GRAPH_CONTEXT_CHARS
    result.update(status='passed', idempotent_edges=count, hub_degree=120,
                  retrieved_edges=len(graph['edges']), retained_newest_50=True,
                  context_chars=len(graph['context']), checked_at_utc=datetime.now(timezone.utc).isoformat())
finally:
    # Only nodes created under the unique namespace above are removed.
    lab.run_cypher('MATCH (n:Lab19 {lab_namespace:$namespace}) DETACH DELETE n')
    after = lab.run_cypher('MATCH (n) RETURN count(n) AS n')[0]['n']
    result.update(nodes_before=before, nodes_after_cleanup=after, fixture_cleaned=(before == after))
    write_json(lab.OUTPUTS / 'neo4j_fixture_verification.json', result)
    lab.LAB_NAMESPACE, lab.match_seeds = original_namespace, original_match_seeds
    lab.driver.close()
assert after == before, 'Fixture cleanup changed existing data.'
print(result)
