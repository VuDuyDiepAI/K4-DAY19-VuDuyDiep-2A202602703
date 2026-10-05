"""Checkpointing, provenance mapping and local configuration for Lab 19."""
import hashlib
import json
import math
import re
import subprocess
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / 'outputs'
CACHE = OUTPUTS / '.cache'
PROMPT_VERSION = 'lab19-v1'
JUDGE_KEY_NAMES = {'openai': 'OPENAI_API_KEY', 'groq': 'GROQ_API_KEY', 'gemini': 'GEMINI_API_KEY'}
OUTPUTS.mkdir(exist_ok=True)
CACHE.mkdir(exist_ok=True)


def is_configured(value):
    value = str(value or '').strip()
    return bool(value) and not any(x in value for x in ('...', '<your', 'your-'))


def fingerprint(value):
    if isinstance(value, pd.DataFrame):
        value = value.fillna('').to_dict('records')
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     default=str).encode('utf-8')).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    default=str, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def cache_path(stage, payload):
    return CACHE / f'{stage}_{fingerprint(payload)}.json'


def cached_json(stage, payload, callback):
    path = cache_path(stage, payload)
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    value = callback()
    write_json(path, value)
    return value


def prepare_local_neo4j():
    """Recover the local container's own auth, never printing its password."""
    env_path = ROOT / '.env'
    if not env_path.exists():
        env_path.write_text((ROOT / '.env.example').read_text(encoding='utf-8'), encoding='utf-8')
    config = dotenv_values(env_path)
    if is_configured(config.get('NEO4J_URI')) and is_configured(config.get('NEO4J_PASSWORD')):
        return 'Kept configured Neo4j credentials.'
    if is_configured(config.get('NEO4J_URI')) and not any(
            host in str(config['NEO4J_URI']) for host in ('localhost', '127.0.0.1')):
        return 'Configured remote Neo4j URI; set its password manually. Local container auth is not reused.'
    response = subprocess.run(['docker', 'inspect', 'neo4j-drug-kg'],
                              capture_output=True, text=True, check=True)
    container = json.loads(response.stdout)[0]
    variables = dict(item.split('=', 1) for item in container['Config']['Env'] if '=' in item)
    auth = variables.get('NEO4J_AUTH', '')
    if '/' not in auth:
        return 'Container auth unavailable; configure Neo4j in .env.'
    username, password = auth.split('/', 1)
    # Re-read before each write so other keys edited by the learner are preserved.
    for key, value in {'NEO4J_URI': 'bolt://localhost:7687', 'NEO4J_USER': username,
                       'NEO4J_PASSWORD': password, 'NEO4J_DATABASE': 'neo4j'}.items():
        current = dotenv_values(env_path)
        if not is_configured(current.get(key)) or key == 'NEO4J_USER' and not is_configured(config.get('NEO4J_PASSWORD')):
            set_key(str(env_path), key, value)
    return 'Local Neo4j credentials saved in ignored .env; no credentials printed.'


def norm_text(value):
    if value is None or isinstance(value, float) and math.isnan(value):
        return ''
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', str(value))).strip()


def column(df, candidates, required=False):
    lookup = {re.sub(r'[\s_-]+', '', str(c).lower()): c for c in df.columns}
    for name in candidates:
        key = re.sub(r'[\s_-]+', '', name.lower())
        if key in lookup:
            return lookup[key]
    if required:
        raise KeyError(f'Missing a column in {candidates}')
    return None


def source_matches(raw, detailed):
    """Match source identity, not a possibly shifted streaming row number."""
    title_col = column(raw, ['title', 'headline'], required=True)
    date_col = column(raw, ['published_date', 'date', 'published_at', 'created_at', 'timestamp'])
    titles = raw[title_col].fillna('').map(lambda x: norm_text(x).casefold())
    dates = pd.to_datetime(raw[date_col], utc=True, errors='coerce').dt.strftime('%Y-%m-%d') if date_col else pd.Series('', index=raw.index)
    url_columns = [c for c in raw.columns if any(word in str(c).lower() for word in ('url', 'link'))]
    records = []
    for q in detailed.itertuples(index=False):
        row_ids = json.loads(q.evidence_row_ids_0based)
        urls = json.loads(q.evidence_urls_json)
        sources = re.findall(r'row\s+(\d+)\s+\(([^)]+)\):\s*(.*?)(?=\s+\|\s+row\s+\d+|$)', str(q.reference_evidence))
        references = {int(row_id): (date[:10], title.strip()) for row_id, date, title in sources}
        for position, original_row_id in enumerate(row_ids):
            url = urls[position] if position < len(urls) else ''
            expected_date, expected_title = references.get(original_row_id, ('', ''))
            mask = pd.Series(False, index=raw.index)
            if url:
                for field in url_columns:
                    mask |= raw[field].fillna('').astype(str).str.rstrip('/').eq(url.rstrip('/'))
            mode = 'url'
            if not mask.any() and expected_title:
                mask = titles.eq(norm_text(expected_title).casefold())
                if date_col and expected_date:
                    mask &= dates.eq(expected_date)
                mode = 'title_date' if date_col else 'title_only'
            matched = raw.index[mask].tolist()
            records.append({'id': q.id, 'original_row_id': original_row_id,
                            'matched_source_row_ids': json.dumps(matched),
                            'matched': bool(matched), 'match_mode': mode if matched else 'missing',
                            'expected_title': expected_title, 'expected_url': url})
    return pd.DataFrame(records)


