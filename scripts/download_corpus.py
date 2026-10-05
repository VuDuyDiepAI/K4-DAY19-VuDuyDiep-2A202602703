"""Download a bounded public HF stream without loading the full corpus into RAM."""
import csv
import json
import os
from pathlib import Path
from datetime import datetime, timezone

from datasets import load_dataset
from dotenv import load_dotenv
from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
target = ROOT / 'data' / 'hackernoon_subset.csv'
token = os.getenv('HF_TOKEN', '')
if not token or '...' in token:
    token = None
target.parent.mkdir(exist_ok=True)

if target.exists():
    print('Corpus already exists; kept unchanged:', target.name)
else:
    temporary = target.with_suffix('.csv.part')
    print('Streaming at most 5000 rows / 300 MiB; no Golden answers used.', flush=True)
    dataset_info = HfApi(token=token).dataset_info('HackerNoon/tech-company-news-data-dump')
    stream = load_dataset('HackerNoon/tech-company-news-data-dump',
                          split='train', streaming=True, token=token, revision=dataset_info.sha)
    count = 0
    with temporary.open('w', encoding='utf-8', newline='') as handle:
        writer = None
        for row in stream:
            if writer is None:
                columns = list(row)
                writer = csv.DictWriter(handle, fieldnames=columns, extrasaction='ignore')
                writer.writeheader()
                print('Columns:', columns, flush=True)
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                             for k, v in row.items()})
            count += 1
            if count % 250 == 0:
                handle.flush()
                print('Downloaded rows:', count, flush=True)
            if count >= 5000 or temporary.stat().st_size >= 300 * 1024 * 1024:
                break
    if not count:
        raise RuntimeError('Dataset stream is empty; no final corpus was written.')
    temporary.replace(target)
    metadata = {
        'dataset': 'HackerNoon/tech-company-news-data-dump', 'split': 'train',
        'downloaded_rows': count, 'columns': columns,
        'downloaded_at_utc': datetime.now(timezone.utc).isoformat(),
        'revision': dataset_info.sha,
        'source_files': [item.rfilename for item in dataset_info.siblings if item.rfilename.endswith('.csv')],
        'source': 'live Hugging Face stream; original Golden row order must be verified',
    }
    (ROOT / 'outputs' / 'corpus_download.json').write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT / 'outputs' / 'corpus_download_status.json').write_text(
        json.dumps({'status': 'passed', **metadata}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Corpus saved:', count, 'rows;', target.stat().st_size, 'bytes', flush=True)
