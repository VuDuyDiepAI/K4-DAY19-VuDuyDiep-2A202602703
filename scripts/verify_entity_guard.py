"""Measure lexical-guard fixtures separately from the real corpus ER audit."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import lab19_runtime as lab
from lab19_support import write_json

pairs = [
    ('Technology', 'Apple Watch', 'Apple Watch Ultra'),
    ('Technology', 'Google Cloud', 'Google Cloud Storage'),
    ('Person', 'Sam Altman', 'Steve Altman'),
    ('Technology', 'Microsoft Windows 11', 'Microsoft Windows 11 Pro'),
    ('Technology', 'Microsoft Windows 11 Pro', 'Microsoft Windows 11 Pro N'),
    ('Technology', 'Microsoft Windows 11 Pro', 'Microsoft Windows 11 Pro for Workstations'),
    ('Technology', 'Microsoft SQL Server', 'Microsoft SQL Server Management Studio'),
    ('Technology', 'Amazon Elastic Compute Cloud', 'Amazon Elastic Compute Cloud Auto Scaling'),
    ('Technology', 'Microsoft Azure Active Directory', 'Microsoft Azure Active Directory Connect'),
    ('Technology', 'Google Chrome', 'Google Chrome Enterprise'),
]
names = list(dict.fromkeys(name for _, left, right in pairs for name in [left, right]))
vectors = lab.get_embedder().encode(names, normalize_embeddings=True, show_progress_bar=False)
by_name = dict(zip(names, vectors))
rows = []
for typ, left, right in pairs:
    score = float(by_name[left] @ by_name[right])
    guard = lab.merge_guard(left, right, typ=typ)
    rows.append({'data_kind': 'synthetic name-pair fixture; real MiniLM embeddings',
                 'type': typ, 'left': left, 'right': right, 'similarity': score,
                 'guard_passed': guard, 'threshold_passed': score >= .90,
                 'decision': 'REJECT_GUARD' if score >= .90 and not guard else 'REJECT_THRESHOLD' if score < .90 else 'MERGE_VECTOR'})
write_json(lab.OUTPUTS / 'entity_guard_fixture.json', rows)
for row in rows:
    print(row['left'], '/', row['right'], round(row['similarity'], 4), row['decision'])
