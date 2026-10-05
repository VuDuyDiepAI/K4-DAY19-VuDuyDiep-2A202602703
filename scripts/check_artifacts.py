"""Read-only check of notebook outputs, configuration status and accidental secrets."""
import json
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab19_support import is_configured, JUDGE_KEY_NAMES

config = dotenv_values(ROOT / '.env')
secret_values = [str(config.get(name) or '') for name in
                 ['NEO4J_PASSWORD', 'GROQ_API_KEY', 'OPENAI_API_KEY', 'GEMINI_API_KEY', 'HF_TOKEN']
                 if is_configured(config.get(name))]
paths = [ROOT / name for name in ['lab19_runtime.py', 'lab19_support.py', 'lab19_reporting.py',
                                  'WORKFLOW.md', 'README.md', 'requirements.txt', 'pytest.ini',
                                  'Day19_GraphRAG_vs_FlatRAG_Production_Lab_Guide.ipynb']]
for folder in ['scripts', 'tests', 'reports', 'outputs']:
    paths.extend(path for path in (ROOT / folder).rglob('*')
                 if path.is_file() and '.cache' not in path.parts and '__pycache__' not in path.parts
                 and path.suffix in {'.py', '.md', '.csv', '.json', '.ipynb'})
leaks = []
for path in paths:
    contents = path.read_text(encoding='utf-8-sig')
    if any(secret in contents for secret in secret_values):
        leaks.append(str(path.relative_to(ROOT)))
notebook = json.loads((ROOT / 'Day19_GraphRAG_vs_FlatRAG_Production_Lab_Guide.ipynb').read_text(encoding='utf-8'))
code_cells = [cell for cell in notebook['cells'] if cell['cell_type'] == 'code']
errors = sum(output['output_type'] == 'error' for cell in code_cells for output in cell['outputs'])
result = {'scanned_artifacts': len(paths), 'secret_leak_paths': leaks,
          'code_cells': len(code_cells), 'executed_cells': sum(cell['execution_count'] is not None for cell in code_cells),
          'error_outputs': errors,
          'groq_key_configured': is_configured(config.get('GROQ_API_KEY')),
          'hf_token_configured': is_configured(config.get('HF_TOKEN')),
          'judge_provider': config.get('JUDGE_PROVIDER'),
          'judge_key_configured': is_configured(config.get(JUDGE_KEY_NAMES.get(str(config.get('JUDGE_PROVIDER') or 'groq').strip().lower(), ''))),
          'default_corpus_present': (ROOT / 'data/hackernoon_subset.csv').exists()}
print(json.dumps(result, ensure_ascii=True, indent=2))
sys.exit(1 if leaks or errors else 0)
