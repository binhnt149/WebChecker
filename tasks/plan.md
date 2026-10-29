# Kế hoạch triển khai phân loại sự cố

Đặc tả: `checker-spec.md` (đã duyệt). Làm việc trên nhánh `feature/evidence-based-diagnostics`; không tự phát hành hay push.

- [x] **Hợp đồng chẩn đoán:** phân loại theo bằng chứng, giai đoạn, mã chi tiết và trạng thái xác định; quy tắc riêng có kiểm tra cấu hình, ưu tiên và bảo toàn kiểu JSON.
- [x] **Profile mạng:** cấu hình profile, thăm dò tham chiếu có giới hạn, không truyền credential và không suy đoán mất mạng.
- [x] **Lưu trữ và email:** migration tương thích v1.2.0, lưu evidence, giữ chờ lỗi chưa rõ, thứ tự DOWN/UP, lọc/gộp và kết quả SMTP không chắc chắn.
- [x] **Monitor và Excel:** form, Test Run, quản lý profile/quy tắc, nhập mẫu cũ/mới và xác thực theo dòng.
- [x] **Giao diện và báo cáo:** Dashboard, Logs, Statistics, export và che dữ liệu nhạy cảm.
- [x] **Kiểm tra cục bộ:** 106 test qua, gồm GUI native macOS, migration và build PyInstaller macOS arm64 trong thư mục tạm; kiểm tra hai biểu mẫu Excel.
- [ ] **Nghiệm thu nền tảng còn lại:** chạy gói Windows x64, macOS Intel và Linux trên môi trường tương ứng; kiểm tra ứng dụng đóng gói và SMTP/website thử nghiệm thực tế khi có môi trường phù hợp. Chưa thể xác nhận D-07 đầy đủ trên máy hiện tại.

Sau mỗi phần, chạy các test tập trung, giữ các thay đổi tương thích và ghi nhận kết quả trước khi tiếp tục. Ưu tiên nguyên tắc không gửi cảnh báo khi không có nhóm lỗi xác định; không dùng dữ liệu production trong test.