def choose_golden(detailed, matches, count=5):
    coverage = matches.groupby('id')['matched'].all()
    eligible = detailed[detailed.id.isin(coverage[coverage].index)].copy()
    selected = []
    for group, quota in [('factoid', 1), ('multi-hop', 2), ('cross-doc', 2)]:
        selected.extend(eligible[eligible.group.eq(group)].sort_values('id').head(quota).id.tolist())
    if len(selected) < 5:
        raise ValueError('Need verified source coverage for 1 factoid, 2 multi-hop and 2 cross-doc questions.')
    selected.extend(eligible[~eligible.id.isin(selected)].sort_values('id').head(max(0, count - 5)).id.tolist())
    result = eligible[eligible.id.isin(selected)].sort_values('id').copy()
    result.to_csv(ROOT / 'data' / 'graphrag_golden_lab.csv', index=False)
    return result


def curated_rows(matches, golden):
    return sorted({row_id for value in matches[matches.id.isin(golden.id)].matched_source_row_ids
                   for row_id in json.loads(value)})


def prepare_corpus(runtime):
    """Freeze a documented coverage-selected demo before any score is observed."""
    raw = runtime.load_news(runtime.DATA_PATH).reset_index(drop=True)
    detailed = pd.read_csv(ROOT / 'data' / 'graphrag_golden_50_first5000_detailed.csv').fillna('')
    matches = source_matches(raw, detailed)
    matches.to_csv(OUTPUTS / 'golden_source_matches.csv', index=False)
    golden = choose_golden(detailed, matches, count=runtime.GOLDEN_COUNT)
    priority_rows = curated_rows(matches, golden)
    news = runtime.standardize_news(raw, priority_rows=priority_rows)
    priority_article_ids = set()
    for row in news.itertuples(index=False):
        if set(json.loads(row.source_row_ids_json)) & set(priority_rows):
            priority_article_ids.add(row.article_id)
    ordered = pd.concat([news[news.article_id.isin(priority_article_ids)],
                         news[~news.article_id.isin(priority_article_ids)]], ignore_index=True)
    chunks = runtime.build_chunks(ordered)
    extraction = chunks.head(runtime.EXTRACTION_TARGET_CHUNKS).copy()
    # Do not put references, expected relations or answers into extraction/chunk inputs.
    rows = []
    for q in golden.itertuples(index=False):
        matched = matches[matches.id.eq(q.id)]
        required = {rid for value in matched.matched_source_row_ids for rid in json.loads(value)}
        def coverage(frame):
            available = {rid for value in frame.source_row_ids_json for rid in json.loads(value)}
            return required <= available
        rows.append({'id': q.id, 'group': q.group, 'corpus_covered': True,
                     'vector_covered': coverage(chunks), 'extraction_covered': coverage(extraction)})
    coverage_df = pd.DataFrame(rows)
    coverage_df.to_csv(OUTPUTS / 'golden_coverage.csv', index=False)
    if not coverage_df.vector_covered.all():
        raise ValueError('Chunk cap removed required Golden sources; adjust sampling before evaluation.')
    chunks.to_csv(OUTPUTS / 'raw_chunks.csv', index=False)
    chunks.drop(columns=['text']).to_csv(OUTPUTS / 'chunk_manifest.csv', index=False)
    corpus_manifest = {
        'sample_policy': 'coverage-selected demonstration using source identity, not answer contents',
        'corpus_fingerprint': fingerprint(raw), 'chunks_fingerprint': fingerprint(chunks),
        'extraction_fingerprint': fingerprint(extraction), 'golden_ids': golden.id.tolist(),
        'priority_source_row_ids': priority_rows, 'article_ids': ordered.article_id.tolist(),
        'extraction_chunk_ids': extraction.chunk_id.tolist(), 'raw_rows': len(raw),
        'articles': len(ordered), 'chunks': len(chunks), 'extraction_chunks': len(extraction),
        'text_kind': pd.read_csv(OUTPUTS / 'preprocessing_stats.csv').iloc[0].text_kind,
        'seed': runtime.SEED, 'frozen_at_utc': datetime.now(timezone.utc).isoformat(),
    }
    runtime.LAB_NAMESPACE = 'day19-' + fingerprint({
        'chunks': corpus_manifest['chunks_fingerprint'],
        'extraction': corpus_manifest['extraction_fingerprint'],
        'model': runtime.GROQ_MODEL,
        'runtime_version': fingerprint((ROOT / 'lab19_runtime.py').read_text(encoding='utf-8-sig')),
    })[:16]
    corpus_manifest['graph_namespace'] = runtime.LAB_NAMESPACE
    write_json(OUTPUTS / 'corpus_manifest.json', corpus_manifest)
    return ordered, chunks, extraction, golden, coverage_df
