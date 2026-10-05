# Thuyết minh kỹ thuật — Lab 19

Học viên: Vũ Duy Diệp. Ngày: 2026-10-05.

1. **Coreference:** chỉ thay đại từ khi antecedent rõ trong cùng chunk; numeric guard khôi phục văn bản gốc nếu số bị thay. Trường hợp đã log trong lần chạy này:

| chunk_id | coref_status | original_text | resolved_text |
| --- | --- | --- | --- |
| 8e74089254231622e67f::c0000 | resolved | SDC23: Samsung and Aqara Partners to Demonstrate Presence Sensor FP2 on SmartThings Platform. The FP2 Presence Sensor is Aqara''s latest occupancy sensor with precise human presence detection and the smart home manufacturer has been working with Samsung to add the SmartThings compatibility to the sensor | SDC23: Samsung and Aqara Partners to Demonstrate Presence Sensor FP2 on SmartThings Platform. The FP2 Presence Sensor is Aqara's latest occupancy sensor with precise human presence detection and Samsung has been working with Samsung to add the SmartThings compatibility to the sensor |

Trong chunk này, “the smart home manufacturer” chỉ Aqara, nhưng model thay bằng Samsung, tạo câu Samsung làm việc với Samsung. Guard số không bắt được lỗi ngữ nghĩa này. Triple cuối vẫn là Samsung `PARTNERED_WITH` Aqara vì extractor lấy evidence từ title gốc; không có bằng chứng false edge từ chunk này đã đi vào graph. Chunk `69178d0227a0ff6c4b24::c0000` còn thay “the company” bằng tên sản phẩm PolsoTM; không có triple được chấp nhận. Nếu tin rewrite mà bỏ evidence gốc, các lỗi này có thể gán sai chủ thể hoặc mất cạnh sau lọc self-loop.

200 chunks: 178 unchanged, 21 text rewrites và 1 rejected; `resolved` không bảo đảm một đại từ đã được phân giải đúng vì có cả sửa dấu câu. Spot-check 5 trường hợp có nhận xét trong output section 5.1 notebook. Numeric guard reject `144366` → `144,366` ở `82639690c6f0f9db3de3::c0000`: giá trị không đổi nhưng cách biểu diễn khác. Cần chuẩn hóa số trước kiểm tra và thêm semantic validation cho antecedent.

2. **Ngưỡng entity:** cosine ≥0.90 trên embeddings normalized, HNSW candidates, guard theo tên/type và hậu tố; Union-Find canonicalization. Precision được ưu tiên vì false merge làm lan cạnh sai.

3. **Cặp bị guard chặn với similarity >0.85:** audit corpus thật có 282 candidate pairs, similarity lớn nhất 0.6835; tất cả dưới ngưỡng nên được giữ riêng. Không có merge hoặc reject-guard cao để viện dẫn từ corpus này.

Không có bản ghi phù hợp trong lần chạy này.

Fixture tên riêng dưới đây dùng **embedding MiniLM thật**, được lưu tách khỏi 282 dòng audit corpus; không tính thành kết quả extraction/ER dữ liệu thật. Guard subset trả false khi một tên chỉ là phần của tên dài hơn. Bảng ghi cả threshold và decision: nếu similarity chưa tới 0.90 thì pipeline reject ở threshold, dù guard cũng không cho gộp.

| data_kind | type | left | right | similarity | guard_passed | threshold_passed | decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| synthetic name-pair fixture; real MiniLM embeddings | Technology | Microsoft Windows 11 | Microsoft Windows 11 Pro | 0.8968769311904907 | False | False | REJECT_THRESHOLD |
| synthetic name-pair fixture; real MiniLM embeddings | Technology | Microsoft Windows 11 Pro | Microsoft Windows 11 Pro N | 0.9490051865577698 | False | True | REJECT_GUARD |

