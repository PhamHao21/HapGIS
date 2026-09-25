============================================================
HAPGIS v1.0.0
CÔNG CỤ ĐÁNH SỐ NHÀ TỰ ĐỘNG
============================================================

1. CHỨC NĂNG
- Đọc dữ liệu ranh thửa và đường giao thông.
- Hỗ trợ File Geodatabase (.gdb), Shapefile (.shp), GeoPackage (.gpkg) và GeoJSON.
- Cho phép xử lý một tuyến hoặc tất cả tuyến.
- Tự động xác định hướng đánh số.
- Phân loại bên TRÁI / PHẢI.
- Tạo thứ tự địa chỉ và sinh số nhà chẵn / lẻ.
- Xuất GeoPackage (.gpkg) hoặc Shapefile (.shp).

2. DỮ LIỆU YÊU CẦU
- Lớp thửa và lớp đường phải cùng hệ tọa độ.
- Hệ tọa độ phải là projected, đơn vị mét.
- Hai lớp cần có trường tenDuong.

3. CÁCH SỬ DỤNG
Bước 1: Chọn dữ liệu Thửa.
Bước 2: Chọn dữ liệu Đường.
Bước 3: Nếu dùng File Geodatabase, chọn đúng layer tương ứng.
Bước 4: Nhập tên tuyến nếu chỉ muốn xử lý một tuyến.
        Để trống ô Tuyến để xử lý tất cả.
Bước 5: Chọn nơi lưu kết quả.
Bước 6: Nhấn BẮT ĐẦU ĐÁNH SỐ NHÀ.

4. ĐỊNH DẠNG ĐẦU RA KHUYẾN NGHỊ
GeoPackage (.gpkg) được khuyến nghị vì giữ đầy đủ tên trường.

5. PHIÊN BẢN
HAPGIS v1.0.0

6. PHẠM VI KIỂM THỬ
Phiên bản 1.0.0 đã được kiểm thử trên bộ dữ liệu hiện tại của dự án.
Một số hình học đặc biệt như vòng xuyến / vòng xoay chưa được kiểm thử đầy đủ.
Nhiều dạng dữ liệu sẽ được kiểm thử sau để hoàn thiện hơn.

