# Trạng thái thực hiện workflow — Lab 19

Ngày thực hiện: 05/10/2026, Asia/Saigon. Pipeline và notebook đã chạy với dữ liệu/API thật.

| Bước | Kết quả | Bằng chứng trong outputs/ |
|---|---|---|
| W0: môi trường | Neo4j Docker, Groq generator/Judge hoạt động; dùng chung Groq key | preflight_status.csv |
| W1: corpus | 5.000 rows HackerNoon; revision cc6144ccce683dcebb6e63f9a50ca084544af1c0 | corpus_download.json, corpus_manifest.json |
| W2: preprocessing | 2.695 rows sau chuẩn hóa → 2.119 exact-dedup → 1.500 bài/1.500 vector chunks | preprocessing_stats.csv, chunk_manifest.csv |
| W2: coreference | 200 chunks; 178 unchanged, 21 rewritten, 1 rejected; spot-check 5 chunks | coref_audit.csv, coref_spotcheck.csv |
| W3: extraction/ER | 52 triples hợp lệ; 10 candidates rejected; 282 ANN audit pairs được giữ riêng | extraction_errors.csv, entity_resolution_audit.csv |
| W3: graph | Namespace cuối có 97 nodes, 52 edges, 0 thiếu provenance; Run All không nhân đôi edges | graph_sanity.csv, run_manifest.json |
| W4: mitigation | Graph thật max degree 3, chưa kích hoạt supernode cap; fixture hub 120 giữ 50 cạnh mới nhất | supernode_status.json, neo4j_fixture_verification.json |
| W5: benchmark | 5 queries: 1 factoid, 2 multi-hop, 2 cross-doc; đủ nguồn ở corpus/vector/extraction | golden_coverage.csv, hai CSV kết quả |
| W6: báo cáo | Technical defense 10 câu; hai failure cases; Reflection và Action Plan đề xuất trợ lý học tập | Các báo cáo trong reports/ |
| Restart & Run All | 22 code cells, 0 errors, 0 PENDING | notebook_execution.json |
| Regression | 40 tests pass; script báo cáo/evidence được compile và kiểm tra artifact | final_validation.json |

Corpus dùng title + description ngắn, không phải full article body. Sample được chọn theo nguồn Golden đã đối chiếu, không phải tập kiểm định ngẫu nhiên độc lập. Reference answers không được đưa vào ingestion hay generation.

Raw Judge cuối chấm cả hai 5/5 ở ba trục. Flat trung bình 3.514s và 899 tokens/query; Hybrid 5.661s và 1.179,8 tokens/query. Review G5000-29 phát hiện số tổng công ty không được snippets hỗ trợ đầy đủ, dù Judge cho điểm cao. G5000-26 không có seed graph và được vector top 4 cứu. Chưa có bằng chứng graph tạo lợi thế chất lượng trong sample này; latency chịu ảnh hưởng mạng/quota/thứ tự gọi.

Coref/extraction dùng 93.459 tokens offline đã đo và được cache; không tính vào online tokens/query. Cache replay giữ latency request gốc và không được đếm thành request mới. Fixture ER/supernode được ghi riêng, không dùng làm benchmark corpus.

Secrets chỉ ở .env đã gitignore. Corpus tải xuống và cache không commit; hai CSV cần nộp có bản sao trong cả outputs/ và reports/. Các giới hạn, lỗi và khắc phục đề xuất được nêu trong báo cáo; các khắc phục chưa thử không được ghi là đã triển khai. Bonus chỉ là scaffold, không tự nhận điểm.

Action Plan là ví dụ cho dự án tương lai khi chưa chốt đồ án cá nhân. Học viên đọc lại phần này trước khi dùng làm kế hoạch của mình. Trạng thái commit/push được xác minh qua Git; học viên gửi link repo cho giảng viên.

Chạy lại từ PowerShell tại repo:

```powershell
.\.venv\Scripts\python.exe scripts\run_lab.py --stage run
.\.venv\Scripts\python.exe scripts\execute_notebook.py
.\.venv\Scripts\python.exe scripts\check_artifacts.py
```

Các lệnh tái sử dụng checkpoint có cùng fingerprint. Đổi corpus/model/prompt tạo run khác; phải review lại answers và failure notes cho run mới.
