"""Nhãn hiển thị; các mã lưu trong SQLite và JSON vẫn giữ nguyên."""

CLASSIFICATIONS = {"confirmed": "Đã xác định", "undetermined": "Chưa xác định", "legacy": "Dữ liệu cũ", "not_applicable": "Không áp dụng"}
PHASES = {"configuration": "Cấu hình", "resolve": "Phân giải DNS", "connect": "Kết nối", "tls": "TLS", "request": "Gửi yêu cầu", "login": "Đăng nhập", "login_page": "Trang đăng nhập", "login_submit": "Gửi đăng nhập", "verify": "Xác minh", "response": "Phản hồi", "assertion": "Kiểm tra nội dung", "network_probe": "Kiểm tra mạng"}
STATES = {"up": "UP", "down": "DOWN", "unknown": "Chưa rõ", "paused": "Tạm dừng"}
DELIVERY = {"pending": "Đang chờ", "failed": "Gửi lỗi", "sending": "Đang gửi", "sent": "Đã gửi", "held": "Đang giữ", "suppressed": "Đã loại", "delivery_uncertain": "Chưa chắc đã gửi"}


def label(mapping: dict[str, str], value: str) -> str:
    return mapping.get(value, value or "-")



from sitesentry.core.translation import message
