# SiteSentry Desktop 1.4.0

## Tính năng mới

- Kiểm tra điểm tham chiếu Internet trước mỗi lượt kiểm tra monitor. Vào **Cài đặt > Internet** để chọn profile Internet do bạn cấu hình; ứng dụng không tự gọi dịch vụ bên ngoài khi chưa chọn profile.
- Ghi sự kiện khi trạng thái kết nối thay đổi và hiển thị kết quả gần nhất trên Tổng quan. Điểm tham chiếu không phản hồi được phân biệt với bằng chứng hệ điều hành báo mạng máy giám sát không khả dụng; các monitor nội bộ/VPN vẫn được kiểm tra.
- Biểu đồ Tổng quan hiển thị số monitor UP, DOWN, chưa rõ và tạm dừng theo trạng thái gần nhất; monitor tạm dừng được tính riêng.
- Việt hóa các màn hình, thao tác, cảnh báo và nội dung email mặc định. Mã kỹ thuật, nội dung từ hệ thống bên ngoài và các mẫu email người dùng đã tùy chỉnh được giữ nguyên.

Sự kiện mạng được ghi riêng tại **Nhật ký > Sự kiện mạng**, không tự phát email; các cảnh báo monitor tiếp tục áp dụng điều kiện phân loại và lịch email đã thiết lập. Kết quả kiểm tra tham chiếu được chia sẻ và dùng lại trong tối đa 60 giây.

## Tải và cài đặt

- `Windows-x64.exe`: ứng dụng Windows chạy trực tiếp; ZIP chứa cùng chương trình, không cần cài Python.
- `macOS-arm64.dmg`: máy Mac Apple Silicon; `macOS-x64.dmg`: máy Mac Intel.
- `SHA256SUMS.txt`: mã kiểm tra SHA-256 của các gói.
- Các gói chưa được ký bằng chứng thư nhà phát hành Windows hoặc notarize bởi Apple; hệ điều hành có thể hiển thị cảnh báo.

## Nâng cấp và khôi phục

Thoát ứng dụng hoàn toàn, kể cả biểu tượng tray, rồi sao lưu **cả database và khóa Fernet** trước khi nâng cấp. Dữ liệu bản đóng gói mặc định ở `%APPDATA%\SiteSentry Desktop\data` trên Windows hoặc `~/Library/Application Support/SiteSentry Desktop/data` trên macOS. Giữ thêm `config.json` trong thư mục ứng dụng nếu đã tùy chỉnh đường dẫn. Để quay lại v1.3.0, khôi phục DB và khóa từ cùng bản sao lưu trước nâng cấp.

Đã chạy 114 kiểm thử cục bộ, gồm GUI native macOS và dữ liệu giả lập; endpoint và SMTP thực tế chưa được kiểm thử. Build và kiểm thử tự động cho từng nền tảng được thực hiện bởi GitHub Actions.