Guard này ưu tiên tránh false merge nhưng có thể false split tên đầy đủ/alias. Threshold 0.90 là cấu hình baseline, chưa được hiệu chỉnh từ nhãn ER trên toàn bộ HackerNoon.

4. **Top 3 degree thực đo:**

| id | name | type | degree |
| --- | --- | --- | --- |
| 18a2f0e496fb60f2b80e8775 | Google Cloud | Company | 3 |
| fc94d4789fde1f6e802475fd | L&T Technology Services | Company | 2 |
| 51e652cc3cb71d3060de600c | Thales | Company | 2 |

5. **Ưu tiên cạnh mới:** degree >100 giới hạn 50 cạnh mới nhất, tổng ≤250 và context ≤14.000 ký tự. Giảm context/latency nhưng có thể loại mất cạnh lịch sử; truy vấn theo thời gian cần policy riêng. Fixture integration và graph thật được báo cáo tách biệt.

6. **Flat và Graph theo nhóm:**

| Loại câu hỏi | Metric | Flat RAG | GraphRAG | Delta Graph - Flat | Sample count | Nhận xét phân tích |
| --- | --- | --- | --- | --- | --- | --- |
| cross-doc | Comprehensiveness | 5.0 | 5.0 | 0.0 | 2 | Hai phương pháp gần nhau. |
| cross-doc | Faithfulness | 5.0 | 5.0 | 0.0 | 2 | Hai phương pháp gần nhau. |
| cross-doc | Multi-hop reasoning | 5.0 | 5.0 | 0.0 | 2 | Hai phương pháp gần nhau. |
| cross-doc | Latency (s) | 1.075 | 6.058 | 4.983 | 2 | Flat RAG thường rẻ/nhanh hơn. |
| cross-doc | Token usage | 965.5 | 1201.0 | 235.5 | 2 | Flat RAG thường rẻ/nhanh hơn. |
| factoid | Comprehensiveness | 5.0 | 5.0 | 0.0 | 1 | Hai phương pháp gần nhau. |
| factoid | Faithfulness | 5.0 | 5.0 | 0.0 | 1 | Hai phương pháp gần nhau. |
| factoid | Multi-hop reasoning | 5.0 | 5.0 | 0.0 | 1 | Hai phương pháp gần nhau. |
| factoid | Latency (s) | 6.908 | 10.152 | 3.244 | 1 | Flat RAG thường rẻ/nhanh hơn. |
| factoid | Token usage | 854.0 | 1195.0 | 341.0 | 1 | Flat RAG thường rẻ/nhanh hơn. |
| multi-hop | Comprehensiveness | 5.0 | 5.0 | 0.0 | 2 | Hai phương pháp gần nhau. |
| multi-hop | Faithfulness | 5.0 | 5.0 | 0.0 | 2 | Hai phương pháp gần nhau. |
| multi-hop | Multi-hop reasoning | 5.0 | 5.0 | 0.0 | 2 | Hai phương pháp gần nhau. |
| multi-hop | Latency (s) | 4.257 | 3.018 | -1.239 | 2 | GraphRAG không đắt hơn trong sample này. |
| multi-hop | Token usage | 855.0 | 1151.0 | 296.0 | 2 | Flat RAG thường rẻ/nhanh hơn. |
| ALL | Comprehensiveness | 5.0 | 5.0 | 0.0 | 5 | Hai phương pháp gần nhau. |
| ALL | Faithfulness | 5.0 | 5.0 | 0.0 | 5 | Hai phương pháp gần nhau. |
| ALL | Multi-hop reasoning | 5.0 | 5.0 | 0.0 | 5 | Hai phương pháp gần nhau. |
| ALL | Latency (s) | 3.514 | 5.661 | 2.146 | 5 | Flat RAG thường rẻ/nhanh hơn. |
| ALL | Token usage | 899.0 | 1179.8 | 280.8 | 5 | Flat RAG thường rẻ/nhanh hơn. |

