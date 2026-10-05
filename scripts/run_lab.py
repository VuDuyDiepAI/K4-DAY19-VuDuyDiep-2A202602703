"""CLI equivalent of the notebook orchestration; safe to resume after configuration."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(ROOT))
from lab19_support import prepare_local_neo4j, prepare_corpus, write_json

parser = argparse.ArgumentParser()
parser.add_argument('--stage', choices=['preflight', 'prepare', 'run'], default='run')
parser.add_argument('--configure-local', action='store_true')
parser.add_argument('--skip-api-probe', action='store_true')
args = parser.parse_args()
if args.configure_local:
    print(prepare_local_neo4j())

import lab19_runtime as lab
status = lab.preflight(check_llm=not args.skip_api_probe)
print(status.to_string(index=False))
if args.stage == 'preflight':
    sys.exit(0 if status[status.check.eq('neo4j_driver')].status.eq('passed').all() else 1)
if not lab.DATA_PATH.exists():
    sys.exit('Corpus missing: place it at data/hackernoon_subset.csv or configure HF_TOKEN and run scripts/download_corpus.py.')

news_df, chunks_df, extraction_source, golden_df, coverage = prepare_corpus(lab)
print(coverage.to_string(index=False))
if args.stage == 'prepare':
    sys.exit(0)
if status.status.isin(['missing_or_placeholder', 'failed']).any():
    sys.exit('Preflight incomplete. Fill .env; see outputs/preflight_status.csv. No benchmark was fabricated.')

coref_df = lab.run_coref(extraction_source)
extraction_source = extraction_source.merge(coref_df, on='chunk_id', validate='one_to_one')
raw_triples_df, extraction_errors_df = lab.run_extraction(extraction_source)
if raw_triples_df.empty:
    sys.exit('No valid triples extracted; see outputs/extraction_errors.csv.')
entity_map, audit_df = lab.build_resolution_map(raw_triples_df)
triples_df = lab.canonicalize_triples(raw_triples_df, entity_map)
nodes_df = lab.build_nodes(triples_df)
lab.bulk_insert_nodes(nodes_df)
lab.bulk_insert_edges(triples_df)
graph_counts, top = lab.graph_checks()
lab.build_flat_index(chunks_df)
lab.build_entity_matcher(nodes_df)
write_json(lab.OUTPUTS / 'supernode_status.json', lab.test_supernode_policy())
evaluation_df = lab.run_evaluation(golden_df)
summary_df = lab.comparison_table(evaluation_df)
summary_df.to_csv(lab.OUTPUTS / 'graphrag_vs_flatrag_summary.csv', index=False)
from lab19_reporting import generate_reports
generate_reports(lab, evaluation_df, summary_df)
write_json(lab.OUTPUTS / 'execution_status.json', {
    'pipeline': 'completed', 'golden_queries': len(evaluation_df),
    'graph_counts': graph_counts, 'audit_rows': len(audit_df),
    'coref_failed_chunks': int(coref_df.coref_status.eq('failed').sum()),
    'extraction_rejections_or_errors': len(extraction_errors_df),
    'rerun_and_personal_reflection_review': 'required before final submission',
})
lab.driver.close()
print('Pipeline and reports exported. Review the actual failure cases and personal reflection before submission.')
