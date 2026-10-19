============================================================
HAPGIS v1.1
CÔNG CỤ ĐÁNH SỐ NHÀ TỰ ĐỘNG
============================================================

1. CHỨC NĂNG
- Đọc dữ liệu ranh thửa và đường giao thông.
- Hỗ trợ File Geodatabase (.gdb), Shapefile (.shp), GeoPackage (.gpkg) và GeoJSON.
- Cửa sổ chọn tuyến riêng có tìm kiếm, con lăn chuột, bộ lọc nhanh và danh sách checkbox.
- Dữ liệu cũ hiển thị phẳng mỗi tenDuong một dòng; schema tenHem hiển thị đúng cây đường cha–hẻm.
- Chọn đường cha tự chọn đường chính và toàn bộ hẻm con; có thể bỏ từng hẻm.
- Nút Quy tắc giải thích điều kiện dữ liệu; Kiểm tra dữ liệu báo CRS, hình học, thửa đè lên đường và tuyến không khớp.
- Nút Dùng nguồn thửa giúp chọn nhanh hai layer cùng GDB/GPKG; Nạp lại để đọc lại dữ liệu.
- Lưu nhật ký phiên ra file .log để kiểm tra hoặc gửi khi gặp lỗi.
- Đường chính và hẻm nhận polygon mặt đường hoặc polyline tim đường (thử nghiệm).
- Tự động xác định hướng đánh số.
- Phân loại bên TRÁI / PHẢI.
- Tạo thứ tự địa chỉ và sinh số nhà chẵn / lẻ.
- Hỗ trợ quan hệ tenDuong–tenHem và dữ liệu cũ; tìm miệng hẻm và ghép số như 236/1.
- Xem trước mẫu số dưới dropdown; báo cáo hẻm có bảng nhỏ cuộn được.
- Xuất GeoPackage (.gpkg) hoặc Shapefile (.shp).

2. DỮ LIỆU YÊU CẦU
- Lớp thửa và lớp đường phải cùng hệ tọa độ.
- Hệ tọa độ phải là projected, đơn vị mét.
- Ưu tiên VN-2000 dạng chiếu, đúng múi chiếu/kinh tuyến trục của khu vực. Không chỉ gán nhãn CRS.
- VN-2000 dạng địa lý (đơn vị độ) và hệ tọa độ dùng feet không được chấp nhận.
- Cả hai lớp bắt buộc có trường tên chính xác là tenDuong; đây là tên đường cha.
- tenHem là trường tùy chọn. Nếu dùng, cả hai lớp phải cùng có tenHem; đường chính để trống,
  hẻm ghi Hẻm 1, Hẻm 2, Hẻm Nam Long… Nếu chỉ một lớp có tenHem
  mà trường này có giá trị, tool chặn vì sai schema; trường tenHem để trống toàn bộ thì được bỏ qua.
- Dữ liệu cũ không có tenHem ở cả hai lớp vẫn chạy bằng tên đầy đủ trong tenDuong,
  ví dụ Hẻm 17 Đường Quyết Thắng.
- Khóa tuyến là cặp (tenDuong, tenHem), nên Hẻm 1 của hai đường cha không bị nhập chung.
- Tool chuẩn hóa Unicode, bỏ khoảng trắng đầu/cuối và không phân biệt hoa/thường.
  Tool vẫn phân biệt dấu, chính tả và khoảng trắng bên trong.
- Thửa cần là Polygon/MultiPolygon hợp lệ, không rỗng.
- Đường chính có thể là polygon mặt đường (Polygon/MultiPolygon) hoặc polyline tim đường
  (LineString/MultiLineString, chế độ thử nghiệm). Tool tự nhận kiểu theo từng tuyến và hiển thị
  kiểu layer sau khi chọn; mỗi tuyến chỉ được dùng một kiểu.
- Tim đường: lớp tim cũng phải có trường tenDuong (tim tạo từ polygon bằng ArcGIS cần Join để chép
  tenDuong sang). Tim không được cắt qua thửa và không khép vòng (vòng xoay) ở đoạn có thửa.
  Vẽ theo chiều nào cũng được.
- Tool tự xử lý tim tạo tự động từ polygon: nối đầu mút lệch tối đa 10 cm, bỏ râu cụt ngắn hơn 15 m
  ở điểm rẽ nhánh và bỏ qua phần tim không có thửa. Tim phân nhánh ở đoạn có thửa (vd. đường chữ T)
  được đánh từng nhánh như một đoạn riêng; tim đứt thành nhiều cụm được đánh liên tục theo chiều tuyến.
  Hai trường hợp này chạy được nhưng có cảnh báo để rà lại trên bản đồ.