Các số liệu thuộc sample được tuyển chọn theo nguồn và 5 Golden queries; không suy rộng thành chất lượng trên toàn bộ dataset. Flat dùng top 6, Hybrid dùng graph + top 4; graph có tối đa 400 chunks extraction.
Corpus lần chạy này dùng `title_and_description` từ dữ liệu nguồn. Với title/description, kết quả đo khả năng nối thông tin trong tiêu đề và mô tả ngắn; corpus không được mở rộng bằng đáp án Golden. Cấu hình reasoning: `low`.
Phạm vi thực đo: 5000 bản ghi nguồn, 1500 bài được chọn, 1500 chunks trong vector index và 200 chunks cho graph extraction.

7. **Ca lỗi và giới hạn kết luận chất lượng:** các điểm Judge cuối đều 5/5 nhưng review G5000-29 phát hiện số tổng không được snippets hỗ trợ. G5000-26 có `NO_SEED` và graph context rỗng; Hybrid trả lời được nhờ vector. Lần diagnostic trước có Flat nhầm nhóm tháng 9 là tổng số, Judge Flat 1/Graph 5, nhưng Graph vẫn suy diễn số tổng. Không có ca đã kiểm chứng đủ để kết luận graph tự nó sửa được lỗi Flat. Xem `failure_analysis.md` và trace; không chọn riêng lần chạy tốt để khẳng định Graph thắng. Generator và Judge cùng Groq model nên không phải phép đánh giá độc lập.

8. **Latency/token:** latency chính bao gồm retrieval + generation và loại Judge; token online Graph bao gồm seed extraction + generation. Usage log local ghi request phát sinh trong phiên; cache replay không phát sinh request nên không được đếm lại. Thống kê checkpoint local tổng hợp usage gốc của 25 coref + 25 extraction batches: 43.215 + 50.244 = 93.459 tokens, không nằm trong token/query online. Embedding chạy local CPU. Missing usage giữ trạng thái thiếu; bài nộp không quy đổi tokens thành giá tiền.

Trung bình cuối: Flat 3.514s, Hybrid 5.661s (Δ 2.146s); Flat 899.0 tokens/query, Hybrid 1179.8 (Δ 280.8). Với sample nhỏ này, Hybrid tăng token mà chưa có lợi thế chất lượng được review xác nhận. Latency chịu ảnh hưởng mạng, quota/retry và thứ tự gọi, không thể quy toàn bộ chênh lệch cho BFS. Cache replay giữ latency của request đo ban đầu, không đo lại tốc độ đọc cache.

9. **Kiểm soát AI Agent:** trong phiên thực hiện, người dùng đã chọn dùng Groq cho cả pipeline và Judge sau khi cân nhắc OpenAI/Gemini. Cấu hình cuối dùng chung Groq key và ghi model/reasoning trong output notebook cùng manifest local; đây là quyết định đơn giản hóa cấu hình, không phải bằng chứng hai Judge khác nhau có chất lượng tương đương. Các biện pháp kiểm chứng thêm gồm HNSW thay cho ma trận pairwise toàn corpus, kiểm tra allowlist/evidence và giữ điểm benchmark đúng với request thật.

10. **Scale 350MB:** đo bottleneck trước khi scale; LLM extraction có thể bị rate limit/chi phí và indexing tăng theo số chunks. Dùng streaming, durable worker queue, batch/retry/resume, HNSW + blocking theo type, ingestion UNWIND và graph partitioning. Không gửi toàn bộ dữ liệu qua LLM trong timebox lab.


# Phân tích hai ca thực nghiệm

Giữ nguyên điểm API Judge trong CSV. Review nguồn là đánh giá bổ sung có hỗ trợ của Agent, không phải điểm Judge mới. Context, diagnostics, coref spot-check và diagnostic trước được trình bày trong section 5.1 của notebook.

### G5000-29 — cross-doc

**Câu hỏi:** How did participation in White House AI commitments broaden from July to September 2023 according to the selected reports?

