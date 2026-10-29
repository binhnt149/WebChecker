from __future__ import annotations

def message(value: object) -> str:
    text = str(value)
    translations = {
        "Network profile needs a valid name": "Cần nhập tên profile mạng hợp lệ",
        "Invalid network profile scope": "Phạm vi profile mạng không hợp lệ",
        "A network profile supports at most 2 targets": "Profile mạng hỗ trợ tối đa 2 địa chỉ tham chiếu",
        "Invalid reference target": "Địa chỉ tham chiếu không hợp lệ",
        "Reference URL must be HTTP(S) without userinfo or fragment": "URL tham chiếu phải là HTTP(S), không chứa thông tin đăng nhập hoặc fragment",
        "Reference URL must not contain secret query parameters": "URL tham chiếu không được chứa tham số bí mật",
        "Reference method must be GET or HEAD": "Phương thức tham chiếu phải là GET hoặc HEAD",
        "Invalid reference timeout": "Thời gian chờ tham chiếu không hợp lệ",
        "Reference timeout must be between 0.1 and 30 seconds": "Thời gian chờ tham chiếu phải từ 0,1 đến 30 giây",
        "Diagnostic rules must be valid JSON": "Quy tắc chẩn đoán phải là JSON hợp lệ",
        "Diagnostic rules must be a list of at most 20 rules": "Danh sách chẩn đoán hỗ trợ tối đa 20 quy tắc",
        "Each diagnostic rule must be an object": "Mỗi quy tắc chẩn đoán phải là một đối tượng",
        "Rule ID must be unique and contain 1–64 letters, numbers, _ or -": "Mã quy tắc phải duy nhất và gồm 1–64 chữ, số, _ hoặc -",
        "invalid enabled, priority or phase": "trạng thái bật, ưu tiên hoặc giai đoạn không hợp lệ",
        "invalid error category": "nhóm lỗi không hợp lệ", "invalid reason code": "mã lý do không hợp lệ",
        "conditions must be a nonempty list of at most 20 items": "điều kiện phải là danh sách từ 1 đến 20 mục",
        "condition must be an object": "điều kiện phải là một đối tượng", "invalid condition source, operator or value": "nguồn, phép so sánh hoặc giá trị không hợp lệ",
        "condition value exceeds 1024 characters": "giá trị điều kiện vượt quá 1024 ký tự", "invalid HTTP status": "mã HTTP không hợp lệ", "invalid HTTP range": "khoảng mã HTTP không hợp lệ", "invalid visible text": "văn bản hiển thị không hợp lệ", "invalid JSON path": "đường dẫn JSON không hợp lệ",
        "Schedule name is required": "Cần nhập tên lịch", "Invalid email schedule type": "Loại lịch email không hợp lệ", "Send time is invalid": "Giờ gửi không hợp lệ", "Select at least one valid weekday": "Chọn ít nhất một ngày trong tuần", "Invalid report period": "Khoảng báo cáo không hợp lệ", "Subject must be a single line": "Chủ đề phải nằm trên một dòng", "Grouping window must be between 0 and 300 seconds": "Thời gian gom phải từ 0 đến 300 giây", "Message is required when the default HTML report is disabled": "Cần nhập nội dung khi tắt báo cáo HTML mặc định",
        "Invalid recipient:": "Người nhận không hợp lệ:", "Unsupported email placeholder:": "Biến email không được hỗ trợ:",
        "SMTP alerts are disabled": "Cảnh báo SMTP đang tắt", "SMTP host is empty": "Chưa nhập máy chủ SMTP", "No alert recipients configured": "Chưa cấu hình người nhận cảnh báo", "Email sent": "Đã gửi email", "SMTP delivery failed": "Gửi SMTP thất bại",
        "Expected text was not found in the response": "Không tìm thấy nội dung mong đợi trong phản hồi", "Expected HTTP": "HTTP mong đợi", ", got ": ", nhận ", "Login rejected: the server rejected the account/password or authentication token.": "Đăng nhập bị từ chối: máy chủ từ chối tài khoản/mật khẩu hoặc token xác thực.", "Login page failed:": "Không mở được trang đăng nhập:", "Login failed:": "Đăng nhập thất bại:", "Verify failed:": "Xác minh thất bại:", "Conflicting diagnostic rules": "Các quy tắc chẩn đoán mâu thuẫn", "Diagnostic rule matched": "Khớp quy tắc chẩn đoán", "Invalid retry configuration": "Cấu hình thử lại không hợp lệ",
        "Rule ": "Quy tắc ",
    }
    for source, target in translations.items():
        text = text.replace(source, target)
    return text
