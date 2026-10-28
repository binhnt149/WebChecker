# SiteSentry Desktop

SiteSentry Desktop là ứng dụng desktop đa nền tảng dùng để giám sát tự động trạng thái hoạt động của website, website cần đăng nhập và REST API endpoint. Ứng dụng chạy nền theo lịch, đo thời gian phản hồi, lưu lịch sử kiểm tra, giảm báo động giả bằng cơ chế retry và gửi email HTML khi phát hiện sự cố hoặc khi hệ thống phục hồi.

Ứng dụng được xây dựng bằng Python 3.10+, giao diện `customtkinter`, kiểm tra mạng bất đồng bộ bằng `httpx`, lưu dữ liệu bằng SQLite, mã hóa dữ liệu nhạy cảm bằng Fernet, lập lịch bằng APScheduler và hỗ trợ cảnh báo SMTP.

## Mục tiêu dự án

SiteSentry Desktop được thiết kế cho nhu cầu theo dõi cục bộ các hệ thống web/API mà không cần triển khai server giám sát riêng. Người dùng có thể cấu hình monitor trực tiếp trên giao diện, import hàng loạt từ Excel, chạy kiểm tra thủ công hoặc để scheduler tự chạy nền.

Các nhóm monitor chính:

- Web thường: gửi HTTP/HTTPS GET tới một URL, kiểm tra HTTP status và nội dung text nếu có cấu hình.
- Auth Web: đăng nhập bằng form POST, giữ session/cookie, sau đó truy cập trang xác minh và kiểm tra status/text.
- REST API: hỗ trợ `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, header/body tùy chỉnh, token bearer hoặc token header khác, kiểm tra HTTP status, text và JSON path.

Các tính năng chính:

- Dashboard tổng quan số lượng monitor, trạng thái `up/down/unknown`, thời gian phản hồi trung bình.
- Thêm/sửa/xóa monitor bằng giao diện tab theo từng loại Web/Auth/API.
- Đánh dấu trường bắt buộc và cảnh báo khi thiếu hoặc nhập sai thông tin.
- Import Excel danh sách monitor và xuất file mẫu Excel.
- Lưu log kiểm tra vào SQLite, chọn khoảng ngày/giờ bằng lịch, xuất Excel/CSV.
- Báo cáo downtime theo khoảng thời gian, xuất Excel gồm thống kê và chi tiết từng đợt sự cố.
- Chạy kiểm tra thủ công từng monitor hoặc toàn bộ monitor.
- Scheduler chạy nền định kỳ cho các monitor đang bật.
- Retry guard: thử lại nhiều lần trước khi kết luận lỗi.
- SMTP HTML alert khi monitor down và email recovery khi monitor phục hồi.
- Nhiều quy tắc email độc lập: DOWN/UP một lần theo chuyển trạng thái, chỉ phục hồi, hoặc tổng hợp Dashboard theo lịch.
- Nhiều người nhận, tùy chỉnh chủ đề/nội dung email và hàng đợi gửi lại khi SMTP lỗi.
- Khai báo ngôn ngữ/framework và web server cho Web/Auth Web/API, hỗ trợ import Excel.
- Mã hóa thông tin nhạy cảm trước khi lưu DB.
- Hỗ trợ chạy ẩn dưới system tray trên Windows/macOS/Linux khi tray khả dụng.

## Giao diện và phân loại sự cố

Dashboard dùng bảng monitor với tìm kiếm theo tên/URL/lỗi, bộ lọc loại monitor và trạng thái. Chọn một dòng để Run, Edit, Pause/Enable hoặc Delete; nhấp đúp để sửa. Khi cập nhật kết quả, app giữ dòng đang chọn. Truy vấn, import, test monitor và xuất file chạy nền, trả kết quả qua queue của luồng giao diện.

Giao diện dùng nền trung tính Light/Dark, màu teal cho thao tác chính, xanh lá cho UP, đỏ cho DOWN và màu cảnh báo riêng. Sidebar đánh dấu màn hình đang mở. Các form dài có vùng cuộn, nút Save/Cancel luôn nằm ngoài vùng cuộn.

App gom việc thu hồi các đối tượng có vòng tham chiếu về luồng Tk mỗi 2 giây. Cách này tránh font/biến Tk bị hủy trên luồng truy vấn DB hoặc mạng khi chuyển màn hình, gây chờ hoặc treo giao diện. Bộ thu gom tự động được khôi phục khi cửa sổ ứng dụng được hủy; cơ chế đếm tham chiếu của Python vẫn hoạt động bình thường. Xem [mô hình luồng Tkinter](https://docs.python.org/3.10/library/tkinter.html#threading-model) và [cơ chế thu gom của Python](https://docs.python.org/3.10/library/gc.html).

Kết quả mới có mã `error_type`, được lưu riêng trong Log và `last_error_type` của monitor, không chỉ phân tích chuỗi thông báo khi gửi mail. Log cũ được giữ nguyên; các lỗi chưa có mã được đánh dấu `unknown`.

| Mã lỗi | Ý nghĩa / bằng chứng |
| --- | --- |
| `auth_credentials` | Máy chủ trả HTTP 401 hoặc form đăng nhập trả thông báo từ chối tài khoản/mật khẩu rõ ràng. Có thể do mật khẩu, tài khoản hoặc token; không khẳng định chính xác trường nào sai. |
| `auth_verification` | Trang xác minh vẫn là trang login hoặc không xác minh được session; có thể liên quan CAPTCHA, MFA, CSRF hay cấu hình form. Không tự coi là sai mật khẩu. |
| `timeout` | Website/API không phản hồi trong thời gian chờ. |
| `target_unreachable` | Không kết nối được server hoặc kết nối bị ngắt. |
| `network_offline` | Hệ điều hành báo mạng không khả dụng/không có route, hoặc không chọn được route IPv4 lẫn IPv6 trên máy giám sát. |
| `dns_error` | Không phân giải được tên miền/địa chỉ. |
| `tls_error` | Chứng chỉ TLS/SSL hoặc bắt tay TLS lỗi. |
| `http_error` | HTTP status khác giá trị mong đợi; HTTP 403 không bị gán nhầm thành sai mật khẩu. |
| `assertion_failed` | Nội dung HTML/text hoặc JSON API không khớp điều kiện kiểm tra. |
| `configuration_error` | URL, JSON header/form hoặc cấu hình monitor không hợp lệ. |
| `unknown` | Chưa có đủ thông tin để phân loại. |

Kiểm tra route chỉ hỏi hệ điều hành, không gửi thông tin đăng nhập hay gọi website thứ ba để dò Internet. Nhiều monitor DOWN đồng thời không đủ để kết luận máy mất mạng. Nếu LAN vẫn có route nhưng mất đường ra Internet, lỗi có thể vẫn được ghi là timeout/kết nối/DNS; app không khẳng định offline khi chưa có bằng chứng. Với lỗi xác thực rõ ràng hoặc cấu hình sai, app không lặp lại cùng yêu cầu theo retry guard để giảm nguy cơ khóa tài khoản.

### Lọc và gom email sự cố

Trong `Settings > Email schedules > Edit/Add schedule`:

- Đánh dấu các nhóm trong `Excluded error categories` để không gửi cảnh báo DOWN thuộc nhóm đó. Log và thống kê trong app vẫn giữ đầy đủ dữ liệu.
- `Group DOWN alerts (seconds)` mặc định 15 giây, cho phép 0–300 giây; đặt 0 để gửi riêng ngay. Những Web/Auth Web/API khác nhau cùng quy tắc trong cửa sổ này được gửi dưới dạng bảng danh sách, kể cả khi chỉ có một người nhận.
- Mỗi cửa sổ được tính từ cảnh báo đầu tiên và không kéo dài thêm khi có monitor mới. Email UP của monitor trong nhóm sẽ đóng nhóm đó để giữ đúng thứ tự DOWN/UP; UP của monitor khác không chia tách nhóm không liên quan. Mỗi quy tắc có nhóm/người nhận/nội dung riêng; không trộn thư của hai quy tắc.
- Không gửi lặp các kết quả DOWN liền kề. Nếu lỗi bị loại chuyển sang lỗi cần cảnh báo khi monitor vẫn DOWN, app vẫn tạo được cảnh báo mới một lần. Đợt DOWN–UP–DOWN mới của cùng monitor được giữ riêng, không bị gộp nhầm là hai monitor khác nhau.
- Với quy tắc DOWN/recovery, sự cố bị loại không tạo email UP đơn lẻ. Nếu DOWN đã được đưa vào hàng đợi hợp lệ, UP được giữ sau DOWN để người nhận đối chiếu.
- Đổi bộ lọc sẽ loại các thư tương ứng còn chờ và chưa bắt đầu gửi. Các lần gửi đã bắt đầu, hoặc đã được SMTP chấp nhận một phần, không thể thu hồi; app tiếp tục theo dõi người nhận còn thiếu để không gửi trùng.
- Trạng thái hàng đợi `suppressed` nghĩa là bị bộ lọc loại, không phải lỗi SMTP.

Thư tạo mới ghi nhận loại quy tắc tại thời điểm tạo. Thư từ bản cũ không có thông tin này được giữ là `legacy_unknown`, không suy đoán từ loại quy tắc hiện tại; nếu người dùng loại nhóm lỗi tương ứng thì thư cũ chưa bắt đầu gửi cũng được loại theo lựa chọn đó. Nâng cấp có thể tiếp tục an toàn sau khi bị ngắt giữa chừng, không cần xóa DB hoặc Fernet key.

Email tổng hợp theo ngày loại các monitor **đang DOWN** thuộc nhóm đã chọn khỏi bảng email, đồng thời ghi số monitor bị loại. Các monitor UP vẫn giữ lịch sử trong ngày; đây không phải phép xóa từng loại lỗi khỏi số liệu lịch sử. Báo cáo đầy đủ trong app/Excel không bị bộ lọc email thay đổi.

Các biến `{error_type}` và `{monitor_count}` có thể dùng trong nội dung/chủ đề email. Thư gom có tên tổng quát như `3 monitors` ở chủ đề và có tên, loại Web/Auth/API, URL, nhóm lỗi, giờ kiểm tra, thông báo lỗi của từng dòng trong nội dung. Hàng đợi, nhóm thư và danh sách người nhận SMTP còn thiếu được lưu trong SQLite để tiếp tục sau khi mở lại app.

### Báo cáo và biểu mẫu

Màn hình `Statistics` có KPI và ba tab `Monitors`, `Incidents`, `Error categories`. File Excel có ba sheet tương ứng `Statistics`, `Incidents`, `Error breakdown`. Phần chi tiết ghi cả các nhóm lỗi gặp trong mỗi đợt DOWN; bảng phân loại đếm số log DOWN theo từng monitor/nhóm lỗi, kể cả lỗi đã loại khỏi email.

Nút `Template` xuất biểu mẫu báo cáo trống. Bản mẫu có sẵn tại `templates/sitesentry_report_template.xlsx`; đây là biểu mẫu báo cáo, không phải file để import monitor. File xuất dùng ngày giờ Excel thật, thời lượng `[h]:mm:ss`, vùng lọc, dòng tổng tính theo các dòng đang lọc và thiết lập in ngang. Các tên/nội dung từ monitor được ghi như văn bản, không thực thi thành công thức Excel.

## Công nghệ sử dụng

| Thành phần | Công nghệ | Vai trò |
| --- | --- | --- |
| Ngôn ngữ | Python 3.10+ | Runtime chính của ứng dụng desktop. |
| GUI | `customtkinter`, `tkinter` | Xây dựng giao diện desktop, sidebar, dashboard, dialog, form settings. |
| HTTP engine | `httpx` async, HTTP/2 | Gửi request kiểm tra website/API, hỗ trợ timeout, redirect, cookie/session. |
| Database | `sqlite3` | Lưu monitor, log kiểm tra và settings cục bộ. |
| Mã hóa | `cryptography.fernet.Fernet` | Mã hóa header/body/token/password/SMTP password trước khi lưu DB. |
| Scheduler | `APScheduler BackgroundScheduler` | Lập lịch kiểm tra định kỳ trong background thread. |
| Email | `smtplib`, `email.mime` | Gửi email HTML cảnh báo/down/recovery qua SMTP. |
| Excel | `openpyxl` | Tạo file mẫu và import danh sách monitor từ `.xlsx`. |
| System tray | `pystray`, `Pillow` | Icon khay hệ thống và menu chạy nền trên hệ điều hành hỗ trợ. |
| Đồ họa asset | `Pillow` | Tạo icon mặc định khi thiếu file icon. |

## Cấu trúc dự án

```text
sitesentry/
├── assets/
│   ├── icon.ico
│   └── icon.png
├── core/
│   ├── security.py        # Quản lý Fernet key, encrypt/decrypt dữ liệu nhạy cảm
│   ├── database.py        # SQLite schema, CRUD monitor/log/settings
│   ├── checker.py         # Engine kiểm tra Web/Auth/API bằng httpx async
│   ├── diagnostics.py     # Mã lỗi, nhận diện lỗi mạng/xác thực
│   ├── scheduler.py       # Lập lịch APScheduler và gọi checker định kỳ
│   ├── notifier.py        # SMTP HTML, hàng đợi và gửi lại từng người nhận
│   ├── email_rules.py     # Quy tắc email, kiểm tra người nhận và mẫu nội dung
│   ├── notification_store.py # Hàng đợi bền vững, lọc và gộp email sự cố
│   ├── reports.py         # Tính downtime và thống kê nhóm lỗi
│   ├── report_export.py   # Báo cáo/biểu mẫu Excel ba sheet
│   └── excel_importer.py  # Tạo template Excel và import monitor hàng loạt
├── ui/
│   ├── main_window.py     # App chính, sidebar, view routing, scheduler/tray integration
│   ├── dashboard_view.py  # Dashboard, danh sách monitor, import Excel, quick actions
│   ├── monitor_dialog.py  # Dialog thêm/sửa monitor theo tab Web/Auth/API
│   ├── logs_view.py       # Bảng log, lọc ngày/giờ, export Excel/CSV
│   ├── reports_view.py    # Báo cáo thống kê theo khoảng thời gian
│   ├── datetime_picker.py # Lịch chọn ngày, giờ, phút, giây
│   ├── theme.py           # Bảng màu Light/Dark, bảng dữ liệu và KPI
│   ├── lifecycle.py       # Thu hồi vòng tham chiếu trên luồng Tk
│   ├── email_rule_dialog.py # Thêm/sửa lịch và nội dung email
│   ├── background.py      # Tác vụ nền, trả kết quả qua queue UI
│   ├── settings_view.py   # SMTP/theme/settings và test email
│   └── focus.py           # Helper xử lý focus/click cho ô nhập liệu
├── main.py                # Entry point, kiểm tra Python runtime rồi mở app
├── run.sh                 # Script chạy app và tự kiểm tra dependencies
├── requirements.txt       # Danh sách thư viện Python
├── config.json            # Cấu hình runtime ban đầu
├── data/                  # SQLite DB và Fernet key được sinh khi chạy
└── templates/             # File mẫu Excel import monitor và báo cáo
```

## Luồng khởi động ứng dụng

1. Người dùng chạy `./run.sh`.
2. Script dò runtime Python phù hợp, ưu tiên wrapper local `./scripts/python3.10` nếu có, sau đó các bản Python 3.13/3.12/3.11/3.10/3.
3. Script kiểm tra các thư viện bắt buộc. Nếu thiếu, script cài theo `requirements.txt`.
4. `main.py` kiểm tra Python phải từ 3.10 trở lên và tắt cảnh báo deprecated Tk trên macOS bằng `TK_SILENCE_DEPRECATION=1`.
5. `SiteSentryApp` trong `ui/main_window.py` được khởi tạo.
6. App đọc `config.json`, tạo icon nếu thiếu, mở Fernet key, mở SQLite DB và khởi tạo schema nếu chưa có.
7. App tạo các service lõi: `SiteChecker`, `EmailNotifier`, `MonitorScheduler`.
8. Giao diện chính hiển thị Dashboard, scheduler bắt đầu chạy và đồng bộ job cho các monitor đang `enabled`.
9. Khi scheduler có kết quả kiểm tra, kết quả được đưa vào queue UI. Main thread đọc queue định kỳ và refresh giao diện an toàn.

## Luồng sử dụng trên giao diện

Dashboard là màn hình mặc định. Tại đây người dùng có thể:

- Xem KPI: tổng monitor, số monitor up/down/unknown, response time trung bình.
- Bấm `Add Monitor` để thêm monitor mới.
- Bấm `Edit` để sửa monitor hiện có.
- Bấm `Run` để kiểm tra ngay một monitor.
- Bấm `Run All` để kiểm tra ngay toàn bộ monitor đang bật.
- Bấm `Enable/Disable` để bật/tắt lịch chạy nền.
- Bấm `Delete` để xóa monitor.
- Bấm `Template` để xuất file mẫu Excel.
- Bấm `Import Excel` để nhập hàng loạt monitor.

Dialog thêm/sửa monitor có ba tab:

- `Web`: cấu hình website thường.
- `Auth Web`: cấu hình website cần đăng nhập bằng form.
- `API`: cấu hình REST API endpoint.

Các trường bắt buộc được đánh dấu `*`. Khi người dùng bấm `Save` hoặc `Test Run`, app kiểm tra dữ liệu đầu vào trước. Nếu thiếu hoặc sai, app hiển thị danh sách lỗi để người dùng sửa trước khi lưu/chạy thử.

Logs View dùng để xem lịch sử kiểm tra gần nhất, lọc theo trạng thái `all/up/down`, lọc theo khoảng thời gian, export Excel/CSV hoặc xóa log.

Settings View có tab `SMTP` để cấu hình máy chủ/người nhận/theme và tab `Email schedules` để quản lý nhiều quy tắc cảnh báo, lịch tổng hợp và nội dung email. Mục `Statistics` trên sidebar tạo báo cáo downtime theo khoảng thời gian.

## Luồng kiểm tra monitor

### Web thường

1. Scheduler hoặc người dùng gọi kiểm tra monitor.
2. `SiteChecker` đọc URL, timeout, header JSON, expected status và expected text.
3. App gửi request `GET` bằng `httpx.AsyncClient` với HTTP/2 và `follow_redirects=True`.
4. App đo thời gian phản hồi bằng millisecond.
5. Nếu HTTP status khác `expected_status`, monitor được đánh dấu `down`.
6. Nếu có `expected_text` nhưng nội dung response không chứa chuỗi đó, monitor được đánh dấu `down`. App chuẩn hóa Unicode, khoảng trắng và hoa/thường để giảm sai khác nhỏ giữa môi trường chạy.
7. Nếu mọi điều kiện đạt, monitor được đánh dấu `up`.

### Auth Web

1. App chuẩn bị header, login URL, protected/verify URL, username/password field và extra fields.
2. App mở `auth_login_url` để nhận cookie/session ban đầu và tự lấy các hidden input trong form login, ví dụ CSRF token.
3. App tạo form data gồm hidden input, username, password và các field phụ trong `auth_extra_fields`.
4. App gửi `POST` tới action của form login hoặc `auth_login_url` bằng cùng một `httpx.AsyncClient` để giữ cookie/session.
5. Nếu bước login trả về HTTP lỗi từ 400 trở lên, monitor được đánh dấu `down`.
6. App gửi `GET` tới `auth_verify_url` hoặc `url` nếu verify URL trống.
7. App kiểm tra HTTP status, expected text chung và `auth_verify_text` nếu có.
8. Nếu xác minh thành công, monitor được đánh dấu `up`.

### REST API

1. App đọc method, endpoint URL, headers JSON, body, token và expected assertions.
2. Nếu có `api_token`, app thêm token vào header được cấu hình bởi `api_token_header` và `api_token_prefix`.
3. App gửi request theo method `GET/POST/PUT/PATCH/DELETE` bằng `httpx.AsyncClient`.
4. App kiểm tra HTTP status và expected text nếu có.
5. Nếu có `expected_json_path`, app parse response JSON và lấy giá trị theo dot path, ví dụ `status` hoặc `data.items[0].state`.
6. Nếu có `expected_json_value`, app so sánh giá trị thực tế với giá trị mong đợi theo dạng chuỗi.
7. Nếu tất cả assertion đạt, monitor được đánh dấu `up`; ngược lại là `down`.

## Retry, log và cảnh báo

Mỗi monitor có các thông số retry riêng:

- `retry_count`: số lần thử trước khi kết luận lỗi.
- `retry_delay_seconds`: thời gian nghỉ giữa các lần thử.

Nếu lần kiểm tra đầu tiên lỗi, checker sẽ thử lại đến khi thành công hoặc hết số lần retry. Kết quả cuối cùng được lưu vào bảng `logs` và cập nhật lại trạng thái cuối trên bảng `monitors`.

Sau khi có kết quả:

1. Scheduler ghi log, cập nhật trạng thái và tạo sự kiện email trong cùng một transaction SQLite.
2. Với quy tắc `DOWN and recovery`, lần đầu `unknown/up -> down` tạo một cảnh báo. Các lần `down -> down` tiếp theo không tạo thêm email, kể cả sau khi khởi động lại app.
3. Khi `down -> up`, app tạo một email phục hồi. `up -> up` không gửi email. Một đợt DOWN mới vẫn được cảnh báo ngay, không bị chặn bởi cooldown của đợt trước.
4. Worker riêng xử lý hàng đợi SMTP, không chặn scheduler hoặc giao diện. Khi gửi lỗi, chờ ít nhất một phút rồi thử lại; mỗi quy tắc giữ thứ tự DOWN trước UP. Hàng đợi tồn tại sau khi khởi động lại.
5. Khi SMTP bị tắt, app vẫn ghi log nhưng không tạo email cảnh báo/tổng hợp mới. Quy tắc bị tắt tạm dừng hàng đợi của chính nó; xóa quy tắc sẽ xóa hàng đợi tương ứng.

`cooldown_minutes` cũ được giữ trong DB/file import để tương thích, nhưng không áp dụng cho cơ chế cảnh báo theo chuyển trạng thái mới.

Email cảnh báo là HTML email gồm tên monitor, loại monitor, URL, trạng thái, HTTP status, response time, số lần thử, thời điểm kiểm tra và lỗi chi tiết.

## Bảo mật dữ liệu

Ứng dụng lưu dữ liệu trên máy người dùng. SQLite DB nằm ở `data/sitesentry.db`, Fernet key nằm ở `data/fernet.key`.

Các trường nhạy cảm được mã hóa trước khi lưu:

- `headers_json`
- `body`
- `api_token`
- `auth_password`
- `auth_extra_fields`
- `smtp_password`

Khi app đọc monitor/settings từ database, các trường này được giải mã để hiển thị hoặc dùng khi kiểm tra. Nếu Fernet key bị mất hoặc thay đổi, dữ liệu đã mã hóa cũ sẽ không giải mã được.

## Dữ liệu và schema chính

SQLite có các nhóm bảng chính:

- `monitors`: cấu hình monitor, trạng thái cuối, thời điểm kiểm tra cuối, thông tin cooldown alert.
- `logs`: lịch sử từng lần kiểm tra, gồm status, HTTP code, response time, error, attempts và detail JSON.
- `settings`: cấu hình ứng dụng và SMTP; các setting nhạy cảm được đánh dấu secret và mã hóa.
- `email_rules`: lịch, loại cảnh báo, người nhận và nội dung email.
- `notification_events`: sự kiện DOWN/UP hoặc bản chụp báo cáo tổng hợp.
- `email_deliveries`: trạng thái gửi, số lần thử, lỗi SMTP và người nhận còn cần gửi lại.

Database bật `PRAGMA foreign_keys = ON` và `journal_mode = WAL` để hỗ trợ ghi/đọc ổn định trong quá trình app chạy nền.

## System tray

Ứng dụng có cơ chế system tray bằng `pystray` và `Pillow`. Khi tray khả dụng, người dùng có thể ẩn app xuống tray, mở lại app, chạy `Run All Now` hoặc thoát app từ menu tray.

Khi người dùng bấm nút đóng cửa sổ, app sẽ ẩn xuống tray thay vì thoát hẳn nếu tray đang hoạt động. Muốn thoát hoàn toàn, chọn `Quit` trong menu tray. Có thể bật/tắt tray qua `config.json` bằng `enable_system_tray`.

## Logs và xuất Excel

Màn hình Logs hỗ trợ:

- Lọc trạng thái `all`, `up`, `down`.
- Bấm `From`/`To` để chọn ngày trên lịch và giờ/phút/giây bằng nút tăng giảm. `Apply` xác nhận; `Clear` bỏ giới hạn ở đầu/cuối khoảng thời gian.
- Xuất Excel `.xlsx` theo đúng bộ lọc đang chọn.
- Xuất CSV theo đúng bộ lọc đang chọn.

Bảng hiển thị tối đa 500 log gần nhất. File xuất lấy toàn bộ log khớp bộ lọc, không bị giới hạn 500 dòng. Truy vấn và xuất file chạy nền. Xóa log cũng làm mất dữ liệu để tính báo cáo lịch sử.

## Quy tắc và lịch email

1. Mở `Settings > SMTP`, bật `Enable SMTP alerts`, nhập host, port, STARTTLS, tài khoản/mật khẩu và địa chỉ gửi. Mật khẩu SMTP được mã hóa bằng Fernet.
2. Ô `Recipients` nhận nhiều địa chỉ, phân cách bằng dấu phẩy, chấm phẩy hoặc xuống dòng. Bấm `Save`, sau đó `Test Email` để kiểm tra kết nối thật.
3. Mở `Email schedules > Add schedule` để tạo nhiều quy tắc độc lập. Lần đầu nâng cấp, app tự tạo một quy tắc `Incident alerts` dùng danh sách người nhận SMTP hiện có.

| Event | Thời điểm gửi |
| --- | --- |
| `DOWN and recovery` | Kết luận DOWN sau retry guard, chờ cửa sổ gộp nếu đã cấu hình, rồi gửi cảnh báo và một email khi UP trở lại. Không nhắc lại DOWN liên tiếp. |
| `Recovery only` | Chỉ gửi khi chuyển từ DOWN sang UP. |
| `Daily summary` | Theo giờ/phút và các thứ được chọn, dùng múi giờ máy đang chạy app. |

Mỗi quy tắc có thể bật/tắt, sửa/xóa, đặt người nhận riêng; để trống sẽ dùng `SMTP > Recipients`. Các quy tắc được xử lý độc lập, nên cùng một người nằm trong hai quy tắc phù hợp sẽ nhận hai email theo cấu hình đó.

Với `Daily summary`, chọn `today` để tổng hợp từ 00:00 đến lúc gửi, hoặc `yesterday` để tổng hợp ngày hôm trước. Nút `Send now` tạo thêm một bản tổng hợp ngay; mỗi lần bấm là một yêu cầu riêng. Nội dung HTML gồm tổng số monitor, UP/DOWN/Unknown và bảng downtime từng monitor. App phải đang chạy (có thể ẩn tray), máy không ngủ và SMTP phải được bật; app không tự gửi bù những lịch đã qua khi máy tắt. Cùng lịch trong cùng ngày không tự tạo trùng khi đồng bộ lại scheduler.

`Subject` và `Message` hỗ trợ các biến sau (biến không phù hợp loại email được thay bằng chuỗi trống):

| Biến | Nội dung |
| --- | --- |
| `{monitor_name}`, `{url}` | Tên và URL monitor, dùng cho email sự cố/phục hồi. |
| `{status}`, `{checked_at}`, `{error}` | DOWN/UP, thời điểm kiểm tra và lỗi; email tổng hợp có status SUMMARY. |
| `{date}` | Ngày kiểm tra hoặc ngày báo cáo. |
| `{total}`, `{up}`, `{down}`, `{unknown}` | Thống kê trạng thái monitor của báo cáo tổng hợp. |
| `{down_count}`, `{downtime}` | Tổng số log DOWN và tổng thời gian DOWN của báo cáo tổng hợp. |

Ví dụ chủ đề: `[Vận hành] {status}: {monitor_name}`. Nội dung tự nhập là văn bản, được escape an toàn khi đưa vào HTML. Bật `Include default HTML report` để bổ sung nội dung bên dưới mẫu mặc định; bỏ chọn để thay hoàn toàn mẫu mặc định (khi đó Message bắt buộc). Dùng `{{` và `}}` để hiển thị dấu ngoặc nhọn.

Khi SMTP chỉ chấp nhận một phần danh sách, app lưu các địa chỉ bị từ chối và chỉ thử lại những địa chỉ đó. Chống trùng dựa trên trạng thái và hàng đợi lưu trong DB; SMTP không bảo đảm exactly-once nếu tiến trình bị dừng đúng lúc server đã nhận thư nhưng app chưa kịp lưu xác nhận.

## Báo cáo thống kê downtime

Mở `Statistics`, chọn `From`/`To`, bấm `Generate` và `Export Excel`. Thời gian tính theo giờ cục bộ của app.

| Chỉ tiêu | Cách tính |
| --- | --- |
| Monitor name | Tên Web/Auth Web/API. Monitor đã xóa vẫn có thể xuất hiện từ log lịch sử. |
| DOWN count | Số dòng log có Status DOWN trong khoảng chọn, không phải số đợt sự cố. |
| Incidents | Số chuỗi DOWN liên tiếp cho đến UP, có giao với khoảng chọn. |
| Total DOWN | Tổng thời gian từ DOWN đầu tiên đến UP của từng đợt, chỉ tính phần nằm trong khoảng chọn. |
| Average DOWN | Total DOWN chia Incidents; bằng 0 nếu không có sự cố. |
| Open | Số đợt chưa có UP tại thời điểm kết thúc quan sát. |

Ví dụ: DOWN lúc 10:00, DOWN lúc 10:05, UP lúc 10:10, DOWN lúc 11:00 và UP lúc 11:20 cho kết quả 3 lần DOWN, 2 đợt, tổng 30 phút, trung bình 15 phút/đợt.

App lấy trạng thái cuối trước `From` để nhận biết sự cố kéo dài từ trước kỳ. Nếu chưa có UP, thời gian được tạm tính đến `min(To, thời điểm tạo báo cáo)` và đánh dấu Open, không giả định đã phục hồi. Trung bình có bao gồm phần tạm tính này. Thời gian là ước lượng theo các lần kiểm tra, không phải thời điểm hạ tầng thực sự ngừng hoạt động; khoảng app không chạy vẫn có thể được tính liên tục nếu log trước đó là DOWN. Xóa log sẽ làm giảm khả năng xác định các khoảng này. Log của các monitor đã xóa cùng tên được gộp theo tên vì DB cũ không giữ ID sau khi xóa.

File Excel có ba sheet `Statistics`, `Incidents` và `Error breakdown` để đối chiếu tổng hợp, từng khoảng DOWN và nhóm lỗi. Ngày giờ là giá trị Excel thật; thời lượng là số với định dạng `[h]:mm:ss`, hỗ trợ tổng vượt 24 giờ và có thể cộng/tính tiếp trong Excel.

Hai cột metadata `language` và `web_server` nằm cuối file mẫu import (AC/AD), áp dụng cho cả ba loại monitor. File mẫu cũ thiếu hai cột này vẫn import được và không xóa metadata đã khai báo. Nếu file có cột nhưng giá trị trống thì metadata được xóa theo dữ liệu nhập.

## Kiểm thử các chức năng mới

```bash
./scripts/python3.10 -m unittest discover -s tests -v
```

Kiểm thử dùng DB/Fernet key tạm và SMTP giả lập, không gửi thư thật. Kiểm tra GUI trên máy có màn hình bằng `SITESENTRY_GUI_TEST=1 ./scripts/python3.10 -m unittest discover -s tests -p test_ui_smoke.py -v` (PowerShell: đặt `$env:SITESENTRY_GUI_TEST="1"` trước khi chạy `python -m unittest ...`).

Bộ kiểm thử bao gồm phân loại lỗi HTTP/auth/mạng, nâng cấp DB cũ, lọc và gộp email, gửi lại từng người nhận, thứ tự DOWN/UP, số liệu downtime, dữ liệu Excel an toàn và vòng đời tài nguyên Tk. Kiểm thử GUI dùng 503 monitor, chuyển màn hình Light/Dark, tìm kiếm/lọc, giữ lựa chọn khi refresh và lưu lịch email.

## Build file cài đặt

Project đã có cấu hình PyInstaller để đóng gói desktop app.

Build macOS trên máy Mac:

```bash
bash scripts/build_macos.sh
```

Kết quả:

- `dist/SiteSentry Desktop.app`
- `dist/SiteSentry-Desktop-macOS.dmg`

Build Windows trên máy Windows:

```powershell
.\scripts\build_windows.ps1
```

Kết quả:

- `dist\SiteSentry Desktop.exe`
- `dist\SiteSentry-Desktop-Windows.zip`

Repo có GitHub Actions workflow tại `.github/workflows/build.yml`, chạy kiểm thử và build trên Windows x64, macOS Intel và macOS Apple Silicon. Push lên `main` hoặc chạy `Actions > Build and release SiteSentry Desktop > Run workflow` sẽ tạo các artifact để tải trong trang Actions. Pull request cũng được kiểm thử/build nhưng không phát hành.

### Phát hành phiên bản lên GitHub Releases

1. Đổi `__version__` trong `sitesentry/__init__.py` theo dạng `X.Y.Z`, cập nhật `RELEASE_NOTES.md`.
2. Commit và push lên `main`.
3. Tạo và push tag trùng phiên bản, ví dụ với phiên bản hiện tại:

```bash
git tag -a v1.2.0 -m "Release SiteSentry Desktop 1.2.0"
git push origin v1.2.0
```

Workflow dùng Python 3.12 trên cả ba runner (Python 3.10 chưa có runner macOS arm64 tương ứng trong manifest của setup-python). Workflow kiểm tra tag phải khớp `__version__`, chạy test trên từng nền tảng rồi build bằng PyInstaller. Chỉ khi cả ba nền tảng thành công, job `Publish GitHub Release` mới gom đủ bốn file, tạo `SHA256SUMS.txt`, tải lên bản nháp và công bố Release. Job phát hành dùng `GITHUB_TOKEN` với quyền `contents: write`, không cần thêm PAT vào source code.

Các file của phiên bản `1.2.0`:

- `SiteSentry-Desktop-v1.2.0-Windows-x64.exe`
- `SiteSentry-Desktop-v1.2.0-Windows-x64.zip`
- `SiteSentry-Desktop-v1.2.0-macOS-x64.dmg`
- `SiteSentry-Desktop-v1.2.0-macOS-arm64.dmg`
- `SHA256SUMS.txt`

Tải tại [GitHub Releases](https://github.com/binhnt149/WebChecker/releases); theo dõi kết quả/log tại [GitHub Actions](https://github.com/binhnt149/WebChecker/actions). Nếu build lỗi, Release không được công bố; sửa lỗi bằng commit mới và phát hành phiên bản/tag mới, không ghi đè tag đã phát hành. Có thể chạy lại job khi lỗi tạm thời (mạng/runner).

Windows EXE là bản portable, không cần cài Python; ZIP chứa cùng file EXE. Trên macOS chọn DMG đúng loại chip, mở rồi kéo app vào Applications. Các gói chưa có chứng chỉ ký của nhà phát hành hoặc Apple notarization, nên Windows SmartScreen/macOS Gatekeeper có thể cảnh báo. Không kèm DB, Fernet key hay mật khẩu cục bộ trong gói phát hành.

Lưu ý: Windows `.exe` phải được build trên Windows hoặc runner Windows của GitHub Actions. macOS không thể tạo Windows `.exe` native bằng PyInstaller một cách đáng tin cậy nếu không dùng môi trường Windows.

## Chạy ứng dụng

Yêu cầu Python 3.10+.

```bash
chmod +x run.sh
./run.sh
```

Script sẽ tự dò `./scripts/python3.10` nếu có, `python3.13`, `python3.12`, `python3.11`, `python3.10`, `python3`, rồi mới chạy app.

Nếu máy đang có wrapper local:

```bash
./scripts/python3.10 --version
./scripts/python3.10 main.py
```

Nếu máy chưa có Python 3.10+, cài Python từ python.org trước. Sau khi cài system-wide, có thể chạy thủ công bằng runtime đang có, ví dụ:

```bash
python3.12 -m pip install -r requirements.txt
python3.12 main.py
```

Không dùng Python 3.9 đi kèm Apple CommandLineTools để chạy GUI. Runtime đó có thể mở cửa sổ Tk nhưng không render được các control CustomTkinter trên một số bản macOS, dẫn tới cửa sổ trống.

## Dữ liệu cục bộ

- SQLite database: `data/sitesentry.db`
- Fernet key: `data/fernet.key`
- Icon: `sitesentry/assets/icon.png`, `sitesentry/assets/icon.ico`

Các thông tin nhạy cảm như mật khẩu đăng nhập, API token, header/body có khả năng chứa secret và SMTP password được mã hóa trước khi lưu vào SQLite.

## Import Excel

Trong Dashboard:

- `Template`: lưu file mẫu `.xlsx` với sheet `Monitors` và `Instructions`.
- `Import Excel`: nhập danh sách monitor từ file `.xlsx`.

File mẫu có sẵn trong project: `templates/sitesentry_monitors_template.xlsx`.

Cột bắt buộc trong sheet `Monitors`: `name`, `monitor_type`, `url`.

`monitor_type` nhận một trong ba giá trị: `simple_web`, `auth_web`, `api`.

Nếu cột `id` có giá trị và monitor tồn tại, app sẽ cập nhật monitor đó. Nếu `id` trống, app sẽ cập nhật theo cặp `name` + `url` nếu đã tồn tại, hoặc tạo mới nếu chưa có.

## Thông số monitor

### Thông số chung

| Thông số | Áp dụng | Bắt buộc | Mặc định | Mô tả |
| --- | --- | --- | --- | --- |
| `id` | Excel import | Không | Trống | ID monitor hiện có. Có giá trị thì import sẽ cập nhật monitor đó. Để trống để tạo mới hoặc cập nhật theo `name` + `url`. |
| `name` | Tất cả | Có | - | Tên hiển thị của monitor trên Dashboard và trong log/email cảnh báo. |
| `monitor_type` | Tất cả | Có | `simple_web` | Loại monitor: `simple_web`, `auth_web`, hoặc `api`. |
| `language` | Tất cả | Không | Trống | Ngôn ngữ/framework ứng dụng, ví dụ PHP, Python, Java, ASP.NET. Metadata mô tả, không thay đổi cách gửi HTTP. |
| `web_server` | Tất cả | Không | Trống | Web server, ví dụ Apache, Nginx, IIS, Tomcat. Metadata mô tả, không thay đổi cơ chế xác thực. |
| `enabled` | Tất cả | Không | `1` | Bật/tắt lịch kiểm tra. Nhận `1`, `0`, `TRUE`, `FALSE`, `yes`, `no`. |
| `url` | Tất cả | Có | - | URL cần kiểm tra. Với Auth Web là trang được bảo vệ; với API là endpoint. |
| `method` | API, Web | Không | `GET` | HTTP method. API hỗ trợ `GET`, `POST`, `PUT`, `PATCH`, `DELETE`. Web thường dùng `GET`. |
| `interval_seconds` | Tất cả | Không | `60` | Chu kỳ kiểm tra định kỳ, tính bằng giây. Tối thiểu 10 giây. |
| `timeout_seconds` | Tất cả | Không | `10` | Thời gian chờ tối đa cho một lần request. |
| `expected_status` | Tất cả | Không | `200` | HTTP status code mong đợi. Nếu khác giá trị này thì monitor bị xem là `down`. |
| `expected_text` | Web, Auth Web, API | Không | Trống | Chuỗi cần xuất hiện trong response body. Để trống nếu chỉ cần kiểm tra HTTP status. Với website redirect về trang đăng nhập, dùng chuỗi ổn định có trên trang login hoặc chuyển sang Auth Web nếu cần xác minh sau đăng nhập. |
| `headers_json` | Tất cả | Không | `{}` | Header request dạng JSON object, ví dụ `{"Accept":"application/json"}`. Dữ liệu này được mã hóa khi lưu DB. |
| `retry_count` | Tất cả | Không | `3` | Số lần thử trước khi kết luận lỗi, giúp giảm báo động giả. |
| `retry_delay_seconds` | Tất cả | Không | `2` | Thời gian nghỉ giữa các lần retry. |
| `cooldown_minutes` | Import cũ | Không | `30` | Giữ để tương thích dữ liệu cũ; không dùng trong cơ chế email theo chuyển trạng thái mới. |

### Web

| Thông số | Bắt buộc | Mặc định | Mô tả |
| --- | --- | --- | --- |
| `name` | Có | - | Tên website cần theo dõi. |
| `monitor_type` | Có | `simple_web` | Dùng `simple_web`. |
| `url` | Có | - | URL website cần kiểm tra HTTP/HTTPS. |
| `expected_status` | Không | `200` | Status code mong đợi khi truy cập website. |
| `expected_text` | Không | Trống | Nội dung phải có trong HTML/text trả về. Để trống nếu chỉ cần biết URL có trả HTTP đúng hay không. |
| `headers_json` | Không | `{}` | Header bổ sung nếu website yêu cầu. |

### Auth Web

| Thông số | Bắt buộc | Mặc định | Mô tả |
| --- | --- | --- | --- |
| `monitor_type` | Có | - | Dùng `auth_web`. |
| `url` | Có | - | Trang sau đăng nhập hoặc trang cần xác minh. |
| `auth_login_url` | Có | Theo `url` nếu trống | URL form login. App gửi request `POST` tới URL này. |
| `auth_username` | Có | Trống | Tài khoản đăng nhập. |
| `auth_password` | Có | Trống | Mật khẩu đăng nhập. Được mã hóa khi lưu DB. |
| `auth_username_field` | Không | `username` | Tên field username trong form login. |
| `auth_password_field` | Không | `password` | Tên field password trong form login. |
| `auth_extra_fields` | Không | `{}` | JSON object cho field phụ. Hidden input trong form login được app tự lấy; chỉ nhập field cần ghi đè hoặc bổ sung. |
| `auth_verify_url` | Không | Theo `url` | URL được gọi sau login để xác minh session/cookie. |
| `auth_verify_text` | Không | Trống | Chuỗi phải xuất hiện sau login, ví dụ `Dashboard` hoặc tên người dùng. Nên nhập để tránh báo UP giả khi đăng nhập thất bại nhưng trang login vẫn trả HTTP 200. |
| `expected_status` | Không | `200` | HTTP status mong đợi ở bước verify. |
| `headers_json` | Không | `{}` | Header bổ sung khi login/verify. |

Ví dụ với `https://at.npc.com.vn:8031`:

