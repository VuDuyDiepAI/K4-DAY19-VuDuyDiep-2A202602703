"""Lab 19 runtime; notebook cells call these functions in section order."""
from IPython.display import display
from dotenv import load_dotenv, dotenv_values
from lab19_support import (ROOT, OUTPUTS, PROMPT_VERSION, is_configured, fingerprint,
                           write_json, cached_json, norm_text, column, JUDGE_KEY_NAMES)
import logging
import math
from datetime import datetime, timezone

# SECTION 5
#@title 1.2 — Imports & config
import os, re, json, time, random, hashlib, unicodedata
from pathlib import Path
from collections import defaultdict, Counter, deque
from difflib import SequenceMatcher

import numpy as np
import pandas as pd
from tqdm.auto import tqdm
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer
import faiss

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
pd.set_option("display.max_colwidth", 120)
load_dotenv(ROOT / '.env')
LOCAL_CONFIG = dotenv_values(ROOT / '.env')
USAGE_LOG = []
LAB_NAMESPACE = 'day19-tech-news-v1'
GOLDEN_COUNT = int(os.getenv('LAB_GOLDEN_COUNT', '5'))


def safe_error(error):
    message = str(error)
    for name in ['NEO4J_PASSWORD', 'GROQ_API_KEY', 'OPENAI_API_KEY', 'GEMINI_API_KEY', 'HF_TOKEN']:
        for value in (os.getenv(name, ''), LOCAL_CONFIG.get(name, '')):
            if value:
                message = message.replace(value, '[REDACTED]')
    return f'{type(error).__name__}: {message[:600]}'

def get_secret(name, default=None):
    try:
        from google.colab import userdata
        value = userdata.get(name)
        if value is not None:
            return value
    except Exception:
        pass
    value = LOCAL_CONFIG.get(name)
    if not is_configured(value):
        value = os.environ.get(name, default)
    return value if is_configured(value) else default

NEO4J_URI = get_secret("NEO4J_URI", "")
NEO4J_USER = get_secret("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = get_secret("NEO4J_PASSWORD", "")
NEO4J_DATABASE = get_secret("NEO4J_DATABASE", "neo4j")

GROQ_API_KEY = get_secret("GROQ_API_KEY", "")
GROQ_MODEL = get_secret("GROQ_MODEL", "")
GROQ_REASONING_EFFORT = get_secret('GROQ_REASONING_EFFORT', 'low')

JUDGE_PROVIDER = get_secret("JUDGE_PROVIDER", "groq").lower()
JUDGE_MODEL = get_secret("JUDGE_MODEL", "")
OPENAI_API_KEY = get_secret("OPENAI_API_KEY", "")
GEMINI_API_KEY = get_secret("GEMINI_API_KEY", "")
HF_TOKEN = get_secret("HF_TOKEN", "")

DATA_PATH = Path(os.getenv('LAB_DATA_PATH', str(ROOT / 'data' / 'hackernoon_subset.csv')))
GOLDEN_PATH = ROOT / 'data' / 'graphrag_golden_lab.csv'
CHECKPOINT = OUTPUTS / 'graphrag_eval_checkpoint.csv'
LAB_MAX_ARTICLES = 1500
LAB_MAX_CHUNKS = 3000
EXTRACTION_MAX_CHUNKS = 400
EXTRACTION_TARGET_CHUNKS = int(get_secret('LAB_EXTRACTION_CHUNKS', EXTRACTION_MAX_CHUNKS))
COREF_BATCH_SIZE = int(get_secret('LAB_COREF_BATCH_SIZE', 5))
EXTRACTION_BATCH_SIZE = int(get_secret('LAB_EXTRACTION_BATCH_SIZE', 4))
if not 1 <= EXTRACTION_TARGET_CHUNKS <= EXTRACTION_MAX_CHUNKS:
    raise ValueError('LAB_EXTRACTION_CHUNKS must be between 1 and 400.')
if not 1 <= COREF_BATCH_SIZE <= 16 or not 1 <= EXTRACTION_BATCH_SIZE <= 16:
    raise ValueError('LLM batch sizes must be between 1 and 16.')
CHUNK_WORDS = 220
CHUNK_OVERLAP_WORDS = 40

# SECTION 8
#@title 1.4 — Neo4j connection + schema
driver = None

def connect_neo4j():
    global driver
    if not NEO4J_URI or not NEO4J_PASSWORD:
        raise ValueError("Thiếu Neo4j secrets.")
    driver = GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD),
    )
    driver.verify_connectivity()
    print('Neo4j connected.')

def run_cypher(query, **params):
    if driver is None:
        raise RuntimeError("Hãy chạy connect_neo4j() trước.")
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(query, namespace=LAB_NAMESPACE, **params)
        rows = [r.data() for r in result]
        result.consume()
    return rows

def setup_graph_schema():
    for stmt in [
        """
        CREATE CONSTRAINT entity_id IF NOT EXISTS
        FOR (n:Entity) REQUIRE n.id IS UNIQUE
        """,
        """
        CREATE INDEX entity_name_norm IF NOT EXISTS
        FOR (n:Entity) ON (n.name_norm)
        """,
        """
        CREATE INDEX company_name_norm IF NOT EXISTS
        FOR (n:Company) ON (n.name_norm)
        """,
        """
        CREATE INDEX person_name_norm IF NOT EXISTS
        FOR (n:Person) ON (n.name_norm)
        """,
        """
        CREATE INDEX technology_name_norm IF NOT EXISTS
        FOR (n:Technology) ON (n.name_norm)
        """,
    ]:
        run_cypher(stmt)
    print('Schema ready.')

# connect_neo4j()
# setup_graph_schema()

# SECTION 9
#@title 1.5 — Loader + exact dedup + chunking
def norm_space(x):
    return norm_text(x)

def sha1(x):
    return hashlib.sha1(str(x).encode("utf-8", errors="ignore")).hexdigest()

def pick_col(df, candidates, required=True):
    return column(df, candidates, required=required)