**Reference đã đối chiếu:** The July report names seven companies including Google, Meta, and OpenAI as making voluntary AI commitments. The September report says IBM, Adobe, Salesforce, and five more companies made similar safety, security, and transparency commitments, explicitly noting similarity to the July pledges by OpenAI and others.

**Flat answer:** The July 2023 report notes that **seven** technology firms – among them Google, Meta and OpenAI – had voluntarily signed the White House’s AI‑management commitments [chunk_id=9781172d2260895c1d09::c0000].

By mid‑September 2023 the list had expanded: **IBM, Adobe, Salesforce and five additional companies** had also joined the pledge, increasing the group of signatories to at least twelve firms [chunk_id=8d2f8b148829f4949b97::c0000].

Thus, participation grew from a core of seven companies in July to a broader coalition of roughly a dozen companies by September 2023.

**Graph answer:** In July 2023 the White House AI‑safety pledge was signed by a core group of **seven** firms – notably Google, Meta and OpenAI (among others) 【chunk_id=9781172d2260895c1d09::c0000】.

By September 12 2023 the roster had expanded: **IBM, Adobe, Salesforce and five additional tech companies** had also joined the voluntary safety, security and transparency commitments 【chunk_id=8d2f8b148829f4949b97::c0000】.

Thus, participation broadened from the original seven companies in July to at least **ten‑plus** firms by mid‑September, adding major players such as IBM, Adobe and Salesforce.

**Judge Flat:** The answer accurately captures the July report's seven companies and the September report's expanded list of IBM, Adobe, Salesforce, and five additional firms, reflecting the growth from seven to roughly twelve signatories. It stays faithful to the provided context and correctly reasons about the increase without omission.

**Judge Graph:** The answer correctly lists the July report’s seven companies (Google, Meta, OpenAI) and the September report’s additional firms (IBM, Adobe, Salesforce, plus five others), matching the reference. It accurately describes the expansion from the original seven to ten‐plus participants and notes the similarity of commitments, fully covering the required information with correct reasoning.

**Diagnostics thực đo:** `{"matched_seeds": [{"id": "40eaff37be8d25234181dcf4", "name": "OpenAI", "type": "Company"}, {"id": "1000af1bd14546d856b4e884", "name": "Microsoft", "type": "Company"}, {"id": "a0a7f532292b4c926208e970", "name": "Amazon", "type": "Company"}, {"id": "305f47a325c69a6635b03f52", "name": "Apple", "type": "Company"}], "expanded_nodes": 8, "collected_edges": 4, "supernode_events": []}`.

**Triệu chứng và kết luận review:** Flat suy ra “roughly a dozen”; Graph thêm “ten-plus”. Hai đoạn nguồn chỉ nêu nhóm tháng 7 có 7 công ty và nhóm tháng 9 gồm IBM, Adobe, Salesforce cùng 5 công ty khác. Chúng không liệt kê đủ hai roster để tính union. Các số tổng phát sinh không được dẫn chứng trực tiếp, dù Judge chấm cả hai 5/5 ở cả ba trục. Điểm 5 ở đây không chứng minh mọi luận điểm đều faithful.

**Truy vết:** cả Flat top 6 và Hybrid top 4 đều chứa `9781172d2260895c1d09::c0000` (21/07/2023, cosine 0.548) và `8d2f8b148829f4949b97::c0000` (12/09/2023, 0.524). Không thiếu hai nguồn thiết yếu. Graph thu 4 cạnh về AP–OpenAI, Microsoft–Viasat, Amazon–Cohere và Apple–Vision Pro; chúng không biểu diễn việc ký cam kết Nhà Trắng. Không có supernode event. Lỗi tổng số nằm ở generation và chưa bị Judge phát hiện; việc thiếu quan hệ cam kết trong schema làm graph không giúp phép đối chiếu này. Chưa có ablation để kết luận context nhiễu gây ra lỗi.