| Thông số | Giá trị gợi ý |
| --- | --- |
| `monitor_type` | `auth_web` |
| `url` / Protected URL | `https://at.npc.com.vn:8031/` |
| `auth_login_url` | `https://at.npc.com.vn:8031/Account/Login` |
| `auth_username_field` | `UserName` |
| `auth_password_field` | `Password` |
| `auth_extra_fields` | `{}` hoặc `{"RememberMe":"false"}` |
| `auth_verify_url` | URL trang cần xác minh sau đăng nhập, thường là `https://at.npc.com.vn:8031/` |
| `auth_verify_text` | Một chuỗi chỉ xuất hiện sau khi đăng nhập thành công, ví dụ tên màn hình dashboard hoặc tên tài khoản. |

Trang này có hidden field `__RequestVerificationToken` thay đổi theo phiên. Không copy token này vào Excel/app; SiteSentry tự lấy token mới từ trang login trước khi POST.

#### Lấy thông tin form bằng DevTools Console

SiteSentry không chạy Java trong trình duyệt; các đoạn dưới đây là **JavaScript** chạy trong Console của Chrome/Edge. Chúng chỉ đọc cấu trúc trang hiện tại, không gửi form và không đọc/in mật khẩu, cookie hoặc giá trị token.

1. Mở URL đăng nhập khi đang ở trạng thái chưa đăng nhập.
2. Mở DevTools (`F12`) → **Console**. Nếu Chrome hiện cảnh báo dán mã, chỉ nhập `allow pasting` khi bạn đã tự đọc và hiểu đoạn mã. Sau đó dán đoạn “Kiểm tra form đăng nhập” và nhấn Enter.
3. Chọn đúng form đăng nhập trong kết quả (trang có thể có nhiều form). Dùng `action` làm Login URL; xem `method`, username/password field và các tên hidden field. Nếu form được dựng trong iframe, chọn frame đó trong Console trước khi chạy mã.
4. Điền username/password field đúng theo thuộc tính `name` trong form. Hidden field được SiteSentry tự lấy lại ở mỗi lần kiểm tra; không chép token hay giá trị hidden vào cấu hình. `Extra login fields JSON` chỉ dành cho field phụ mà form cần nhưng không tự có trong HTML ban đầu.
5. Đăng nhập thủ công bằng trình duyệt. Trên trang đích đã đăng nhập, chạy đoạn “Gợi ý Verify text” để tìm một chuỗi ổn định, chỉ xuất hiện sau đăng nhập. Nhập URL trang đó vào Verify URL (để trống nếu muốn dùng Protected URL).
6. Chạy **Test Run** trong SiteSentry. Nếu thất bại, mở DevTools → **Network**, chọn request đăng nhập thành công, rồi đối chiếu Request URL/Method, tên field và Request Headers. JavaScript trong Console không thể đọc đầy đủ các header do trình duyệt quản lý; không cần chép toàn bộ header trình duyệt vào `Headers JSON`. SiteSentry tự đặt Content-Type cho form và Referer của POST; chỉ thêm header tùy chỉnh khi máy chủ thực sự yêu cầu. Không chia sẻ mật khẩu, cookie, giá trị token hoặc dữ liệu phiên.

