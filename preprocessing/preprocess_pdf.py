import os
import re
import json
import fitz  # PyMuPDF
from typing import Dict, List

# --- Patterns ---
HEADER_FOOTER_PATTERNS = [
    re.compile(r"^\s*CÔNG BÁO/Số", re.IGNORECASE),
    re.compile(r"CÔNG\s*BÁO/Số\s*\d+\s*\+\s*\d+/[\s*Ngày]*", re.IGNORECASE),
    re.compile(r"^\s*\d+\s+CÔNG BÁO/Số", re.IGNORECASE),
    re.compile(r"^\s*Trang\s+\d+\s*/\s*\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*\d+\s*$"),  # Lọc số trang đứng một mình
]

SIGNATURE_PATTERNS = [
    re.compile(r"^\s*(KT\.|TM\.|TL\.)?\s*(THỦ TƯỚNG|BỘ TRƯỞNG|THỐNG ĐỐC)\s*$", re.IGNORECASE),
    re.compile(
        r"^\s*(Phạm Minh Chính|Nguyễn Xuân Phúc|Vũ Đức Đam|Nguyễn Tấn Dũng|Nguyễn Bắc Son|Nguyễn Văn Bình|Nguyễn Sinh Hùng)\s*$",
        re.IGNORECASE),
    re.compile(r"^\s*\./\.\s*$"),
]

SECTION_PATTERNS = {
    "chapter": re.compile(r"^\s*([IVXLCDM]+)\.\s*(.*)", re.IGNORECASE),
    "section": re.compile(r"^\s*(\d+)\.\s+([^\d].*)"),
    "subsection": re.compile(r"^\s*([a-zđ])\)\s*(.*)", re.IGNORECASE),
    "point": re.compile(r"^\s*-\s+(.*)", re.IGNORECASE),
}

METADATA_PATTERNS = {
    "so_hieu": re.compile(r"Số:\s*(\S+)"),
    "date": re.compile(
        r"(?:(Hà Nội|TP\. Hồ Chí Minh)\s*,)?\s*ngày\s+(\d{1,2})\s*(?:tháng|-|/|\s)\s*(\d{1,2})\s*(?:năm|-|/|\s)\s*(\d{4})",
        re.IGNORECASE),
    "type": re.compile(r"^(CHỈ THỊ|NGHỊ ĐỊNH|THÔNG TƯ|QUYẾT ĐỊNH|LUẬT|CÔNG ĐIỆN)\s*$", re.IGNORECASE),
}

IGNORE_PATTERNS = [
    re.compile(r"^\s*CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\s*$", re.IGNORECASE),
    re.compile(r"^\s*Độc lập - Tự do - Hạnh phúc\s*$", re.IGNORECASE),
    re.compile(r"^\s*THỦ TƯỚNG CHÍNH PHỦ\s*$", re.IGNORECASE),
    re.compile(r"^\s*Ký bởi: Cổng Thông tin điện tử Chính phủ\s*$", re.IGNORECASE),
    re.compile(r"^\s*Email: thongtinchinhphu@chinhphu\.vn\s*$", re.IGNORECASE),
    re.compile(r"^\s*Cơ quan: Văn phòng Chính phủ\s*$", re.IGNORECASE),
    re.compile(r"^\s*Thời gian ký: \d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2} \+\d{2}:\d{2}\s*$", re.IGNORECASE),
]

ISSUER_MAP = {
    "CT-TTg": "THỦ TƯỚNG CHÍNH PHỦ",
    "CT-NHNN": "NGÂN HÀNG NHÀ NƯỚC VIỆT NAM",
    "CT-BTTTT": "BỘ THÔNG TIN VÀ TRUYỀN THÔNG",
    "CT-VPCP": "VĂN PHÒNG CHÍNH PHỦ",
    "QĐ-TTg": "THỦ TƯỚNG CHÍNH PHỦ",
    "TT-BCA": "BỘ CÔNG AN",
    "TT-BGDĐT": "BỘ GIÁO DỤC VÀ ĐÀO TẠO",
    "TT-BKHĐT": "BỘ KẾ HOẠCH VÀ ĐẦU TƯ",
    "VBPL": "QUỐC HỘI",
    "NĐ-CP": "CHÍNH PHỦ",
}


