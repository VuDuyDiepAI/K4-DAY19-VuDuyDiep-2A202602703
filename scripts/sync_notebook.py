"""Wire the supplied notebook to the tested runtime, preserving its markdown/metadata."""
import json
import sys
from pathlib import Path
import textwrap
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--markdown-only', action='store_true')
parser.add_argument('--cell', type=int, action='append', help='Update only selected code cells; preserve other outputs.')
args = parser.parse_args()

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / 'Day19_GraphRAG_vs_FlatRAG_Production_Lab_Guide.ipynb'
notebook = json.loads(path.read_text(encoding='utf-8-sig'))
sources = {
4: '''
# 1.1 — Local environment: install only when recreating .venv
import sys, importlib.util
required_modules = ['neo4j', 'pandas', 'numpy', 'sentence_transformers', 'faiss', 'groq', 'openai', 'dotenv']
missing_modules = [name for name in required_modules if importlib.util.find_spec(name) is None]
print('Kernel:', sys.executable)
print('Missing modules:', missing_modules)
if missing_modules:
    raise RuntimeError('Install requirements.txt plus jupyterlab/ipykernel in this kernel environment.')
''',
5: '''
# 1.2 — Imports, .env and Windows paths
import importlib
import pandas as pd
from IPython.display import display
import lab19_runtime as lab
import lab19_support as support
lab = importlib.reload(lab)  # Re-read .env after editing keys; no secrets are displayed.
print('Repo:', lab.ROOT)
print('Scale guard:', lab.LAB_MAX_ARTICLES, lab.LAB_MAX_CHUNKS, lab.EXTRACTION_MAX_CHUNKS)
print('Runtime implementation: lab19_runtime.py; workflow: WORKFLOW.md')
data_ready = graph_ready = retrieval_ready = False
eval_results_df = None
''',
7: '''
# 1.3 — Use an existing corpus; gated download requires a configured HF_TOKEN
if lab.DATA_PATH.exists():
    print('Using corpus:', lab.DATA_PATH)
elif lab.HF_TOKEN:
    import subprocess
    subprocess.run([sys.executable, str(lab.ROOT / 'scripts/download_corpus.py')], check=True)
else:
    print('PENDING W1: add the original corpus at data/hackernoon_subset.csv, or configure HF_TOKEN.')
''',
8: '''
# 1.4 — Driver, schema, secret status and minimal provider probes
preflight_df = lab.preflight(check_llm=True)
display(preflight_df)
neo4j_ready = preflight_df.loc[preflight_df.check.eq('neo4j_driver'), 'status'].eq('passed').all()
llm_ready = not preflight_df.status.isin(['missing_or_placeholder', 'failed']).any()
print('Neo4j ready:', neo4j_ready, '| LLM ready:', llm_ready)
''',
9: '''
# 1.5 — Dedup, source identity, coverage-selected sample and chunks
if lab.DATA_PATH.exists():
    try:
        news_df, chunks_df, extraction_source, golden_df, golden_coverage_df = support.prepare_corpus(lab)
        data_ready = True
        display(chunks_df.head())
        display(golden_coverage_df)
        print('Selected articles/chunks/extraction:', len(news_df), len(chunks_df), len(extraction_source))
    except Exception as error:
        print('PENDING W1/W2:', lab.safe_error(error))
else:
    print('PENDING W1/W2: corpus is missing; no synthetic corpus is substituted.')
''',
11: '''
# 1.6 — Retry/JSON implementation and provider configuration
from lab19_runtime import groq_chat, groq_json, parse_json_object
print('Generator model:', lab.GROQ_MODEL, '| Judge:', lab.JUDGE_PROVIDER, lab.JUDGE_MODEL)
print('Credentials are read from .env/Colab Secrets and never printed.')
''',
13: '''
# 1.7 — Conservative coreference with per-batch checkpoints and numeric guard
if data_ready and llm_ready:
    coref_df = lab.run_coref(extraction_source)
    extraction_source = extraction_source.merge(coref_df, on='chunk_id', validate='one_to_one')
    display(coref_df.head())
    display(coref_df.coref_status.value_counts())
else:
    print('PENDING W2: coreference requires the corpus and configured LLM.')
''',
15: '''
# 2.1 — Schema-checked triples; evidence must be copied from original text
if data_ready and llm_ready:
    raw_triples_df, extraction_errors_df = lab.run_extraction(extraction_source)
    display(raw_triples_df.head())
    display(extraction_errors_df.head())
    print('Valid triples:', len(raw_triples_df), '| errors/rejections:', len(extraction_errors_df))
else:
    raw_triples_df = pd.DataFrame()
    print('PENDING W3: NER/RE has not run.')
''',
17: '''
# 2.2 — Alias → normalized HNSW candidates → lexical/type guard → Union-Find
if not raw_triples_df.empty:
    entity_map, entity_resolution_audit_df = lab.build_resolution_map(raw_triples_df, threshold=0.90)
    triples_df = lab.canonicalize_triples(raw_triples_df, entity_map)
    display(entity_resolution_audit_df.head(20))
    print('Audit rows:', len(entity_resolution_audit_df))
else:
    print('PENDING W3: no extracted triples to resolve.')
''',
18: '''
# 2.3 — Bulk UNWIND; nodes and relationships are scoped to LAB_NAMESPACE
if not raw_triples_df.empty and neo4j_ready:
    nodes_df = lab.build_nodes(triples_df)
    lab.bulk_insert_nodes(nodes_df)
    lab.bulk_insert_edges(triples_df)
    graph_ready = True
    print('Ingested nodes/triples:', len(nodes_df), len(triples_df))
else:
    print('PENDING W3: ingestion has not run.')
''',
19: '''
# 2.4 — Includes NULL, empty-string provenance and a real top-degree table
if graph_ready:
    graph_counts, top_degree_df = lab.graph_checks()
else:
    print('PENDING W3: graph integrity has not been measured.')
''',
21: '''
# 3.1 — Flat RAG index over the same corpus chunks
if data_ready:
    lab.build_flat_index(chunks_df)
    print('Flat baseline ready; top-k = 6.')
else:
    print('PENDING W4: Flat index requires corpus chunks.')
''',
23: '''
# 3.2 — Seed resolution: exact aliases then embedding fallback 0.66
if graph_ready:
    lab.build_entity_matcher(nodes_df)
    retrieval_ready = True
else:
    print('PENDING W4: entity matcher requires canonical graph nodes.')
''',
24: '''
# 3.3 — Policy is tested offline separately from real-data graph measurements
print({'hops': 2, 'degree_threshold': lab.SUPER_NODE_DEGREE,
       'supernode_edge_cap': lab.SUPER_NODE_EDGE_CAP, 'global_edge_cap': lab.GLOBAL_EDGE_CAP,
       'graph_context_chars': lab.MAX_GRAPH_CONTEXT_CHARS})
print('Behavioral regression tests: python -m pytest tests/test_base.py -q')
''',
25: '''
# 3.4 — Smoke answers. Golden references are not passed to either generator.
if retrieval_ready and llm_ready:
    smoke_question = golden_df.iloc[0].question
    smoke_answers = support.cached_json('smoke', {
        'version': support.PROMPT_VERSION, 'question': smoke_question,
        'corpus': support.fingerprint(chunks_df), 'model': lab.GROQ_MODEL,
        'reasoning_effort': lab.GROQ_REASONING_EFFORT, 'namespace': lab.LAB_NAMESPACE},
        lambda: {'flat': lab.answer_flat_rag(smoke_question)['answer'],
                 'graph': lab.answer_graph_rag(smoke_question)['answer']})
    display(smoke_answers)
else:
    print('PENDING W4: real answers have not been generated.')
''',
27: '''
# 4.1 — Verify the selected Golden; original CSV names do not imply 50 records
original_golden = pd.read_csv(lab.ROOT / 'data/graphrag_golden_50_first5000_detailed.csv')
print('Available Golden records:', len(original_golden))
display(original_golden.group.value_counts())
if data_ready:
    lab.validate_golden(golden_df)
    display(golden_df[['id', 'group', 'question']])
else:
    print('PENDING W1/W5: source coverage must be verified before choosing final Golden queries.')
''',
28: '''
# 4.2 — Judge uses the full candidate context and validates integer scores 1–5
from lab19_runtime import judge_answer, judge_json, validate_golden
print('Judge provider:', lab.JUDGE_PROVIDER, '| Model:', lab.JUDGE_MODEL)
print('Judge configured:', bool(lab.JUDGE_MODEL and lab.JUDGE_PROVIDER in lab.JUDGE_KEY_NAMES
                                and support.is_configured(lab.judge_credentials()[1])))
''',
29: '''
# 4.3 — Resume by run fingerprint/query ID; cache answers before Judge calls
if retrieval_ready and llm_ready:
    eval_results_df = lab.run_evaluation(golden_df)
    display(eval_results_df)
else:
    print('PENDING W5: evaluation has not run; no scores/tokens/latency are fabricated.')
''',
30: '''
# 4.4 — Export comparison by group + ALL with deltas and sample counts
if eval_results_df is not None:
    comparison_df = lab.comparison_table(eval_results_df)
    comparison_df.to_csv(lab.OUTPUTS / 'graphrag_vs_flatrag_summary.csv', index=False)
    display(comparison_df)
    from lab19_reporting import generate_reports
    generate_reports(lab, eval_results_df, comparison_df)
else:
    print('PENDING W5/W6: required benchmark CSVs await real evaluation.')
''',
32: '''
# 5.1 — Report whether the actual graph exercises the supernode branch
if graph_ready:
    supernode_status = lab.test_supernode_policy()
    support.write_json(lab.OUTPUTS / 'supernode_status.json', supernode_status)
    lab.show_resolution_audit(entity_resolution_audit_df)
else:
    print('Real-data supernode and entity audit are pending; fixtures are covered by pytest.')
''',
35: '''
# Bonus — Community ID alone does not meet the global-search bonus requirements
from lab19_runtime import build_communities
print('Optional scaffold only. Complete community reports/querying and quantify before claiming bonus.')
''',
36: '''
# Bonus — Bounded hop2 → hop3 → vector fallback; enable after the core benchmark
from lab19_runtime import self_correcting_context, context_sufficient
print('Optional scaffold only. Compare quality/latency/tokens before claiming bonus.')
''',
}
for number, source in ({} if args.markdown_only else sources).items():
    if args.cell and number not in args.cell:
        continue
    cell = notebook['cells'][number - 1]
    if cell['cell_type'] != 'code':
        raise ValueError(f'Notebook cell {number} changed type; review before syncing.')
    cell['source'] = textwrap.dedent(source).strip().splitlines(keepends=True)
    cell['execution_count'] = None
    cell['outputs'] = []
