# Báo cáo Day 19 — Flat RAG vs GraphRAG

**Họ tên:** Vũ Duy Điệp · **MSSV:** 2A202602703 · **Ngày chạy cuối:** 06/10/2026

Bộ đề: `LAB_GUIDE.md` và `SUBMISSION.md` của VinUni. Kết quả lấy từ `ket_qua_benchmark_kg.txt`, sinh trực tiếp bằng `python bench_kg.py --judge`. Dùng ontology gợi ý, không đăng ký bonus. Thiết kế chi tiết: [ONTOLOGY.md](ONTOLOGY.md).

Corpus có 18 Điều luật và 20 bài báo, tạo 176 chunk (`chunk_size=800`, `top_k=3`). Graph cuối có **181 node / 346 cạnh**. Cả hai pipeline dùng **Groq `openai/gpt-oss-20b`** và embedding local `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`; Judge dùng cùng model Groq. Tên model có tiền tố `openai/` nhưng endpoint và key đều là Groq.

## 1. Chi phí

Hai bảng dưới đây giữ nguyên từ file benchmark:

```text
== Indexing (one-off)
pipeline  calls    in_tok  out_tok       USD  seconds
flat        176         0        0   0.00000      7.8
graph       196     37646     3839   0.00398    242.6

== Querying (mean per question)
pipeline  recall  judge   in_tok  out_tok       USD  seconds
flat        0.23   0.33      824      149   0.00011     6.84
graph       0.54   1.50     2834      205   0.00027    21.76
```

| Chỉ số | Flat | Graph | Graph / Flat |
| --- | ---: | ---: | ---: |
| Indexing USD | 0,00000 | 0,00398 | Không xác định: Flat = 0 |
| Indexing giây | 7,8 | 242,6 | 31,10× |
| Mỗi câu: USD | 0,00011 | 0,00027 | 2,45× |
| Mỗi câu: giây | 6,84 | 21,76 | 3,18× |
| Mỗi câu: in_tok | 824 | 2.834 | 3,44× |