def clean_text(text: str) -> str:
    """Làm sạch văn bản, chuẩn hóa khoảng trắng và ký tự."""
    text = re.sub(r"\s+", " ", text.strip())
    text = re.sub(r"[\n\r]+", "\n", text)
    return text


def is_header_footer(line: str) -> bool:
    """Kiểm tra xem dòng có phải là header/footer không."""
    line = line.strip()
    if not line:
        return False
    return any(pattern.search(line) for pattern in HEADER_FOOTER_PATTERNS)


def is_signature(line: str) -> bool:
    """Kiểm tra xem dòng có phải là chữ ký hoặc kết thúc văn bản không."""
    line = line.strip()
    return any(pattern.match(line) for pattern in SIGNATURE_PATTERNS)


def is_ignore_line(line: str) -> bool:
    """Kiểm tra xem dòng có phải là dòng cần bỏ qua không."""
    line = line.strip()
    if not line:
        return True
    return any(pattern.match(line) for pattern in IGNORE_PATTERNS)


def is_bold_span(span: dict) -> bool:
    """Kiểm tra xem span có định dạng in đậm không."""
    font = span.get("font", "").lower()
    # print(font)
    # Chỉ kiểm tra font chứa 'TimesNewRoman,Bold' hoặc tương tự
    # Mở rộng kiểm tra font đậm phổ biến hơn
    return (
            "timesnewromanps-boldmt" in font
            or "bold" in font
            or "-bd" in font
            or "ps-bold" in font
            or "timesnewroman,bold" in font
    )


def read_pdf(file_path: str) -> List[Dict]:
    """Đọc PDF bằng PyMuPDF và trả về danh sách các block văn bản kèm định dạng."""
    try:
        doc = fitz.open(file_path)
        blocks = []
        for page in doc:
            page_blocks = page.get_text("dict")["blocks"]
            for block in page_blocks:
                if block["type"] == 0:  # Chỉ lấy block văn bản
                    for line in block["lines"]:
                        for span in line["spans"]:
                            text = clean_text(span["text"])
                            if text and not is_ignore_line(text):
                                blocks.append({
                                    "text": text,
                                    "font": span["font"],
                                    "size": span["size"],
                                    "flags": span["flags"],
                                    "bbox": span["bbox"],
                                    "page": page.number
                                })
        doc.close()
        return blocks
    except Exception as e:
        raise Exception(f"Lỗi đọc PDF {file_path}: {e}")


def get_issuer(so_hieu: str) -> str:
    """Xác định nơi ban hành dựa trên số hiệu."""
    if not so_hieu:
        return "Không xác định"
    for key, issuer in ISSUER_MAP.items():
        if key in so_hieu:
            return issuer
    # Fallback logic
    if "CP" in so_hieu: return "CHÍNH PHỦ"
    if "TTg" in so_hieu: return "THỦ TƯỚNG CHÍNH PHỦ"
    if "QH" in so_hieu: return "QUỐC HỘI"
    if "UBTVQH" in so_hieu: return "ỦY BAN THƯỜNG VỤ QUỐC HỘI"
    # if "NNHN" in so_hieu:
    return "Không xác định"


def collect_title_lines(lines: List[str], start_idx: int, current_line: str) -> tuple[str, int]:
    """Gộp các dòng tiếp theo để tạo tiêu đề hoàn chỉnh."""
    title_parts = [current_line.strip()]
    i = start_idx + 1
    while i < len(lines):
        next_line = lines[i].strip()
        if not next_line or is_header_footer(next_line) or is_signature(next_line):
            i += 1
            continue
        # Dừng nếu gặp cấu trúc khác hoặc dòng trống
        if any(p.match(next_line) for p in SECTION_PATTERNS.values()) or not next_line.strip():
            break
        title_parts.append(next_line)
        i += 1
    return " ".join(title_parts).strip(), i


