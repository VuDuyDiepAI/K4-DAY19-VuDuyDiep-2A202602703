# Submission — Day 19 Knowledge Graph

## 1. Nộp gì

Repo GitHub **cá nhân**, đặt tên `K4-DAY19-HoVaTen-MSSV`. Nộp link repo lên vlearn.

```
K4-DAY19-HoVaTen-MSSV/
├── src/graph.py                 ← đã hoàn thành KG-1..KG-4
├── ket_qua_benchmark_kg.txt     ← output của: python bench_kg.py --judge
└── report/
    ├── ONTOLOGY.md              ← bản thiết kế ontology (BẮT BUỘC, kể cả khi dùng ontology gợi ý)
    ├── REPORT_KG.md             ← điền theo template có sẵn
    └── img/
        ├── kg_count.png         ← truy vấn Q-A (LAB_GUIDE 8.1)
        ├── kg_cross_kb.png      ← truy vấn Q-B theo ontology của bạn (LAB_GUIDE 8.1)
        └── kg_my_case.png       ← truy vấn Q-D với người bạn tự chọn
```

**Không** được có trong repo: `.env`, API key ở bất kỳ file nào, `.venv/`.

## 2. Kỳ vọng đầu ra

### Code

| Lệnh | Kỳ vọng |
| --- | --- |
| `pytest tests/ -q` | `48 passed` (41 base + 7 graph) |
| `python bench_kg.py --check` | 7 dòng `[OK]`, không có `[LỖI …]` |

`--check` kiểm theo **hợp đồng** (`doc_id` trên node, có đường đi xuyên 2 KB, `context()` trả về Điều luật), **không** theo tên label. Ontology nào cũng qua được nếu đúng hợp đồng.

### Bản thiết kế (`report/ONTOLOGY.md`)

| Mục | Kỳ vọng tối thiểu | Bài tốt thường có thêm |
| --- | --- | --- |
| Sơ đồ, entity, relationship | Đủ mọi label và quan hệ **thật sự có** trong graph của bạn | Property được chọn có chủ đích, không thừa |
| Node cầu nối | Chỉ ra node nào, vì sao, khi nào gãy | Có cơ chế xử lý khi gãy |
| Competency questions | Đường đi cho cả 6 câu | Chỉ ra câu nào ontology không trả lời được và lý do |
| Quyết định thiết kế | 3 quyết định, mỗi cái có phương án thay thế | Liên hệ với lỗi tìm được ở Bước 8 |

Bản thiết kế phải **khớp với graph thật**: người chấm chạy `MATCH (n) RETURN DISTINCT labels(n)` và `MATCH ()-[r]->() RETURN DISTINCT type(r)` rồi so với bản thiết kế.

### Benchmark (`ket_qua_benchmark_kg.txt`)

- Chạy **với** `--judge`, đủ 3 phần: `Indexing`, `Querying`, `Per question`.
- File **sinh ra từ code của bạn**: số node/rel ở dòng đầu, số chunk, số liệu phải khớp với báo cáo.
- Kỳ vọng định tính: trên các câu `cross-kb`, GraphRAG có `recall` cao hơn Flat RAG. Không đạt thì vẫn nộp, nhưng báo cáo phải giải thích vì sao.

### Báo cáo (`report/REPORT_KG.md`)

| Mục | Kỳ vọng tối thiểu | Bài tốt thường có thêm |
| --- | --- | --- |
| 1. Chi phí | 2 bảng copy từ file kết quả; tỉ lệ Graph/Flat cho indexing và mỗi câu hỏi | Tách được chi phí tăng thêm đến từ đâu (trích xuất? prompt dài hơn?), ước tính điểm hòa vốn theo số câu hỏi |
| 2. Từng câu | Bảng Q1–Q6: recall, judge, bên thắng, 1 câu lý do | Liên hệ "loại câu hỏi" với "bên thắng" thành một quy luật |
| 3. Phân tích lỗi | ≥ 2 nhóm lỗi trong E1–E6, mỗi lỗi đủ 4 phần: hiện tượng, bằng chứng, nguyên nhân, đề xuất sửa | Chỉ ra lỗi nằm ở bước nào của pipeline, kể cả ở chính thiết kế ontology |
| 4. Kết luận | Khi nào nên dùng KG, khi nào Flat RAG đủ, dẫn số liệu của mình | Nêu điều kiện cụ thể (loại dữ liệu, loại câu hỏi, số lượng câu hỏi) |
| 5. Tự kiểm | Dán output `pytest` và `--check` | |

**Bằng chứng** nghĩa là người chấm đọc vào kiểm chứng được: trích nguyên văn câu trả lời (ghi rõ câu Qx, pipeline nào), hoặc Cypher kèm kết quả trả về. Câu như "graph có vẻ bị trùng node" mà không kèm truy vấn thì **không** tính là bằng chứng.

## 3. Thang điểm (100 + bonus 15)

