"""Export source-backed review notes; never change the raw Judge scores."""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab19_support import write_json

evaluation = pd.read_csv(ROOT / 'outputs/graphrag_eval_results.csv')
run_id = evaluation.run_id.iloc[0]
assert evaluation.run_id.nunique() == 1
count_case = evaluation[evaluation.id.eq('G5000-29')].iloc[0]
assert 'roughly a dozen' in count_case.flat_answer and 'ten' in count_case.graph_answer, \
    'These review notes describe the observed final run; review new answers before regenerating them.'
traces = {}
for query_id in ['G5000-29', 'G5000-26']:
    trace = ROOT / 'outputs/.cache' / f'trace_{run_id}_{query_id}.json'
    traces[query_id] = json.loads(trace.read_text(encoding='utf-8'))

notes = {
    'G5000-29': """**Triệu chứng và kết luận review:** Flat suy ra “roughly a dozen”; Graph thêm “ten-plus”. Hai đoạn nguồn chỉ nêu nhóm tháng 7 có 7 công ty và nhóm tháng 9 gồm IBM, Adobe, Salesforce cùng 5 công ty khác. Chúng không liệt kê đủ hai roster để tính union. Các số tổng phát sinh không được dẫn chứng trực tiếp, dù Judge chấm cả hai 5/5 ở cả ba trục. Điểm 5 ở đây không chứng minh mọi luận điểm đều faithful.

**Truy vết:** cả Flat top 6 và Hybrid top 4 đều chứa `9781172d2260895c1d09::c0000` (21/07/2023, cosine 0.548) và `8d2f8b148829f4949b97::c0000` (12/09/2023, 0.524). Không thiếu hai nguồn thiết yếu. Graph thu 4 cạnh về AP–OpenAI, Microsoft–Viasat, Amazon–Cohere và Apple–Vision Pro; chúng không biểu diễn việc ký cam kết Nhà Trắng. Không có supernode event. Lỗi tổng số nằm ở generation và chưa bị Judge phát hiện; việc thiếu quan hệ cam kết trong schema làm graph không giúp phép đối chiếu này. Chưa có ablation để kết luận context nhiễu gây ra lỗi.

**Câu trả lời được nguồn hỗ trợ:** “Tháng 7 có 7 công ty, trong đó có Google, Meta và OpenAI. Tháng 9, nhóm ký các cam kết tương tự gồm IBM, Adobe, Salesforce và 5 công ty khác; điều này cho thấy phạm vi tham gia rộng hơn. Các snippets không đủ roster để xác nhận tổng số công ty duy nhất.”

**Khắc phục đề xuất:** tách cohort/date khỏi cumulative count; chỉ tính tổng khi có danh sách thành viên và kiểm tra giao hai tập. Bổ sung kiểm tra claim–evidence cho số đếm trong Judge và review người dùng. Nếu mở rộng schema, dùng sự kiện `Commitment` và `SIGNED` có ngày, thay vì ép thành `PARTNERED_WITH`. Các thay đổi này chưa được benchmark trong bài nộp. Trace lần chạy đầu được giữ riêng trong `diagnostic_initial_case.json`; không dùng nó để thay điểm CSV cuối.""",
    'G5000-26': """**Triệu chứng:** graph diagnostics trả `NO_SEED`, không có cạnh/context graph, dù graph corpus có cạnh Amazon `USES` Cohere tại `613de2c24d2456048c08::c0000`. Đây là lỗi thành phần graph retrieval; câu trả lời Hybrid cuối vẫn đúng nhờ vector fallback cố định top 4.

**Truy vết:** các vector chunks top 4 chứa bản 26/07 bị cắt ở “healthcare ...” và bản 27/07 `ae3e878731488df141c0::c0000` có đầy đủ clinical notes. Vì vậy lỗi không nằm ở thiếu corpus hoặc supernode cap. Điểm cuối 5/5 không đo riêng đóng góp của graph. Trace chỉ lưu kết quả sau matching, chưa lưu danh sách seed LLM trước matching; chưa thể phân biệt LLM không trích xuất Amazon với resolver từ chối tên/type. Không khẳng định nguyên nhân sâu hơn khi thiếu log.

**Khắc phục đề xuất:** log raw seeds, exact/fuzzy candidates, similarity và lý do reject; bổ sung fallback nhận diện tên/alias có sẵn trong query và kiểm thử Amazon/Amazon Web Services. Đo ablation graph-only, vector-only và hybrid trên cùng token budget. Chưa triển khai các thay đổi retrieval này trong benchmark hiện tại.""",
}
write_json(ROOT / 'outputs/evidence_review.json', {
    'run_id': run_id, 'review_method': 'Agent-assisted source and trace review; not a second Judge run',
    'case_notes': notes, 'raw_judge_scores_modified': False,
})
write_json(ROOT / 'outputs/failure_case_traces.json', {'run_id': run_id, 'cases': traces})

