# Reflection và Action Plan — Vũ Duy Diệp

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

1. `pytest tests/test_base.py` báo không tìm thấy file và `jupyter` chưa được nhận diện. Cần kiểm tra cấu trúc repo và interpreter của `.venv`; sau đó bổ sung dependencies và kiểm tra bằng tests local và gọi Jupyter qua Python của môi trường đó. Một lệnh có trong hướng dẫn chưa chứng minh file/gói tương ứng đã tồn tại.
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