| # | Hạng mục | Điểm | Cách chấm |
| --- | --- | --- | --- |
| 1 | KG-1, KG-4 | 10 | `pytest tests/test_graph.py`: 7 test, mỗi test fail trừ 2 điểm (tối thiểu 0) |
| 2 | KG-2, KG-3 | 15 | `--check`: có `[OK] KG-2` → 7, có `[OK] KG-3` → 8 |
| 3 | Base không bị phá | 5 | `pytest tests/test_base.py` → `41 passed` |
| 4 | Bản thiết kế `ONTOLOGY.md` | 15 | Đủ 6 mục đầu, khớp với graph thật. Không nộp → 0 điểm mục này **và** không xét bonus |
| 5 | File benchmark hợp lệ | 5 | Đủ 3 phần, có `judge`, khớp số liệu báo cáo |
| 6 | Báo cáo mục 1: Chi phí | 10 | |
| 7 | Báo cáo mục 2: Từng câu | 10 | |
| 8 | Báo cáo mục 3: Phân tích lỗi | 20 | 10 điểm/lỗi, tối đa 2 lỗi. Thiếu bằng chứng: tối đa 3/10 cho lỗi đó |
| 9 | Báo cáo mục 4: Kết luận | 5 | Có dẫn số liệu → đủ điểm; chỉ nêu cảm tính → tối đa 2 |
| 10 | 3 ảnh Neo4j | 5 | Đúng quy cách ở LAB_GUIDE 8.2: thấy ô truy vấn và Results overview. Thiếu hoặc sai mỗi ảnh trừ 2 điểm |
| | **Tổng** | **100** | |
| ★ | **Bonus: tự thiết kế ontology** | **+15** | Xem dưới |

### Bonus +15: tự thiết kế ontology

Điều kiện để được xét:
- Ontology **khác ontology gợi ý một cách có chủ đích**. Đổi tên label hoặc tên quan hệ thì **không** tính.
- Mục 7 trong `ONTOLOGY.md` được điền đủ.
- Code dựng đúng ontology đó, và `--check` đạt `[OK] KG-2` + `[OK] KG-3`.

| Tiêu chí | Điểm |
| --- | --- |
| Mỗi điểm khác so với gợi ý **giải quyết một vấn đề cụ thể** (ví dụ: giảm trùng thực thể, mô hình hóa ngưỡng khối lượng, tách giai đoạn tố tụng, gộp tên chất đồng nghĩa) | 6 |
| Có **bằng chứng** cải thiện: Cypher trước/sau, hoặc số liệu benchmark trước/sau. Nộp kèm file kết quả của ontology gợi ý, đặt tên `ket_qua_benchmark_kg.hint.txt` | 6 |
| Competency questions: ontology mới trả lời được câu mà ontology gợi ý trả lời sai hoặc thiếu (chỉ rõ câu nào) | 3 |

Tổng điểm tối đa là **115**.

### Trừ điểm và điểm liệt

| Vi phạm | Hậu quả |
| --- | --- |
| Commit `.env` hoặc API key (kể cả đã xóa ở commit sau, vì vẫn còn trong lịch sử git) | **−20** và phải thu hồi key ngay |
| Số liệu trong báo cáo không khớp `ket_qua_benchmark_kg.txt`, hoặc không có file này | Mục 1, 2, 4 của báo cáo = **0** |
| File benchmark không sinh từ code trong repo (sửa tay, chép của người khác) | Hạng mục 5 và mục 1, 2, 4 của báo cáo = **0** |
| Sửa test hoặc `bench_kg.py` để test/check pass | Hạng mục 1–3 = **0** |
| `ONTOLOGY.md` mô tả ontology khác với graph thật | Hạng mục 4 = **0**, không xét bonus |
| Báo cáo hoặc bản thiết kế giống bài khác | Cả hai bài = **0** phần tương ứng |

## 4. Checklist trước khi nộp

```bash
pytest tests/ -q                   # 48 passed
python bench_kg.py --check         # 7 [OK]
python bench_kg.py --judge         # sinh lại ket_qua_benchmark_kg.txt từ code cuối cùng
git status                         # .env KHÔNG được xuất hiện
git log --all -p | grep "sk-"      # PHẢI không ra gì
```

- [ ] `src/graph.py` không còn `raise NotImplementedError`
- [ ] `report/ONTOLOGY.md` đủ mục, khớp với graph thật (label và quan hệ)
- [ ] `ket_qua_benchmark_kg.txt` có cột `judge` khác `-`
- [ ] `report/REPORT_KG.md` đủ 5 mục, số liệu khớp file kết quả
- [ ] Phân tích ít nhất 2 lỗi, mỗi lỗi có bằng chứng
- [ ] Có 3 ảnh trong `report/img/`, mỗi ảnh thấy được ô truy vấn
- [ ] (Bonus) Điền mục 7 `ONTOLOGY.md`, nộp kèm `ket_qua_benchmark_kg.hint.txt`
- [ ] Repo tên `K4-DAY19-HoVaTen-MSSV`, đã push, link đã nộp lên vlearn
- [ ] Đã tắt Neo4j nếu không dùng nữa: `docker stop neo4j-drug-kg`