notebook['cells'][0]['source'] = ''.join(notebook['cells'][0]['source']).split('\n\n**Bản triển khai local:**')[0].replace(
    '**Môi trường:** Google Colab (T4 GPU khuyến nghị) + Neo4j AuraDB',
    '**Môi trường:** Windows + `.venv` + JupyterLab + Neo4j Docker; cũng hỗ trợ Colab khi có runtime files'
).splitlines(keepends=True)
notebook['cells'][0]['source'].extend(['\n\n**Bản triển khai local:** [WORKFLOW.md](WORKFLOW.md), ',
    '[lab19_runtime.py](lab19_runtime.py), [tests/test_base.py](tests/test_base.py).\n',
    'Cell in PENDING khi thiếu dữ liệu/secrets; trạng thái này không có nghĩa pipeline đã hoàn thành.\n'])
markdown = {
3: '''# PHẦN 1 — SETUP & PREPROCESSING

### Local Windows
Secrets được nạp từ `.env` bằng `python-dotenv`; không in hoặc commit secrets.
Neo4j local dùng `bolt://localhost:7687`. Dataset, checkpoint và exports dùng đường dẫn trong repo.
Cấu hình Groq cho extraction/generation; Judge dùng OpenAI, Groq hoặc Gemini theo `JUDGE_PROVIDER`.
Mặc định dùng `JUDGE_PROVIDER=groq` và model Groq phù hợp; pipeline/Judge dùng chung `GROQ_API_KEY`.
Trong Colab, cần có các file runtime/support và có thể dùng Colab Secrets.
''',
6: '''## 1.3 — Corpus nguồn và streaming có giới hạn

Ưu tiên bản `hackernoon_subset.csv` gốc để đối chiếu Golden. Script `scripts/download_corpus.py`
stream tối đa 5.000 dòng/300 MiB từ Hugging Face; dataset có gated access nên cần `HF_TOKEN` hợp lệ.
Tải lại không bảo đảm thứ tự row giống bản Golden: pipeline khớp URL hoặc title/date trước khi sample.
Giữ scale guard 1.500 articles/3.000 chunks/400 extraction chunks cho phần xử lý.
''',
26: '''# PHẦN 4 — GOLDEN DATASET & LLM-AS-A-JUDGE

Repo có 25 câu thực tế trong các CSV mang tên `golden_50`. Bản detailed chứa nguồn và reference answers.
Pipeline mặc định chọn 5 câu có nguồn đã xác minh: 1 factoid, 2 multi-hop, 2 cross-doc.
`outputs/golden_coverage.csv` phân biệt độ phủ corpus, vector và extraction.
Reference answers chỉ đưa cho Judge; không đưa vào retrieval, extraction hoặc generator.
Latency chính đo retrieval + generation; token online GraphRAG gồm seed extraction + generation.
''',
}
for number, source in markdown.items():
    notebook['cells'][number - 1]['source'] = source.splitlines(keepends=True)
notebook['cells'][36]['source'] = ['# Rubric áp dụng và trạng thái bài nộp\n',
    '\nTheo `RUBRIC.md`: Pipeline 40đ, Failure modes 20đ, Evaluation 20đ, Technical defense/Reflection 20đ.\n',
    '\nChỉ đánh dấu hoàn thành sau khi chạy thật. Xem `WORKFLOW.md` và `reports/execution_status.md` ',
    'để theo dõi việc đã kiểm tra và những bước còn chờ dữ liệu/secrets.\n']
path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
print('Notebook synced; metadata and section order preserved; markdown-only:', '--markdown-only' in sys.argv)