def parse_pdf_content(blocks: List[Dict], file_name: str) -> Dict:
    """Phân tích và chunk nội dung PDF từ các block PyMuPDF (Chỉ sửa logic trích yếu)."""
    result = {
        "metadata": {
            "so_hieu": "",
            "loai_van_ban": "",
            "noi_ban_hanh": "",
            "ngay_ban_hanh": "",
            "ten_van_ban": "",
            "trich_yeu": "",
            "file_name": file_name
        },
        "chuong": []
    }

    # Giữ nguyên cleaned_lines từ code gốc của bạn
    cleaned_lines = [b["text"] for b in blocks if not is_header_footer(b["text"])]

    type_found = False
    type_block_index = -1  # Index của block chứa loại văn bản

    # --- Trích xuất metadata (Giữ nguyên logic gốc, chỉ thêm type_block_index) ---
    i = 0
    while i < len(blocks):
        block = blocks[i]
        line = block["text"].strip()
        if not line:
            i += 1
            continue

        # Debug font và bold (Giữ nguyên)
        # print(f"Debug: Line=\'{line}\', Font={block["font"]}, Size={block["size"]}, Bold={is_bold_span(block)}")

        # Loại văn bản (Lưu index)
        if match := METADATA_PATTERNS["type"].match(line):
            if not result["metadata"]["loai_van_ban"]:
                result["metadata"]["loai_van_ban"] = match.group(1).upper()
                type_found = True
                type_block_index = i  # Lưu index của block này
                if result["metadata"]["so_hieu"]:
                    result["metadata"]["ten_van_ban"] = f"{match.group(1).title()} {result["metadata"]["so_hieu"]}"
            i += 1
            continue

        # Số hiệu (Giữ nguyên)
        if match := METADATA_PATTERNS["so_hieu"].search(line):
            if not result["metadata"]["so_hieu"]:
                result["metadata"]["so_hieu"] = match.group(1)
                result["metadata"]["noi_ban_hanh"] = get_issuer(match.group(1))
                if result["metadata"]["loai_van_ban"]:
                    result["metadata"]["ten_van_ban"] = f"{result["metadata"]["loai_van_ban"].title()} {match.group(1)}"
            i += 1
            continue

        # Ngày ban hành (Giữ nguyên)
        if match := METADATA_PATTERNS["date"].search(line):
            if not result["metadata"]["ngay_ban_hanh"]:
                day, month, year = match.group(2), match.group(3), match.group(4)
                result["metadata"]["ngay_ban_hanh"] = f"{int(day):02d}/{int(month):02d}/{year}"
            i += 1
            continue

        # Bỏ qua logic trích yếu cũ ở đây
        i += 1

    # --- Logic trích yếu MỚI - Chỉ sửa phần này ---
    if type_found and type_block_index != -1:
        trich_yeu_parts = []
        # Bắt đầu quét từ block ngay sau block loại văn bản
        j = type_block_index + 1
        potential_summary_blocks = []
        max_lookahead = 15  # Giới hạn số block quét để tránh lỗi
        count_lookahead = 0

        while j < len(blocks) and count_lookahead < max_lookahead:
            block = blocks[j]
            line = block["text"].strip()

            # Điều kiện dừng quét: gặp dòng trống, header/footer, signature, hoặc cấu trúc section
            if result["metadata"]["loai_van_ban"] == "CÔNG ĐIỆN":
                if not line or is_header_footer(line) or is_signature(line) or any(
                        p.match(line) for p in SECTION_PATTERNS.values()) or re.search(r"điện\s*:", line, re.IGNORECASE):
                    break
            else:
                if not line or is_header_footer(line) or is_signature(line) or any(
                        p.match(line) for p in SECTION_PATTERNS.values()):
                    break

                # Bỏ qua các dòng ignore khác
            if is_ignore_line(line):
                j += 1
                count_lookahead += 1
                continue

            potential_summary_blocks.append(block)
            j += 1
            count_lookahead += 1

        # Lọc các block đã thu thập để lấy text in đậm
        for block in potential_summary_blocks:
            if is_bold_span(block):
                trich_yeu_parts.append(block["text"].strip())
            # Quan trọng: Không dừng ngay cả khi gặp dòng không đậm
            # Chỉ dừng khi quét hết potential_summary_blocks

        result["metadata"]["trich_yeu"] = " ".join(trich_yeu_parts).strip()
        # Cập nhật lại tên văn bản nếu cần (giữ logic cũ)
        if not result["metadata"]["ten_van_ban"] and result["metadata"]["trich_yeu"]:
            result["metadata"]["ten_van_ban"] = result["metadata"]["trich_yeu"]

    # --- Chunk nội dung (Giữ nguyên hoàn toàn logic gốc của bạn) ---
    current_chapter = None
    current_section = None
    current_subsection = None
    current_points = []
    content_started = False
    i = 0  # Reset index để quét lại từ đầu cho phần nội dung

    # Tìm điểm bắt đầu nội dung (logic này có thể cần xem lại nếu gây lỗi, nhưng giữ nguyên theo yêu cầu)
    while i < len(cleaned_lines):
        line = cleaned_lines[i].strip()
        if not line:
            i += 1
            continue
        if not content_started and any(
                p.match(line) for p in [SECTION_PATTERNS["chapter"], SECTION_PATTERNS["section"]]):
            content_started = True
            break  # Bắt đầu xử lý nội dung từ đây
        i += 1

    # Nếu không tìm thấy điểm bắt đầu rõ ràng, có thể bắt đầu từ đầu (hoặc sau metadata)
    if not content_started:
        i = 0  # Hoặc một index phù hợp hơn sau khi metadata được trích xuất
        print(f"Warning: Không xác định được điểm bắt đầu nội dung rõ ràng cho {file_name}")

    # Vòng lặp xử lý nội dung chính (Giữ nguyên logic gốc)
    while i < len(cleaned_lines):
        line = cleaned_lines[i].strip()
        if not line:
            i += 1
            continue

        # Bỏ qua các dòng header/footer/ignore/signature trong nội dung
        if is_header_footer(line) or is_ignore_line(line):
            i += 1
            continue

        if is_signature(line):
            if current_points:
                if current_subsection:
                    current_subsection["diem"] = current_points
                elif current_section:
                    current_section["khoan"].append({"ten_khoan": "", "tieu_de": "", "diem": current_points})
            break

        # Chương
        if match := SECTION_PATTERNS["chapter"].match(line):
            if current_points:
                if current_subsection:
                    current_subsection["diem"] = current_points
                elif current_section:
                    current_section["khoan"].append({"ten_khoan": "", "tieu_de": "", "diem": current_points})
                current_points = []

            title, new_i = collect_title_lines(cleaned_lines, i, match.group(2))
            current_chapter = {
                "ten_chuong": f"Chương {match.group(1)}",
                "tieu_de": title,
                "muc": []
            }
            result["chuong"].append(current_chapter)
            current_section = None
            current_subsection = None
            i = new_i
            continue

        # Mục
        if match := SECTION_PATTERNS["section"].match(line):
            if current_points:
                if current_subsection:
                    current_subsection["diem"] = current_points
                elif current_section:
                    current_section["khoan"].append({"ten_khoan": "", "tieu_de": "", "diem": current_points})
                current_points = []

            title, new_i = collect_title_lines(cleaned_lines, i, match.group(2))
            current_section = {
                "ten_muc": f"Mục {match.group(1)}",
                "tieu_de": title,
                "khoan": []
            }
            if current_chapter:
                current_chapter["muc"].append(current_section)
            else:
                # Tạo chương ảo nếu không có chương nào trước đó
                result["chuong"].append({
                    "ten_chuong": "",
                    "tieu_de": "",
                    "muc": [current_section]
                })
                current_chapter = result["chuong"][-1]
            current_subsection = None
            i = new_i
            continue

        # Khoản (Điểm a, b, c)
        if match := SECTION_PATTERNS["subsection"].match(line):
            if current_points:
                if current_subsection:
                    current_subsection["diem"] = current_points
                elif current_section:
                    current_section["khoan"].append({"ten_khoan": "", "tieu_de": "", "diem": current_points})
                current_points = []

            title, new_i = collect_title_lines(cleaned_lines, i, match.group(2))
            current_subsection = {
                "ten_khoan": f"Khoản {match.group(1)}",  # Sửa lại tên key cho nhất quán
                "tieu_de": title,
                "diem": []
            }
            if current_section:
                current_section["khoan"].append(current_subsection)
            elif current_chapter:  # Nếu không có Mục, thêm vào Chương
                # Cần tạo Mục ảo nếu chưa có
                if not current_chapter["muc"]:
                    current_chapter["muc"].append({"ten_muc": "", "tieu_de": "", "khoan": []})
                current_chapter["muc"][-1]["khoan"].append(current_subsection)
            else:  # Nếu không có Chương, Mục
                # Tạo Chương và Mục ảo
                result["chuong"].append({"ten_chuong": "", "tieu_de": "",
                                         "muc": [{"ten_muc": "", "tieu_de": "", "khoan": [current_subsection]}]})
                current_chapter = result["chuong"][-1]
                current_section = current_chapter["muc"][-1]

            i = new_i
            continue

        # Điểm (-)
        if match := SECTION_PATTERNS["point"].match(line):
            current_points.append(match.group(1).strip())
            i += 1
            continue

        # Nội dung thông thường (Giữ nguyên)
        if content_started:
            if current_points:
                # Nối vào điểm cuối cùng
                current_points[-1] = f"{current_points[-1]} {line}"
            elif current_subsection:
                # Nối vào tiêu đề/nội dung của khoản
                current_subsection["tieu_de"] = f"{current_subsection["tieu_de"]} {line}"
            elif current_section:
                # Nối vào tiêu đề/nội dung của mục
                current_section["tieu_de"] = f"{current_section["tieu_de"]} {line}"
            elif current_chapter:
                # Nối vào tiêu đề/nội dung của chương
                current_chapter["tieu_de"] = f"{current_chapter["tieu_de"]} {line}"

        i += 1

    # Lưu điểm cuối cùng (Giữ nguyên)
    if current_points:
        if current_subsection:
            current_subsection["diem"] = current_points
        elif current_section:
            # Thêm vào khoản cuối cùng của mục, hoặc tạo khoản ảo nếu chưa có
            if not current_section["khoan"]:
                current_section["khoan"].append({"ten_khoan": "", "tieu_de": "", "diem": []})
            current_section["khoan"][-1]["diem"] = current_points
        elif current_chapter:
            # Thêm vào mục/khoản cuối cùng của chương
            if not current_chapter["muc"]:
                current_chapter["muc"].append(
                    {"ten_muc": "", "tieu_de": "", "khoan": [{"ten_khoan": "", "tieu_de": "", "diem": []}]})
            elif not current_chapter["muc"][-1]["khoan"]:
                current_chapter["muc"][-1]["khoan"].append({"ten_khoan": "", "tieu_de": "", "diem": []})
            current_chapter["muc"][-1]["khoan"][-1]["diem"] = current_points

    signatory_name = ""
    signatory_title = ""
    potential_signatory_lines = []

    # Scan the last 50 blocks/lines of the document for signatory info
    scan_start_idx = max(0, len(blocks) - 50)

    for k in range(scan_start_idx, len(blocks)):
        block = blocks[k]
        line = block["text"].strip()

        if not line or is_header_footer(line) or is_ignore_line(line):
            continue

        potential_signatory_lines.append(line)

    # Now process the collected potential signatory lines in reverse order
    # to find title and name, as title usually appears above name
    for i in range(len(potential_signatory_lines) - 1, -1, -1):
        line = potential_signatory_lines[i]

        # Look for title (e.g., THỦ TƯỚNG, BỘ TRƯỞNG)
        # Expanded pattern for common titles
        title_pattern = re.compile(
            r"^(KT\.|TM\.|TL\.)?\s*(THỦ TƯỚNG|BỘ TRƯỞNG|THỐNG ĐỐC|CHỦ TỊCH QUỐC HỘI|CHỦ TỊCH NƯỚC|CHỦ TỊCH HỘI ĐỒNG NHÂN DÂN|CHỦ TỊCH ỦY BAN NHÂN DÂN|PHÓ THỦ TƯỚNG|PHÓ CHỦ TỊCH QUỐC HỘI|PHÓ CHỦ TỊCH NƯỚC|PHÓ CHỦ TỊCH HỘI ĐỒNG NHÂN DÂN|PHÓ CHỦ TỊCH ỦY BAN NHÂN DÂN)\s*$",
            re.IGNORECASE)
        title_match = title_pattern.match(line)
        if title_match and not signatory_title:
            signatory_title = title_match.group(2).strip().upper()  # Extract the actual title part
            continue

        # Look for name (e.g., Nguyễn Xuân Phúc)
        # A name usually consists of 2-4 capitalized words, or a common name from a list
        # This regex assumes names start with a capital letter and contain Vietnamese characters
        name_pattern = re.compile(
            r"^[A-ZĐ][a-zđàáạảãăắằặẳẵâấầậẩẫèéẹẻẽêếềệểễìíịỉĩòóọỏõôốồộổỗơớờợởỡùúụủũưứừựửữýỳỵỷỹ]+\s+([A-ZĐ][a-zđàáạảãăắằặẳẵâấầậẩẫèéẹẻẽêếềệểễìíịỉĩòóọỏõôốồộổỗơớờợởỡùúụủũưứừựửữýỳỵỷỹ]+\s*){1,4}$",
            re.IGNORECASE)  # Added re.IGNORECASE for names
        name_match = name_pattern.match(line)
        if name_match and not signatory_name:
            # Basic heuristic: name line should not be too short or too long
            if 5 <= len(line) <= 50:
                signatory_name = line.strip()
                # If we found a name and a title, we can stop
                if signatory_title:
                    break
            continue

        # If we've found a title and a name, and we encounter a line that's neither,
        # it's likely we've passed the signatory block.
        if signatory_title and signatory_name:
            break

    # Assign extracted values to metadata
    result["metadata"]["chuc_vu_nguoi_ky"] = signatory_title
    result["metadata"]["nguoi_ky"] = signatory_name

    return result


