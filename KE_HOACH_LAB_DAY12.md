**Lab buổi 12 — Tổng hợp kiến thức và kế hoạch thực hiện**

Mục tiêu: đưa một API AI từ localhost lên URL HTTPS công khai, có xác thực, giới hạn tốc độ, kiểm soát chi phí, chia sẻ lịch sử giữa các instance và xử lý shutdown đúng cách. Mock LLM đã được cung cấp; không cần mua API key của nhà cung cấp LLM.

Nguồn: [README.md](/Users/phanducduy/Desktop/ml+dl/AI_20k/K4-L3A-PhanDucDuy-2A202602397Cloud-Service-And-Deployment/README.md), [LAB_GUIDE.md](/Users/phanducduy/Desktop/ml+dl/AI_20k/K4-L3A-PhanDucDuy-2A202602397Cloud-Service-And-Deployment/LAB_GUIDE.md), [CHECKPOINTS.md](/Users/phanducduy/Desktop/ml+dl/AI_20k/K4-L3A-PhanDucDuy-2A202602397Cloud-Service-And-Deployment/CHECKPOINTS.md), [RUBRIC.md](/Users/phanducduy/Desktop/ml+dl/AI_20k/K4-L3A-PhanDucDuy-2A202602397Cloud-Service-And-Deployment/RUBRIC.md), mã khung và bộ test. Đây là tài liệu học và kế hoạch, chưa phải kết quả chạy kiểm chứng bài làm.

**Điểm xuất phát đã kiểm tra ngày 28/09/2026**

- Python 3.12.10 đáp ứng yêu cầu Python 3.11+.
- Có Docker CLI; kiểm tra Docker server báo không tìm thấy socket. Cần bật Docker Desktop hoặc Docker runtime đang sử dụng.
- Settings chưa có sáu trường; 15 hàm trong app còn ném NotImplementedError.
- Dockerfile đang một stage; Compose chỉ có Redis; .dockerignore thiếu mục bắt buộc.
- DEPLOYMENT.md còn placeholder, exercises.md chưa trả lời, screenshots chưa có ảnh.
- Git working tree sạch khi kiểm tra; .env không được theo dõi trong index hiện tại. Chưa kiểm tra toàn bộ lịch sử Git hay chạy pytest.

**Kiến thức cần nắm**

1. **12-Factor và config.** Code giữ nguyên giữa local và cloud; cấu hình thay đổi theo môi trường nằm trong biến môi trường. Lab vận dụng config, process stateless, logs, concurrency và disposability; không yêu cầu triển khai toàn bộ 12 nguyên tắc.

   Sáu biến: PORT, AGENT_API_KEY, REDIS_URL, RATE_LIMIT_PER_MINUTE, MONTHLY_BUDGET_USD, LOG_LEVEL. Các cấu hình thường có thể có mặc định; secret phải được cung cấp rõ ràng. Fail fast nghĩa là thiếu cấu hình thì phát hiện ngay khi startup. Cần xác nhận Settings được khởi tạo lúc startup, thay vì chỉ đọc ở request đầu tiên.

   .env phục vụ local và không commit; .env.example mô tả biến với giá trị mẫu. Trên cloud, secret nằm trong dashboard/secret store.

2. **FastAPI, validation và log.** FastAPI nhận HTTP; Pydantic kiểm tra input; Depends ghép auth, limiter, guard và store. Trong khung bài, question dài 1–2.000 ký tự; dữ liệu không hợp lệ trả 422.

   Một event log là một dòng JSON stdout, có event, level, timestamp UTC; log /ask thêm user_id, token input/output và cost_usd. Nhờ đó có thể lọc lỗi, thống kê sử dụng và tổng hợp chi phí. Không ghi secret vào log.

3. **Docker và Compose.** Image là gói môi trường chạy; container là instance đang chạy. Multi-stage tách build/cài dependency khỏi runtime; stage cuối chỉ mang thành phần cần chạy. Copy requirements và cài thư viện trước khi copy source giúp dùng lại cache khi sửa code.

   Dùng image slim, user thường, .dockerignore và healthcheck. Mục tiêu image dưới 500 MB phải đo thật. Non-root giảm quyền tiến trình; một lỗi Python không tự động đồng nghĩa có quyền root trên host.

   Uvicorn bind 0.0.0.0 và đọc PORT. Trong Compose, redis://redis:6379/0 dùng hostname service; localhost trong container trỏ về chính container đó.

