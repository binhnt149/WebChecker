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
- Lưu log kiểm tra vào SQLite, xem log trong app và xuất CSV.
- Chạy kiểm tra thủ công từng monitor hoặc toàn bộ monitor.
- Scheduler chạy nền định kỳ cho các monitor đang bật.
- Retry guard: thử lại nhiều lần trước khi kết luận lỗi.
- SMTP HTML alert khi monitor down và email recovery khi monitor phục hồi.
- Cooldown theo từng monitor để tránh spam email cảnh báo.
- Mã hóa thông tin nhạy cảm trước khi lưu DB.
- Hỗ trợ chạy ẩn dưới system tray trên Windows/macOS/Linux khi tray khả dụng.

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
│   ├── scheduler.py       # Lập lịch APScheduler và gọi checker định kỳ
│   ├── notifier.py        # SMTP email alert, HTML template, cooldown
│   └── excel_importer.py  # Tạo template Excel và import monitor hàng loạt
├── ui/
│   ├── main_window.py     # App chính, sidebar, view routing, scheduler/tray integration
│   ├── dashboard_view.py  # Dashboard, danh sách monitor, import Excel, quick actions
│   ├── monitor_dialog.py  # Dialog thêm/sửa monitor theo tab Web/Auth/API
│   ├── logs_view.py       # Xem log, lọc trạng thái, export CSV, xóa log
│   ├── settings_view.py   # SMTP/theme/settings và test email
│   └── focus.py           # Helper xử lý focus/click cho ô nhập liệu
├── main.py                # Entry point, kiểm tra Python runtime rồi mở app
├── run.sh                 # Script chạy app và tự kiểm tra dependencies
├── requirements.txt       # Danh sách thư viện Python
├── config.json            # Cấu hình runtime ban đầu
├── data/                  # SQLite DB và Fernet key được sinh khi chạy
└── templates/             # File mẫu Excel cho import monitor
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

Settings View dùng để cấu hình SMTP, bật/tắt STARTTLS, người gửi, người nhận, mật khẩu SMTP, cooldown mặc định và theme giao diện.

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

1. Scheduler so sánh trạng thái mới với trạng thái cũ.
2. Nếu monitor chuyển sang `down`, app kiểm tra cooldown rồi gửi email cảnh báo.
3. Nếu monitor trước đó `down` và nay `up`, app gửi email recovery.
4. Khi gửi email thành công, app lưu `last_alert_at` hoặc `last_recovery_alert_at` để áp dụng cooldown cho lần sau.

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

SQLite có ba nhóm bảng chính:

- `monitors`: cấu hình monitor, trạng thái cuối, thời điểm kiểm tra cuối, thông tin cooldown alert.
- `logs`: lịch sử từng lần kiểm tra, gồm status, HTTP code, response time, error, attempts và detail JSON.
- `settings`: cấu hình ứng dụng và SMTP; các setting nhạy cảm được đánh dấu secret và mã hóa.

Database bật `PRAGMA foreign_keys = ON` và `journal_mode = WAL` để hỗ trợ ghi/đọc ổn định trong quá trình app chạy nền.

## System tray

Ứng dụng có cơ chế system tray bằng `pystray` và `Pillow`. Khi tray khả dụng, người dùng có thể ẩn app xuống tray, mở lại app, chạy `Run All Now` hoặc thoát app từ menu tray.

Khi người dùng bấm nút đóng cửa sổ, app sẽ ẩn xuống tray thay vì thoát hẳn nếu tray đang hoạt động. Muốn thoát hoàn toàn, chọn `Quit` trong menu tray. Có thể bật/tắt tray qua `config.json` bằng `enable_system_tray`.

## Logs và xuất Excel

Màn hình Logs hỗ trợ:

- Lọc trạng thái `all`, `up`, `down`.
- Lọc theo khoảng thời gian bằng `From` và `To`, định dạng `YYYY-MM-DD` hoặc `YYYY-MM-DD HH:MM:SS`.
- Xuất Excel `.xlsx` theo đúng bộ lọc đang chọn.
- Xuất CSV theo đúng bộ lọc đang chọn.

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

Repo cũng có GitHub Actions workflow tại `.github/workflows/build.yml`. Khi push tag dạng `v1.0.0` hoặc chạy `workflow_dispatch`, GitHub Actions sẽ build cả macOS DMG và Windows EXE, rồi upload artifact trong trang Actions.

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
| `cooldown_minutes` | Tất cả | Không | `30` | Thời gian chống spam email cảnh báo cho cùng một monitor. |

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
