# Đặc tả kỹ thuật: phân loại sự cố trước khi gửi email

**Dự án:** SiteSentry Desktop

**Ngày:** 28/10/2026

**Cơ sở:** mã nguồn v1.2.0, commit `687d0cf`

**Trạng thái:** phạm vi và các mặc định đã được duyệt; tài liệu này là hợp đồng yêu cầu và tiêu chí nghiệm thu cho phiên bản nâng cấp.

## 1. Mục tiêu và phạm vi

Người vận hành dùng một ứng dụng desktop để theo dõi Web, Auth Web và REST API trên Internet và trong mạng nội bộ/VPN. Ứng dụng cần xác định **nhóm lỗi có bằng chứng** trước khi quyết định gửi email sự cố; bằng chứng phải đủ rõ để người vận hành phân biệt hiện tượng quan sát được với nguyên nhân chỉ đang nghi ngờ.

Kết quả cần đạt:

1. Nhận diện lỗi chung tự động và hỗ trợ quy tắc phân loại riêng cho từng monitor.
2. Ghi trạng thái, nhóm lỗi, giai đoạn thất bại và bằng chứng đã che dữ liệu nhạy cảm; hiển thị và xuất dữ liệu này.
3. Monitor DOWN mà chưa xác định được nhóm lỗi vẫn được lưu log và tiếp tục kiểm tra, nhưng không tạo email DOWN/UP của sự cố đó. Monitor này cũng không xuất hiện trong email tổng hợp theo lịch khi đang DOWN chưa phân loại.
4. Giữ thứ tự DOWN/UP, bộ lọc, gộp danh sách, lịch email, nhiều người nhận và khả năng nâng cấp dữ liệu v1.2.0.
5. Cập nhật form monitor, Test Run, template/import Excel, Dashboard, Logs, báo cáo và cấu hình lịch email cùng một hợp đồng phân loại.

Không sửa chữa hoặc thay đổi cấu hình hệ thống Web/API đích. Không thể cam kết suy ra mọi nguyên nhân gốc nếu máy chủ không cung cấp bằng chứng; trường hợp đó phải thể hiện đúng mức chưa xác định.

### 1.1 Quyết định và giả định

| Nội dung | Trạng thái |
| --- | --- |
| Chỉ email sự cố sau khi xác định nhóm lỗi; vẫn lưu và kiểm tra lại lỗi chưa xác định | Đã xác nhận |
| Tự động phân loại chung kết hợp quy tắc riêng theo monitor | Đã xác nhận |
| Hỗ trợ Internet và mạng nội bộ/VPN | Đã xác nhận |
| Bỏ monitor đang DOWN chưa phân loại khỏi email tổng hợp | Đã xác nhận |
| Các giới hạn, thứ tự ưu tiên, tên cột và giá trị mặc định trong tài liệu | Đã duyệt trong phạm vi nâng cấp |
| Không tự thăm dò Internet/địa chỉ thứ ba mặc định; profile mạng và đích thăm dò do người dùng cấu hình | Đã duyệt |
| Nếu không xác định được SMTP đã nhận thư hay chưa, đánh dấu cần xử lý thay vì tự hứa gửi đúng một lần | Đã duyệt; xem §10 và §17 |

## 2. Bản đồ năng lực

Đây là một tài liệu duy nhất theo yêu cầu; các mã module dưới đây giúp truy vết yêu cầu và tiêu chí nghiệm thu. Tên file triển khai trong §14 là vị trí dự kiến, không bắt buộc tạo module mới nếu vẫn bảo đảm hợp đồng.

| Mã | Trách nhiệm | Phụ thuộc |
| --- | --- | --- |
| `evidence-classification` | Thu thập bằng chứng và phân loại Web/Auth/API | — |
| `network-diagnostics` | Bằng chứng mạng theo phạm vi Internet hoặc nội bộ/VPN | `evidence-classification` |
| `monitor-rules` | Quy tắc riêng, kiểm tra cấu hình, profile và import Excel | `evidence-classification` |
| `incident-persistence` | Lưu lần kiểm tra, trạng thái sự cố, nâng cấp SQLite | `evidence-classification` |
| `incident-email` | Điều kiện gửi, gom, lọc và phục hồi theo từng lịch | `incident-persistence` |
| `operator-views` | Form, Test Run, Dashboard, Logs, báo cáo và Excel | `monitor-rules`, `incident-persistence`, `incident-email` |

Hướng phụ thuộc: bộ phân loại định nghĩa kết quả chung; các phần mạng/quy tắc cung cấp bằng chứng cho bộ phân loại; lưu trữ và email dùng kết quả đó; giao diện trình bày kết quả và cấu hình. Bản đồ là ranh giới chức năng, không yêu cầu chia nhỏ thành nhiều file đặc tả.

## 3. Hiện trạng cần thay đổi

- `checker.py` và `diagnostics.py` trả `CheckResult.error_type`; 11 nhóm cũ gồm `unknown` đã có trong Dashboard/Logs và email.
- HTTP 401 hiện được gán `auth_credentials` cho cả Web/Auth/API; điều đó xác nhận yêu cầu chưa được xác thực, không chứng minh riêng mật khẩu sai. 403 hiện là `http_error`.
- Auth Web dùng form POST, cookie và trang verify; nhận diện thông báo từ chối dựa trên tập câu cố định. Không phải mọi website đều trả thông báo theo các câu đó.
- API HTTP 200 chỉ bị DOWN theo nội dung khi có cấu hình expected text hoặc JSON assertion. Không tự biết `{"success": false}` là lỗi nghiệp vụ.
- Kiểm tra route hiện chỉ đưa ra bằng chứng ở máy giám sát; một route còn tồn tại không chứng minh kết nối Internet/VPN hoạt động.
- `record_check_result` ghi log, trạng thái monitor và quyết định tạo email trong SQLite. Quy tắc hiện tại có thể đưa `unknown` vào hàng đợi nếu người dùng không loại nó; điều này phải thay đổi theo §10.
- File mẫu monitor v1.2.0 có sheet `Monitors` và `Instructions`, 30 cột kết thúc bằng `language`, `web_server`. Dữ liệu và file cũ cần tiếp tục dùng được.

## 4. Thuật ngữ và hợp đồng kết quả

