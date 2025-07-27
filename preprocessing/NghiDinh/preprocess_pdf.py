import os
import re
import json
import fitz  # PyMuPDF
from typing import Dict, List, Optional, Tuple

# --- Patterns ---
HEADER_FOOTER_PATTERNS = [
    re.compile(r"^\s*CÔNG BÁO/Số", re.IGNORECASE),
    re.compile(r"CÔNG\s*BÁO/Số\s*\d+\s*\+\s*\d+/[\s*Ngày]*", re.IGNORECASE),
    re.compile(r"^\s*\d+\s+CÔNG BÁO/Số", re.IGNORECASE),
    re.compile(r"^\s*\d+\s*$"),  # Filter page numbers standing alone
]

SIGNATURE_PATTERNS = [
    re.compile(r"^\s*(TM\. CHÍNH PHỦ|CHỦ TỊCH QUỐC HỘI)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(THỦ TƯỚNG|CHỦ TỊCH)\s*$", re.IGNORECASE),
    re.compile(
        r"^\s*(Nguyễn Tấn Dũng|Nguyễn Phú Trọng|Nguyễn Thị Kim Ngân|Vương Đình Huệ|Trần Thanh Mẫn|Nguyễn Sinh Hùng)\s*$",
        re.IGNORECASE),
    re.compile(r"^\s*\./\.\s*$"),
]

# Patterns for both regular and amending laws
SECTION_PATTERNS = {
    "chuong": re.compile(r"^\s*Chương\s+([IVXLCDM]+)\s*$", re.IGNORECASE),
    "dieu": re.compile(r"^\s*(Điều\s+\d+)\.\s+(.*)"),
    "khoan": re.compile(r"^\s*(\d+)\.\s+(.*)"),  # Used for Khoan in regular laws AND numbered changes in amending laws
    "diem": re.compile(r"^\s*([a-zđ])\)\s+(.*)")
}

# Updated, more generic metadata patterns
METADATA_PATTERNS = {
    "so_hieu": re.compile(r"Số:\s*(\S+)", re.IGNORECASE),
    "date": re.compile(
        r"(?:(Hà Nội|TP\. Hồ Chí Minh)\s*,)?\s*ngày\s+(\d{1,2})\s*tháng\s*(\d{1,2})\s*năm\s*(\d{4})",
        re.IGNORECASE),
    "type": re.compile(r"^(LUẬT|NGHỊ ĐỊNH|QUYẾT ĐỊNH|THÔNG TƯ|CHỈ THỊ)\s*$", re.IGNORECASE),
    "issuer": re.compile(r"^(CHÍNH PHỦ|QUỐC HỘI)\s*$", re.IGNORECASE),
    # Pattern for date in the closing text of laws
    "law_date": re.compile(
        r".*khóa\s+([IVXLCDM]+).*kỳ họp thứ\s+(\S+)\s+thông qua\s+ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s*(\d{4})",
        re.IGNORECASE),
}

IGNORE_PATTERNS = [
    re.compile(r"^\s*CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\s*$", re.IGNORECASE),
    re.compile(r"^\s*Độc lập - Tự do - Hạnh phúc\s*$", re.IGNORECASE),
    re.compile(r"^\s*Căn cứ Hiến pháp.*$", re.IGNORECASE),
    re.compile(r"^\s*Căn cứ Luật.*$", re.IGNORECASE),
    re.compile(r"^\s*Theo đề nghị của.*$", re.IGNORECASE),
    re.compile(r"^\s*Ký bởi: Cổng Thông tin điện tử Chính phủ\s*$", re.IGNORECASE),
    re.compile(r"^\s*Email: thongtinchinhphu@chinhphu\.vn\s*$", re.IGNORECASE),
    re.compile(r"^\s*Cơ quan: Văn phòng Chính phủ\s*$", re.IGNORECASE),
    re.compile(r"^\s*Thời gian ký: \d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2} \+\d{2}:\d{2}\s*$", re.IGNORECASE),
    re.compile(r"^\s*VGP\s*$", re.IGNORECASE),
    re.compile(r"^\s*CHINHPHU.VN\s*$", re.IGNORECASE),
    re.compile(r"^\s*LONG THONG TIN DIEN TU\s*$", re.IGNORECASE),
]

ISSUER_MAP = {
    "QH": "QUỐC HỘI",
    "CP": "CHÍNH PHỦ"
}


def clean_text(text: str) -> str:
    """Cleans text, normalizes whitespace."""
    return re.sub(r"\s+", " ", text).strip()


