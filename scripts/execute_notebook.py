"""Execute the actual notebook with the current .venv interpreter and preserve outputs."""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab19_support import write_json

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
os.environ['PATH'] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get('PATH', '')
os.environ['PYTHONIOENCODING'] = 'utf-8'
path = ROOT / 'Day19_GraphRAG_vs_FlatRAG_Production_Lab_Guide.ipynb'
notebook = nbformat.read(path, as_version=4)
client = NotebookClient(notebook, timeout=600, kernel_name='python3',
                        resources={'metadata': {'path': str(ROOT)}})
try:
    client.execute()
finally:
    nbformat.write(notebook, path)
code_cells = [cell for cell in notebook.cells if cell.cell_type == 'code']
errors = [output for cell in code_cells for output in cell.outputs if output.output_type == 'error']
pending_cells = [i + 1 for i, cell in enumerate(notebook.cells)
                 if cell.cell_type == 'code' and any('PENDING' in str(output.get('text', '')) for output in cell.outputs)]
status = {'executed_code_cells': len(code_cells), 'error_outputs': len(errors),
          'pending_cells': pending_cells, 'pipeline_complete': not pending_cells and not errors,
          'executed_at_utc': datetime.now(timezone.utc).isoformat(),
          'python': sys.executable}
write_json(ROOT / 'outputs' / 'notebook_execution.json', status)
print(status)