**Nhóm lỗi đã xác định** nghĩa là có bằng chứng trực tiếp cho nhóm hiện tượng, hoặc khớp quy tắc do người dùng cấu hình. Ví dụ HTTP 503 xác nhận nhóm HTTP 5xx; nó không xác nhận nguyên nhân gốc là ứng dụng, proxy hay bảo trì. Một quy tắc riêng chỉ xác nhận “khớp quy tắc người dùng”, độ đúng của quy tắc phụ thuộc cấu hình.

**Chưa xác định** là chưa có đủ bằng chứng cho một nhóm lỗi, bằng chứng xung đột, hoặc kết quả chẩn đoán đã cũ/không cùng phạm vi mạng. Không suy đoán nguyên nhân để đủ điều kiện gửi thư.

Kết quả của một lần kiểm tra sau retry phải có ít nhất:

| Trường logic | Kiểu / ý nghĩa |
| --- | --- |
| `status` | `up` hoặc `down`; giữ tương thích các giá trị cũ `unknown`/paused của monitor |
| `classification_state` | `confirmed`, `undetermined` hoặc `not_applicable` khi UP |
| `error_type` | Mã nhóm ổn định trong §5; `unknown` khi `undetermined`, rỗng khi UP |
| `reason_code` | Mã chi tiết tùy chọn, chỉ được đặt khi có bằng chứng tương ứng |
| `phase` | `configuration`, `resolve`, `connect`, `tls`, `request`, `login_page`, `login_submit`, `verify`, `response`, `assertion` hoặc `network_probe` |
| `evidence_source` | `transport`, `http`, `response_rule`, `assertion`, `local_network` hoặc `network_probe`; ghi `rule_id` nếu do quy tắc riêng |
| `evidence` | Các trường an toàn, có cấu trúc: HTTP code, loại exception, thời điểm, trạng thái probe, tên quy tắc, phần mô tả đã che bí mật |
| `checked_at`, `attempts`, `response_ms` | Thời gian, số lần thử, thời gian phản hồi; có thể null khi không đo được |

Bất biến: `UP` không có nhóm lỗi hoạt động; `DOWN + confirmed` phải có mã khác `unknown` và bằng chứng; `DOWN + undetermined` dùng `unknown` và không đủ điều kiện email. Lưu dấu thời gian theo cùng quy ước v1.2.0 cho dữ liệu cũ; không diễn giải lại múi giờ của log lịch sử. Các sự kiện mới phải so sánh và hiển thị nhất quán theo múi giờ máy đã cấu hình.

Ví dụ hợp đồng dự kiến, dùng dữ liệu giả:

```python
Diagnosis(
    status="down",
    classification_state="confirmed",
    error_type="http_error",
    reason_code="http_503",
    phase="response",
    evidence_source="http",
    evidence={"status_code": 503},
)
```

Tên class/schema cụ thể có thể điều chỉnh khi triển khai nếu các trường và bất biến vẫn được bảo đảm. Mã, hàm và biến Python dùng `snake_case`; kiểu/class dùng `PascalCase`. Mã nhóm và mã chi tiết là định danh ổn định, không dịch theo ngôn ngữ giao diện.

Ví dụ phong cách từ `sitesentry/core/reports.py` hiện có:

```python
def format_duration(seconds: float) -> str:
    seconds = max(0, round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
```

## 5. Danh mục phân loại và mức bằng chứng

Giữ các mã nhóm v1.2.0 để bộ lọc/log cũ không mất ý nghĩa. `reason_code` mở rộng mức chi tiết, không bắt buộc giá trị đó phải có trong dữ liệu cũ.

| `error_type` | Tình huống / `reason_code` gợi ý | Bằng chứng tối thiểu và giới hạn |
| --- | --- | --- |
| `auth_credentials` | `auth_rejected`, `username_rejected`, `password_rejected`, `token_rejected` | HTTP 401 là từ chối xác thực chung; chỉ tách username/mật khẩu/token nếu thông báo/quy tắc chỉ rõ. Không suy từ 401/403 một mình. |
| `auth_verification` | `login_page_returned`, `session_unverified`, `captcha_required`, `mfa_required`, `csrf_rejected` | Giai đoạn login/verify, URL hoặc nội dung đặc thù khớp quy tắc/điều kiện; CAPTCHA/MFA/CSRF chỉ ghi chi tiết khi có bằng chứng riêng. |
| `timeout` | `connect_timeout`, `read_timeout`, `write_timeout`, `pool_timeout` | Exception timeout đúng giai đoạn; `pool_timeout` là chờ tài nguyên phía máy giám sát, không kết luận server DOWN. |
| `target_unreachable` | `connection_refused`, `connection_reset`, `remote_protocol`, `proxy_error` | Exception kết nối/giao thức/proxy; giữ `phase` và phạm vi, không tự xác nhận nguyên nhân gốc. |
| `network_offline` | `local_interface_down`, `local_no_route` | Bằng chứng hệ điều hành về trạng thái mạng/route thực sự áp dụng cho đích; lỗi tới riêng một host không đủ kết luận máy mất mạng. |
| `dns_error` | `dns_resolution_failed` | Exception phân giải tên; không gán lỗi DNS thành sai mật khẩu hoặc chắc chắn mất Internet. |
| `tls_error` | `certificate_invalid`, `tls_handshake_failed` | Exception SSL/TLS hoặc bằng chứng lỗi chứng chỉ; không tự tắt xác minh TLS. |
| `http_error` | `http_403`, `http_404`, `http_429`, `http_5xx`, `http_unexpected` | HTTP khác kỳ vọng; 403 là bị từ chối quyền/yêu cầu, 429 là giới hạn yêu cầu, 5xx là phản hồi lỗi server/proxy. Không đoán nguyên nhân sâu hơn. |
| `assertion_failed` | `text_mismatch`, `json_path_missing`, `json_value_mismatch`, `business_rule_match` | HTTP 200 nhưng điều kiện text/JSON hoặc quy tắc nghiệp vụ thất bại. Chỉ kết luận nội dung thực tế khớp/không khớp; không tự gọi là lỗi nghiệp vụ khi chưa có quy tắc. |
| `configuration_error` | `invalid_url`, `invalid_headers`, `invalid_rule`, `invalid_profile` | Cấu hình không hợp lệ được xác thực trước request; không quy kết website ngừng hoạt động. |
| `unknown` | `unclassified`, `conflicting_evidence` | Bằng chứng không đủ hoặc xung đột; `classification_state=undetermined`. Không coi `unknown` là nhóm đủ điều kiện email. |