def is_header_footer(line: str) -> bool:
    """Checks if a line is a header/footer."""
    return any(pattern.search(line) for pattern in HEADER_FOOTER_PATTERNS)


def is_signature(line: str) -> bool:
    """Checks if a line is part of a signature block."""
    return any(pattern.match(line) for pattern in SIGNATURE_PATTERNS)


def is_ignore_line(line: str) -> bool:
    """Checks if a line should be ignored."""
    if not line:
        return True
    return any(pattern.match(line) for pattern in IGNORE_PATTERNS)


def is_bold_span(span: dict) -> bool:
    """Checks if a text span is bold based on font name."""
    font = span.get("font", "").lower()
    return (
            "bold" in font or
            "-bd" in font or
            "ps-bold" in font or
            "timesnewromanps-boldmt" in font
    )


def read_pdf(file_path: str) -> List[Dict]:
    """Reads a PDF and returns a list of text blocks with formatting."""
    try:
        doc = fitz.open(file_path)
        blocks = []
        for page_num, page in enumerate(doc):
            page_blocks = page.get_text("dict")["blocks"]
            for block in page_blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            text = clean_text(span["text"])
                            if text and not is_header_footer(text) and not is_ignore_line(text):
                                blocks.append({
                                    "text": text,
                                    "font": span["font"],
                                    "is_bold": is_bold_span(span),
                                    "page": page_num
                                })
        doc.close()
        return blocks
    except Exception as e:
        print(f"Error reading PDF {file_path}: {e}")
        return []


def get_issuer(so_hieu: str) -> str:
    """Determines the issuer from the 'so_hieu' identifier."""
    if not so_hieu:
        return "Không xác định"
    for key, issuer in ISSUER_MAP.items():
        if key in so_hieu:
            return issuer
    return "Không xác định"


def collect_content_lines(lines: List[str], start_idx: int) -> Tuple[str, int]:
    """Collects subsequent lines of content for a structured element."""
    content_parts = [lines[start_idx].strip()]
    i = start_idx + 1
    while i < len(lines):
        next_line = lines[i].strip()
        if not next_line or is_signature(next_line):
            i += 1
            continue
        if any(p.match(next_line) for p in SECTION_PATTERNS.values()):
            break
        content_parts.append(next_line)
        i += 1
    return " ".join(content_parts).strip(), i


def parse_regular_law(result: Dict, cleaned_lines: List[str]) -> Dict:
    """Parses a standard law with Chương, Điều, Khoản, Điểm."""
    current_chuong = None
    current_dieu = None
    current_khoan = None

    i = 0
    content_started = False
    while i < len(cleaned_lines):
        line = cleaned_lines[i].strip()
        if not line or is_signature(line):
            i += 1
            continue

        if not content_started and not any(p.match(line) for p in SECTION_PATTERNS.values()):
            i += 1
            continue
        content_started = True

        chuong_match = SECTION_PATTERNS["chuong"].match(line)
        if chuong_match:
            chuong_title, new_i = collect_content_lines(cleaned_lines, i + 1)
            current_chuong = {
                "ten_chuong": chuong_match.group(1).strip(), "tieu_de": chuong_title, "dieu": []
            }
            result["chuong"].append(current_chuong)
            current_dieu = current_khoan = None
            i = new_i
            continue

        dieu_match = SECTION_PATTERNS["dieu"].match(line)
        if dieu_match:
            full_dieu_content, new_i = collect_content_lines(cleaned_lines, i)
            dieu_title_full = re.sub(r"^\s*Điều\s+\d+\.\s*", "", full_dieu_content, 1)
            current_dieu = {
                "ten_dieu": clean_text(dieu_match.group(1)), "tieu_de": dieu_title_full, "khoan": []
            }
            if not current_chuong:
                current_chuong = {"ten_chuong": "", "tieu_de": "", "dieu": []}
                result["chuong"].append(current_chuong)
            current_chuong["dieu"].append(current_dieu)
            current_khoan = None
            i = new_i
            continue

        khoan_match = SECTION_PATTERNS["khoan"].match(line)
        if khoan_match and current_dieu:
            full_khoan_content, new_i = collect_content_lines(cleaned_lines, i)
            current_khoan = {
                "ten_khoan": f"Khoản {khoan_match.group(1)}", "noi_dung": full_khoan_content, "diem": []
            }
            current_dieu["khoan"].append(current_khoan)
            i = new_i
            continue

        diem_match = SECTION_PATTERNS["diem"].match(line)
        if diem_match and current_khoan:
            full_diem_content, new_i = collect_content_lines(cleaned_lines, i)
            diem_obj = {
                "ten_diem": f"Điểm {diem_match.group(1)})", "noi_dung": full_diem_content
            }
            current_khoan["diem"].append(diem_obj)
            i = new_i
            continue

        i += 1
    return result