**Câu trả lời được nguồn hỗ trợ:** “Tháng 7 có 7 công ty, trong đó có Google, Meta và OpenAI. Tháng 9, nhóm ký các cam kết tương tự gồm IBM, Adobe, Salesforce và 5 công ty khác; điều này cho thấy phạm vi tham gia rộng hơn. Các snippets không đủ roster để xác nhận tổng số công ty duy nhất.”

**Khắc phục đề xuất:** tách cohort/date khỏi cumulative count; chỉ tính tổng khi có danh sách thành viên và kiểm tra giao hai tập. Bổ sung kiểm tra claim–evidence cho số đếm trong Judge và review người dùng. Nếu mở rộng schema, dùng sự kiện `Commitment` và `SIGNED` có ngày, thay vì ép thành `PARTNERED_WITH`. Các thay đổi này chưa được benchmark trong bài nộp. Câu trả lời và điểm Judge của lần diagnostic đầu được ghi rõ trong section 5.1 notebook; không dùng nó để thay điểm CSV cuối.

### G5000-26 — multi-hop

**Câu hỏi:** What external technology provider is named inside Amazon's July AI-service expansion, and what other new AI capability is mentioned alongside it?

**Reference đã đối chiếu:** Amazon's AI-service story names access to technology from Cohere. It also mentions a program for building more conversational customer-service agents; one follow-up additionally mentions a healthcare system for generating clinical notes after patient visits.

**Flat answer:** The July expansion references the external provider **Cohere** – Amazon added “technology access from the startup Cohere” – and alongside it announced a new **health‑care system that can generate clinical notes after a patient visit**【chunk_id=613de2c24d2456048c08::c0000】.

**Graph answer:** The July expansion of Amazon’s AI service references the external technology provider **Cohere** — the startup whose technology is being used to build more conversational customer‑service agents 【chunk_id=613de2c24d2456048c08::c0000】.
Alongside this, Amazon also announced a new **health‑care system that can generate clinical notes after a patient visit** 【chunk_id=ae3e878731488df141c0::c0000】.

**Judge Flat:** The candidate correctly identifies Cohere as the external technology provider and the healthcare system that generates clinical notes, matching the reference. It fully covers both required pieces, stays faithful to the supplied context, and requires no complex multi‐hop reasoning beyond linking the two facts, which it does accurately.

**Judge Graph:** The candidate correctly identifies Cohere as the external technology provider and accurately mentions the new healthcare system that generates clinical notes, matching the reference. All required information is present and faithful to the supplied context, with no reasoning errors.

**Diagnostics thực đo:** `{"reason": "NO_SEED", "supernode_events": []}`.

**Triệu chứng:** graph diagnostics trả `NO_SEED`, không có cạnh/context graph, dù graph corpus có cạnh Amazon `USES` Cohere tại `613de2c24d2456048c08::c0000`. Đây là lỗi thành phần graph retrieval; câu trả lời Hybrid cuối vẫn đúng nhờ vector fallback cố định top 4.

**Truy vết:** các vector chunks top 4 chứa bản 26/07 bị cắt ở “healthcare ...” và bản 27/07 `ae3e878731488df141c0::c0000` có đầy đủ clinical notes. Vì vậy lỗi không nằm ở thiếu corpus hoặc supernode cap. Điểm cuối 5/5 không đo riêng đóng góp của graph. Trace chỉ lưu kết quả sau matching, chưa lưu danh sách seed LLM trước matching; chưa thể phân biệt LLM không trích xuất Amazon với resolver từ chối tên/type. Không khẳng định nguyên nhân sâu hơn khi thiếu log.

**Khắc phục đề xuất:** log raw seeds, exact/fuzzy candidates, similarity và lý do reject; bổ sung fallback nhận diện tên/alias có sẵn trong query và kiểm thử Amazon/Amazon Web Services. Đo ablation graph-only, vector-only và hybrid trên cùng token budget. Chưa triển khai các thay đổi retrieval này trong benchmark hiện tại.


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