coref = pd.read_csv(ROOT / 'outputs/coref_audit.csv').fillna('')
checks = {
    '8e74089254231622e67f::c0000': 'Sai: smart home manufacturer là Aqara; rewrite thành Samsung working with Samsung. Triple cuối vẫn Samsung–Aqara nhờ evidence từ title gốc.',
    '69178d0227a0ff6c4b24::c0000': 'Sai: the company bị thay bằng sản phẩm PolsoTM khi tên công ty chưa có trong snippet. Không có triple được chấp nhận từ chunk này.',
    'dcaa0ba4dc9d6a046c47::c0000': 'Hợp lý: its -> Synopsys; foundry -> TSMC theo câu/title trong cùng chunk.',
    '809b337a488d409aeebb::c0000': 'Hợp lý: he -> Mike Dixon, được nêu ngay trước đó.',
    '82639690c6f0f9db3de3::c0000': 'Guard reject do 144366 đổi thành 144,366. Giá trị số không đổi; đây là false positive vì so sánh token số theo chuỗi.',
}
spotcheck = coref[coref.chunk_id.isin(checks)].copy()
spotcheck['review_note'] = spotcheck.chunk_id.map(checks)
spotcheck.to_csv(ROOT / 'outputs/coref_spotcheck.csv', index=False)

offline = {}
for stage in ['coref', 'extract']:
    files = sorted((ROOT / 'outputs/.cache').glob(stage + '_*.json'))
    assert len(files) == 25, 'Review cache scope before aggregating a different offline configuration.'
    usage = [json.loads(path.read_text(encoding='utf-8'))['usage'] for path in files]
    offline[stage] = {'cached_batches': len(files),
                      **{field: sum(item[field] for item in usage)
                         for field in ['prompt_tokens', 'completion_tokens', 'total_tokens']}}
write_json(ROOT / 'outputs/offline_usage_summary.json', {
    'scope': '200 selected extraction chunks, batch 8; original measured responses, counted once',
    'model': 'openai/gpt-oss-120b', 'provider': 'groq', 'reasoning_effort': 'low',
    'stages': offline, 'total_tokens': sum(item['total_tokens'] for item in offline.values()),
    'cache_replay_is_new_api_usage': False,
})

# Preserve a prior observed failure without selecting it as the final benchmark.
initial_id = '2b7b5ef7a40b3cbfb9a86bc063936f6a7cdca560a13caf698dcf6f8bbc62fca9'
prior = ROOT / 'outputs/.cache' / f'trace_{initial_id}_G5000-29.json'
if prior.exists():
    previous = json.loads(prior.read_text(encoding='utf-8'))
    import lab19_runtime as lab
    from lab19_support import cache_path
    def existing_only(stage, payload, callback):
        path = cache_path(stage, payload)
        if not path.exists():
            raise RuntimeError('Prior Judge cache is absent; no new request is permitted here.')
        return json.loads(path.read_text(encoding='utf-8'))
    lab.cached_json = existing_only
    row = evaluation[evaluation.id.eq('G5000-29')].iloc[0]
    prior_judges = {system: lab.judge_answer(row.question, row.reference_answer,
                    previous[system]['answer'], previous[system]['context']) for system in ['flat', 'graph']}
    write_json(ROOT / 'outputs/diagnostic_initial_case.json', {
        'run_id': initial_id, 'id': row.id, 'label': 'earlier diagnostic run, excluded from final summary',
        'question': row.question, 'reference_answer': row.reference_answer,
        'trace': previous, 'judges': prior_judges,
        'review': 'Flat confused September cohort size with cumulative total (7 to 8). Graph avoided that claim but added an unsupported cumulative bound. Raw Judge gave Flat 1 and Graph 5; this difference alone does not prove Graph is correct.',
    })
print('Review artifacts exported; raw evaluation CSV unchanged.')