4. **Ba lớp bảo vệ API.** API key xác nhận quyền gọi service. X-User-Id trong lab là nhãn client gửi để chia quota/history, chưa phải danh tính được xác thực riêng.

| Cơ chế | Kiểm soát | Kết quả |
|---|---|---|
| API key | Quyền gọi API | Thiếu/sai key → 401; dùng secrets.compare_digest |
| Sliding window | Số request trong 60 giây gần nhất | Vượt quota → 429 và Retry-After |
| Cost guard | Chi tiêu theo user/tháng | Vượt ngân sách theo quy tắc lab → 402 |

Fixed window 10/phút có thể cho qua 10 request cuối phút và 10 request đầu phút kế tiếp. Sliding window tránh kẽ hở đó. Redis Sorted Set lưu timestamp: xóa entry cũ → đếm entry còn lại → nếu còn quota thì thêm request mới. Member phải duy nhất, tránh ghi đè khi trùng timestamp.

Chi phí mô phỏng phụ thuộc cả input và output:

```text
chi phí = token_input / 1000 × giá_input
        + token_output / 1000 × giá_output
```

Giá trong mock_llm là giá giả lập của bài. History càng dài càng tăng input; giới hạn history cũng giúp kiểm soát chi phí.

5. **Redis và stateless.** State cần chia sẻ không nằm riêng trong RAM từng instance. Mọi agent dùng chung Redis để thấy cùng history, quota và chi tiêu.

| Dữ liệu | Key | Cấu trúc / thao tác | Giới hạn |
|---|---|---|---|
| Rate limit | `ratelimit:<user>` | Sorted Set; ZREMRANGEBYSCORE, ZCARD, ZADD | TTL 60 giây |
| Chi phí | `cost:<user>:<YYYY-MM>` | Giá trị số; GET, INCRBYFLOAT | TTL 40 ngày; tháng theo UTC |
| History | `history:<user>` | List JSON; RPUSH, LRANGE, LTRIM | 20 message; TTL 7 ngày |

Một lần hỏi ghi hai message: user và assistant. Với user mới, history_length lần lượt 0, 2, 4… vì response lấy độ dài lịch sử trước lượt hiện tại; sau đó dừng ở 20.

fake:// dành cho học/test. Trong khung bài, mỗi get_redis_client(fake://) tạo một FakeRedis riêng; nó không chứng minh chia sẻ state giữa container. Thử scaling bằng Redis thật.

6. **Health, readiness và shutdown.**

| Trạng thái | /health | /ready |
|---|---|---|
| Process hoạt động, Redis truy cập được | 200 | 200 |
| Process hoạt động, Redis lỗi | 200 | 503 |
| Đang shutdown, endpoint còn phục vụ | 503 theo yêu cầu lab | 503 |

/health kiểm tra process, không gọi Redis. /ready kiểm tra có nhận traffic được không, được gọi Redis. Platform/load balancer cần được cấu hình sử dụng probe phù hợp; tạo endpoint chưa tự rút traffic khỏi instance.

