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