- Hẻm vẽ bằng polygon cần đường cha polygon. Hẻm vẽ bằng tim đường dùng được với đường cha là tim
  hoặc polygon: miệng hẻm là đầu tim gần đường cha nhất (cách tối đa 20 m) và phải gần hơn hẳn
  các đầu tim khác. Tim hẻm phải liền một khối, không vòng; nhánh hẻm ngắn được giữ nguyên.
  Hẻm tim thông hai đường phải ghi đường cha trong tên hẻm hoặc tenHem (không so mặt cắt được).
- Với polygon mặt đường, thửa không được vẽ đè lên mặt đường cùng tuyến. Kiểm tra dữ liệu chặn chạy khi tâm thửa
  (representative point) nằm trong polygon đường, hoặc thửa bị đường cắt thành từ 2 phần trở lên
  (vẽ xuyên qua đường); thửa lấn quá 25% diện tích lên mặt đường được cảnh báo.
  Thửa tiếp giáp hoặc cách mép đường một khoảng vẫn đánh số bình thường.
- Khi đánh hẻm, lớp đường phải có cả đường chính để xác định miệng hẻm, kể cả khi chỉ chọn một hẻm.
- Hẻm phải là một mạng liên thông không tạo vòng. Hẻm phân nhánh được dựng thành cây tim tuyến,
  có gốc tại miệng hẻm. Tool chỉ nối tham chiếu ảo tới đúng đường cha khi khe hở không quá 10 cm;
  hình học nguồn không bị thay đổi.

3. CÁCH SỬ DỤNG
Bước 1: Chọn dữ liệu Thửa.
Bước 2: Chọn dữ liệu Đường.
Bước 3: Nếu dùng File Geodatabase hoặc GeoPackage, chọn đúng layer tương ứng.
Bước 4: Cây tuyến tự tải sau khi chọn đủ hai lớp hợp lệ.
        Tích đường cha để chọn đường chính và toàn bộ hẻm; bỏ tích từng hẻm nếu không chạy.
        Có thể chọn nhiều đường cha/hẻm độc lập, cuộn bằng con lăn, lọc Chỉ đường/Chỉ hẻm,
        chọn mọi kết quả tìm kiếm hoặc bỏ chọn. Bấm Áp dụng lựa chọn để xác nhận.
        Nút Tất cả chọn toàn bộ khóa tuyến có chung ở hai lớp.
        Nhập tay schema mới theo dạng Đường Quyết Thắng › Hẻm 1; nhiều tuyến dùng dấu ;.
        So khớp không phân biệt hoa/thường, chuẩn hóa Unicode và bỏ khoảng trắng đầu/cuối.
        Khi đổi nguồn hoặc layer, cần chọn lại giá trị; lớp thiếu tenDuong sẽ bị chặn.
Bước 5: Nhấn Kiểm tra dữ liệu, đọc các lỗi/lưu ý và chọn nơi lưu kết quả.
Bước 6: Nhấn Bắt đầu đánh số ở thanh cuối cửa sổ; nhấn Nhật ký để mở/thu gọn log.
        Có thể chuyển giao diện Sáng / Tối / Hệ thống trên thanh đầu trang.
        Nút Quy tắc luôn có ở thanh công cụ. Các bảng dài đều có thể cuộn.
        Kiểm tra đầu vào cũng tự chạy trước thuật toán; không tự sửa CRS hay hình học nguồn.

4. ĐỊNH DẠNG ĐẦU RA KHUYẾN NGHỊ
GeoPackage (.gpkg) được khuyến nghị vì giữ đầy đủ tên trường.
soNhaHienThi có kiểu chuỗi: số thường là "1", số trong hẻm là "236/1".
Thửa không có tuyến tương ứng vẫn để trống số nhà, không biến thành "None" hay "nan".
traiPhai và thuTuDiaChi giữ ý nghĩa hiện tại; huong của hẻm là MIENG-HEM.

QUY TẮC HẺM
- Schema khuyến nghị: đường chính tenDuong=Đường A, tenHem trống; hẻm dùng tenDuong=Đường A,
  tenHem=Hẻm 1/Hẻm 236/Hẻm Nam Long. Số tiền tố được bóc từ tenHem.