def parse_amending_law(result: Dict, cleaned_lines: List[str]) -> Dict:
    """Parses an amending law, distinguishing instructions from content."""
    result["amending_articles"] = []
    current_article = None

    i = 0
    content_started = False
    while i < len(cleaned_lines):
        line = cleaned_lines[i].strip()
        if not line or is_signature(line):
            i += 1
            continue

        if not content_started and not (SECTION_PATTERNS["dieu"].match(line) or SECTION_PATTERNS["khoan"].match(line)):
            i += 1
            continue
        content_started = True

        dieu_match = SECTION_PATTERNS["dieu"].match(line)
        if dieu_match:
            title, new_i = collect_content_lines(cleaned_lines, i)
            title_text = re.sub(r"^Điều\s+\d+\.\s*", "", title, 1).strip()
            current_article = {
                "type": "article",
                "identifier": dieu_match.group(1).strip(),
                "title": title_text,
                "changes": []
            }
            result["amending_articles"].append(current_article)
            i = new_i
            continue

        khoan_match = SECTION_PATTERNS["khoan"].match(line)
        if khoan_match and current_article:
            instruction, new_i_instr = collect_content_lines(cleaned_lines, i)
            change_obj = {
                "identifier": f"Mục {khoan_match.group(1)}",
                "instruction": instruction.strip(),
                "content": ""
            }

            content_parts = []
            i = new_i_instr
            while i < len(cleaned_lines):
                content_line = cleaned_lines[i].strip()
                if not content_line or is_signature(content_line):
                    i += 1
                    continue

                if SECTION_PATTERNS["khoan"].match(content_line) or SECTION_PATTERNS["dieu"].match(content_line):
                    break

                content_parts.append(content_line)
                i += 1

            if content_parts:
                change_obj["content"] = "\n".join(content_parts).strip('“”" ')

            current_article["changes"].append(change_obj)
            continue
        i += 1

    if "chuong" in result:
        del result["chuong"]  # Remove unused key
    return result


def parse_pdf_content(blocks: List[Dict], file_name: str) -> Optional[Dict]:
    """Detects law type and delegates to the appropriate parser."""
    result = {
        "metadata": {
            "so_hieu": "", "loai_van_ban": "", "noi_ban_hanh": "",
            "ngay_ban_hanh": "", "ten_van_ban": "", "trich_yeu": "",
            "file_name": file_name, "nguoi_ky": "", "chuc_vu_nguoi_ky": "",
            "khoa": "", "ky_hop": ""
        },
        "chuong": []
    }

    if not blocks: return None
    cleaned_lines = [b["text"] for b in blocks]

    # --- METADATA EXTRACTION ---
    type_block_index = -1

    # First pass to get all potential metadata from the top part of the document
    for i, block in enumerate(blocks[:40]):  # Scan top 40 blocks for efficiency
        line = block["text"]

        if not result["metadata"]["noi_ban_hanh"]:
            if match := METADATA_PATTERNS["issuer"].match(line):
                result["metadata"]["noi_ban_hanh"] = match.group(1).strip().upper()

        if not result["metadata"]["loai_van_ban"]:
            if match := METADATA_PATTERNS["type"].match(line):
                result["metadata"]["loai_van_ban"] = match.group(1).strip().upper()
                type_block_index = i

        if not result["metadata"]["so_hieu"]:
            if match := METADATA_PATTERNS["so_hieu"].search(line):
                so_hieu = match.group(1)
                result["metadata"]["so_hieu"] = so_hieu
                if not result["metadata"]["noi_ban_hanh"]:
                    result["metadata"]["noi_ban_hanh"] = get_issuer(so_hieu)

        if not result["metadata"]["ngay_ban_hanh"]:
            if match := METADATA_PATTERNS["date"].search(line):
                day, month, year = match.group(2), match.group(3), match.group(4)
                result["metadata"]["ngay_ban_hanh"] = f"{int(day):02d}/{int(month):02d}/{year}"

    # Trích yếu (Summary) - Uses bold text after the document type
    if type_block_index != -1:
        trich_yeu_parts = []
        for i in range(type_block_index + 1, len(blocks)):
            block = blocks[i]
            # Stop if we hit the start of the content or preamble
            if any(p.match(block["text"]) for p in SECTION_PATTERNS.values()) or re.match(r"^\s*Căn cứ", block["text"],
                                                                                          re.IGNORECASE):
                break
            if block["is_bold"]:
                trich_yeu_parts.append(block["text"])
            elif trich_yeu_parts:  # Stop after the first non-bold line after finding some bold lines
                break
        result["metadata"]["trich_yeu"] = " ".join(trich_yeu_parts)

    # Combined Name and Title
    if result["metadata"]["loai_van_ban"] and result["metadata"]["so_hieu"]:
        result["metadata"][
            "ten_van_ban"] = f"{result['metadata']['loai_van_ban'].title()} {result['metadata']['so_hieu']}"

    # For laws, find date, term, session from closing text
    if result["metadata"]["loai_van_ban"] == "LUẬT":
        closing_text = " ".join(cleaned_lines[-20:])
        if match := METADATA_PATTERNS["law_date"].search(closing_text):
            day, month, year = match.group(3), match.group(4), match.group(5)
            result["metadata"]["ngay_ban_hanh"] = f"{int(day):02d}/{int(month):02d}/{year}"
            result["metadata"]["khoa"] = match.group(1).strip()
            result["metadata"]["ky_hop"] = match.group(2).strip()

    # --- PARSER DELEGATION ---
    is_amending_law = "SỬA ĐỔI, BỔ SUNG" in result["metadata"]["trich_yeu"].upper()
    if is_amending_law:
        print(f"-> Detected Amending Law: {file_name}")
        return parse_amending_law(result, cleaned_lines)
    else:
        print(f"-> Detected Regular Law: {file_name}")
        return parse_regular_law(result, cleaned_lines)