Các nhóm áp dụng cho cả Web/Auth/API khi có hiện tượng tương ứng; `auth_verification` chủ yếu cho Auth Web, JSON assertion cho API. `reason_code` chưa biết vẫn được phép để trống nếu nhóm đã có bằng chứng. HTTP 401 chỉ là nhóm xác thực chung; HTTP 403 không tự động là lỗi mật khẩu. Ngữ nghĩa HTTP dựa trên [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html) và [RFC 6585, mục 4](https://www.rfc-editor.org/rfc/rfc6585.html#section-4); các giai đoạn timeout/transport tham khảo [HTTPX Exceptions](https://www.python-httpx.org/exceptions/).

## 6. Luồng kiểm tra và quy tắc ưu tiên

1. Xác thực cấu hình monitor và profile; lỗi cấu hình được phân loại trước khi tạo request.
2. Chạy request đã cấu hình cho Web/API hoặc các bước login/verify của Auth Web; thu thập bằng chứng an toàn. Test Run dùng cùng bộ phân loại nhưng không ghi sự cố hay gửi email.
3. Áp dụng retry guard hiện có. Không tự thử lại đăng nhập bị từ chối rõ ràng hoặc cấu hình lỗi; các lần thử còn lại tôn trọng `retry_count` và `retry_delay_seconds`. Chỉ kết quả cuối sau retry quyết định trạng thái monitor và email.
4. Khi cần và profile cho phép, lấy bằng chứng mạng bổ sung theo §8; thời gian chẩn đoán được giới hạn và không chặn luồng GUI.
5. Phân loại theo thứ tự: lỗi cấu hình/transport có bằng chứng → quy tắc riêng áp dụng đúng giai đoạn, không mâu thuẫn bằng chứng transport → HTTP khác mong đợi → assertion nội dung → `unknown` nếu thiếu hoặc xung đột bằng chứng. Quy tắc nội dung không được biến lỗi TLS/transport hoặc phản hồi HTTP 5xx thành lỗi mật khẩu. Với 401/403/429, quy tắc riêng chỉ được bổ sung phân loại cụ thể hơn khi điều kiện bao gồm chính HTTP status đó và bằng chứng nội dung, đồng thời vẫn lưu mã HTTP thực tế.
6. Lưu kết quả và cập nhật trạng thái sự cố bằng giao dịch SQLite; chỉ sau đó xét lịch, bộ lọc, thời gian gộp và hàng đợi email.

Phân biệt **chẩn đoán** và **nguyên nhân gốc**: nếu xác định được nhóm HTTP nhưng chưa rõ nguyên nhân gốc, `confirmed/http_error` vẫn được xét gửi theo lịch; email ghi HTTP và bằng chứng, không khẳng định nguyên nhân gốc. Nếu không xác định nổi nhóm, giữ `unknown/undetermined`.

## 7. Quy tắc riêng cho từng monitor

Mỗi monitor có thể khai báo danh sách quy tắc có `id`, `enabled`, `priority`, `phase`, điều kiện và kết quả `error_type`/`reason_code`. Cùng một cấu hình dùng cho kiểm tra định kỳ và Test Run. Các mẫu ví dụ dùng nội dung giả, không chứa tài khoản hay token.

Điều kiện tối thiểu cần hỗ trợ:

- HTTP status khớp một mã hoặc dải mã; điều kiện text hiển thị `equals`/`contains` sau chuẩn hóa Unicode/khoảng trắng; tùy chọn phân biệt chữ hoa/thường.
- JSON path theo cú pháp hiện có (`a.b`, `a[0].b`) và phép bằng/khác trên giá trị JSON có kiểu. Với quy tắc mới, `true`, `false`, số, chuỗi và `null` phải giữ đúng kiểu; giá trị `false`, `0` và chuỗi rỗng không được coi là chưa nhập.
- Giai đoạn `login_page`, `login_submit`, `verify`, `response` hoặc `assertion`, phù hợp loại monitor. Chuỗi ẩn, script/style và nội dung hỗ trợ tĩnh không được mặc định coi là thông báo đăng nhập bị từ chối.
- Chỉ nhận danh mục nhóm lỗi hợp lệ; không cho người dùng định nghĩa mã `unknown` thành kết quả xác nhận. Quy tắc không thể tự xác nhận `network_offline` chỉ bằng text/JSON website.

Đề xuất an toàn: tối đa 20 quy tắc/monitor, tối đa 1.024 ký tự/giá trị so khớp và không hỗ trợ regex trong phiên bản đầu; form và import hiển thị lỗi nếu vượt giới hạn. Các giới hạn này cần được review trước triển khai.

Quy tắc có `priority` cao hơn được xét trước. Nếu nhiều quy tắc cùng ưu tiên cao nhất cùng khớp và kết luận các nhóm khác nhau, kết quả là `unknown/conflicting_evidence`; ghi danh sách `rule_id`, không gửi cảnh báo. Nếu cùng nhóm, chọn theo `id` ổn định và lưu các quy tắc đã khớp. Quy tắc chỉ có hiệu lực trên response/giai đoạn đã chỉ định.

Hợp đồng JSON đề xuất cho `diagnostic_rules_json`: mảng object có `id` duy nhất trong monitor, `enabled` Boolean, `priority` số nguyên, `phase`, `conditions` không rỗng và `result`. Tất cả điều kiện trong một rule phải cùng khớp; điều kiện OR được biểu diễn bằng các rule riêng. `source` là `http_status`, `visible_text` hoặc `json`; `json` cần `path`, mọi điều kiện cần `operator` và `value`. `reason_code` có thể trống hoặc gồm 1–64 ký tự `a-z`, `0-9`, `_`; `error_type` phải thuộc danh mục xác định ở §5.

| `source` | `operator` | `value` |
| --- | --- | --- |
| `http_status` | `equals`, `range` | Số nguyên 100–599; với `range` là mảng hai số nguyên `[min, max]`, bao gồm cả hai đầu |
| `visible_text` | `equals`, `contains` | Chuỗi; mặc định không phân biệt hoa/thường, có thể bật `case_sensitive: true` |
| `json` | `equals`, `not_equals` | Giá trị JSON giữ kiểu; `path` phải tồn tại để điều kiện khớp |

Ví dụ cho API:

```json
[
  {
    "id": "api-success-false",
    "enabled": true,
    "priority": 100,
    "phase": "response",
    "conditions": [
      {"source": "json", "path": "success", "operator": "equals", "value": false}
    ],
    "result": {"error_type": "assertion_failed", "reason_code": "business_rule_match"}
  }
]
```

Với rule này, API trả HTTP 200, JSON `{"success": false}` → `assertion_failed/business_rule_match`. Nếu không có assertion/quy tắc, HTTP 200 vẫn có thể UP; form cần giải thích giới hạn này. Với Auth Web, phản hồi chỉ ghi “tài khoản hoặc mật khẩu không đúng” → `auth_credentials/auth_rejected`, không tự tách tài khoản và mật khẩu.

Trường `expected_json_path`/`expected_json_value` cũ tiếp tục dùng cách so sánh chuỗi v1.2.0, kể cả trường hợp giá trị mong đợi rỗng trước đây chỉ kiểm tra sự tồn tại của path. Không tự chuyển ý nghĩa chuỗi `"false"` thành Boolean `false`; khi người dùng muốn so sánh theo kiểu, họ khai báo quy tắc mới như ví dụ trên. Có thể hỗ trợ thao tác chuyển đổi rõ ràng trong form, kèm preview và yêu cầu người dùng lưu cấu hình đã chuyển.

## 8. Chẩn đoán mạng Internet và nội bộ/VPN

Một **network profile** có tên duy nhất, phạm vi mô tả (`internet`, `intranet_vpn`, `custom`) và danh sách đích kiểm tra tham chiếu do người dùng nhập. Monitor có thể gắn một profile; không gắn profile là hợp lệ. Khái niệm profile là cấu hình người dùng, không tự phát hiện hay sửa cấu hình VPN.

- Mặc định không có đích bên ngoài và không tự gửi probe. Khi được cấu hình/bật, probe chỉ dùng HTTP(S) GET/HEAD tới URL tham chiếu, không kèm cookie, token, tài khoản, body hoặc header của monitor; không gửi POST/PUT/PATCH/DELETE cho mục đích chẩn đoán. URL probe không được chứa userinfo hoặc tham số bí mật; redirect không tự đi tới host ngoài danh sách đích đã cấu hình.
- Probe chỉ chạy khi cần phân tích lỗi kết nối hoặc do người dùng chủ động thử profile. Đề xuất mặc định: timeout 2 giây/đích; tối đa 2 đích/profile; mỗi profile chỉ có một probe đang chạy; tái sử dụng kết quả tối đa 60 giây. Nếu hết hạn, không dùng kết quả cũ để khẳng định nhóm lỗi. Giới hạn và việc tự động probe phải hiển thị trong cấu hình.
- Probe thành công chứng minh có đường tới **đích tham chiếu đó** ở thời điểm kiểm tra. Probe thất bại chỉ chứng minh không tới được đích tham chiếu; không tự chứng minh toàn bộ Internet, VPN hoặc máy giám sát offline. HTTP response bất kỳ chứng minh đã tới một HTTP endpoint, không chứng minh dịch vụ được giám sát khỏe.
- Chỉ xác nhận `network_offline` khi có bằng chứng hệ điều hành áp dụng cho mạng/route của đích. Không gán `ENETUNREACH` của riêng một đích thành mất toàn bộ mạng máy nếu không có kiểm chứng bổ sung. Nếu thiếu bằng chứng, giữ nhóm trực tiếp quan sát được (`timeout`, `dns_error`, `target_unreachable`) hoặc `unknown`; không suy ra trạng thái máy.
- Hệ thống không đưa credential hoặc dữ liệu nhạy cảm vào log/email probe. Hồ sơ nội bộ/VPN có thể dùng đích tham chiếu nội bộ do người quản trị lựa chọn; không yêu cầu truy cập Internet công cộng.

Không tạo request thay đổi dữ liệu ngoài request monitor người dùng đã cấu hình. Các monitor API POST/PUT/PATCH/DELETE hiện hữu tiếp tục thực hiện theo cấu hình và retry guard; các tác động có thể có của chính request đó cần được nêu rõ trong form và tài liệu.

## 9. Trạng thái sự cố và lưu bền vững

Trạng thái sau đây là trạng thái logic theo **monitor + một đợt DOWN**; quyền gửi còn được xét riêng cho từng lịch email:

| Trước | Kết quả mới | Hành vi |
| --- | --- | --- |
| UP/unknown | DOWN chưa xác định | Mở đợt DOWN, lưu `undetermined`; không tạo email; kiểm tra lại theo lịch monitor. |
| DOWN chưa xác định | DOWN đã phân loại | Cập nhật bằng chứng và nhóm; xét từng lịch đang bật, bộ lọc và cửa sổ gộp; tối đa một DOWN cho đợt/lịch. |
| DOWN chưa xác định | UP | Đóng đợt, giữ log; không tạo email DOWN hoặc UP đơn lẻ cho đợt đó. |
| DOWN đã phân loại | DOWN cùng/khác nhóm | Lưu mọi lần kiểm tra; không gửi DOWN lặp cho lịch đã được gửi/đưa vào hàng đợi hợp lệ. Nếu trước đó nhóm bị lịch loại mà nhóm sau được phép, xét gửi một lần như v1.2.0. |
| DOWN đã được lịch chấp nhận | UP | Lịch `incident` tạo tối đa một UP sau DOWN tương ứng, kể cả khi lần kiểm tra gần nhất chưa rõ, dựa trên nhóm/bằng chứng của DOWN đã chấp nhận. |
| DOWN đã phân loại, lịch `recovery_only` đủ điều kiện | UP | Tối đa một UP nếu nhóm được phân loại và không bị lịch loại; DOWN không được gửi bởi lịch này. |

Nếu một đợt đã có DOWN hợp lệ nhưng gửi SMTP chưa hoàn tất, UP được xếp sau DOWN theo thứ tự của từng monitor/lịch. Một đợt `unknown → UP` không tạo UP cho cả `incident` lẫn `recovery_only`. Tắt monitor, xóa rule, thay đổi rule hoặc SMTP phải được xử lý theo quyền hiện có và không tạo email UP mồ côi.

Kết quả `unknown` lưu trong DB, tồn tại qua restart và được đánh giá lại ở **lần kiểm tra mới**, không sửa log lịch sử hay giả định lỗi đã hết. Lần kiểm tra lại giữ chu kỳ, timeout và retry của monitor; không chạy vòng lặp chẩn đoán liên tục. Thời điểm bắt đầu DOWN, thời điểm xác định nhóm và thời điểm gửi là ba trường khác nhau.

Nếu lịch hoặc SMTP được bật lại trong khi đợt DOWN đã xác định vẫn mở, lần kiểm tra DOWN hợp lệ tiếp theo xét gửi một lần cho lịch chưa có DOWN hợp lệ; không gửi lại cho lịch đã có DOWN. Nếu đợt đã UP khi lịch/SMTP còn tắt, không tạo email hồi tố hay UP mồ côi khi bật lại.

Giao dịch phải ghi kết quả, trạng thái sự cố và quyết định hàng đợi nhất quán. Một worker không được tạo trùng sự kiện khi hai lần kiểm tra cùng monitor chồng lấp hoặc sau restart. Giao dịch SQLite bảo đảm thay đổi cùng transaction cùng thành công hoặc cùng rollback; tham khảo [SQLite transactions](https://sqlite.org/transactional.html). Gửi SMTP nằm ngoài transaction và có giới hạn ở §10.

## 10. Email, lọc, gộp và lịch tổng hợp

1. Điều kiện email sự cố: `DOWN + confirmed + error_type != unknown`, lịch bật, SMTP bật và nhóm không bị lịch loại. Kiểm tra lại điều kiện tại thời điểm claim/gửi để tránh cấu hình thay đổi giữa lúc đọc hàng đợi và bắt đầu gửi.
2. Lọc nhóm áp dụng độc lập theo từng lịch; thay đổi loại trừ phải chặn các thư chưa bắt đầu gửi. Thư đã SMTP chấp nhận không thể thu hồi. Lưu kết quả nhóm/bằng chứng của DOWN cho UP tương ứng; không để thay đổi loại lịch làm mất nguồn gốc sự kiện cũ.
3. Gom DOWN của các monitor khác nhau theo cùng lịch trong cửa sổ 0–300 giây; mặc định kế thừa 15 giây. Cửa sổ tính từ sự kiện đầu, không kéo dài vì có monitor mới. Giữ phân biệt các đợt DOWN–UP–DOWN liên tiếp của cùng monitor và thứ tự sự kiện theo monitor. Email nhóm liệt kê tên, loại monitor, URL đã che, nhóm lỗi, thời điểm và mô tả an toàn.
4. Email tổng hợp theo lịch **không liệt kê monitor đang DOWN chưa phân loại**. KPI/tổng ở email phải tính nhất quán trên tập dòng còn lại; Dashboard/Logs/báo cáo/Excel trong app vẫn bao gồm đầy đủ log. Monitor đang UP giữ hành vi thống kê lịch sử v1.2.0; đây là tổng hợp theo monitor, không khẳng định nguyên nhân của log `unknown` cũ.
5. Nhiều người nhận: lưu trạng thái từng địa chỉ; chỉ tự thử lại địa chỉ đã được xác định là chưa được SMTP chấp nhận. Giữ thứ tự DOWN/UP trong cùng lịch khi gửi lại. Cho phép subject/body tùy chỉnh; escape HTML và loại CR/LF khỏi subject.
6. Không có giao dịch chung giữa SQLite và SMTP. Nếu tiến trình bị ngắt sau khi SMTP có thể đã chấp nhận thư nhưng trước khi lưu kết quả, hệ thống không thể bảo đảm tuyệt đối “đúng một lần”. Đề xuất đánh dấu `delivery_uncertain`, hiển thị cho người vận hành và không tự gửi lại phần không rõ; thao tác thử lại thủ công cần giải thích nguy cơ trùng. Cách xử lý này cần review ở §17.
7. Email test SMTP do người dùng chủ động bấm là thao tác kiểm tra cấu hình, không phải email cảnh báo sự cố và không yêu cầu phân loại monitor.

## 11. Lưu trữ và tương thích nâng cấp

- Migration SQLite **thêm mới, có phiên bản, chạy lại an toàn**, giữ DB, Fernet key, monitor, mật khẩu/token, settings, email rules, log, thứ tự sự kiện và dữ liệu báo cáo hiện có. Không xóa hoặc tự tái mã hóa key.
- Bổ sung lưu trữ cấu hình profile/quy tắc monitor và kết quả phân loại có cấu trúc; có chỉ mục phù hợp cho truy vấn theo monitor, thời gian và nhóm. Có thể dùng bảng mới hoặc cột mới nếu bảo đảm hợp đồng và migration.
- Log lịch sử không có bằng chứng vẫn giữ `unknown` hoặc mã lịch sử đã lưu; đánh dấu nguồn lịch sử, không tự biến nó thành bằng chứng mới để phát email. Giữ thời gian và cách tính downtime v1.2.0.
- Với email chờ từ phiên bản cũ: tái kiểm tra điều kiện bằng bằng chứng gắn với sự kiện nếu có; sự kiện không chứng minh được nhóm được giữ chờ, không xóa và không gửi. Lần kiểm tra mới có thể cung cấp bằng chứng cho một đợt DOWN còn mở. Không tạo UP cho đợt `unknown → UP` chỉ vì nâng cấp.
- Thư đang gửi hoặc đã được SMTP chấp nhận trước thời điểm nâng cấp không thể thu hồi. Giữ tình trạng người nhận và provenance của sự kiện; mọi trường hợp gửi chưa rõ kết quả áp dụng §10.6.
- Sau lỗi migration hoặc bị ngắt, DB vẫn mở lại được và migration tiếp tục an toàn. Tài liệu nâng cấp yêu cầu sao lưu DB **và** Fernet key; rollback về v1.2.0 dùng bản sao lưu trước nâng cấp, không giả định bản cũ hiểu schema mới.

## 12. Form, import/export và báo cáo

### 12.1 Khai báo và Test Run

- Form Web/Auth/API có phần chọn profile mạng, thêm/sửa/xóa/bật quy tắc riêng, chọn giai đoạn, điều kiện, giá trị, nhóm, mã chi tiết và ưu tiên. Có mô tả ngắn và ví dụ giả; kiểm tra lỗi theo trường trước Save/Test Run.
- Test Run cho biết UP/DOWN, nhóm và nhãn, trạng thái xác định/chưa xác định, giai đoạn, bằng chứng đã che, `rule_id` nếu áp dụng, HTTP code, số lần thử và thời gian. Chạy nền và trả kết quả trên luồng GUI; không tạo log/email sự cố.
- Màn hình profile cho phép cấu hình phạm vi, đích GET/HEAD, timeout và thử thủ công, nêu rõ probe chỉ chứng minh kết nối tới đích tham chiếu. Giữ nguyên cấu hình nếu người dùng chưa dùng tính năng này.

### 12.2 File mẫu và import monitor

- Giữ sheet `Monitors`, `Instructions`, toàn bộ tên 30 cột v1.2.0 và quy tắc nhận dạng monitor theo `id` hoặc `(name, url)` hiện tại. Thêm cột đề xuất `network_profile` và `diagnostic_rules_json` sau các cột cũ; sheet Instructions mô tả kiểu, giới hạn, ví dụ an toàn và cách cấu hình profile trước khi import.
- `diagnostic_rules_json` là mảng JSON theo hợp đồng §7. Các giá trị JSON có kiểu được giữ nguyên; lỗi JSON, mã nhóm, giai đoạn, ưu tiên, xung đột ID hoặc profile không tồn tại báo số dòng/cột, bỏ qua dòng lỗi và không cập nhật dở một monitor. Các dòng hợp lệ khác tiếp tục theo hành vi import hiện có.
- Import file cũ **không có cột mới** bảo toàn profile/quy tắc đang có; monitor mới nhận profile trống và danh sách quy tắc rỗng. Với dòng cập nhật trong file mới, ô trống cũng bảo toàn cấu hình cũ; `[]` xóa danh sách quy tắc, `__CLEAR__` xóa profile. Không cho dùng `__CLEAR__` làm tên profile.
- Template chỉ chứa dữ liệu giả. File XLSX do người dùng tự điền có thể chứa thông tin nhạy cảm: tài liệu hướng dẫn bảo vệ và xóa bản sao theo quy trình của họ; bản thân file Excel không được giả định đã mã hóa.

### 12.3 Dashboard, Logs và báo cáo

- Dashboard hiển thị trạng thái, nhóm/chi tiết, `confirmed` hoặc `undetermined`, lần kiểm tra cuối và thông tin đủ để phân biệt "chưa phân loại" với UP. Có tìm kiếm/lọc theo nhóm và trạng thái phân loại.
- Logs có bộ lọc ngày/giờ, monitor, trạng thái, nhóm, trạng thái phân loại và giai đoạn; xuất CSV/XLSX giữ mã, nhãn, nguồn/bằng chứng đã che và thời gian. Log chưa phân loại không bị ẩn/xóa.
- Statistics và ba sheet `Statistics`, `Incidents`, `Error breakdown` giữ cách đếm: số lần DOWN là số log DOWN, thời gian DOWN theo đợt và trung bình theo số đợt. Bổ sung `undetermined` và phân loại chi tiết; không đếm một log vào hai nhóm. Ngày/thời lượng vẫn là giá trị Excel thực; nội dung ngoài được xuất dạng văn bản an toàn.
- Giao diện vẫn hoạt động với Light/Dark, dữ liệu lớn và điều khiển bằng bàn phím; tác vụ mạng/DB/export không chạy trên luồng Tk. Đổi màn hình hoặc đóng dialog khi tác vụ nền hoàn tất không được làm treo/crash.

## 13. Bảo mật và giới hạn bằng chứng

- Mật khẩu, token, cookie, Authorization, session/CSRF/CAPTCHA, headers/body nhạy cảm, URL userinfo và query có khả năng chứa secret không được ghi nguyên văn vào log, bằng chứng, email, Excel export hoặc thông báo lỗi. Không lưu response body thô; chỉ lưu dữ liệu đã che và giới hạn độ dài. Tên/giá trị quy tắc có thể chứa dữ liệu nhạy cảm phải được mã hóa khi lưu bằng Fernet; không đưa key vào DB hoặc repo.
- Kiểm tra TLS theo cấu hình an toàn hiện có; không tự tắt xác minh chứng chỉ để làm probe thành công. Không tự giải CAPTCHA/MFA hoặc thử mật khẩu thay thế. Không lặp xác thực đã bị từ chối rõ ràng.
- Không dựa vào một câu chữ trong trang trợ giúp, nội dung ẩn, text HTML không liên quan, hay nhiều monitor DOWN đồng thời để khẳng định sai mật khẩu/mất mạng. Nếu bằng chứng không rõ, giữ nhóm chung đã xác định hoặc `unknown`.
- Escape dữ liệu monitor, URL, thông báo và nội dung tùy chỉnh khi dựng HTML email. Tránh công thức Excel từ dữ liệu bên ngoài; không ghi secret vào log lỗi hay test fixture.

## 14. Công nghệ, cấu trúc và lệnh

Giữ Python 3.10+, `customtkinter` 5.2.2, `httpx[http2]` 0.27.2, SQLite, `cryptography` 43.0.3, APScheduler 3.10.4, `smtplib`/`email.mime`, `openpyxl` 3.1.5, `pystray` và Pillow như `requirements.txt`. Windows/macOS/Linux là mục tiêu; CI build hiện có Windows x64 và macOS Intel/Apple Silicon. Không tự thêm dependency hoặc thay đổi workflow trong tài liệu đặc tả này.

| Vị trí dự kiến | Trách nhiệm |
| --- | --- |
| `sitesentry/core/checker.py`, `diagnostics.py` | Thu thập, phân loại và hợp đồng kết quả |
| `sitesentry/core/` | Profile mạng và engine quy tắc, nếu tách module |
| `sitesentry/core/database.py`, `notification_store.py` | Migration, log, trạng thái sự cố và hàng đợi |
| `sitesentry/core/scheduler.py`, `email_rules.py`, `notifier.py` | Retry, lịch, lọc/gộp và SMTP |
| `sitesentry/core/excel_importer.py`, `reports.py`, `report_export.py` | Import/template và báo cáo |
| `sitesentry/ui/` | Monitor/profile form, Test Run, Dashboard, Logs, Statistics, lịch email |
| `tests/` | Unit, integration, migration, SMTP giả lập và GUI có màn hình |
| `templates/`, `README.md`, `checker-spec.md` | Template Excel, hướng dẫn và đặc tả |

Các lệnh hiện có, chạy ở thư mục gốc dự án:

```bash
# Cài phụ thuộc với Python 3.10+ đã được chọn
python3 -m pip install -r requirements.txt

# Chạy ứng dụng từ source trên macOS/Linux
./run.sh

# Toàn bộ kiểm thử; GUI cần môi trường có màn hình
./scripts/python3.10 -m unittest discover -s tests -v
SITESENTRY_GUI_TEST=1 ./scripts/python3.10 -m unittest discover -s tests -p test_ui_smoke.py -v

# Kiểm tra cú pháp và lỗi khoảng trắng trong thay đổi
./scripts/python3.10 -m compileall -q main.py sitesentry tests
git diff --check

# Đóng gói macOS trên macOS, sau khi cài requirements-build.txt
PYTHON_BIN=./scripts/python3.10 bash scripts/build_macos.sh
```

Trên Windows PowerShell: `python -m unittest discover -s tests -v`; nếu có màn hình để kiểm thử GUI, đặt `$env:SITESENTRY_GUI_TEST="1"` rồi chạy `python -m unittest discover -s tests -p test_ui_smoke.py -v`. Đóng gói Windows bằng `powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1`. Wrapper `./scripts/python3.10` là tùy chọn của máy hiện tại; nơi khác thay bằng Python 3.10+ đã cài. Hai script đóng gói hiện tại xóa thư mục `build/` và `dist/` trước khi build; cần bảo toàn các artifact muốn giữ. Repo chưa cấu hình lệnh lint/type-check riêng; không tự coi `compileall` là lint.

## 15. Chiến lược kiểm thử

`unittest` là framework hiện có. Không dùng tài khoản thật, website sản xuất, SMTP thật hay DB/Fernet key của người dùng trong test tự động. Dùng `httpx.MockTransport`, exception giả, SQLite/key trong thư mục tạm, SMTP mock và đồng hồ có thể điều khiển.

- **Unit:** từng nhóm lỗi và `reason_code`, ưu tiên, chuẩn hóa text, text ẩn, HTTP/JSON có kiểu, xung đột quy tắc, route/probe cùng phạm vi, che bí mật.
- **Integration:** checker → lưu log → trạng thái sự cố → email queue → bộ lọc/gộp → SMTP giả; kiểm tra restart và truy vấn UI/report/export.
- **Migration:** snapshot DB v1.2.0 có monitor, secret mã hóa, log, nhiều rule, thư đã gửi/chờ/đang gửi và batch; kiểm tra thành công, chạy lại, ngắt giữa chừng và mở lại.
- **Native GUI:** máy có màn hình, ba loại monitor, form dài, Test Run, profile, import/export, Dark/Light, đổi view khi tác vụ đang chạy, tập dữ liệu ít nhất 500 monitor.
- **Đóng gói:** chạy test và build Windows x64, macOS Intel và Apple Silicon trên runner tương ứng; Linux chạy test/core và GUI khi có display. Không coi build thành công là xác nhận runtime/SMTP thật.
- Không đặt ngưỡng phần trăm coverage giả định. Độ bao phủ bắt buộc là toàn bộ tiêu chí có ID ở §16, cả đường thành công, lỗi và cạnh tranh trạng thái; không xóa/skip test hiện có để đạt kết quả.

## 16. Tiêu chí nghiệm thu

Mỗi tiêu chí phải có test tự động hoặc, với thao tác GUI/build native, bằng chứng test trên nền tảng tương ứng.

### 16.1 Phân loại

| ID | Given / When | Then |
| --- | --- | --- |
| C-01 | Web, Auth và API lần lượt gặp connect/read timeout, DNS, TLS, connection refused/reset | Mỗi kết quả DOWN có nhóm phù hợp, phase, bằng chứng; không báo sai mật khẩu chỉ vì transport lỗi. |
| C-02 | Web/API/Auth nhận HTTP 401 không phải status kỳ vọng | Nhóm xác thực bị từ chối chung; không khẳng định tên hay mật khẩu cụ thể. |
| C-03 | Không có quy tắc riêng; server trả 403, 404, 429, 503 khác status kỳ vọng | `http_error` và HTTP/reason tương ứng; không ghi sai mật khẩu hoặc kết luận nguyên nhân gốc của 503. |
| C-04 | Auth trả thông báo hiển thị “tài khoản hoặc mật khẩu không đúng” | `auth_credentials/auth_rejected`; không lặp lần đăng nhập bị từ chối và không tách sai trường. |
| C-05 | Text lỗi chỉ có trong script/ẩn, hoặc là câu hướng dẫn chung | Không kết luận sai tài khoản/mật khẩu; kiểm tra session/content theo bằng chứng còn lại. |
| C-06 | Verify vẫn là trang login; hoặc CAPTCHA/MFA/CSRF được nhận diện bằng quy tắc riêng | Phân loại phiên/chi tiết phù hợp; chỉ có reason CAPTCHA/MFA/CSRF khi có bằng chứng. |
| C-07 | API trả 200 `{"success": false}` | Không cấu hình assertion/quy tắc: trạng thái theo HTTP hiện có; có quy tắc Boolean false: DOWN `assertion_failed`, lưu `rule_id`. |
| C-08 | JSON path thiếu, JSON sai, giá trị `false`, `0`, `null`, `""` trong quy tắc mới; import monitor dùng assertion cũ | Quy tắc mới xử lý đúng kiểu, không bỏ qua giá trị falsey; assertion cũ giữ nghĩa v1.2.0 như §7. |
| C-09 | URL/header/rule/profile sai | `configuration_error`, nêu trường/giai đoạn, không gửi request hoặc tự retry cấu hình lỗi. |
| C-10 | Hai quy tắc cùng ưu tiên cao nhất khớp nhưng khác nhóm | `unknown/conflicting_evidence`, có rule IDs; không gửi email. Quy tắc ưu tiên cao hơn được dùng xác định khi không mâu thuẫn transport. |
| C-11 | Exception lạ không khớp nhóm; nhiều monitor cùng DOWN | Lưu `unknown`, không suy ra mất mạng máy hoặc sai mật khẩu. |
| C-12 | Dùng Test Run hoặc kiểm tra định kỳ với cùng cấu hình/response giả | Cùng nhóm và bằng chứng; Test Run không tạo event hay gửi email. |

### 16.2 Mạng

| ID | Given / When | Then |
| --- | --- | --- |
| N-01 | Không cấu hình profile | Không có probe ngoài request monitor; phân loại theo bằng chứng thực có, không giả định Internet/VPN offline. |
| N-02 | Probe Internet thành công, target nội bộ lỗi; hoặc probe nội bộ thành công, target Internet lỗi | Chỉ kết luận phạm vi của probe và lỗi target đã quan sát; không coi probe thành công là bằng chứng target khác UP. |
| N-03 | Probe tham chiếu không phản hồi nhưng route còn; hoặc chỉ một đích báo `ENETUNREACH` | Không tự gán `network_offline` toàn máy; dùng nhóm trực tiếp hoặc `unknown`. |
| N-04 | Hệ điều hành báo interface/route áp dụng cho đích không khả dụng | `network_offline` có evidence phạm vi, timestamp và phase. |
| N-05 | Nhiều monitor cùng profile lỗi gần nhau | Tối đa một probe đồng thời/profile; dùng kết quả còn hạn; timeout và số đích không vượt cấu hình; GUI vẫn phản hồi. |
| N-06 | Monitor có token/cookie; probe có URL không hợp lệ, userinfo, tham số bí mật hoặc redirect ra host chưa cấu hình | Không chuyển credential sang probe; từ chối URL không hợp lệ/nhạy cảm, không theo redirect ra host chưa khai báo. |

### 16.3 Email và trạng thái sự cố

| ID | Given / When | Then |
| --- | --- | --- |
| E-01 | UNKNOWN DOWN qua nhiều retry và restart | Có log/đợt chờ, tiếp tục kiểm tra theo lịch; không có email DOWN/UP. |
| E-02 | UNKNOWN DOWN → DOWN đã xác định, nhóm được phép | Đúng một DOWN/lịch có nhóm, thời điểm và bằng chứng; lần DOWN tiếp theo không gửi lặp. |
| E-03 | UNKNOWN DOWN → UP | Không có DOWN hay UP mồ côi, kể cả lịch recovery-only; log/đợt vẫn có trong báo cáo. |
| E-04 | DOWN đã gửi/đưa vào hàng đợi hợp lệ → UNKNOWN DOWN → UP | UP được xếp sau DOWN của cùng lịch và tham chiếu nhóm đã xác định; không phát thêm DOWN trùng. |
| E-05 | Nhóm ban đầu bị loại, sau đó chuyển sang nhóm xác định được phép | Một DOWN mới cho lịch tương ứng; log đủ cả hai nhóm. |
| E-06 | Web/Auth/API DOWN xác định cùng cửa sổ 15 giây; một monitor có DOWN–UP–DOWN nhanh | Gom các monitor phù hợp, giữ từng đợt và thứ tự DOWN/UP; không gộp hai đợt của cùng monitor thành hai monitor. |
| E-07 | Bộ lọc đổi sau khi lấy queue nhưng trước claim | Email nhóm bị loại chưa bắt đầu gửi bị chặn; không làm mất đợt mới hay tạo UP mồ côi. |
| E-08 | SMTP chấp nhận một địa chỉ và từ chối địa chỉ khác | Ghi nhận người đã chấp nhận, chỉ thử lại người chắc chắn chưa được chấp nhận, giữ thứ tự DOWN/UP. |
| E-09 | Mất tiến trình sau khi SMTP có thể nhận nhưng trước khi lưu | Thể hiện trạng thái chưa chắc gửi; không tuyên bố gửi đúng một lần; hành vi thử lại theo quyết định §10.6/§17. |
| E-10 | Email tổng hợp có monitor UP, DOWN đã xác định và DOWN chưa xác định | Bỏ monitor DOWN chưa xác định; tổng và số dòng email nhất quán; báo cáo trong app vẫn đủ. |

### 16.4 Dữ liệu, giao diện và đóng gói

| ID | Given / When | Then |
| --- | --- | --- |
| D-01 | Nâng cấp DB v1.2.0 có monitor/log/rule/secret/queue | Dữ liệu và Fernet key dùng được; log cũ không bị bịa bằng chứng; pending không đủ bằng chứng không gửi. |
| D-02 | Migration bị ngắt; mở lại nhiều lần | Không mất dữ liệu, không tạo event trùng, migration tiếp tục/rollback an toàn. |
| D-03 | Import XLSX cũ không có hai cột mới | Tạo/cập nhật theo quy tắc v1.2.0; profile và quy tắc đang có không bị xóa. |
| D-04 | Import XLSX mới hợp lệ/sai JSON/profile không tồn tại | Cột mới lưu đúng; lỗi ghi số dòng/cột và bỏ qua dòng; `[]`/`__CLEAR__` xóa đúng cấu hình được chọn. |
| D-05 | Dashboard/Logs/Statistics và Excel chứa known/unknown | Hiển thị, lọc, xuất đúng nhóm, phase và trạng thái; tổng downtime/count nhất quán, không lộ secret hoặc thực thi công thức Excel ngoài. |
| D-06 | Mở/sửa ba loại monitor, test profile/Test Run, chuyển view, Dark/Light với 500 monitor; mô phỏng tác vụ nền mất 3 giây | Form đủ trường; callback Tk lên lịch sau 200 ms được thực thi trước khi tác vụ hoàn tất; tác vụ kết thúc an toàn khi dialog/view đã đóng. |
| D-07 | Build Windows x64, macOS x64/arm64 và test Linux | Các test tự động qua; gói Windows/macOS chạy được trên nền tảng kiểm thử tương ứng, Linux chạy từ source; báo cáo rõ nếu chưa có môi trường chạy native. |
| D-08 | Secret giả xuất hiện trong URL, header, cookie, response và quy tắc | Không xuất hiện nguyên văn trong log, bằng chứng, email, báo cáo hoặc export; cấu hình nhạy cảm được mã hóa. |

## 17. Quyết định và nghiệm thu thực tế

1. **SMTP không rõ đã nhận:** dùng `delivery_uncertain`, không tự gửi lại phần không chắc và cho phép người vận hành thử lại sau khi được cảnh báo nguy cơ trùng.
2. **Giới hạn quy tắc/probe:** dùng 20 quy tắc/monitor, 1.024 ký tự/giá trị, tối đa 2 đích/profile, timeout mặc định 2 giây và cache 60 giây.
3. **Môi trường nghiệm thu thật:** cần chọn một Web, một Auth Web và một API thử nghiệm cùng profile Internet/nội bộ, tài khoản kiểm thử và SMTP thử nghiệm phù hợp. Chỉ dùng khi chủ hệ thống cung cấp và cho phép; test tự động vẫn độc lập dữ liệu thật.

## 18. Ranh giới thực hiện

- **Luôn:** giữ hợp đồng §4–§10; kiểm thử bằng dữ liệu giả; bảo toàn dữ liệu/secret và khả năng mở lại DB; ghi rõ bất định; cập nhật tài liệu và template đồng bộ.
- **Cần quyết định trước khi áp dụng:** thay đổi có tác động sản phẩm chưa được xác nhận; phát hành/push theo yêu cầu cụ thể của người dùng.
- **Không:** đưa credential vào repo/log/email/test; tự sửa website đích; vô hiệu hóa TLS để làm test qua; xóa test thất bại; gửi email sự cố `unknown` chỉ để tránh bỏ sót.