Tỉ lệ được tính từ số đã làm tròn trong bảng xuất. Giá USD là **ước tính theo token**, theo [bảng giá Groq](https://console.groq.com/docs/models) kiểm tra ngày 05/10/2026: GPT-OSS 20B có giá niêm yết 0,075 USD/triệu input token và 0,30 USD/triệu output token. Đây không phải hóa đơn hoặc xác nhận số tiền bị trừ; lượt chạy dùng quota tài khoản hiện có. Embedding local không có phí/token API, nhưng vẫn tốn CPU và thời gian. `calls=176` của Flat là 176 thao tác embedding local; Graph thêm 20 lần gọi chat trích tin. Nạp model lần đầu nằm ngoài đồng hồ indexing của script.

Chi phí dựng graph tăng chủ yếu ở trích xuất tin bằng LLM: **37.646 input + 3.839 output token**. Luật được trích bằng regex. Chi phí truy vấn tăng vì chèn thêm facts: Graph có input trung bình gấp 3,44 lần Flat. Thời gian đo gồm embedding truy vấn, Cypher, gọi sinh đáp án, network và chờ/retry API; không phải thời gian tính toán thuần. Các lượt Judge không được tính trong hai bảng pipeline, dù cũng sử dụng quota.

Theo số đã làm tròn, tổng cho 6 câu gồm indexing và generation là khoảng **0,00066 USD** với Flat và **0,00560 USD** với Graph, chưa tính Judge, CPU/điện hoặc vận hành Neo4j. Nếu chi phí mỗi câu vẫn cao hơn như lần đo này, không có điểm hòa vốn chỉ xét phí API: `C_flat(N) ≈ 0,00011N`; `C_graph(N) ≈ 0,00398 + 0,00027N`. Giá trị của câu trả lời tốt hơn phải bù chi phí tăng thêm; không thể kết luận chỉ từ “graph rẻ dần khi có nhiều câu”.

## 2. Từng câu hỏi

Recall là phép kiểm substring của bộ đề; Judge chấm 0–2. Cột thắng cân nhắc nội dung và chi phí, không chỉ recall.

| Câu | Loại | Flat recall / judge | Graph recall / judge | Thắng | Vì sao |
| --- | --- | --- | --- | --- | --- |
| Q1 | single-hop-law | 0,00 / 0 | 1,00 / 2 | Graph | Flat nói không đủ thông tin; routing luật PCMT bổ sung đúng định nghĩa tiền chất. |
| Q2 | single-hop-news | 1,00 / 2 | 1,00 / 2 | Flat về chi phí | Cả hai nêu đúng Trần Thanh Tuấn và Trần Minh Tâm; Flat mất 6,99 giây, Graph 22,02 giây. |
| Q3 | cross-kb | 0,00 / 0 | 0,00 / 2 | Graph về nội dung | Graph nêu đúng 36 tháng, Điều 251 và khung 2–7 năm; recall sai lệch vì định dạng, xem E4. |
| Q4 | cross-kb | 0,00 / 0 | 0,67 / 2 | Graph | Nối vụ Hoàng Nato sang Điều 255, trả mức tối đa 20 năm hoặc chung thân; Unicode làm mất một keyword. |
| Q5 | cross-kb-multi-hop | 0,40 / 0 | 0,60 / 0 | Chưa bên nào đúng | Flat bịa Điều 12 và mức bồi thường; Graph có Điều 250 nhưng chọn nhầm khoản 3, xem E5. |
| Q6 | aggregation | 0,00 / 0 | 0,00 / 1 | Graph một phần | Graph nhận ra vụ Cái Quang Huy nhưng tách trùng thành hai mục và bỏ các vụ còn lại; chưa đạt tính đầy đủ. |

Q1 cho thấy graph/routing có thể cứu cả câu single-hop khi vector top-k bỏ sót nguồn: audit retrieval trả các tài liệu BLHS 253, 254 và 250, không có `pcmt-dieu-2`. Q3–Q4 cần nối tin với luật; Graph tăng điểm Judge. Q2 có đáp án gọn trong một bài nên thêm graph không tăng chất lượng. Q5–Q6 cho thấy graph có dữ liệu vẫn chưa đủ để bảo đảm suy luận số học và tổng hợp đầy đủ.

## 3. Phân tích lỗi

### E3 — Trùng thực thể chất do khác chữ hoa/thường

- **Hiện tượng:** cùng tên Ketamine thành hai node, làm phân mảnh các cạnh INVOLVES.
- **Bằng chứng:** chạy trên graph cuối:

```cypher
MATCH (s:Substance)
WITH toLower(s.name) AS normalized, collect(s.name) AS names, count(*) AS nodes
WHERE nodes > 1
RETURN normalized, names, nodes;
```

```text
normalized  names                      nodes
ketamine    ["Ketamine", "ketamine"]    2
```

```cypher
MATCH (k:Case)-[:INVOLVES]->(s:Substance)
WHERE toLower(s.name) = 'ketamine'
RETURN s.name AS name, count(DISTINCT k) AS cases;
```

```text
Ketamine  3
ketamine  1
```

- **Nguyên nhân:** `add_news_case` MERGE Substance theo chuỗi `name` nguyên trạng; constraint UNIQUE phân biệt hoa/thường. `link_entity` đang chuẩn hóa tội danh, chưa được áp dụng cho tên chất trước khi ghi graph.
- **Đề xuất sửa:** thêm khóa chất chuẩn hóa Unicode/chữ thường và alias có kiểm chứng trong `src/graph.py`, áp dụng ở cả nạp luật và tin. Không tự gộp mọi tên đường phố thành một chất hóa học. Đánh đổi là phải quản lý danh sách alias và có thể gộp nhầm nếu chuẩn hóa quá rộng.

### E4 — Recall bằng 0 dù Q3 trả lời đúng

- **Hiện tượng:** Q3 Graph có recall 0,00 nhưng Judge 2; đọc nội dung thấy các ý chính khớp nguồn.
- **Bằng chứng:** nguyên văn đáp án Q3 Graph trong file kết quả:

> **Lê Minh Thành** bị tuyên **36 tháng tù** (tức 3 năm) **về tội mua bán trái phép chất ma túy**.
> Tội này được quy định tại **Điều 251 Bộ luật Hình sự** (tội mua bán trái phép chất ma túy).
> Khung hình phạt cơ bản của điều này là **từ 2 năm đến 7 năm tù** (khoản 1).

So sánh chuỗi thực tế:

```text
"36\u202ftháng"                 ≠ "36 tháng"
"Điều\u202f251"                 ≠ "Điều 251"
"2\u202fnăm đến 7\u202fnăm"     ≠ "02 năm đến 07 năm"
```

- **Nguyên nhân:** `keyword_recall` chỉ lower rồi tìm substring. Khoảng trắng hẹp U+202F không bằng dấu cách U+0020; số có/không có zero đầu cũng không khớp. Q4 và tên Cái Quang Huy trong Q6 gặp vấn đề tương tự. Recall thô không đo đúng mức độ đầy đủ nội dung trong những trường hợp này.
- **Đề xuất sửa:** trong một phép đánh giá bổ sung, chuẩn hóa Unicode, whitespace và cách biểu diễn số, rồi chấm các ý cần có; vẫn giữ Judge và đọc tay. Không sửa `bench_kg.py` để tăng điểm bộ đề. Toàn bộ recall trong báo cáo này giữ nguyên từ benchmark.

### E5 — Q5 suy luận sai ngưỡng dù context có khoản đúng

- **Hiện tượng:** Graph cho MDMA hơn 9,6 kg thuộc khoản 3 Điều 250, khung 15–20 năm; Judge chấm 0. Flat cũng sai và bịa một căn cứ pháp luật ngoài corpus.
- **Bằng chứng:** Q5 Graph viết:

> Trong trường hợp này, tổng khối lượng MDMA (9,6 kg) vượt xa 30 g, vì vậy **điều 250 khoản 3** được áp dụng.

Graph thực tế có khoản 4:

```cypher
MATCH (a:Article {id:'Điều 250 BLHS'})-[:HAS_CLAUSE]->(cl:Clause {number:4})
RETURN a.id, cl.number, cl.penalty, cl.text;
```

```text
Điều 250 BLHS | 4 | phạt tù 20 năm, tù chung thân hoặc tử hình
b) Heroine, Cocaine, Methamphetamine, Amphetamine, MDMA hoặc XLR-11
   có khối lượng 100 gam trở lên;
```

Tái tạo retrieval bằng cùng embedding, chunk_size=800, top_k=3 và graph cuối cho Q5 trả **25 facts / 4.961 ký tự**; context thực sự có dòng `[Điều 250 BLHS ...] khoản 4` và điểm b trên. Vì vậy không phải chỉ có graph nhưng thiếu hoàn toàn khoản đúng trong prompt. Theo snapshot luật của bộ đề, 9,6 kg = 9.600 gam, vượt ngưỡng 100 gam; khoản 3 có cận trên dưới 100 gam.

- **Nguyên nhân:** LLM chỉ so với cận dưới 30 gam, bỏ cận trên và khoản 4. Ontology giữ amount/text dạng chuỗi, chưa có bước chuẩn hóa đơn vị và lựa chọn khoản bằng rule; lời văn tự tin không chứng minh suy luận đúng.
- **Đề xuất sửa:** trích ngưỡng số và đơn vị thành thuộc tính có cấu trúc, đổi kg sang gam, kiểm tra cả hai cận bằng code trước khi đưa kết luận vào prompt. Khi dữ liệu/điều kiện không đủ thì không tự kết luận khoản. Đánh đổi là thêm parser và kiểm thử cho nhiều chất, nhiều đơn vị, các điều kiện phối hợp; không thể chỉ sửa prompt là bảo đảm đúng.

**Giới hạn riêng Q6:** Cypher `MATCH (k:Case)-[:INVOLVES]->(:Substance {name:'MDMA'}) RETURN k.name, k.doc_id` trả 4 Case, gồm vụ Cái Quang Huy, vụ Lê Minh Thành và hai bài về Viện Pháp y tâm thần. Tuy nhiên context Q6 có 18 facts / 8.976 ký tự và **không còn cạnh INVOLVES MDMA nào**: tóm tắt và các khoản luật đứng trước đã chiếm ngân sách ký tự. Các tóm tắt còn lại không nêu rõ MDMA, nên thông tin xác nhận membership bị mất. Cần routing aggregation để ưu tiên `Case–INVOLVES–MDMA`, giảm luật không liên quan và gộp vụ theo ID ổn định. Kết quả hiện tại chưa chứng minh Graph trả lời aggregation đầy đủ.

## 4. Kết luận

Trong lần đo này, Graph tăng Judge trung bình từ **0,33 lên 1,50/2**, recall thô từ **0,23 lên 0,54**. Với Q3–Q5 xuyên KB, Judge trung bình của Graph khoảng **1,33**, Flat **0,00**; nhưng Q5 vẫn sai nên không thể nói mọi câu multi-hop đã được giải quyết. Q3 còn chứng minh cần đọc đáp án, vì recall 0 không đồng nghĩa sai nội dung.

KG đáng cân nhắc khi câu hỏi cần nối người/vụ trong tin sang tội/Điều/khoản trong luật, có cầu nối chuẩn và có cách kiểm tra câu trả lời. Với Q2 đáp án nằm trong một bài, Flat đã đạt Judge 2 và rẻ/nhanh hơn; dùng Graph ở đó chưa có lợi về chất lượng. Cần chấp nhận chi phí dựng thêm **0,00398 USD ước tính và khoảng 234,8 giây**, cùng mỗi câu chậm hơn trung bình **14,92 giây** trong lần đo có chờ API này.

Chưa nên dùng các đáp án này như kết luận pháp lý tự động: Q5 sai ngưỡng và Q6 bỏ sót dù graph có dữ liệu. Corpus chỉ có 20 bài, luật là snapshot của bộ đề, Judge cùng model với generator và chỉ có 6 câu; chưa có phép đo lặp để kết luận ưu thế chung hoặc latency ổn định. Embedding local có max_seq_length=128 trong khi chunking theo 800 ký tự, cũng là một giới hạn retrieval cần đánh giá riêng.

## 5. Tự kiểm

```text
$ python -m pytest tests/ -q
................................................                         [100%]
48 passed in 0.09s

$ python bench_kg.py --check
[OK] Dữ liệu: 18 điều luật, 20 bài báo
[OK] KG-1 link_entity
[OK] Neo4j kết nối được
[provider] chat = groq:openai/gpt-oss-20b | embedding = local:sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
[OK] KG-2 build_graph: 145 node / 288 cạnh, đường xuyên 2 KB dài 2 cạnh
[OK] KG-3 context: 16 dữ kiện, có Điều 251
[OK] KG-4 GraphRAGAgent.answer
[OK] Chi phí check: 1 lần gọi LLM, $0.00030. Graph nhỏ (luật + 1 bài) vẫn còn trong Neo4j để bạn xem; chạy --judge để dựng graph đầy đủ.
```

`--check` dùng luật + 1 bài nên số node/cạnh khác graph đầy đủ. Sau check đã chạy lại `--judge` thành công và chụp ảnh trên graph đầy đủ. Có **0 Article/Clause/Case thiếu doc_id**, **51 đường Person→Case→Crime←Article** trong graph cuối. Label/cạnh kiểm trực tiếp khớp ONTOLOGY.md:

```text
Nodes: Clause=99, Person=24, Article=18, Substance=14, Crime=13, Case=9, Location=4.
Relationships: MENTIONS=169, HAS_CLAUSE=99, INVOLVED_IN=27, INVOLVES=15,
               CHARGED_WITH=14, DEFINES=13, LOCATED_IN=9.
```

Ảnh nộp: [kg_count.png](img/kg_count.png), [kg_cross_kb.png](img/kg_cross_kb.png), [kg_my_case.png](img/kg_my_case.png). Người chọn: **Cái Quang Huy**, có đường tới **Điều 250 BLHS**. Ba ảnh chụp graph cuối 181 node / 346 cạnh; giữ nguyên các file ảnh do học viên chụp.

## Vấn đề gặp phải

Bắt đầu từ nhầm bộ repo notebook HackerNoon; đã chuyển sang đúng repo `K4-Track3-Day19-GraphRAG-Knowledge-Graphs`. Bản notebook cũ và graph cũ được sao lưu local. File benchmark, 41 test base, 7 test graph và code base chunking/store/agent/embeddings/models giữ nguyên từ repo mẫu; chỉ thêm provider Groq/local vào `src/llm.py` và triển khai `src/graph.py`.

Model `llama-3.3-70b-versatile` không xuất hiện trong danh sách model mà key truy cập được. Lần chạy GPT-OSS 120B dừng ở Q5 vì quota TPD=200.000 (`Used 194888, Requested 8158`). Lần chạy 20B đầu dừng ở Q5 vì TPM=8.000 (`Requested 8021`). Sau đó giới hạn context và lọc vụ theo người; chạy lại toàn bộ cùng 20B. Hai lần lỗi không được trộn vào bảng kết quả cuối. Quota/network làm latency biến động; không suy diễn các số giây trên thành tốc độ Cypher thuần.

Đã chụp đủ ba ảnh và tắt container bằng `docker stop neo4j-drug-kg`. Link repo phải được nộp lên trang vlearn của lớp sau khi chốt bài.