**Kiểm tra form đăng nhập** (chạy ở trang login):

```javascript
(() => {
  const redact = (value) => value ? "<có giá trị; đã ẩn>" : "<rỗng>";
  const forms = [...document.forms].map((form, index) => ({
    form: index,
    action: new URL(form.getAttribute("action") || location.href, location.href).href,
    method: (form.method || "get").toUpperCase(),
    enctype: form.enctype,
    fields: [...form.elements]
      .filter((el) => el.name)
      .map((el) => ({
        name: el.name,
        id: el.id || "",
        type: (el.type || el.tagName).toLowerCase(),
        autocomplete: el.autocomplete || "",
        required: Boolean(el.required),
        disabled: Boolean(el.disabled),
        value: redact(el.value)
      }))
  }));
  console.log({
    pageUrl: location.href,
    origin: location.origin,
    forms,
    note: "Chỉ dùng name của hidden field để đối chiếu. SiteSentry tự lấy giá trị hidden mới theo phiên."
  });
})();
```

Kết quả cung cấp URL trang login, URL/action gửi POST, method, enctype, `name`/`id`/loại của input và tên các hidden field. Với form login thông thường, chọn tên input có `type: "text"` hoặc `email` làm Username field và `type: "password"` làm Password field. Giá trị field bị ẩn có chủ ý.

