# SiteSentry Desktop 1.3.0

## Điểm mới

- Phân loại sự cố Web, Auth Web và API theo bằng chứng, trạng thái xác định, giai đoạn và mã lý do; hỗ trợ quy tắc riêng cho từng monitor.
- Profile mạng do người dùng cấu hình hỗ trợ kiểm tra tham chiếu cho Internet và mạng nội bộ/VPN, không gửi credential monitor tới địa chỉ tham chiếu.
- Dashboard, Logs, Statistics và báo cáo Excel hiển thị chi tiết chẩn đoán. Mẫu import monitor có thêm profile mạng và quy tắc JSON; file mẫu cũ vẫn được hỗ trợ.
- Hàng đợi email hiển thị thư cũ thiếu bằng chứng và thư chưa xác định được kết quả SMTP; thư chưa chắc đã gửi chỉ được thử lại khi người vận hành chủ động xác nhận.

## Thay đổi cần lưu ý

- Monitor DOWN chưa xác định nhóm lỗi tiếp tục được ghi log và kiểm tra, nhưng không gửi cảnh báo sự cố hoặc email phục hồi mồ côi. Monitor đang DOWN chưa phân loại cũng được loại khỏi email tổng hợp. Các lỗi có bằng chứng mới được xét theo lịch và bộ lọc email.
- Nếu SMTP có thể đã nhận thư nhưng app chưa lưu xác nhận, trạng thái là `delivery_uncertain`. Người vận hành có thể thử lại thủ công với nguy cơ gửi trùng.
- Quy tắc riêng cần được cấu hình và kiểm thử theo ứng dụng đích; HTTP 401 chỉ xác nhận từ chối xác thực, không chứng minh riêng tên đăng nhập hay mật khẩu sai.

## Tải và cài đặt

- `Windows-x64.exe`: ứng dụng Windows chạy trực tiếp; ZIP chứa cùng chương trình, không cần cài Python.
- `macOS-arm64.dmg`: máy Mac Apple Silicon; `macOS-x64.dmg`: máy Mac Intel.
- `SHA256SUMS.txt`: mã kiểm tra SHA-256 của các gói.
- Gói chưa được ký bằng chứng thư nhà phát hành Windows hoặc notarize bởi Apple; hệ điều hành có thể hiển thị cảnh báo.

## Nâng cấp và khôi phục

Thoát ứng dụng hoàn toàn, kể cả biểu tượng tray, rồi sao lưu **cả DB và khóa Fernet** trước khi nâng cấp. Dữ liệu bản đóng gói mặc định ở `%APPDATA%\SiteSentry Desktop\data` trên Windows hoặc `~/Library/Application Support/SiteSentry Desktop/data` trên macOS. Giữ thêm `config.json` trong thư mục ứng dụng nếu đã tùy chỉnh đường dẫn. Để quay lại v1.2.0, khôi phục DB và khóa từ cùng bản sao lưu trước nâng cấp.

Đã chạy 106 kiểm thử cục bộ, gồm giao diện macOS và 500 monitor; SMTP và endpoint dùng dữ liệu giả lập. Kết quả build từng nền tảng được xác nhận trong GitHub Actions; chưa thay thế kiểm thử trên máy người dùng hoặc hệ thống SMTP/website thực tế.