def load_news(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        return pd.read_json(path, lines=True)
    if path.suffix.lower() == ".json":
        return pd.read_json(path)
    if path.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported: {path.suffix}")

def standardize_news(raw, priority_rows=None):
    text_col = pick_col(raw, ["text", "content", "article", "body", "story"], required=False)
    description_col = pick_col(raw, ['description', 'summary', 'snippet'], required=False)
    if not text_col and not description_col:
        raise KeyError('Corpus needs article text or a description/summary/snippet column.')
    title_col = pick_col(raw, ["title", "headline"], required=False)
    date_col = pick_col(raw, ["published_date", "date", "published_at", "created_at", "timestamp"], required=False)
    id_col = pick_col(raw, ["id", "article_id", "story_id", "uuid"], required=False)

    df = pd.DataFrame()
    df['source_row_id'] = range(len(raw))
    df["title"] = raw[title_col].fillna("").map(norm_space) if title_col else ""
    if text_col:
        df['text'] = raw[text_col].fillna('').map(norm_space)
        text_kind = 'article_text'
    else:
        # HackerNoon's published CSV contains headlines and short descriptions.
        # Retain the title as evidence instead of inventing an article body.
        descriptions = raw[description_col].fillna('').map(norm_space)
        df['text'] = [norm_space(f'{title}. {description}') if description else title
                      for title, description in zip(df['title'], descriptions)]
        text_kind = 'title_and_description'

    if date_col:
        df["published_date"] = (
            pd.to_datetime(raw[date_col], errors="coerce", utc=True)
            .dt.strftime("%Y-%m-%d")
            .fillna("")
        )
    else:
        df["published_date"] = ""

    df['source_article_id'] = raw[id_col].fillna('').astype(str) if id_col else ''
    # Source IDs can repeat; content-based IDs remain unique and stable.
    df["article_id"] = [sha1(f"{t}\n{x}")[:20] for t, x in zip(df["title"], df["text"])]

    df = df[df["text"].str.len() >= 80].copy()
    df["dedup_key"] = [
        sha1(norm_space(f"{t}\n{x}").lower())
        for t, x in zip(df["title"], df["text"])
    ]
    before = len(df)
    provenance = df.groupby('dedup_key')['source_row_id'].agg(list).to_dict()
    df['source_row_ids_json'] = df.dedup_key.map(lambda key: json.dumps(provenance[key]))
    priority = set(priority_rows or [])
    df['priority'] = df.dedup_key.map(lambda key: bool(priority & set(provenance[key])))
    df = df.drop_duplicates("dedup_key").drop(columns="dedup_key").reset_index(drop=True)
    print(f"Exact dedup: {before:,} -> {len(df):,}")

    if LAB_MAX_ARTICLES and len(df) > LAB_MAX_ARTICLES:
        keep = df[df.priority]
        if len(keep) > LAB_MAX_ARTICLES:
            raise ValueError('Required sources exceed LAB_MAX_ARTICLES.')
        rest = df[~df.priority].sample(LAB_MAX_ARTICLES - len(keep), random_state=SEED)
        df = pd.concat([keep, rest]).sort_index().reset_index(drop=True)
    pd.DataFrame([{'raw_rows': len(raw), 'nonempty_rows': before, 'deduped_rows': len(provenance),
                   'selected_articles': len(df), 'missing_dates': int(df.published_date.eq('').sum()),
                   'text_kind': text_kind}]).to_csv(
        OUTPUTS / 'preprocessing_stats.csv', index=False)
    return df.drop(columns='priority')

def chunk_text(text, size=220, overlap=40):
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError('Chunk size must be positive and 0 <= overlap < size.')
    words = norm_space(text).split()
    step = max(1, size - overlap)
    out = []
    for start in range(0, len(words), step):
        part = words[start:start+size]
        if not part:
            break
        out.append(" ".join(part))
        if start + size >= len(words):
            break
    return out

def build_chunks(news_df):
    rows = []
    for r in tqdm(news_df.itertuples(index=False), total=len(news_df), desc="Chunking"):
        for i, text in enumerate(chunk_text(r.text, CHUNK_WORDS, CHUNK_OVERLAP_WORDS)):
            rows.append({
                "chunk_id": f"{r.article_id}::c{i:04d}",
                "article_id": r.article_id,
                "source_row_ids_json": getattr(r, 'source_row_ids_json', '[]'),
                "title": r.title,
                "published_date": r.published_date,
                "text": text,
            })
            if LAB_MAX_CHUNKS and len(rows) >= LAB_MAX_CHUNKS:
                return pd.DataFrame(rows)
    return pd.DataFrame(rows)

# raw_df = load_news(DATA_PATH)
# news_df = standardize_news(raw_df)
# chunks_df = build_chunks(news_df)
# display(chunks_df.head())

# SECTION 11
#@title 1.6 — LLM wrapper có retry + JSON parsing
from groq import Groq
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

def parse_json_object(text):
    text = str(text).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("No JSON object found.")
    return json.loads(text[a:b+1])

def groq_chat(messages, model=None, json_mode=False, max_retries=4, purpose='generation'):
    if groq_client is None:
        raise RuntimeError("Thiếu GROQ_API_KEY.")
    model = model or GROQ_MODEL
    if not model:
        raise RuntimeError("Thiếu GROQ_MODEL.")

    last = None
    for attempt in range(max_retries):
        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": 0.0,
                'timeout': 60.0,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            if model.startswith('openai/gpt-oss-'):
                kwargs['reasoning_effort'] = GROQ_REASONING_EFFORT

            resp = groq_client.chat.completions.create(**kwargs)
            usage = {}
            if getattr(resp, "usage", None):
                usage = {
                    "prompt_tokens": getattr(resp.usage, "prompt_tokens", None),
                    "completion_tokens": getattr(resp.usage, "completion_tokens", None),
                    "total_tokens": getattr(resp.usage, "total_tokens", None),
                }
            USAGE_LOG.append({'provider': 'groq', 'model': model, 'purpose': purpose, **usage})
            return resp.choices[0].message.content, usage
        except Exception as e:
            last = e
            if attempt == max_retries - 1 or getattr(e, 'status_code', None) in (400, 401, 403, 404):
                break
            time.sleep(min(20, 2**attempt + random.random()))
    raise RuntimeError(safe_error(last))

def groq_json(system, user, model=None, purpose='structured'):
    text, usage = groq_chat(
        [{"role": "system", "content": system},
         {"role": "user", "content": user}],
        model=model,
        json_mode=True,
        purpose=purpose,
    )
    return parse_json_object(text), usage

# SECTION 13
#@title 1.7 — Coreference resolution theo batch
COREF_SYSTEM = """
You are a conservative coreference-resolution component for a knowledge-graph pipeline.
Resolve pronouns and generic references only when the antecedent is clearly supported in the same chunk.
Never invent facts. Preserve dates, numbers, tickers and product names.
Return strict JSON only.
""".strip()

def resolve_coref_batch(batch_df):
    payload = [{"chunk_id": r.chunk_id, "text": r.text}
               for r in batch_df.itertuples(index=False)]

    prompt = f"""
Resolve coreferences.

Return:
{{
  "items": [
    {{
      "chunk_id": "...",
      "resolved_text": "...",
      "unresolved_mentions": ["..."]
    }}
  ]
}}

INPUT:
{json.dumps(payload, ensure_ascii=False)}
""".strip()

    cached = cached_json('coref', {'version': PROMPT_VERSION, 'model': GROQ_MODEL, 'reasoning_effort': GROQ_REASONING_EFFORT,
                                 'system': COREF_SYSTEM, 'prompt': prompt},
                         lambda: dict(zip(('result', 'usage'), groq_json(COREF_SYSTEM, prompt, purpose='coreference'))))
    obj, usage = cached['result'], cached['usage']
    if not isinstance(obj.get('items'), list):
        raise ValueError('Coreference JSON items must be a list.')
    by_id = {x.get("chunk_id"): x for x in obj['items'] if isinstance(x, dict)}

    rows = []
    for r in batch_df.itertuples(index=False):
        item = by_id.get(r.chunk_id, {})
        resolved = norm_space(item.get('resolved_text') or r.text)
        unresolved = item.get('unresolved_mentions', [])
        status = 'resolved' if resolved != r.text else 'unchanged'
        if not item or not isinstance(unresolved, list):
            resolved, unresolved, status = r.text, ['INVALID_OR_MISSING_COREF_ITEM'], 'rejected'
        if Counter(re.findall(r'\b\d+(?:[.,]\d+)*\b', r.text)) != Counter(re.findall(r'\b\d+(?:[.,]\d+)*\b', resolved)):
            resolved, unresolved, status = r.text, ['COREF_CHANGED_NUMBERS'], 'rejected'
        rows.append({
            "chunk_id": r.chunk_id,
            "resolved_text": resolved,
            "unresolved_mentions": unresolved,
            'coref_status': status,
        })
    return pd.DataFrame(rows), usage

def run_coref(chunks_subset, batch_size=None):
    batch_size = COREF_BATCH_SIZE if batch_size is None else batch_size
    out = []
    for start in tqdm(range(0, len(chunks_subset), batch_size), desc="Coref"):
        batch = chunks_subset.iloc[start:start+batch_size]
        try:
            df, _ = resolve_coref_batch(batch)
        except Exception as error:
            df = pd.DataFrame({
                "chunk_id": batch["chunk_id"].tolist(),
                "resolved_text": batch["text"].tolist(),
                "unresolved_mentions": [["COREF_BATCH_FAILED"] for _ in range(len(batch))],
                'coref_status': ['failed'] * len(batch),
            })
            print('Coreference batch failed:', safe_error(error))
        out.append(df)
    result = pd.concat(out, ignore_index=True) if out else pd.DataFrame()
    result.to_csv(OUTPUTS / 'coref_checkpoint.csv', index=False)
    if not result.empty:
        audit = result.copy()
        original = chunks_subset.set_index('chunk_id')['text'].to_dict()
        audit['original_text'] = audit.chunk_id.map(original)
        audit['unresolved_mentions'] = audit.unresolved_mentions.map(json.dumps)
        audit.to_csv(OUTPUTS / 'coref_audit.csv', index=False)
    return result

# extraction_source = chunks_df.head(EXTRACTION_MAX_CHUNKS).copy()
# coref_df = run_coref(extraction_source)
# extraction_source = extraction_source.merge(coref_df, on="chunk_id", how="left")

# SECTION 15
#@title 2.1 — NER + RE extraction
ALLOWED_NODE_TYPES = {"Company", "Person", "Technology"}
ALLOWED_RELATIONS = {
    "ACQUIRED", "DEVELOPED", "INVESTED_IN", "FOUNDED",
    "WORKED_AT", "PARTNERED_WITH", "USES", "LEADS"
}

EXTRACT_SYSTEM = f"""
Extract a high-precision knowledge graph from tech-news text.
Allowed node types: {sorted(ALLOWED_NODE_TYPES)}
Allowed relations: {sorted(ALLOWED_RELATIONS)}
Use only explicitly supported facts. Prefer precision over recall.
Every relation needs short evidence copied verbatim from original_text, not rewritten text.
Do not turn a plan, consideration or speculation into a confirmed relation. Return strict JSON only.
""".strip()

def extract_batch(batch_df):
    payload = [{
        "chunk_id": r.chunk_id,
        "published_date": r.published_date,
        "text": getattr(r, "resolved_text", None) or r.text,
        'original_text': r.text,
    } for r in batch_df.itertuples(index=False)]

    prompt = f"""
Return:
{{
  "items": [
    {{
      "chunk_id": "...",
      "relations": [
        {{
          "source": "...",
          "source_type": "Company|Person|Technology",
          "relation": "ALLOWED_RELATION",
          "target": "...",
          "target_type": "Company|Person|Technology",
          "evidence": "...",
          "confidence": 0.0
        }}
      ]
    }}
  ]
}}

INPUT:
{json.dumps(payload, ensure_ascii=False)}
""".strip()
    cached = cached_json('extract', {'version': PROMPT_VERSION, 'model': GROQ_MODEL, 'reasoning_effort': GROQ_REASONING_EFFORT,
                                   'system': EXTRACT_SYSTEM, 'prompt': prompt},
                         lambda: dict(zip(('result', 'usage'), groq_json(EXTRACT_SYSTEM, prompt, purpose='relation_extraction'))))
    return cached['result'], cached['usage']

def run_extraction(source_df, batch_size=None):
    batch_size = EXTRACTION_BATCH_SIZE if batch_size is None else batch_size
    meta = source_df.set_index("chunk_id")["published_date"].to_dict()
    original = source_df.set_index('chunk_id')['text'].map(norm_space).to_dict()
    triples, errors = [], []

    for start in tqdm(range(0, len(source_df), batch_size), desc="NER+RE"):
        batch = source_df.iloc[start:start+batch_size]
        try:
            obj, _ = extract_batch(batch)
        except Exception as e:
            errors.append({"start": start, "error": safe_error(e)})
            continue

        if not isinstance(obj.get('items'), list):
            errors.append({'start': start, 'error': 'Invalid JSON items list'})
            continue
        for item in obj['items']:
            if not isinstance(item, dict):
                errors.append({'start': start, 'error': 'Invalid JSON item'})
                continue
            cid = item.get("chunk_id")
            if cid not in set(batch.chunk_id):
                errors.append({'start': start, 'error': 'Unknown batch chunk_id'})
                continue
            relations = item.get('relations', [])
            if not isinstance(relations, list):
                errors.append({'start': start, 'error': 'Invalid relations list'})
                continue
            for x in relations:
                if not isinstance(x, dict):
                    errors.append({'start': start, 'error': 'Invalid relation object'})
                    continue
                s, t = norm_space(x.get("source")), norm_space(x.get("target"))
                st, tt, rel = x.get("source_type"), x.get("target_type"), x.get("relation")
                if not s or not t:
                    continue
                if st not in ALLOWED_NODE_TYPES or tt not in ALLOWED_NODE_TYPES:
                    continue
                if rel not in ALLOWED_RELATIONS:
                    errors.append({'start': start, 'error': 'Relation outside allowlist'})
                    continue
                evidence = norm_space(x.get('evidence'))
                try:
                    confidence = float(x.get('confidence'))
                except (TypeError, ValueError):
                    confidence = math.nan
                date = norm_space(meta[cid])
                if (not evidence or evidence not in original[cid] or
                        not math.isfinite(confidence) or not 0 <= confidence <= 1 or
                        pd.isna(pd.to_datetime(date, utc=True, errors='coerce'))):
                    errors.append({'start': start, 'chunk_id': cid,
                                   'error': 'Rejected invalid evidence/confidence/date'})
                    continue
                triples.append({
                    "source_raw": s,
                    "source_type": st,
                    "relation": rel,
                    "target_raw": t,
                    "target_type": tt,
                    "source_chunk_id": cid,
                    "published_date": meta[cid] or "",
                    "evidence": evidence,
                    "confidence": confidence,
                })

    columns = ['source_raw', 'source_type', 'relation', 'target_raw', 'target_type',
               'source_chunk_id', 'published_date', 'evidence', 'confidence']
    result = pd.DataFrame(triples, columns=columns).drop_duplicates(
        ['source_raw', 'source_type', 'relation', 'target_raw', 'target_type', 'source_chunk_id'])
    error_df = pd.DataFrame(errors, columns=['start', 'chunk_id', 'error'])
    result.to_csv(OUTPUTS / 'triples_checkpoint.csv', index=False)
    error_df.to_csv(OUTPUTS / 'extraction_errors.csv', index=False)
    return result, error_df

# raw_triples_df, extraction_errors_df = run_extraction(extraction_source)
# display(raw_triples_df.head())

# SECTION 17
#@title 2.2 — Entity resolution
CORP_SUFFIXES = {"inc","incorporated","corp","corporation","ltd","limited","llc","plc","co","company"}
MANUAL_ALIASES = {
    "msft": "Microsoft",
    "microsoft corp": "Microsoft",
    "microsoft corporation": "Microsoft",
    "goog": "Google",
    "googl": "Google",
    "google llc": "Google",
    "meta platforms": "Meta",
    "meta platforms inc": "Meta",
    "aapl": "Apple",
    "apple inc": "Apple",
}

def norm_entity(name):
    s = unicodedata.normalize("NFKC", norm_space(name)).lower()
    s = re.sub(r"[^\w\s\-\.]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def strip_suffix(name):
    toks = norm_entity(name).replace(".", "").split()
    while toks and toks[-1] in CORP_SUFFIXES:
        toks.pop()
    return " ".join(toks)

def merge_guard(a, b, typ=None):
    na, nb = strip_suffix(a), strip_suffix(b)
    if na == nb:
        return True
    tokens_a, tokens_b = na.split(), nb.split()
    if not tokens_a or not tokens_b:
        return False
    if typ == 'Person' and tokens_a[0] != tokens_b[0]:
        return False
    # A company's bare name and its longer product name are distinct entities.
    if set(tokens_a) < set(tokens_b) or set(tokens_b) < set(tokens_a):
        return False
    return SequenceMatcher(None, na, nb).ratio() >= 0.72

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
embedder = None

def get_embedder():
    global embedder
    if embedder is None:
        embedder = SentenceTransformer(EMBED_MODEL)
    return embedder

class UF:
    def __init__(self, n):
        self.p = list(range(n))
    def find(self, x):
        if self.p[x] != x:
            self.p[x] = self.find(self.p[x])
        return self.p[x]
    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.p[b] = a

def build_resolution_map(raw_triples_df, threshold=0.90, top_k=5):
    mentions = []
    for r in raw_triples_df.itertuples(index=False):
        mentions += [(r.source_type, r.source_raw), (r.target_type, r.target_raw)]

    counts = Counter((t, norm_entity(n)) for t, n in mentions)
    display_name = {}
    for t, n in mentions:
        display_name.setdefault((t, norm_entity(n)), n)

    mapping, audit = {}, []

    for key in counts:
        t, norm = key
        if t == 'Company' and norm in MANUAL_ALIASES:
            mapping[key] = MANUAL_ALIASES[norm]
            audit.append({
                "type": t, "left": display_name[key],
                "right": MANUAL_ALIASES[norm],
                "similarity": 1.0, "decision": "MERGE_MANUAL"
            })

    for typ in sorted(ALLOWED_NODE_TYPES):
        keys = [k for k in counts if k[0] == typ and k not in mapping]
        if not keys:
            continue
        names = [display_name[k] for k in keys]
        vecs = get_embedder().encode(
            names, batch_size=128, show_progress_bar=False,
            normalize_embeddings=True
        ).astype("float32")

        index = faiss.IndexHNSWFlat(vecs.shape[1], 32, faiss.METRIC_INNER_PRODUCT)
        index.hnsw.efConstruction = 40
        index.hnsw.efSearch = 64
        index.add(vecs)
        sims, nbrs = index.search(vecs, min(top_k, len(names)))
        uf = UF(len(names))

        seen_pairs = set()
        for i in range(len(names)):
            for score, j in zip(sims[i], nbrs[i]):
                pair = tuple(sorted((i, int(j))))
                if j < 0 or i == j or pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                guard_ok = merge_guard(names[i], names[j], typ=typ)
                ok = float(score) >= threshold and guard_ok
                audit.append({
                    "type": typ, "left": names[i], "right": names[j],
                    "similarity": float(score),
                    "decision": 'MERGE_VECTOR' if ok else ('REJECT_THRESHOLD' if float(score) < threshold else 'REJECT_GUARD'),
                    'reason': 'similarity_below_threshold' if float(score) < threshold else
                              ('guard_passed' if guard_ok else 'name_or_product_guard'),
                })
                if ok:
                    uf.union(i, j)

        groups = defaultdict(list)
        for i in range(len(names)):
            groups[uf.find(i)].append(i)

        for idxs in groups.values():
            best = sorted(
                idxs,
                key=lambda i: (-counts[keys[i]], len(names[i]), names[i].lower())
            )[0]
            canonical = names[best]
            for i in idxs:
                mapping[keys[i]] = canonical

    for key in counts:
        mapping.setdefault(key, display_name[key])

    audit_df = pd.DataFrame(audit, columns=['type', 'left', 'right', 'similarity', 'decision', 'reason'])
    for side in ['left', 'right']:
        audit_df['canonical_' + side] = [mapping.get((row.type, norm_entity(getattr(row, side))), getattr(row, side))
                                        for row in audit_df.itertuples(index=False)]
    audit_df.to_csv(OUTPUTS / 'entity_resolution_audit.csv', index=False)
    return mapping, audit_df

def canonicalize_triples(raw_df, mapping):
    df = raw_df.copy()
    def canon(name, typ):
        n = norm_entity(name)
        return mapping.get((typ, n), MANUAL_ALIASES.get(n, name) if typ == 'Company' else name)

    df["source_name"] = [canon(n,t) for n,t in zip(df.source_raw, df.source_type)]
    df["target_name"] = [canon(n,t) for n,t in zip(df.target_raw, df.target_type)]
    df["source_name_norm"] = df.source_name.map(norm_entity)
    df["target_name_norm"] = df.target_name.map(norm_entity)
    df["source_id"] = [sha1(f"{LAB_NAMESPACE}:{t}:{n}")[:24] for t,n in zip(df.source_type, df.source_name_norm)]
    df["target_id"] = [sha1(f"{LAB_NAMESPACE}:{t}:{n}")[:24] for t,n in zip(df.target_type, df.target_name_norm)]
    return df[df.source_id != df.target_id].reset_index(drop=True)

# entity_map, entity_resolution_audit_df = build_resolution_map(raw_triples_df)
# triples_df = canonicalize_triples(raw_triples_df, entity_map)
# display(entity_resolution_audit_df.head(20))

# SECTION 18
#@title 2.3 — Node table + UNWIND bulk insert
def build_nodes(triples_df):
    rows = []
    for r in triples_df.itertuples(index=False):
        rows += [
            {"id":r.source_id,"name":r.source_name,"name_norm":r.source_name_norm,"type":r.source_type,"alias":r.source_raw},
            {"id":r.target_id,"name":r.target_name,"name_norm":r.target_name_norm,"type":r.target_type,"alias":r.target_raw},
        ]
    tmp = pd.DataFrame(rows)
    if tmp.empty:
        return tmp

    out = []
    for (node_id,name,name_norm,typ), g in tmp.groupby(["id","name","name_norm","type"]):
        aliases = sorted(set(g["alias"].map(norm_space)))
        out.append({
            "id":node_id, "name":name, "name_norm":name_norm, "type":typ,
            "aliases":aliases,
            "aliases_norm":sorted(set(norm_entity(x) for x in aliases))
        })
    return pd.DataFrame(out)

def batches(records, size=1000):
    for i in range(0, len(records), size):
        yield records[i:i+size]

def bulk_insert_nodes(nodes_df, batch_size=1000):
    if not set(nodes_df.type) <= ALLOWED_NODE_TYPES:
        raise ValueError('Node type outside allowlist.')
    for typ in sorted(ALLOWED_NODE_TYPES):
        part = nodes_df[nodes_df.type == typ]
        if part.empty:
            continue
        query = f"""
        UNWIND $rows AS row
        MERGE (n:Entity {{id: row.id}})
        SET n:{typ}:Lab19,
            n.lab_namespace=$namespace,
            n.name=row.name,
            n.name_norm=row.name_norm,
            n.entity_type=row.type,
            n.aliases=row.aliases,
            n.aliases_norm=row.aliases_norm
        """
        for b in batches(part.to_dict("records"), batch_size):
            run_cypher(query, rows=b)

def bulk_insert_edges(triples_df, batch_size=1000):
    required = {"source_chunk_id","published_date"}
    if not required.issubset(triples_df.columns):
        raise ValueError("Missing edge provenance.")
    for field in required | {'evidence'}:
        if triples_df[field].fillna('').astype(str).str.strip().eq('').any():
            raise ValueError(f'Empty edge provenance: {field}')
    if not set(triples_df.relation) <= ALLOWED_RELATIONS:
        raise ValueError('Relationship outside allowlist.')
    confidence = pd.to_numeric(triples_df.confidence, errors='coerce')
    if confidence.isna().any() or not confidence.between(0, 1).all():
        raise ValueError('Invalid confidence.')
    if pd.to_datetime(triples_df.published_date, utc=True, errors='coerce').isna().any():
        raise ValueError('Invalid published_date.')

    for rel in sorted(ALLOWED_RELATIONS):
        part = triples_df[triples_df.relation == rel]
        if part.empty:
            continue

        query = f"""
        UNWIND $rows AS row
        MATCH (s:Lab19 {{id: row.source_id, lab_namespace:$namespace}})
        MATCH (t:Lab19 {{id: row.target_id, lab_namespace:$namespace}})
        MERGE (s)-[r:{rel} {{source_chunk_id: row.source_chunk_id}}]->(t)
        SET r.lab_namespace=$namespace,
            r.published_date=row.published_date,
            r.evidence=row.evidence,
            r.confidence=row.confidence
        """

        cols = ["source_id","target_id","source_chunk_id","published_date","evidence","confidence"]
        for b in batches(part[cols].to_dict("records"), batch_size):
            run_cypher(query, rows=b)

# nodes_df = build_nodes(triples_df)
# bulk_insert_nodes(nodes_df)
# bulk_insert_edges(triples_df)

# SECTION 19
#@title 2.4 — Sanity checks
def graph_checks():
    invalid = run_cypher("""
    MATCH (:Lab19 {lab_namespace:$namespace})-[r]->(:Lab19 {lab_namespace:$namespace})
    WHERE r.lab_namespace=$namespace AND
      (trim(coalesce(r.source_chunk_id,''))='' OR trim(coalesce(r.published_date,''))='' OR
       trim(coalesce(r.evidence,''))='')
    RETURN count(r) AS n
    """)[0]["n"]

    counts = {
        "nodes": run_cypher("MATCH (n:Lab19 {lab_namespace:$namespace}) RETURN count(n) AS n")[0]["n"],
        "edges": run_cypher("MATCH ()-[r]->() WHERE r.lab_namespace=$namespace RETURN count(r) AS n")[0]["n"],
        "invalid_provenance_edges": invalid,
    }
    print(counts)
    assert invalid == 0

    top = pd.DataFrame(run_cypher("""
    MATCH (n:Lab19 {lab_namespace:$namespace})
    OPTIONAL MATCH (n)-[r]-()
    WHERE r.lab_namespace=$namespace
    WITH n, count(r) AS degree
    RETURN n.id AS id, n.name AS name, n.entity_type AS type, degree
    ORDER BY degree DESC LIMIT 15
    """))
    display(top)
    pd.DataFrame([counts]).to_csv(OUTPUTS / 'graph_sanity.csv', index=False)
    top.to_csv(OUTPUTS / 'top_degree_entities.csv', index=False)
    return counts, top

# graph_counts, top_degree_df = graph_checks()

# SECTION 21
#@title 3.1 — Flat RAG
flat_index = None
flat_store = None
entity_match_vectors = None
entity_match_store = None

def build_flat_index(chunks_df):
    global flat_index, flat_store
    if chunks_df.empty:
        raise ValueError('Cannot index an empty corpus.')
    vecs = get_embedder().encode(
        chunks_df.text.fillna("").tolist(),
        batch_size=128, show_progress_bar=True,
        normalize_embeddings=True
    ).astype("float32")

    flat_index = faiss.IndexFlatIP(vecs.shape[1])
    flat_index.add(vecs)
    flat_store = chunks_df.reset_index(drop=True).copy()
    print("Flat vectors:", flat_index.ntotal)

def retrieve_flat_context(query, k=6):
    if flat_index is None or flat_store is None:
        raise RuntimeError('Build the Flat RAG index before retrieval.')
    qv = get_embedder().encode(
        [query], normalize_embeddings=True, show_progress_bar=False
    ).astype("float32")
    scores, ids = flat_index.search(qv, min(k, flat_index.ntotal))

    rows = []
    for score, idx in zip(scores[0], ids[0]):
        if idx < 0:
            continue
        r = flat_store.iloc[int(idx)]
        rows.append({
            "score":float(score), "chunk_id":r.chunk_id,
            "published_date":r.published_date, "text":r.text
        })

    df = pd.DataFrame(rows)
    context = "\n\n".join(
        f"[chunk_id={r.chunk_id} | date={r.published_date} | score={r.score:.3f}]\n{r.text}"
        for r in df.itertuples(index=False)
    )
    return context, df

# build_flat_index(chunks_df)

# SECTION 23
#@title 3.2 — Seed matching
SEED_SYSTEM = """
Extract useful seed entities for graph retrieval.
Allowed types: Company, Person, Technology.
Do not answer the question. Return strict JSON only.
""".strip()

def extract_seeds(query):
    obj, _ = groq_json(SEED_SYSTEM, f"""
Question: {query}
Return {{"seeds":[{{"name":"...","type":"Company|Person|Technology|null"}}]}}
""", purpose='seed_extraction')
    return [
        {"name":norm_space(x.get("name")),
         "type":x.get("type") if x.get("type") in ALLOWED_NODE_TYPES else None}
        for x in obj.get("seeds", [])
        if norm_space(x.get("name"))
    ]

def build_entity_matcher(nodes_df):
    global entity_match_vectors, entity_match_store
    entity_match_store = nodes_df.reset_index(drop=True).copy()
    entity_match_vectors = get_embedder().encode(
        entity_match_store.name.tolist(),
        batch_size=128, show_progress_bar=False,
        normalize_embeddings=True
    ).astype("float32")

def match_seeds(query, fuzzy_threshold=0.66):
    matched = []
    for seed in extract_seeds(query):
        exact = run_cypher("""
        MATCH (n:Lab19 {lab_namespace:$namespace})
        WHERE (n.name_norm=$name OR $name IN coalesce(n.aliases_norm,[]))
          AND ($typ IS NULL OR n.entity_type=$typ)
        RETURN n.id AS id, n.name AS name, n.entity_type AS type
        LIMIT 5
        """, name=norm_entity(seed["name"]), typ=seed["type"])

        if exact:
            matched += exact
            continue

        if entity_match_vectors is None:
            continue

        mask = np.ones(len(entity_match_store), dtype=bool)
        if seed["type"]:
            mask = entity_match_store.type.eq(seed["type"]).to_numpy()
        idxs = np.flatnonzero(mask)
        if not len(idxs):
            continue

        qv = get_embedder().encode(
            [seed["name"]], normalize_embeddings=True, show_progress_bar=False
        ).astype("float32")[0]
        sims = entity_match_vectors[idxs] @ qv
        j = int(np.argmax(sims))
        if float(sims[j]) >= fuzzy_threshold:
            r = entity_match_store.iloc[int(idxs[j])]
            matched.append({"id":r.id,"name":r.name,"type":r.type})

    return list({x["id"]: x for x in matched}.values())

# build_entity_matcher(nodes_df)

# SECTION 24
#@title 3.3 — Graph traversal + super-node mitigation
SUPER_NODE_DEGREE = 100
SUPER_NODE_EDGE_CAP = 50
GLOBAL_EDGE_CAP = 250
MAX_GRAPH_CONTEXT_CHARS = 14000

def node_degree(node_id):
    return int(run_cypher("""
    MATCH (n:Lab19 {id:$id, lab_namespace:$namespace})
    OPTIONAL MATCH (n)-[r]-()
    WHERE r.lab_namespace=$namespace
    RETURN count(r) AS degree
    """, id=node_id)[0]["degree"])

def recent_edges(node_id, limit):
    return run_cypher("""
    MATCH (n:Lab19 {id:$id, lab_namespace:$namespace})
    MATCH (n)-[r]-(m:Lab19 {lab_namespace:$namespace})
    WHERE r.lab_namespace=$namespace
    RETURN
      startNode(r).id AS source_id,
      startNode(r).name AS source_name,
      startNode(r).entity_type AS source_type,
      type(r) AS relation,
      endNode(r).id AS target_id,
      endNode(r).name AS target_name,
      endNode(r).entity_type AS target_type,
      r.source_chunk_id AS source_chunk_id,
      r.published_date AS published_date,
      r.evidence AS evidence,
      m.id AS neighbor_id
    ORDER BY coalesce(r.published_date,'') DESC
    LIMIT $limit
    """, id=node_id, limit=int(limit))

def textualize(edges):
    edges = sorted(edges, key=lambda e:e.get("published_date") or "", reverse=True)
    lines, used = [], 0
    for e in edges:
        line = (
            f"{e['source_name']} [{e['source_type']}] -{e['relation']}-> "
            f"{e['target_name']} [{e['target_type']}] "
            f"| date={e.get('published_date') or 'unknown'} "
            f"| chunk={e.get('source_chunk_id') or 'unknown'}"
        )
        if e.get("evidence"):
            line += f" | evidence={norm_space(e['evidence'])}"
        if used + len(line) + 1 > MAX_GRAPH_CONTEXT_CHARS:
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)

def retrieve_graph_context(query, max_hops=2, edge_limit=50, return_debug=False):
    seeds = match_seeds(query)
    if not seeds:
        out = {"context":"","edges":pd.DataFrame(),
               "diagnostics":{"reason":"NO_SEED","supernode_events":[]}}
        return out if return_debug else ""

    frontier = deque((x["id"],0) for x in seeds)
    expanded, seen_edges, collected = set(), set(), []
    supernode_events = []

    while frontier and len(collected) < GLOBAL_EDGE_CAP:
        node_id, hop = frontier.popleft()
        if node_id in expanded or hop >= max_hops:
            continue
        expanded.add(node_id)

        degree = node_degree(node_id)
        limit = int(edge_limit)
        if degree > SUPER_NODE_DEGREE:
            limit = min(limit, SUPER_NODE_EDGE_CAP)
            supernode_events.append({"node_id":node_id,"degree":degree,"limit":limit})

        for e in recent_edges(node_id, limit):
            key = (e["source_id"],e["relation"],e["target_id"],e["source_chunk_id"])
            if key in seen_edges:
                continue
            seen_edges.add(key)
            collected.append(e)
            if len(collected) >= GLOBAL_EDGE_CAP:
                break

            nb = e.get("neighbor_id")
            if nb and nb not in expanded and hop + 1 < max_hops:
                frontier.append((nb, hop+1))

    out = {
        "context": textualize(collected),
        "edges": pd.DataFrame(collected),
        "diagnostics": {
            "matched_seeds": seeds,
            "expanded_nodes": len(expanded),
            "collected_edges": len(collected),
            "supernode_events": supernode_events,
        }
    }
    return out if return_debug else out["context"]

# SECTION 25
#@title 3.4 — Flat answer vs Hybrid GraphRAG answer
ANSWER_SYSTEM = """
Answer only from supplied context.
Be concise but complete. Do not invent facts.
Cite provenance inline as [chunk_id=...] whenever possible.
If evidence is insufficient or conflicting, say so.
""".strip()

def generate_answer(question, context):
    prompt = f"QUESTION:\n{question}\n\nCONTEXT:\n{context}\n\nANSWER:"
    t0 = time.perf_counter()
    text, usage = groq_chat(
        [{"role":"system","content":ANSWER_SYSTEM},
         {"role":"user","content":prompt}],
        model=GROQ_MODEL
    )
    return {
        "answer": text.strip(),
        "latency_s": time.perf_counter()-t0,
        "total_tokens": usage.get("total_tokens"),
    }

def answer_flat_rag(question):
    started = time.perf_counter()
    context, retrieved = retrieve_flat_context(question, k=6)
    retrieval_latency = time.perf_counter() - started
    out = generate_answer(question, context)
    out.update(generation_latency_s=out['latency_s'], retrieval_latency_s=retrieval_latency,
               end_to_end_latency_s=time.perf_counter()-started)
    out['latency_s'] = out['end_to_end_latency_s']
    out['online_total_tokens'] = out['total_tokens']
    out.update({"context":context,"retrieved":retrieved})
    return out

def answer_graph_rag(question):
    started = time.perf_counter()
    usage_start = len(USAGE_LOG)
    g = retrieve_graph_context(question, max_hops=2, edge_limit=50, return_debug=True)
    vctx, vdocs = retrieve_flat_context(question, k=4)
    retrieval_usage = USAGE_LOG[usage_start:]
    retrieval_latency = time.perf_counter() - started
    context = f"=== GRAPH ===\n{g['context']}\n\n=== VECTOR ===\n{vctx}"
    out = generate_answer(question, context)
    seed_tokens = [entry.get('total_tokens') for entry in retrieval_usage]
    out.update(generation_latency_s=out['latency_s'], retrieval_latency_s=retrieval_latency,
               end_to_end_latency_s=time.perf_counter()-started,
               seed_extraction_tokens=sum(seed_tokens) if all(x is not None for x in seed_tokens) else None)
    out['latency_s'] = out['end_to_end_latency_s']
    out['online_total_tokens'] = (out['total_tokens'] + out['seed_extraction_tokens']
                                  if out['total_tokens'] is not None and out['seed_extraction_tokens'] is not None else None)
    out.update({"context":context,"graph_debug":g,"vector_docs":vdocs})
    return out

# SECTION 28
#@title 4.2 — LLM-as-a-Judge
JUDGE_SYSTEM = """
You are a strict evaluator of RAG answers.
Score 1-5:
- comprehensiveness
- faithfulness to supplied candidate context
- multi_hop_reasoning accuracy
Use the reference answer as correctness anchor.
Return strict JSON only.
""".strip()

def judge_credentials():
    name = JUDGE_KEY_NAMES.get(JUDGE_PROVIDER)
    if name is None:
        raise ValueError('JUDGE_PROVIDER must be openai, groq or gemini.')
    return name, globals()[name]


def judge_json(system, user, purpose='judge'):
    if not JUDGE_MODEL:
        raise RuntimeError("Thiếu JUDGE_MODEL.")

    if JUDGE_PROVIDER == "groq":
        return groq_json(system, user, model=JUDGE_MODEL, purpose=purpose)[0]

    key_name, key = judge_credentials()
    if not is_configured(key):
        raise RuntimeError(f'Thiếu {key_name}.')
    from openai import OpenAI
    options = {'api_key': key, 'timeout': 60.0, 'max_retries': 3}
    response_format = {'type': 'json_object'}
    if JUDGE_PROVIDER == 'gemini':
        # Google's documented compatibility endpoint; requests use the Gemini key.
        options['base_url'] = 'https://generativelanguage.googleapis.com/v1beta/openai/'
        properties = ({'ok': {'type': 'boolean'}} if purpose == 'preflight' else {
            **{axis: {'type': 'integer', 'minimum': 1, 'maximum': 5} for axis in
               ['comprehensiveness', 'faithfulness', 'multi_hop_reasoning']},
            'rationale': {'type': 'string'},
        })
        response_format = {'type': 'json_schema', 'json_schema': {
            'name': 'lab19_judge_response', 'strict': True,
            'schema': {'type': 'object', 'properties': properties,
                       'required': list(properties), 'additionalProperties': False},
        }}
    try:
        with OpenAI(**options) as client:
            resp = client.chat.completions.create(
                model=JUDGE_MODEL,
                messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
                temperature=0.0,
                response_format=response_format,
            )
        usage = getattr(resp, 'usage', None)
        USAGE_LOG.append({'provider': JUDGE_PROVIDER, 'model': JUDGE_MODEL, 'purpose': purpose,
                          **{field: getattr(usage, field, None) for field in
                             ['prompt_tokens', 'completion_tokens', 'total_tokens']}})
        return parse_json_object(resp.choices[0].message.content)
    except Exception as error:
        raise RuntimeError(safe_error(error)) from None

def judge_answer(question, reference, answer, context):
    prompt = f"""
QUESTION:
{question}

REFERENCE:
{reference}

CANDIDATE:
{answer}

CANDIDATE CONTEXT:
{context}

Return:
{{
 "comprehensiveness":1,
 "faithfulness":1,
 "multi_hop_reasoning":1,
 "rationale":"2-5 sentences"
}}
"""
    obj = cached_json('judge', {'version': PROMPT_VERSION, 'provider': JUDGE_PROVIDER,
                               'model': JUDGE_MODEL, 'reasoning_effort': GROQ_REASONING_EFFORT,
                               'system': JUDGE_SYSTEM, 'prompt': prompt},
                      lambda: judge_json(JUDGE_SYSTEM, prompt))
    out = {}
    for k in ["comprehensiveness","faithfulness","multi_hop_reasoning"]:
        score = obj.get(k)
        if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 5:
            raise ValueError(f'Invalid Judge score for {k}: expected integer 1-5.')
        out[k] = score
    out["rationale"] = norm_space(obj.get("rationale"))
    if not out['rationale']:
        raise ValueError('Judge rationale is empty.')
    return out

# SECTION 29
#@title 4.3 — Evaluation runner + checkpoint
def run_evaluation(golden_df):
    validate_golden(golden_df)
    rows = []
    manifest = json.loads((OUTPUTS / 'corpus_manifest.json').read_text(encoding='utf-8'))
    evaluation_config = {'version': PROMPT_VERSION, 'corpus': manifest['chunks_fingerprint'],
                         'extraction': manifest['extraction_fingerprint'], 'golden': fingerprint(golden_df),
                         'generator': GROQ_MODEL, 'judge_provider': JUDGE_PROVIDER, 'judge': JUDGE_MODEL,
                         'reasoning_effort': GROQ_REASONING_EFFORT,
                         'graph_namespace': LAB_NAMESPACE, 'embedding': EMBED_MODEL,
                         'answer_prompt': ANSWER_SYSTEM, 'judge_prompt': JUDGE_SYSTEM,
                         'entity_threshold': 0.90, 'seed_threshold': 0.66, 'hops': 2,
                         'flat_k': 6, 'hybrid_vector_k': 4, 'edge_cap': GLOBAL_EDGE_CAP,
                         'node_cap': SUPER_NODE_EDGE_CAP, 'context_cap': MAX_GRAPH_CONTEXT_CHARS}
    run_id = fingerprint(evaluation_config)
    write_json(OUTPUTS / 'run_manifest.json', {**manifest, **evaluation_config, 'run_id': run_id,
               'latency_definition': 'retrieval plus generation wall-clock seconds, excludes Judge',
               'token_definition': 'online generator plus seed extraction; offline indexing/Judge separate'})
    existing = {}
    if CHECKPOINT.exists():
        saved = pd.read_csv(CHECKPOINT).fillna('')
        if 'run_id' in saved.columns:
            existing = {r['id']: r for r in saved[saved.run_id.eq(run_id)].to_dict('records')}
    errors = []
    for q in tqdm(golden_df.itertuples(index=False), total=len(golden_df), desc="Evaluation"):
        if q.id in existing:
            rows.append(existing[q.id])
            continue
        try:
            # Save completed answers before Judge so a Judge failure does not repeat retrieval/generation.
            def compute_answers():
                flat_answer = answer_flat_rag(q.question)
                graph_answer = answer_graph_rag(q.question)
                def serializable(out):
                    return {key: value.to_dict('records') if isinstance(value, pd.DataFrame) else
                            {k: v.to_dict('records') if isinstance(v, pd.DataFrame) else v for k, v in value.items()}
                            if isinstance(value, dict) else value for key, value in out.items()}
                return {'flat': serializable(flat_answer), 'graph': serializable(graph_answer)}
            answers = cached_json('answers', {'run_id': run_id, 'id': q.id, 'question': q.question}, compute_answers)
            flat, graph = answers['flat'], answers['graph']
            jf = judge_answer(q.question, q.reference_answer, flat['answer'], flat['context'])
            jg = judge_answer(q.question, q.reference_answer, graph['answer'], graph['context'])
        except Exception as error:
            errors.append({'id': q.id, 'error': safe_error(error)})
            pd.DataFrame(errors).to_csv(OUTPUTS / 'evaluation_errors.csv', index=False)
            print('Evaluation failed:', q.id, safe_error(error))
            continue

        rows.append({
            "id":q.id, "group":q.group, "question":q.question,
            "reference_answer":q.reference_answer,
            'run_id': run_id,
            "flat_answer":flat["answer"], "graph_answer":graph["answer"],
            "flat_comprehensiveness":jf["comprehensiveness"],
            "graph_comprehensiveness":jg["comprehensiveness"],
            "flat_faithfulness":jf["faithfulness"],
            "graph_faithfulness":jg["faithfulness"],
            "flat_multi_hop_reasoning":jf["multi_hop_reasoning"],
            "graph_multi_hop_reasoning":jg["multi_hop_reasoning"],
            "flat_latency_s":flat["latency_s"],
            "graph_latency_s":graph["latency_s"],
            "flat_total_tokens":flat.get("online_total_tokens"),
            "graph_total_tokens":graph.get("online_total_tokens"),
            'flat_generation_tokens': flat.get('total_tokens'),
            'graph_generation_tokens': graph.get('total_tokens'),
            'graph_seed_tokens': graph.get('seed_extraction_tokens'),
            'flat_retrieval_latency_s': flat['retrieval_latency_s'],
            'graph_retrieval_latency_s': graph['retrieval_latency_s'],
            'flat_generation_latency_s': flat['generation_latency_s'],
            'graph_generation_latency_s': graph['generation_latency_s'],
            "flat_judge_rationale":jf["rationale"],
            "graph_judge_rationale":jg["rationale"],
            "graph_supernode_events":len(
                graph["graph_debug"]["diagnostics"].get("supernode_events",[])
            )
        })
        pd.DataFrame(rows).to_csv(CHECKPOINT, index=False)
        write_json(OUTPUTS / '.cache' / f'trace_{run_id}_{q.id}.json', answers)
        write_json(OUTPUTS / 'usage_log.json', USAGE_LOG)
    if errors:
        raise RuntimeError(f'{len(errors)} Golden queries failed. Check evaluation_errors.csv; rerun resumes successful queries.')
    result = pd.DataFrame(rows)
    result.to_csv(OUTPUTS / 'graphrag_eval_results.csv', index=False)
    return result

# validate_golden(golden_df, require_answers=True)
# eval_results_df = run_evaluation(golden_df)
# display(eval_results_df)

# SECTION 30
#@title 4.4 — Comparison table + export
def comparison_table(eval_df):
    metric_map = {
        "Comprehensiveness":("flat_comprehensiveness","graph_comprehensiveness"),
        "Faithfulness":("flat_faithfulness","graph_faithfulness"),
        "Multi-hop reasoning":("flat_multi_hop_reasoning","graph_multi_hop_reasoning"),
        "Latency (s)":("flat_latency_s","graph_latency_s"),
        "Token usage":("flat_total_tokens","graph_total_tokens"),
    }

    rows = []
    groups = list(eval_df.groupby('group')) + [('ALL', eval_df)]
    for group, g in groups:
        for metric, (fc,gc) in metric_map.items():
            f = pd.to_numeric(g[fc], errors="coerce").mean()
            gr = pd.to_numeric(g[gc], errors="coerce").mean()

            if metric in {"Latency (s)","Token usage"}:
                comment = "Flat RAG thường rẻ/nhanh hơn." if f < gr else "GraphRAG không đắt hơn trong sample này."
            else:
                delta = gr - f
                if delta >= .75:
                    comment = "GraphRAG cải thiện rõ; kiểm tra rationale và provenance."
                elif delta <= -.5:
                    comment = "Flat RAG tốt hơn; graph extraction/retrieval có thể gây mất thông tin hoặc nhiễu."
                else:
                    comment = "Hai phương pháp gần nhau."

            rows.append({
                "Loại câu hỏi":group, "Metric":metric,
                "Flat RAG":round(f,3) if pd.notna(f) else np.nan,
                "GraphRAG":round(gr,3) if pd.notna(gr) else np.nan,
                'Delta Graph - Flat': round(gr - f, 3) if pd.notna(f) and pd.notna(gr) else np.nan,
                'Sample count': len(g),
                "Nhận xét phân tích":comment
            })
    return pd.DataFrame(rows)

# comparison_df = comparison_table(eval_results_df)
# display(comparison_df)
# eval_results_df.to_csv("/content/graphrag_eval_results.csv", index=False)
# comparison_df.to_csv("/content/graphrag_vs_flatrag_summary.csv", index=False)

# SECTION 32
#@title 5.1 — Super-node check + entity audit
def test_supernode_policy():
    rows = run_cypher("""
    MATCH (n:Lab19 {lab_namespace:$namespace})-[r]-()
    WHERE r.lab_namespace=$namespace
    WITH n, count(r) AS degree
    ORDER BY degree DESC LIMIT 1
    RETURN n.id AS id, n.name AS name, degree
    """)
    if not rows:
        print("Graph empty.")
        return {'status': 'not_exercised', 'reason': 'empty_graph'}

    n = rows[0]
    limit = 50 if n["degree"] > SUPER_NODE_DEGREE else 1000
    edges = recent_edges(n["id"], limit)
    print(n, "fetched=", len(edges))
    if n["degree"] > SUPER_NODE_DEGREE:
        assert len(edges) <= 50
        print('Super-node cap OK.')
    return {'status': 'passed' if n['degree'] > SUPER_NODE_DEGREE else 'not_exercised',
            'reason': '' if n['degree'] > SUPER_NODE_DEGREE else 'no_real_supernode',
            'degree': n['degree'], 'fetched': len(edges)}

def show_resolution_audit(audit_df):
    if audit_df.empty:
        print("No audit rows.")
        return
    display(
        audit_df.sort_values("similarity", ascending=False).head(30)
    )
    print('High-similarity rejected pairs:')
    display(audit_df[audit_df.decision.eq('REJECT_GUARD')].sort_values('similarity', ascending=False).head(20))


def validate_golden(df, require_answers=True):
    required = {'id', 'group', 'question', 'reference_answer'}
    if not required <= set(df.columns):
        raise ValueError(f'Missing Golden columns: {required - set(df.columns)}')
    if len(df) < 5 or not {'factoid', 'multi-hop', 'cross-doc'} <= set(df.group):
        raise ValueError('Golden needs at least 5 questions covering all three groups.')
    if df.id.isna().any() or df.id.astype(str).str.strip().eq('').any() or df.id.duplicated().any():
        raise ValueError('Golden IDs must be nonempty and unique.')
    if df.question.fillna('').str.strip().eq('').any():
        raise ValueError('Golden question is empty.')
    if require_answers and df.reference_answer.fillna('').str.strip().eq('').any():
        raise ValueError('Golden reference_answer is empty.')
    return True


def preflight(check_llm=True):
    statuses = []
    required = {'NEO4J_URI': NEO4J_URI, 'NEO4J_PASSWORD': NEO4J_PASSWORD,
                'GROQ_API_KEY': GROQ_API_KEY, 'GROQ_MODEL': GROQ_MODEL, 'JUDGE_MODEL': JUDGE_MODEL}
    judge_key_name = JUDGE_KEY_NAMES.get(JUDGE_PROVIDER)
    judge_key = globals()[judge_key_name] if judge_key_name else ''
    statuses.append({'check': 'JUDGE_PROVIDER', 'status': 'configured' if judge_key_name else 'failed',
                     'detail': JUDGE_PROVIDER if judge_key_name else 'Expected openai, groq or gemini'})
    if judge_key_name:
        required[judge_key_name] = judge_key
    for name, value in required.items():
        statuses.append({'check': name, 'status': 'configured' if is_configured(value) else 'missing_or_placeholder'})
    statuses.append({'check': 'corpus', 'status': 'present' if DATA_PATH.exists() else 'missing'})
    statuses.append({'check': 'HF_TOKEN', 'status': 'configured' if HF_TOKEN else 'needed_for_gated_download'})
    try:
        connect_neo4j()
        assert run_cypher('RETURN 1 AS ok')[0]['ok'] == 1
        existing = run_cypher('MATCH (n) RETURN count(n) AS nodes')[0]['nodes']
        statuses.append({'check': 'neo4j_driver', 'status': 'passed', 'detail': f'{existing} existing nodes; lab queries are namespaced'})
        setup_graph_schema()
    except Exception as error:
        statuses.append({'check': 'neo4j_driver', 'status': 'failed', 'detail': safe_error(error)})
    if check_llm and GROQ_API_KEY and GROQ_MODEL:
        try:
            groq_json('Return strict JSON.', 'Return {"ok": true}', purpose='preflight')
            statuses.append({'check': 'groq_request', 'status': 'passed'})
        except Exception as error:
            statuses.append({'check': 'groq_request', 'status': 'failed', 'detail': safe_error(error)})
    if check_llm and JUDGE_MODEL and is_configured(judge_key):
        try:
            probe = judge_json('Return strict JSON.', 'Return {"ok": true}', purpose='preflight')
            if probe.get('ok') is not True:
                raise ValueError('Judge probe did not return ok=true.')
            statuses.append({'check': 'judge_request', 'status': 'passed'})
        except Exception as error:
            statuses.append({'check': 'judge_request', 'status': 'failed', 'detail': safe_error(error)})
    result = pd.DataFrame(statuses).fillna('')
    result.to_csv(OUTPUTS / 'preflight_status.csv', index=False)
    return result

# test_supernode_policy()
# show_resolution_audit(entity_resolution_audit_df)

# SECTION 35
#@title Bonus — NetworkX community fallback
import networkx as nx

def build_communities(limit_edges=20000):
    edge_df = pd.DataFrame(run_cypher("""
    MATCH (a:Lab19 {lab_namespace:$namespace})-[r]->(b:Lab19 {lab_namespace:$namespace})
    WHERE r.lab_namespace=$namespace
    RETURN a.id AS source, b.id AS target
    LIMIT $limit
    """, limit=int(limit_edges)))

    G = nx.Graph()
    G.add_edges_from(edge_df[["source","target"]].itertuples(index=False, name=None))
    communities = nx.algorithms.community.greedy_modularity_communities(G)

    rows = []
    for cid, members in enumerate(communities):
        rows += [{"id":node_id,"community_id":int(cid)} for node_id in members]

    for b in batches(rows, 1000):
        run_cypher("""
        UNWIND $rows AS row
        MATCH (n:Lab19 {id:row.id, lab_namespace:$namespace})
        SET n.community_id=row.community_id
        """, rows=b)

    return pd.DataFrame(rows)

# community_df = build_communities()

# SECTION 36
#@title Bonus — Self-correction scaffold
SUFFICIENCY_SYSTEM = """
Decide whether the supplied retrieval context is sufficient to answer the question faithfully.
Do not answer the question. Return strict JSON only.
""".strip()

def context_sufficient(question, context):
    obj, _ = groq_json(
        SUFFICIENCY_SYSTEM,
        f"""QUESTION: {question}
CONTEXT:
{context[:16000]}
Return {{"sufficient":true,"missing":"..."}}"""
        , purpose='context_sufficiency'
    )
    return bool(obj.get("sufficient")), norm_space(obj.get("missing"))

def self_correcting_context(question):
    g2 = retrieve_graph_context(question, 2, 50, True)
    ok, missing = context_sufficient(question, g2["context"])
    if ok:
        return {"route":"hop2","context":g2["context"],"missing":""}

    g3 = retrieve_graph_context(question, 3, 50, True)
    ok, missing2 = context_sufficient(question, g3["context"])
    if ok:
        return {"route":"hop3","context":g3["context"],"missing":missing}

    flat, _ = retrieve_flat_context(question, k=8)
    return {
        "route":"hop3+vector",
        "context":f"=== GRAPH ===\n{g3['context']}\n\n=== VECTOR ===\n{flat}",
        "missing":missing2
    }