**Gợi ý Verify text** (chạy sau khi đăng nhập thành công):

```javascript
(() => {
  const visible = (el) => {
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0;
  };
  const candidates = [...document.querySelectorAll("h1,h2,h3,[role='heading'],nav a,button,[role='button']")]
    .filter(visible)
    .map((el) => (el.innerText || el.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim())
    .filter((text) => text.length >= 2 && text.length <= 100);
  console.log({
    currentUrl: location.href,
    title: document.title,
    candidates: [...new Set(candidates)].slice(0, 50),
    note: "Chọn một chuỗi ổn định chỉ có sau khi đăng nhập; kiểm tra chuỗi đó có trong response HTML mà SiteSentry nhận được."
  });
})();
```

Đoạn Verify chỉ gợi ý text nhìn thấy trong DOM; một số ứng dụng render nội dung bằng JavaScript nên nội dung đó có thể không xuất hiện trong HTML mà checker HTTP nhận được. Nếu vậy, chọn text có sẵn trong response HTML hoặc dùng một endpoint verify phù hợp. `document.cookie` không được đọc hoặc in ra: cookie phiên là dữ liệu nhạy cảm và trình duyệt cũng ẩn cookie `HttpOnly` khỏi JavaScript.

### API

| Thông số | Bắt buộc | Mặc định | Mô tả |
| --- | --- | --- | --- |
| `monitor_type` | Có | - | Dùng `api`. |
| `url` | Có | - | REST API endpoint cần kiểm tra. |
| `method` | Không | `GET` | HTTP method: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`. |
| `headers_json` | Không | `{}` | Header dạng JSON object. |
| `body` | Không | Trống | Request body cho `POST`, `PUT`, `PATCH`, hoặc API cần payload. Được mã hóa khi lưu DB. |
| `api_token` | Không | Trống | Token API. Được mã hóa khi lưu DB. |
| `api_token_header` | Không | `Authorization` | Tên header chứa token. |
| `api_token_prefix` | Không | `Bearer` | Tiền tố token. Để trống nếu header chỉ cần token thô. |
| `expected_status` | Không | `200` | HTTP status code mong đợi. |
| `expected_text` | Không | Trống | Chuỗi cần có trong response. |
| `expected_json_path` | Không | Trống | Đường dẫn JSON dạng dot path, ví dụ `status` hoặc `data.items[0].state`. |
| `expected_json_value` | Không | Trống | Giá trị mong đợi tại `expected_json_path`. So sánh theo dạng chuỗi. |