def save_to_json(data: List[Dict], output_path: str):
    """Lưu danh sách tài liệu vào file JSON."""
    # Đảm bảo thư mục tồn tại
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"Đã lưu vào: {output_path}")


def process_pdf_folder(folder_path: str, output_json: str):
    """Xử lý tất cả file PDF trong thư mục."""
    documents = []
    if not os.path.isdir(folder_path):
        print(f"Lỗi: Thư mục không tồn tại: {folder_path}")
        return

    for file in os.listdir(folder_path):
        if not file.lower().endswith(".pdf"):
            continue

        pdf_path = os.path.join(folder_path, file)
        try:
            print(f"Đang xử lý: {file}")
            blocks = read_pdf(pdf_path)
            if not blocks:
                print(f"Cảnh báo: Không trích xuất được block nào từ {file}")
                continue
            doc_info = parse_pdf_content(blocks, file)

            if doc_info.get("chuong"):
                documents.append(doc_info)
        except Exception as e:
            print(f"Lỗi xử lý {file}: {e}")
            import traceback
            traceback.print_exc()  # In chi tiết lỗi để debug

    if documents:
        save_to_json(documents, output_json)
    else:
        print("Không có tài liệu nào được xử lý thành công.")


# --- Main Execution (Giữ nguyên logic gốc của bạn) ---
if __name__ == "__main__":
    folder_to_process = "../data/CongThongTinDienTu"
    folder_to_save = "../preprocessing"

    for folder_name in os.listdir(folder_to_process):
        if folder_name.endswith("zip"):
            continue

        if folder_name == "CongDien" or folder_name == "ChiThi":
            folder_path = os.path.join(folder_to_process, folder_name)

            output_folder_to_save = os.path.join(folder_to_save, folder_name)
            os.makedirs(output_folder_to_save, exist_ok=True)

            output_file_to_save = output_folder_to_save + "/" + f"processed_documents_{folder_name.lower()}.json"

            process_pdf_folder(folder_path, output_file_to_save)
