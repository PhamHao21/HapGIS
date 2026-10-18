# -*- coding: utf-8 -*-
"""User-facing data contract, shared by the rules panel and documentation."""
RULES = [
    ("01", "tenDuong bắt buộc, tenHem tùy chọn",
     "Cả lớp thửa và lớp đường phải có trường tên chính xác là tenDuong. Nên thêm tenHem vào cả hai lớp khi một đường cha có nhiều hẻm: đường chính để tenHem trống, hẻm ghi Hẻm 1, Hẻm 2… Nếu chỉ một lớp có tenHem mà trường này có giá trị, tool báo lỗi schema; nếu trường đó để trống toàn bộ thì được bỏ qua và chạy chỉ với tenDuong. Dữ liệu cũ không có tenHem ở cả hai lớp vẫn được hỗ trợ bằng tên đầy đủ trong tenDuong."),
    ("02", "Giá trị khớp nhau, không phải tên file", 
     "Tên file và tên layer không cần giống nhau. Khóa (tenDuong, tenHem) ở hai lớp phải tương ứng. Tool chuẩn hóa Unicode, bỏ khoảng trắng đầu/cuối và không phân biệt hoa/thường; hẻm nAm LONG khớp Hẻm Nam Long. Tool vẫn phân biệt dấu, chính tả và khoảng trắng bên trong; Hem Nam Long không tự ghép với Hẻm Nam Long."),
    ("03", "Cùng hệ tọa độ phẳng, đơn vị mét", 
     "Hai lớp phải có CRS, cùng CRS dạng projected và hai trục ngang có đơn vị mét (meter/metre). Không dùng tọa độ kinh/vĩ độ theo độ hoặc hệ dùng feet. Khi sai CRS, hãy chuyển hệ bằng Project/Reproject; chỉ gán nhãn CRS không làm thay đổi tọa độ."),
    ("04", "VN-2000 đúng khu vực", 
     "Với dữ liệu địa chính Việt Nam, ưu tiên VN-2000 dạng chiếu, đúng múi chiếu và kinh tuyến trục của địa phương. VN-2000 dạng địa lý vẫn có đơn vị độ và không đáp ứng yêu cầu. Tool không tự chọn múi chiếu hoặc chuyển hệ. CRS phẳng khác dùng mét vẫn được xử lý, kèm nhắc kiểm tra tính phù hợp."),
    ("05", "Hình học và phạm vi tuyến", 
     "Thửa phải là Polygon/MultiPolygon hợp lệ, không rỗng. Đường chính vẽ bằng polygon mặt đường hoặc polyline tim đường (LineString/MultiLineString, chế độ thử nghiệm); tool tự nhận kiểu theo từng tuyến, mỗi tuyến chỉ một kiểu. Tim đường phải liên thông (đầu mút lệch tối đa 10 cm được tự nối), không phân nhánh, không khép vòng và không cắt qua thửa; vẽ theo chiều nào cũng được. Với polygon mặt đường, thửa không được vẽ đè lên mặt đường cùng tuyến: thửa có tâm (representative point) nằm trong polygon đường hoặc bị đường cắt thành từ 2 phần trở lên là lỗi chặn chạy; thửa lấn quá 25% diện tích lên mặt đường được cảnh báo. Thửa chỉ tiếp giáp hoặc cách đường một khoảng vẫn hợp lệ. Khóa nội bộ là cặp (tenDuong, tenHem), nên Hẻm 1 của hai đường cha không bị nhập chung. Kiểm tra chỉ xét tuyến đã chọn và đường cha thực sự cần tham chiếu."),
    ("06", "Tên hẻm và số nhà hiển thị",
     "Với schema mới, số hẻm được lấy từ tenHem: Hẻm 1 tạo 1/1, 1/2…; Hẻm 236 tạo 236/1, 236/2… Với dữ liệu cũ, tên đầy đủ Hẻm 1 đường A trong tenDuong vẫn hoạt động. Chỉ lấy số nguyên ngay sau Hẻm/Hem. Hẻm không số đánh 1, 2…; Hẻm 1A và Hẻm 236/5 phải chuẩn hóa. soNhaHienThi là chuỗi; dấu / là quy cách dữ liệu, không phải công thức tại Điều 7."),
    ("07", "Miệng hẻm và chiều đánh số",
     "Lớp đường phải chứa polygon hẻm và đường chính với tenHem trống. Hẻm và đường cha của hẻm đang chọn phải là polygon; tim đường mới hỗ trợ cho đường chính. Chọn riêng hẻm vẫn tự dùng đường cha làm tham chiếu. Tool chấp nhận tiếp giáp điểm hoặc khe hở tối đa 10 cm chỉ với đúng đường cha, tại đầu tim hẻm, và ghi cảnh báo sai số digitize; không sửa hình học nguồn. Hẻm một cửa và hẻm phân nhánh được đánh từ miệng theo khoảng cách trên mạng tim hẻm; trái lẻ/phải chẵn theo hướng cục bộ từng nhánh. Hai hẻm cùng đường cha có miệng riêng được phép tiếp giáp và có cảnh báo. Vòng, đoạn rời, nhiều miệng mơ hồ hoặc hẻm cấp 2 không có miệng riêng vẫn chặn lượt ghi. Căn cứ Điều 6–7, VBHN 05/VBHN-BXD ngày 13/02/2026."),
    ("08", "Kiểm tra trước, lưu ra file mới", 
     "Danh sách cây cho phép chọn nhiều đường/hẻm. Tích đường cha sẽ tích đường chính và toàn bộ hẻm con; có thể bỏ từng hẻm. Nhập tay schema mới theo dạng Đường Quyết Thắng › Hẻm 1, nhiều tuyến cách nhau bằng dấu ;. Nhấn Kiểm tra dữ liệu trước khi chạy. Khuyến nghị GeoPackage; các trường traiPhai, thuTuDiaChi, soNhaHienThi và huong được tạo lại."),
]


def format_report(report):
    title = "CẦN SỬA DỮ LIỆU" if report["errors"] else "ĐỦ ĐIỀU KIỆN CƠ BẢN"
    lines = [title, "", *report["details"]]
    if report["errors"]:
        lines += ["", "LỖI CẦN SỬA", *[f"• {item}" for item in report["errors"]]]
    if report["warnings"]:
        lines += ["", "LƯU Ý", *[f"• {item}" for item in report["warnings"]]]
    lines += ["", "Kiểm tra này không thay thế việc kiểm tra đúng vị trí, múi chiếu và chất lượng dữ liệu trên bản đồ."]
    return "\n".join(lines)
