# Phân tích hai ca thực nghiệm

Giữ nguyên điểm API Judge trong CSV. Review nguồn dưới đây là đánh giá bổ sung có hỗ trợ của Agent, không phải điểm Judge mới. Bằng chứng công khai: [failure_case_traces.json](../outputs/failure_case_traces.json), [coref_spotcheck.csv](../outputs/coref_spotcheck.csv) và [diagnostic_initial_case.json](../outputs/diagnostic_initial_case.json).

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

**Khắc phục đề xuất:** tách cohort/date khỏi cumulative count; chỉ tính tổng khi có danh sách thành viên và kiểm tra giao hai tập. Bổ sung kiểm tra claim–evidence cho số đếm trong Judge và review người dùng. Nếu mở rộng schema, dùng sự kiện `Commitment` và `SIGNED` có ngày, thay vì ép thành `PARTNERED_WITH`. Các thay đổi này chưa được benchmark trong bài nộp. Trace lần chạy đầu được giữ riêng trong `diagnostic_initial_case.json`; không dùng nó để thay điểm CSV cuối.

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
