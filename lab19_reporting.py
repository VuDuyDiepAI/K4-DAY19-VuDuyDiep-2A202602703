"""Generate reports only from actual completed evaluation artifacts."""
import json
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from lab19_support import ROOT


def markdown_table(frame):
    if frame.empty:
        return 'Không có bản ghi phù hợp trong lần chạy này.'
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')
    columns = list(frame.columns)
    lines = ['| ' + ' | '.join(map(cell, columns)) + ' |',
             '| ' + ' | '.join(['---'] * len(columns)) + ' |']
    lines.extend('| ' + ' | '.join(cell(v) for v in row) + ' |' for row in frame.itertuples(index=False, name=None))
    return '\n'.join(lines)


def generate_reports(lab, evaluation, summary):
    lab.validate_golden(evaluation)
    reports = ROOT / 'reports'
    manifest = json.loads((lab.OUTPUTS / 'run_manifest.json').read_text(encoding='utf-8'))
    top = pd.read_csv(lab.OUTPUTS / 'top_degree_entities.csv').head(3)
    audit = pd.read_csv(lab.OUTPUTS / 'entity_resolution_audit.csv')
    coref = pd.read_csv(lab.OUTPUTS / 'coref_audit.csv').fillna('')
    changed = coref[coref.chunk_id.eq('8e74089254231622e67f::c0000')]
    review_path = lab.OUTPUTS / 'evidence_review.json'
    review = json.loads(review_path.read_text(encoding='utf-8')) if review_path.exists() else {}
    case_notes = review.get('case_notes', {}) if review.get('run_id') == manifest['run_id'] else {}
    fixture_path = lab.OUTPUTS / 'entity_guard_fixture.json'
    fixture = pd.DataFrame(json.loads(fixture_path.read_text(encoding='utf-8'))) if fixture_path.exists() else pd.DataFrame()
    if not fixture.empty:
        fixture = fixture[fixture.similarity.gt(.85) & ~fixture.guard_passed]
    rejected = audit[audit.decision.eq('REJECT_GUARD') & audit.similarity.gt(.85)].head(1)
    sums = evaluation[['graph_comprehensiveness', 'graph_faithfulness', 'graph_multi_hop_reasoning']].sum(axis=1)
    flat_sums = evaluation[['flat_comprehensiveness', 'flat_faithfulness', 'flat_multi_hop_reasoning']].sum(axis=1)
    delta = sums - flat_sums
    selected_indices = list(dict.fromkeys([delta.idxmax(), sums.idxmin()]))
    if case_notes:
        selected_indices = [evaluation[evaluation.id.eq(query_id)].index[0]
                            for query_id in case_notes if evaluation.id.eq(query_id).any()]
    if len(selected_indices) < 2:
        selected_indices.extend(i for i in evaluation.index if i not in selected_indices)
    cases = []
    for index in selected_indices[:2]:
        row = evaluation.loc[index]
        # Trace files are generated separately and contain the original contexts/diagnostics.
        trace_path = lab.OUTPUTS / '.cache' / f"trace_{manifest['run_id']}_{row.id}.json"
        trace = json.loads(trace_path.read_text(encoding='utf-8')) if trace_path.exists() else {}
        diagnostics = trace.get('graph', {}).get('graph_debug', {}).get('diagnostics', {})
        cases.append(f"""### {row.id} — {row.group}

**Câu hỏi:** {row.question}

**Reference đã đối chiếu:** {row.reference_answer}

**Flat answer:** {row.flat_answer}

**Graph answer:** {row.graph_answer}

**Judge Flat:** {row.flat_judge_rationale}

**Judge Graph:** {row.graph_judge_rationale}

**Diagnostics thực đo:** `{json.dumps(diagnostics, ensure_ascii=False)}`.

{case_notes.get(row.id, 'Chưa có review nguồn cho run này; cần đối chiếu context/triples trước khi kết luận nguyên nhân gốc.')}
""")
    failure = '# Phân tích hai ca thực nghiệm\n\nGiữ nguyên điểm API Judge trong CSV. Review nguồn dưới đây là đánh giá bổ sung có hỗ trợ của Agent, không phải điểm Judge mới. Bằng chứng công khai: [failure_case_traces.json](../outputs/failure_case_traces.json), [coref_spotcheck.csv](../outputs/coref_spotcheck.csv) và [diagnostic_initial_case.json](../outputs/diagnostic_initial_case.json).\n\n' + '\n'.join(cases)
    overall = summary[summary['Loại câu hỏi'].eq('ALL')]
    latency = overall[overall.Metric.eq('Latency (s)')].iloc[0]
    tokens = overall[overall.Metric.eq('Token usage')].iloc[0]
    technical = f"""# Thuyết minh kỹ thuật — Lab 19

Học viên: Vũ Duy Diệp. Ngày: {datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date().isoformat()}.

1. **Coreference:** chỉ thay đại từ khi antecedent rõ trong cùng chunk; numeric guard khôi phục văn bản gốc nếu số bị thay. Trường hợp đã log trong lần chạy này:

{markdown_table(changed[['chunk_id', 'coref_status', 'original_text', 'resolved_text']])}

Trong chunk này, “the smart home manufacturer” chỉ Aqara, nhưng model thay bằng Samsung, tạo câu Samsung làm việc với Samsung. Guard số không bắt được lỗi ngữ nghĩa này. Triple cuối vẫn là Samsung `PARTNERED_WITH` Aqara vì extractor lấy evidence từ title gốc; không có bằng chứng false edge từ chunk này đã đi vào graph. Chunk `69178d0227a0ff6c4b24::c0000` còn thay “the company” bằng tên sản phẩm PolsoTM; không có triple được chấp nhận. Nếu tin rewrite mà bỏ evidence gốc, các lỗi này có thể gán sai chủ thể hoặc mất cạnh sau lọc self-loop.

200 chunks: 178 unchanged, 21 text rewrites và 1 rejected; `resolved` không bảo đảm một đại từ đã được phân giải đúng vì có cả sửa dấu câu. Spot-check 5 trường hợp có nhận xét trong `coref_spotcheck.csv`. Numeric guard reject `144366` → `144,366` ở `82639690c6f0f9db3de3::c0000`: giá trị không đổi nhưng cách biểu diễn khác. Cần chuẩn hóa số trước kiểm tra và thêm semantic validation cho antecedent.

2. **Ngưỡng entity:** cosine ≥0.90 trên embeddings normalized, HNSW candidates, guard theo tên/type và hậu tố; Union-Find canonicalization. Precision được ưu tiên vì false merge làm lan cạnh sai.

3. **Cặp bị guard chặn với similarity >0.85:** audit corpus thật có {len(audit)} candidate pairs, similarity lớn nhất {audit.similarity.max():.4f}; tất cả dưới ngưỡng nên được giữ riêng. Không có merge hoặc reject-guard cao để viện dẫn từ corpus này.

{markdown_table(rejected)}

Fixture tên riêng dưới đây dùng **embedding MiniLM thật**, được lưu tách khỏi 282 dòng audit corpus; không tính thành kết quả extraction/ER dữ liệu thật. Guard subset trả false khi một tên chỉ là phần của tên dài hơn. Bảng ghi cả threshold và decision: nếu similarity chưa tới 0.90 thì pipeline reject ở threshold, dù guard cũng không cho gộp.

{markdown_table(fixture)}

Guard này ưu tiên tránh false merge nhưng có thể false split tên đầy đủ/alias. Threshold 0.90 là cấu hình baseline, chưa được hiệu chỉnh từ nhãn ER trên toàn bộ HackerNoon.

4. **Top 3 degree thực đo:**

{markdown_table(top)}

5. **Ưu tiên cạnh mới:** degree >100 giới hạn 50 cạnh mới nhất, tổng ≤250 và context ≤14.000 ký tự. Giảm context/latency nhưng có thể loại mất cạnh lịch sử; truy vấn theo thời gian cần policy riêng. Fixture integration và graph thật được báo cáo tách biệt.

6. **Flat và Graph theo nhóm:**

{markdown_table(summary)}

Các số liệu thuộc sample được tuyển chọn theo nguồn và {len(evaluation)} Golden queries; không suy rộng thành chất lượng trên toàn bộ dataset. Flat dùng top 6, Hybrid dùng graph + top 4; graph có tối đa 400 chunks extraction.
Corpus lần chạy này dùng `{manifest.get('text_kind', 'article_text')}` từ dữ liệu nguồn. Với title/description, kết quả đo khả năng nối thông tin trong tiêu đề và mô tả ngắn; corpus không được mở rộng bằng đáp án Golden. Cấu hình reasoning: `{manifest.get('reasoning_effort', 'provider default')}`.
Phạm vi thực đo: {manifest['raw_rows']} bản ghi nguồn, {manifest['articles']} bài được chọn, {manifest['chunks']} chunks trong vector index và {manifest['extraction_chunks']} chunks cho graph extraction.

7. **Ca lỗi và giới hạn kết luận chất lượng:** các điểm Judge cuối đều 5/5 nhưng review G5000-29 phát hiện số tổng không được snippets hỗ trợ. G5000-26 có `NO_SEED` và graph context rỗng; Hybrid trả lời được nhờ vector. Lần diagnostic trước có Flat nhầm nhóm tháng 9 là tổng số, Judge Flat 1/Graph 5, nhưng Graph vẫn suy diễn số tổng. Không có ca đã kiểm chứng đủ để kết luận graph tự nó sửa được lỗi Flat. Xem `failure_analysis.md` và trace; không chọn riêng lần chạy tốt để khẳng định Graph thắng. Generator và Judge cùng Groq model nên không phải phép đánh giá độc lập.

8. **Latency/token:** latency chính bao gồm retrieval + generation và loại Judge; token online Graph bao gồm seed extraction + generation. `usage_log.json` ghi request phát sinh trong phiên; cache replay không phát sinh request nên không được đếm lại. `offline_usage_summary.json` tổng hợp usage gốc của 25 coref + 25 extraction batches: 43.215 + 50.244 = 93.459 tokens, không nằm trong token/query online. Embedding chạy local CPU. Missing usage giữ trạng thái thiếu; bài nộp không quy đổi tokens thành giá tiền.

Trung bình cuối: Flat {latency['Flat RAG']:.3f}s, Hybrid {latency['GraphRAG']:.3f}s (Δ {latency['Delta Graph - Flat']:.3f}s); Flat {tokens['Flat RAG']:.1f} tokens/query, Hybrid {tokens['GraphRAG']:.1f} (Δ {tokens['Delta Graph - Flat']:.1f}). Với sample nhỏ này, Hybrid tăng token mà chưa có lợi thế chất lượng được review xác nhận. Latency chịu ảnh hưởng mạng, quota/retry và thứ tự gọi, không thể quy toàn bộ chênh lệch cho BFS. Cache replay giữ latency của request đo ban đầu, không đo lại tốc độ đọc cache.

9. **Kiểm soát AI Agent:** trong phiên thực hiện, người dùng đã chọn dùng Groq cho cả pipeline và Judge sau khi cân nhắc OpenAI/Gemini. Cấu hình cuối dùng chung Groq key và ghi model/reasoning trong manifest; đây là quyết định đơn giản hóa cấu hình, không phải bằng chứng hai Judge khác nhau có chất lượng tương đương. Các biện pháp kiểm chứng thêm gồm HNSW thay cho ma trận pairwise toàn corpus, kiểm tra allowlist/evidence và giữ điểm benchmark đúng với request thật.

10. **Scale 350MB:** đo bottleneck trước khi scale; LLM extraction có thể bị rate limit/chi phí và indexing tăng theo số chunks. Dùng streaming, durable worker queue, batch/retry/resume, HNSW + blocking theo type, ingestion UNWIND và graph partitioning. Không gửi toàn bộ dữ liệu qua LLM trong timebox lab.
"""
    reflection = """# Reflection và Action Plan — Vũ Duy Diệp

| Khái niệm | Module | Hàm implementation | Quan sát |
|---|---|---|---|
| Coreference bảo thủ | 1 | `resolve_coref_batch`, `run_coref` | Prompt và numeric guard chưa bắt lỗi Samsung/Aqara |
| Schema và evidence guard | 2 | `extract_batch`, `run_extraction` | 52 triples được chấp nhận; 10 candidates bị reject |
| Bulk ingestion | 2 | `bulk_insert_nodes`, `bulk_insert_edges` | UNWIND, namespace; chạy lại không tăng 52 edges |
| Entity resolution | 3 | `build_resolution_map`, `merge_guard`, `UF` | 282 ANN pairs dưới ngưỡng; fixture tách riêng |
| Super-node mitigation | 4 | `retrieve_graph_context`, `recent_edges` | Graph thật max degree 3; fixture 120 → 50 |
| LLM Judge | 5 | `judge_answer`, `run_evaluation` | 5 queries đủ 3 nhóm; Judge vẫn bỏ sót claim số tổng |
| Flat RAG và Hybrid GraphRAG | 4 | `build_flat_index`, `answer_flat_rag`, `answer_graph_rag` | Hybrid G5000-26 được vector cứu khi NO_SEED |
| Reproducibility và provenance | 1–5 | `prepare_corpus`, fingerprint, manifest, checkpoints | Snapshot nguồn, config, trace và latency request gốc |

## Bài học debug từ phiên lab

Các lỗi sau có trong quá trình thực hiện lab với sự hỗ trợ của Agent:

1. `pytest tests/test_base.py` báo không tìm thấy file và `jupyter` chưa được nhận diện. Cần kiểm tra cấu trúc repo và interpreter của `.venv`; sau đó bổ sung tests/dependencies còn thiếu và gọi Jupyter qua Python của môi trường đó. Một lệnh có trong hướng dẫn chưa chứng minh file/gói tương ứng đã tồn tại.
2. Có `HF_TOKEN` vẫn chưa tải được dataset vì tài khoản cần chấp nhận điều kiện truy cập. Docker cũng cần daemon/container và kết nối driver hoạt động. Bài học là kiểm tra từng lớp: credential → quyền truy cập → dịch vụ → request thực tế.
3. CSV HackerNoon có `title` và `description`, còn loader ban đầu tìm `text/content/body`. Đã sửa fallback theo schema thật, giữ tiêu đề làm evidence và ghi `title_and_description` trong manifest. Không suy diễn mô tả ngắn thành toàn bộ bài báo.
4. Model Groq mặc định trả HTTP 404. Đã kiểm tra danh sách model theo key, dùng model truy cập được và thử request JSON. Đồng thời chọn Groq cho cả generator/Judge để dùng chung key; kết luận benchmark vẫn phụ thuộc model và quota được ghi nhận.

Đối với kết quả, source row index cần được đối chiếu bằng URL/title/date, tên file Golden không xác định số câu thực tế và latency phải bao gồm retrieval + generation. Tôi cần đọc rationale, context và provenance trước khi kết luận một phương pháp tốt hơn.

Review còn phát hiện coreference Samsung/Aqara bị sai nhưng evidence từ title cứu triple, cùng Judge bỏ sót suy diễn số tổng ở G5000-29. Provenance đầy đủ cho biết nguồn ở đâu; nó không tự chứng minh quan hệ hoặc câu trả lời đúng. Khi triển khai, cần kiểm tra antecedent, trạng thái sự kiện (ví dụ agreed-to-acquire khác completed acquisition) và từng claim số đếm.

## Action Plan dự kiến: trợ lý học tập

Đây là phương án ứng dụng được đề xuất khi chưa chốt đồ án cá nhân. Kế hoạch dưới đây mô tả việc sẽ làm, không khẳng định hệ thống đã được triển khai.

- **Dữ liệu dự kiến:** slide môn học, ghi chú, README và notebook được phép sử dụng; lưu môn học, buổi học, trang/cell và nguồn ở từng chunk.
- **Câu hỏi mẫu:** “Để hiểu GraphRAG, tôi cần ôn những khái niệm nào và đọc tài liệu ở đâu?”; “Khái niệm entity resolution liên quan đến bước nào của pipeline trong notebook?”.
- **Tuần 1:** chuẩn hóa tài liệu và làm baseline Flat RAG; lập 20 câu Golden có nguồn, gồm factoid, multi-hop và cross-doc; cố định tập đánh giá trước khi thử graph.
- **Tuần 2:** nếu câu hỏi cần nối quan hệ giữa tài liệu, thử schema Môn học–Khái niệm–Tài liệu với quan hệ HAS_TOPIC, PREREQUISITE_OF và EXPLAINED_IN; có evidence, alias/guard, giới hạn hops và degree cap. Giữ cùng corpus/generator cho hai baseline.
- **ER và supernode:** tên khái niệm cần kèm môn học/ngữ cảnh để tránh gộp từ đồng âm; chỉ dùng alias do người soạn xác nhận. Nếu node “AI” liên kết quá nhiều tài liệu, lọc môn/buổi học trước BFS rồi lấy cạnh theo relevance; dùng date cap như lab làm baseline nhưng không bỏ tài liệu nền tảng chỉ vì cũ.
- **Đánh giá:** đo ba điểm Judge 1–5 cùng rationale, latency P50/P95, token/query và tỷ lệ câu trả lời có nguồn. Review thủ công ít nhất hai ca sai; kiểm tra trích dẫn có hỗ trợ đúng khẳng định.
- **Quyết định triển khai:** ưu tiên Flat RAG cho truy vấn tìm một đoạn kiến thức. Chỉ giữ graph nếu các câu cần nối quan hệ có cải thiện đo được và chi phí vận hành phù hợp; không giả định GraphRAG luôn thắng.
"""
    for name, text in [('technical_defense.md', technical), ('failure_analysis.md', failure),
                       ('reflection_VuDuyDiep.md', reflection),
                       ('lab_report.md', technical + '\n\n' + failure + '\n\n' + reflection)]:
        (reports / name).write_text('\n'.join(line.rstrip() for line in text.splitlines()).rstrip() + '\n', encoding='utf-8')
    for name in ['graphrag_eval_results.csv', 'graphrag_vs_flatrag_summary.csv']:
        shutil.copy2(lab.OUTPUTS / name, reports / name)