- Dữ liệu cũ không có tenHem vẫn nhận dạng tên bắt đầu Hẻm/Hem trong tenDuong.
- Hẻm 1 đường A / Hẻm 1 A: trái 1/1, 1/3...; phải 1/2, 1/4...
- Hẻm 236 đường A: trái 236/1, 236/3...; phải 236/2, 236/4...
- Hẻm không có số: trái 1, 3...; phải 2, 4...
- Đường số 236 không được nhận diện thành hẻm. Hẻm 1 đường số 236 chỉ lấy tiền tố 1.
- Chỉ hỗ trợ số nguyên ngay sau Hẻm/Hem; Hẻm 1A và Hẻm 236/5 bị chặn, không tự cắt mất ký tự.
- Đánh từ miệng hẻm vào trong, trái lẻ/phải chẵn theo chiều đi; hẻm cong dùng hướng tại từng đoạn.
- Hẻm thông hai đường: dùng đường gốc trong tên; chưa đặt tên thì so mặt cắt đường tại miệng khi đo chắc chắn.
- Trường hợp giao xiên, mặt cắt không ổn định/bằng nhau hoặc chưa khớp tên đường gốc phải kiểm tra lại dữ liệu.
- Chấp nhận tiếp giáp điểm hoặc khe hở tối đa 10 cm tại đầu hẻm khi đường cha đã xác định rõ.
  Mọi lần dùng dung sai đều hiện cảnh báo; không dùng đường gần nhất làm đường cha.
- Dải chồng hẻm–hẻm có diện tích nhưng mỏng dưới ngưỡng được coi là sai số digitize.
- Hẻm phân nhánh được đánh theo khoảng cách ngắn nhất trên cây tim tuyến tính từ miệng hẻm;
  bên trái/phải được xác định theo hướng đi cục bộ trên từng nhánh. Báo cáo luôn ghi rõ số nhánh.
- Hai hẻm có cùng đường cha, mỗi hẻm có miệng riêng, được phép tiếp giáp nhau; chỗ tiếp giáp chỉ
  là cảnh báo và không được dùng để thay thế miệng hẻm.
- Thiếu đường cha, nhiều miệng phù hợp, vòng, đoạn rời hoặc hẻm cấp 2 chỉ nối qua hẻm khác vẫn
  chặn ghi file vì không xác định được một gốc đánh số duy nhất.
- Chỉ hình học của tuyến đã chọn và đường cha cần dùng mới được kiểm tra; lỗi của tuyến không liên quan
  không chặn lượt chạy. Lỗi của hẻm đang chọn hoặc đường cha của nó vẫn chặn trước khi ghi file.
- Dấu / là quy cách hiển thị theo yêu cầu dữ liệu. Quy định về chiều, trái lẻ/phải chẵn tham chiếu Điều 6–7,
  VBHN 05/VBHN-BXD ngày 13/02/2026, hợp nhất Thông tư 08/2024/TT-BXD và sửa đổi tại Thông tư 09/2025/TT-BXD.
  Nguồn: https://congbao.cdnchinhphu.vn/180507251028987904/2026/3/24/cong-bao-so-159-ngay-25-03-47073_1774343631_signed.pdf

5. PHIÊN BẢN
HAPGIS v1.1

6. PHẠM VI KIỂM THỬ
Phiên bản 1.1 đã được kiểm thử trên bộ dữ liệu hiện tại của dự án.
Một số hình học đặc biệt như vòng xuyến / vòng xoay chưa được kiểm thử đầy đủ.
Nhánh đánh hẻm có kiểm thử tổng hợp cho nhiều hướng, hẻm rẽ góc/chữ U, mạng phân nhánh,
hai đầu thông đường, polygon nhiều mảnh liền nhau, tọa độ lớn, lỗi hình học/miệng hẻm và xuất GPKG/Shapefile.
Chế độ tim đường (thử nghiệm) có kiểm thử tổng hợp cho đường thẳng, đường cong, chữ L, nhiều góc xoay,
tim vẽ ngược chiều, tim nhiều đoạn, thửa lấn mặt đường, các lỗi tim và chạy từ GPKG/Shapefile.
Quan hệ hai trường được kiểm thử với 10 hẻm cùng đường cha, trùng tên Hẻm 1 ở hai đường,
Unicode/hoa thường, schema lệch và cô lập lỗi hình học ngoài phạm vi chọn.

Tham khảo hệ tọa độ/đơn vị:
- pyproj CRS: https://pyproj4.github.io/pyproj/stable/api/crs/crs.html
- EPSG Geodetic Parameter Dataset: https://epsg.org/

============================================================
HAPGIS | House Address Processing GIS
GIS FOR BETTER CITIES
============================================================
