import re
import fitz  # Thư viện PyMuPDF, cần cài đặt: pip install pymupdf
import json
import os


def extract_spans_with_formatting(pdf_path: str) -> list:
    """
    Hàm này đọc một file PDF và trích xuất từng mẩu văn bản nhỏ (span)
    cùng với thông tin định dạng chi tiết của nó.

    Args:
        pdf_path (str): Đường dẫn đến file PDF cần đọc.

    Returns:
        list: Một danh sách các dictionary, mỗi dictionary đại diện cho một span.
              Trả về danh sách rỗng nếu có lỗi.
    """
    # Kiểm tra xem file có tồn tại không
    if not os.path.exists(pdf_path):
        print(f"(!) Lỗi: File không tồn tại tại đường dẫn: {pdf_path}")
        return []

    all_spans_data = []
    try:
        # Mở file PDF
        doc = fitz.open(pdf_path)
        print(f"\n--- Đang đọc file: {os.path.basename(pdf_path)} ---")

        # Lặp qua từng trang (page) trong tài liệu
        for page_num, page in enumerate(doc):

            # Sử dụng get_text("dict") để lấy cấu trúc chi tiết của trang
            # Cấu trúc này có dạng: Page -> Block -> Line -> Span
            page_blocks = page.get_text("dict").get("blocks", [])

            for block in page_blocks:
                # Block type 0 là block chứa văn bản
                if block.get("type") == 0:
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):

                            # Lấy text và làm sạch khoảng trắng thừa
                            span_text = span['text'].strip()

                            # Chỉ xử lý các span có nội dung
                            if span_text:
                                # Kiểm tra xem font chữ có phải là in đậm không
                                font_name = span.get("font", "").lower()
                                is_bold = "bold" in font_name or "bd" in font_name or "heavy" in font_name

                                # Tạo một dictionary chứa thông tin quan trọng của span này
                                span_info = {
                                    "text": span_text,
                                    "font": span.get("font"),
                                    "size": round(span.get("size"), 2),
                                    "is_bold": is_bold,
                                    "flags": span.get("flags"),
                                    "page": page_num + 1  # Ghi lại số trang (bắt đầu từ 1)
                                }

                                # Thêm dictionary này vào danh sách kết quả
                                all_spans_data.append(span_info)

        # Đóng file sau khi xử lý xong
        doc.close()
        print(f"--- Hoàn thành đọc file, trích xuất được {len(all_spans_data)} spans. ---")

    except Exception as e:
        print(f"(!) Đã xảy ra lỗi nghiêm trọng khi đọc file {pdf_path}: {e}")

    return all_spans_data


def filter_junk_spans(raw_spans: list) -> list:
    """
    Hàm này nhận vào danh sách span thô và lọc bỏ các span chứa thông tin rác.

    Args:
        raw_spans (list): Danh sách các span từ hàm extract_spans_with_formatting.

    Returns:
        list: Một danh sách mới chỉ chứa các span thuộc nội dung chính.
    """
    print(f"\n--- [Bước 2] Bắt đầu lọc thông tin rác... ---")

    # TỔNG HỢP LẠI CÁC PATTERN RÁC TỪ FILE CŨ CỦA BẠN
    # Chúng ta gom chúng lại để kiểm tra một lần cho tiện
    JUNK_PATTERNS = [
        # Từ HEADER_FOOTER_PATTERNS
        re.compile(r"^\s*CÔNG BÁO/Số", re.IGNORECASE),
        re.compile(r"^\s*\d+\s*$"),  # Lọc số trang đứng một mình
        # Từ IGNORE_PATTERNS
        re.compile(r"^\s*CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\s*$", re.IGNORECASE),
        re.compile(r"^\s*Độc lập - Tự do - Hạnh phúc\s*$", re.IGNORECASE),
        re.compile(r"^\s*Ký bởi: Cổng Thông tin điện tử Chính phủ\s*$", re.IGNORECASE),
        re.compile(r"^\s*Email: thongtinchinhphu@chinhphu\.vn\s*$", re.IGNORECASE),
        re.compile(r"^\s*Cơ quan: Văn phòng Chính phủ\s*$", re.IGNORECASE),
        re.compile(r"^\s*Thời gian ký:", re.IGNORECASE),
        # Thêm các pattern khác nếu cần
    ]

    cleaned_spans = []
    for span in raw_spans:
        text_to_check = span['text']
        is_junk = False

        # Kiểm tra xem text của span có khớp với bất kỳ pattern rác nào không
        for pattern in JUNK_PATTERNS:
            if pattern.search(text_to_check):
                is_junk = True
                break  # Nếu đã là rác thì không cần kiểm tra nữa

        # Nếu không phải là rác, thì giữ lại span này
        if not is_junk:
            cleaned_spans.append(span)

    print(f"--- [Bước 2] Hoàn thành, còn lại {len(cleaned_spans)} spans sau khi lọc. ---")
    return cleaned_spans


# --- CÁCH SỬ DỤNG VÀ XEM KẾT QUẢ ---
if __name__ == "__main__":
    file_can_xu_ly = "../data/CongThongTinDienTu/ChiThi/28_CT-TTg(12709).pdf"

    # 1. Chạy Bước 1: Lấy dữ liệu thô
    raw_spans = extract_spans_with_formatting(file_can_xu_ly)

    # 2. Chạy Bước 2: Lọc bỏ rác
    cleaned_spans = filter_junk_spans(raw_spans)

    # 3. SO SÁNH TRƯỚC VÀ SAU KHI LỌC
    if cleaned_spans:
        print("\n--- VÍ DỤ TRƯỚC KHI LỌC (CÓ THỂ CHỨA RÁC) ---")
        for i in range(min(5, len(raw_spans))):
            print(raw_spans[i]['text'])

        print("\n--- VÍ DỤ SAU KHI LỌC (ĐÃ SẠCH HƠN) ---")
        for i in range(min(5, len(cleaned_spans))):
            print(cleaned_spans[i]['text'])

        # 4. Lưu kết quả đã làm sạch ra file JSON để dùng cho bước tiếp theo
        output_filename = os.path.splitext(os.path.basename(file_can_xu_ly))[0] + "_cleaned_spans.json"
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(cleaned_spans, f, ensure_ascii=False, indent=2)

        print(f"\n>>> Đã lưu danh sách span đã làm sạch vào file: {output_filename}")