def save_all_to_json(data_list: List[Dict], output_path: str):
    """Saves a list of document dictionaries to a single JSON file."""
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
    print(f"All documents saved to: {output_path}")


def process_pdf_folder(folder_path: str, output_file: str):
    """Xử lý tất cả các file PDF trong một thư mục, lọc và chỉ lưu các Nghị định."""
    if not os.path.isdir(folder_path):
        print(f"Lỗi: Thư mục không tồn tại: {folder_path}")
        return

    all_decrees = []  # Danh sách chỉ chứa các Nghị định
    for file in os.listdir(folder_path):
        if not file.lower().endswith(".pdf"):
            continue

        pdf_path = os.path.join(folder_path, file)
        try:
            print(f"Đang xử lý file: {file}")
            blocks = read_pdf(pdf_path)
            if not blocks:
                print(f"Cảnh báo: Không trích xuất được nội dung từ {file}")
                continue

            doc_info = parse_pdf_content(blocks, file)

            # --- LOGIC LỌC THEO NGHỊ ĐỊNH ---
            if doc_info and doc_info["metadata"].get("loai_van_ban") == "NGHỊ ĐỊNH":
                print(f"-> Phát hiện Nghị định. Thêm vào danh sách để lưu.")
                all_decrees.append(doc_info)
            elif doc_info:
                print(f"-> Bỏ qua file (Loại văn bản: {doc_info['metadata'].get('loai_van_ban', 'Không xác định')})")
            else:
                print(f"Cảnh báo: Không thể phân tích nội dung cho file {file}")

        except Exception as e:
            print(f"Lỗi khi xử lý file {file}: {e}")
            import traceback
            traceback.print_exc()

    # Lưu danh sách các Nghị định đã lọc vào file JSON
    if all_decrees:
        print(f"\nTìm thấy và xử lý thành công {len(all_decrees)} Nghị định.")
        save_all_to_json(all_decrees, output_file)
    else:
        print("Không có Nghị định nào được tìm thấy hoặc xử lý thành công trong thư mục.")


# --- Main Execution ---
if __name__ == "__main__":
    folder_to_process = "../../data/CongThongTinDienTu/NghiDinh"
    output_json_file = "processed_documents_nghidinh.json"  # Đổi tên file output cho rõ ràng

    print(f"Bắt đầu xử lý các file PDF từ thư mục: {folder_to_process}")

    if os.path.exists(folder_to_process):
        process_pdf_folder(folder_to_process, output_json_file)
        print(f"\nXử lý hoàn tất. Các Nghị định đã được lưu tại: {output_json_file}")
    else:
        print(f"Lỗi: Không tìm thấy thư mục đầu vào tại '{folder_to_process}'. Vui lòng kiểm tra lại đường dẫn.")