Docker HEALTHCHECK đánh dấu healthy/unhealthy; việc tự restart phụ thuộc runtime/orchestrator. [Dockerfile reference](https://docs.docker.com/reference/dockerfile/#healthcheck)

Graceful shutdown: nhận SIGTERM/SIGINT → đánh dấu shutting_down → phối hợp rút traffic → để Uvicorn hoàn tất request đang chạy và thoát. Handler của bài phải gọi lại handler cũ nếu callable. Nếu dùng shell mở rộng PORT, cần chuyển tiếp signal đúng; exec giúp Uvicorn nhận signal trực tiếp. [Docker ENTRYPOINT](https://docs.docker.com/reference/dockerfile/#entrypoint)

7. **Cloud và CI/CD.** Deploy đạt khi URL HTTPS gọi được, /health và /ready đúng, /ask có auth, environment đúng và có bằng chứng chạy thật. Build thành công chưa đủ.

   CI chạy test/build khi có thay đổi. CD đưa bản đã kiểm tra lên cloud. GitHub Actions cần needs để deploy phụ thuộc các job kiểm tra; chỉ deploy nhánh chính. Token platform nằm trong GitHub Secrets. Bonus làm sau phần bắt buộc.

**Luồng /ask**

```text
Request + validation
 → API key → rate limit → cost guard
 → đọc history → mock LLM
 → lưu message user + assistant → cộng chi phí
 → log JSON và trả response
```

Các lớp chặn chạy trước LLM. Test CP3 dùng StubStore nên không phụ thuộc CP4 đã hoàn thành; kiểm tra CP3 trước rồi kiểm chứng store thật ở CP4.

**Kế hoạch 240 phút**

Dùng khung thời gian chính thức để tổ chức việc làm; nếu lần đầu học Docker/cloud, chừa thêm thời gian setup.

| Mốc | Công việc | Điều kiện hoàn thành |
|---|---|---|
| 0–20 phút — CP0 | Kiểm tra tên repo GitHub; chuẩn bị Python/dependency; tạo .env và key riêng; bật Docker/Redis; đăng nhập trước cloud | pytest thu thập/chạy được; phân biệt lỗi môi trường với lỗi TODO |
| 20–60 phút — CP1, 15 điểm | config.py, logging_utils.py, /health; đọc Settings ở startup; làm sớm hai hàm lifecycle đang chặn startup | Test CP1 xanh; Uvicorn chạy; /health 200; thiếu key báo lỗi startup |
| 60–105 phút — CP2, 15 điểm | Lưu/build Dockerfile cũ để đo đối chứng; multi-stage, non-root, PORT, healthcheck, .dockerignore, Compose agent | Test CP2 xanh; build/chạy thật; image dưới 500 MB |
| 105–115 phút | Giải lao | — |
| 115–160 phút — CP3, 20 điểm | auth.py, rate_limiter.py, cost_guard.py; ghép /ask | Test CP3 xanh; đúng 401/429/402; request hợp lệ trả answer và ghi chi phí |
| 160–200 phút — CP4, 20 điểm | store.py, /ready, kiểm chứng lifecycle; thử restart/multiple instance cùng Redis nếu có thời gian | Test CP4 xanh; history có TTL/giới hạn; probe và signal đúng |
| 200–230 phút — CP5, 15 điểm | Deploy một platform; nối Redis; set environment; kiểm tra HTTPS/auth; điền DEPLOYMENT.md và chụp ảnh | Test CP5 đạt; output thật; ảnh dashboard và health |
| 230–240 phút — phản ánh, 15 điểm | Hoàn thiện 10 câu từ ghi chép; toàn bộ test/grade; kiểm tra secret/tên repo; commit và nộp | Hiểu test fail/skip; giải thích được bài |
| Sau phần bắt buộc — bonus +10 | Workflow test → build → deploy; badge/run thật | Test bonus đạt; tổng điểm cuối tối đa 100 |

Commit sau mỗi checkpoint. Kẹt quá 10 phút: ghi lỗi cụ thể, hỏi Lab Coach và tiếp tục phần độc lập. Nginx là mở rộng, không có bonus riêng.

Chạy từ thư mục gốc repo bằng Python environment đã chuẩn bị:

```bash
python -m pytest tests/ -v -m "not docker"
python -m pytest tests/test_cp1.py -v
python -m pytest tests/test_cp2.py -v
python -m pytest tests/test_cp3.py -v
python -m pytest tests/test_cp4.py -v
python -m pytest tests/test_cp5.py -v
python -m pytest tests/ -v
python grade.py
```

Ở CP0, test khung bài dự kiến còn fail. Test bị skip không chứng minh tính năng đã chạy. Giữ nguyên bộ test và grade.py.

**Các điểm cần xử lý sớm**

- **Startup:** lifespan gọi lifecycle.install() còn TODO. TestClient CP1/CP3 không chạy lifespan; test CP1 xanh chưa chứng minh Uvicorn khởi động. Làm sớm install/request_shutdown, kiểm chứng đầy đủ tại CP4.
- **Scale và cổng:** 8000:8000 phù hợp một agent; ba replica không thể cùng chiếm host port 8000. Khi thử scale, dùng host port tự cấp hoặc cấu hình riêng Nginx nhận cổng ngoài, agent chỉ phục vụ mạng Compose. Thử scaling local, không cần mua gói cloud cho việc này. [Docker Compose networking](https://docs.docker.com/compose/how-tos/networking/)
- **PORT:** healthcheck phải gọi đúng cổng Uvicorn đang nghe; thử cả PORT mặc định và PORT khác.
- **Shell:** có AGENT_API_KEY trong .env không đồng nghĩa curl đọc được $AGENT_API_KEY. Bảo đảm biến đã export trước khi dùng curl; không dán key vào tài liệu/ảnh.
- **Test cloud:** DEPLOY_API_KEY trong .env cục bộ phải là key service cloud, không phải token Railway/Render. Test chung đặt AGENT_API_KEY thành key giả của bộ test.
- **Giới hạn cost guard:** từ luồng khung bài, kiểm tra chi tiêu rồi ghi sau LLM chưa bảo đảm trần tiền tuyệt đối: request cuối có thể vượt budget; request đồng thời có thể cùng qua check. Hiểu giới hạn khi giải thích; dự trù chi phí/kiểm tra nguyên tử là bước mở rộng nếu có yêu cầu thực tế.

**Cloud và dự phòng**

Chọn một platform. Kế hoạch mặc định dùng Railway nếu tài khoản có trial dùng được và nối Redis thuận lợi; Render là lựa chọn khác nếu đã có tài khoản.

Tài liệu chính thức kiểm tra ngày 28/09/2026: Railway trial một lần $5, tối đa 30 ngày; sau đó Free plan có $1 credit/tháng. Kiểm tra usage để service còn hoạt động đến ngày chấm, không mặc định credit đủ cho cả API và Redis. [Railway Free Trial](https://docs.railway.com/pricing/free-trial)

Render Free web service ngủ sau 15 phút không traffic, mất khoảng một phút để bật lại. Free Key Value mất dữ liệu khi restart: chia sẻ state được nhưng không bảo đảm lưu bền history/chi tiêu. Ghi rõ giới hạn nếu dùng minh họa lab; ngân sách thực tế cần nơi lưu bền. [Render Free](https://render.com/docs/free)

Nếu cloud không dùng được: LOCAL_FALLBACK=true, chạy Docker thật, hoàn thiện ảnh/output và ghi lý do. CP5 tối đa 9/15; nếu mọi phần khác đạt tối đa, có thể đạt 94/100 trước khoản trừ.

**Ghi chép cho exercises.md ngay khi làm**

| CP | Câu | Bằng chứng/nội dung |
|---|---|---|
| CP1 | 1–2 | Lỗi thiếu key; JSON log thật từ /ask khi endpoint hoàn thiện; hai cách dùng log |
| CP2 | 3–5 | Dung lượng image cũ/mới; cache rebuild sau sửa source; tác dụng USER |
| CP3 | 6–7 | Ranh giới phút; tình huống limiter/guard chặn khác nhau |
| CP4 | 8–9 | Probe khi Redis lỗi; history_length qua nhiều instance cùng user |
| CP5 | 10 | Lỗi deploy thật, thông báo, cách tìm nguyên nhân và sửa |

Giữ Dockerfile ban đầu để build đối chứng câu 3. Không bịa số đo, output, lỗi deploy hay ảnh. Viết bằng lời mình và giải thích được cơ chế.

**Trước khi nộp**

- Repo GitHub đúng mẫu `K4-L3A-DAY12-<HoVaTen>-<MSSV>-CloudServicesAndDeployment`. Nếu MSSV là 2A202602397: `K4-L3A-DAY12-PhanDucDuy-2A202602397-CloudServicesAndDeployment`. Tên thư mục local khác mẫu chưa đủ kết luận tên repo GitHub sai; kiểm tra repo thật.
- Không còn NotImplementedError; test/grade.py nguyên vẹn.
- DEPLOYMENT.md có thông tin, URL/platform, tên biến và output; hết placeholder.
- Có screenshots/dashboard.png, screenshots/health.png; ảnh không lộ key.
- Đủ 10 câu exercises.md từ quan sát thực tế và commit theo tiến trình.
- .env/secret không nằm trong bài nộp. Sai tên repo trừ 5; lộ secret trừ 10. Theo RULES.md, secret đã lộ phải rotate; xóa ở commit mới chưa đủ.
- Nộp link GitHub public lên Codelab; giải thích được /ask, Redis, probe và lifecycle.
