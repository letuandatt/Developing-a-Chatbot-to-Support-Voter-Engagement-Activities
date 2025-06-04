import pdfplumber
import pandas as pd
import os
import json
import re
import subprocess
import shutil
import traceback

# --- Global Patterns (v28 - Added specific footer pattern) ---
HEADER_FOOTER_PATTERNS = [
    re.compile(r"^\s*CÔNG BÁO/Số", re.IGNORECASE),
    re.compile(r"CÔNG BÁO/Số\s*\d+\s*\+\s*\d+/Ngày", re.IGNORECASE),
    re.compile(r"^\s*Ký bởi: Cổng Thông tin điện tử Chính phủ"),
    re.compile(r"^\s*Email: thongtinchinhphu@chinhphu\.vn"),
    re.compile(r"^\s*Cơ quan: Văn phòng Chính phủ"),
    re.compile(r"^\s*Thời gian ký: \d{2}\.\d{2}\.\d{4}"),
    re.compile(r"^\s*\d+\s+CÔNG BÁO/Số", re.IGNORECASE),
    re.compile(r"^\s*CÔNG BÁO/Số.*\s+\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*Trang\s+\d+\s*/\s*\d+\s*$", re.IGNORECASE),
    re.compile(r"\f") # Form feed character
]

# Specific Footer Block to Remove (NEW v28)
SPECIFIC_FOOTER_PATTERN = re.compile(
    r"THỐNG ĐỐC\s+Nguyễn Văn Bình.*?Giá:\s*\d+\.\d+\s*đồng",
    re.IGNORECASE | re.DOTALL
)

# Section header regex (v28: No change)
ROMAN_NUMERAL_REGEX = re.compile(r"^\s*([IVXLCDM]+)\.\s+(.*)")
ARABIC_NUMERAL_REGEX = re.compile(r"^\s*(\d+)\.\s+(.*)")
SECTION_HEADER_REGEX_SIMPLE = re.compile(r"^\s*(?:[\dIVXLCDM]+)\.\s+") # For quick checks

END_MARKER_REGEX = re.compile(r"^\s*(KT\.|TM\.|TL\.)?\s*(THỦ TƯỚNG|BỘ TRƯỞNG)\s*$", re.IGNORECASE)
SIGNATURE_NAME_REGEX = re.compile(
    r"^\s*(Phạm Minh Chính|Nguyễn Xuân Phúc|Vũ Đức Đam|Nguyễn Tấn Dũng|Nguyễn Bắc Son)\s*$",
    re.IGNORECASE)
DOT_MARKER_REGEX = re.compile(r"^\s*\./\.\s*$")
CONTENT_START_REGEX = re.compile(r"^\s*(- |[a-z]\)\s+|\*\s+|\+\s+|\s{4,}[^-*+a-z0-9])", re.IGNORECASE)

# --- Issuer Mapping (v28: Retained) ---
ISSUER_MAPPING = {
    "CT-TTg": "THỦ TƯỚNG CHÍNH PHỦ",
    "CT-NHNN": "NGÂN HÀNG NHÀ NƯỚC VIỆT NAM",
    "CT-BTTTT": "BỘ THÔNG TIN TRUYỀN THÔNG",
    "CT-VPCP": "VĂN PHÒNG CHÍNH PHỦ"
}

def is_header_footer(line):
    """ Check if a line matches any header/footer pattern. (v27 logic retained) """
    line_stripped = line.strip()
    if not line_stripped:
        return False
    if any(pattern.search(line) for pattern in HEADER_FOOTER_PATTERNS):
         if SECTION_HEADER_REGEX_SIMPLE.match(line_stripped):
             return False
         if SIGNATURE_NAME_REGEX.match(line_stripped):
             return False
         if END_MARKER_REGEX.match(line_stripped):
             return False
         if DOT_MARKER_REGEX.match(line_stripped):
             return False
         return True
    return False

def read_pdf_with_pdftotext(file_path, output_txt_path="extracted_text_layout.txt"):
    """ Uses pdftotext to extract text with layout preserved. (v24 logic retained) """
    try:
        output_dir = os.path.dirname(output_txt_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        command = ["pdftotext", "-layout", file_path, output_txt_path]
        result = subprocess.run(command, capture_output=True, text=True, check=False, encoding="utf-8")
        if result.returncode != 0:
            stderr_lower = result.stderr.lower() if result.stderr else ""
            if "no such file or directory" in stderr_lower or "could not open file" in stderr_lower:
                raise FileNotFoundError(f"Lỗi: Không tìm thấy file PDF đầu vào: {file_path}")
            elif "command not found" in stderr_lower or "not recognized as an internal or external command" in stderr_lower:
                raise FileNotFoundError(
                    "Lỗi: Lệnh \"pdftotext\" không tìm thấy. Hãy đảm bảo poppler-utils đã được cài đặt.")
            else:
                raise Exception(f"Lỗi khi chạy pdftotext (code: {result.returncode}):\nStderr: {result.stderr}\nStdout: {result.stdout}")
        if not os.path.exists(output_txt_path) or os.path.getsize(output_txt_path) == 0:
            if result.returncode == 0:
                 try:
                     img_check_cmd = ["pdfimages", "-list", file_path]
                     img_check_res = subprocess.run(img_check_cmd, capture_output=True, text=True, check=False, encoding="utf-8")
                     if img_check_res.returncode == 0 and "page" in img_check_res.stdout:
                         print(f"Cảnh báo: pdftotext thành công nhưng file kết quả \"{output_txt_path}\" trống. PDF có thể là dạng ảnh.")
                     else:
                          print(f"Cảnh báo: pdftotext thành công nhưng file kết quả \"{output_txt_path}\" trống. PDF có thể bị lỗi hoặc không chứa text.")
                 except FileNotFoundError:
                      print(f"Cảnh báo: pdftotext thành công nhưng file kết quả \"{output_txt_path}\" trống. PDF có thể là dạng ảnh hoặc bị lỗi (không thể kiểm tra bằng pdfimages).")
                 except Exception as img_e:
                      print(f"Cảnh báo: pdftotext thành công nhưng file kết quả \"{output_txt_path}\" trống. PDF có thể là dạng ảnh hoặc bị lỗi (Lỗi kiểm tra ảnh: {img_e}).")
            else:
                raise Exception(
                    f"Lỗi không xác định: pdftotext không tạo được file kết quả hợp lệ.\nStderr: {result.stderr}\nStdout: {result.stdout}")
        return output_txt_path
    except FileNotFoundError as e:
        print(f"Lỗi FileNotFoundError trong read_pdf_with_pdftotext: {e}")
        raise e
    except Exception as e:
        print(f"Lỗi Exception trong read_pdf_with_pdftotext: {e}")
        raise Exception(f"Lỗi không xác định trong quá trình chạy pdftotext: {str(e)}")

def finalize_content(content_lines):
    """ Cleans, joins lines, removes specific footer, removes newlines, collapses whitespace. (REVISED v28) """
    if not content_lines:
        return ""

    # Filter out potential end markers first
    cleaned_lines = []
    found_end = False
    for line in content_lines:
        line_stripped = line.strip()
        if END_MARKER_REGEX.match(line_stripped) or \
           SIGNATURE_NAME_REGEX.match(line_stripped) or \
           DOT_MARKER_REGEX.match(line_stripped):
            found_end = True
            break
        cleaned_lines.append(line)

    # Join lines, then remove specific footer
    full_content = "\n".join(cleaned_lines).strip()
    full_content = SPECIFIC_FOOTER_PATTERN.sub("", full_content).strip() # Remove specific footer (NEW v28)

    # Replace newlines with spaces and collapse whitespace
    full_content = full_content.replace("\n", " ")
    full_content = re.sub(r"\s+", " ", full_content)

    return full_content.strip()

def load_metadata(metadata_file):
    """ Loads metadata from a JSONL file. (v25 logic retained) """
    metadata_dict = {}
    try:
        with open(metadata_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line)
                    so_hieu = record.get("Số hiệu")
                    if so_hieu:
                        metadata_dict[so_hieu] = record
                except json.JSONDecodeError as e:
                    print(f"Cảnh báo: Bỏ qua dòng không hợp lệ trong metadata: {line.strip()} - Lỗi: {e}")
    except FileNotFoundError:
        print(f"Lỗi: Không tìm thấy file metadata: {metadata_file}")
    except Exception as e:
        print(f"Lỗi khi đọc file metadata {metadata_file}: {e}")
    return metadata_dict

def get_issuer_from_so_hieu(so_hieu):
    """ Determines the issuing authority. (v25 logic retained) """
    if not so_hieu:
        return "Không xác định"
    for key, issuer in ISSUER_MAPPING.items():
        if key in so_hieu:
            return issuer
    if "CT-TTg" in so_hieu or "/CT-TTg" in so_hieu:
        return "THỦ TƯỚNG CHÍNH PHỦ"
    return "Không xác định"

def extract_document_info_from_text(text_content, metadata_lookup):
    """
    Trích xuất thông tin cấu trúc từ nội dung text, bổ sung từ metadata.
    (REVISED v28: Added continuation check for subsection splitting)
    """
    info = {
        "so_hieu": "",
        "loai_van_ban": "",
        "noi_ban_hanh": "",
        "ngay_ban_hanh": "",
        "tom_tat": "",
        "ten_van_ban": "",
        "ngay_hieu_luc": "",
        "noi_dung_muc": None
    }

    lines = text_content.split("\n")

    # --- Pre-filter headers/footers AND subsequent blank lines (v27 logic) ---
    indices_to_remove = set()
    i = 0
    while i < len(lines):
        if is_header_footer(lines[i]):
            indices_to_remove.add(i)
            if i + 1 < len(lines) and not lines[i+1].strip():
                indices_to_remove.add(i + 1)
                if i + 2 < len(lines) and not lines[i+2].strip():
                    indices_to_remove.add(i + 2)
                    i += 2
                else:
                    i += 1
        i += 1
    filtered_lines = [lines[idx] for idx in range(len(lines)) if idx not in indices_to_remove]
    # --- End Pre-filtering ---

    # --- Extract Metadata Fields (from filtered_lines) ---
    so_hieu_found = False
    date_found = False
    metadata_lines_indices_filtered = set()
    date_regex = re.compile(r"(Hà Nội|TP\. Hồ Chí Minh)[,\s]+ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})", re.IGNORECASE)
    so_hieu_regex = re.compile(r"Số:\s*(\S+)")

    for i, line in enumerate(filtered_lines):
        line_stripped = line.strip()
        if not line_stripped: continue
        match_so_hieu = so_hieu_regex.search(line)
        if match_so_hieu and not so_hieu_found:
            info["so_hieu"] = match_so_hieu.group(1).strip()
            so_hieu_found = True
            metadata_lines_indices_filtered.add(i)
        match_date = date_regex.search(line)
        if match_date and not date_found:
            day, month, year = match_date.group(2), match_date.group(3), match_date.group(4)
            info["ngay_ban_hanh"] = f"{int(day):02d}/{int(month):02d}/{year}"
            date_found = True
            metadata_lines_indices_filtered.add(i)
        if line_stripped == "THỦ TƯỚNG CHÍNH PHỦ": metadata_lines_indices_filtered.add(i)
        if line_stripped == "CHỈ THỊ":
             info["loai_van_ban"] = "CHỈ THỊ"
             metadata_lines_indices_filtered.add(i)
        if "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM" in line_stripped: metadata_lines_indices_filtered.add(i)
        if "Độc lập - Tự do - Hạnh phúc" in line_stripped:
             metadata_lines_indices_filtered.add(i)
             if i + 1 < len(filtered_lines) and "---o0o---" in filtered_lines[i+1]:
                  metadata_lines_indices_filtered.add(i+1)

    # --- Determine Issuer & Populate from Metadata (v25 logic retained) ---
    info["noi_ban_hanh"] = get_issuer_from_so_hieu(info["so_hieu"])
    if info["so_hieu"] in metadata_lookup:
        meta_record = metadata_lookup[info["so_hieu"]]
        info["ten_van_ban"] = meta_record.get("Tên văn bản", "")
        info["tom_tat"] = meta_record.get("Tóm tắt", "")
        info["ngay_hieu_luc"] = meta_record.get("Ngày hiệu lực", "")
        if meta_record.get("Ngày ban hành"): info["ngay_ban_hanh"] = meta_record.get("Ngày ban hành")
    else:
        print(f"Cảnh báo: Không tìm thấy Số hiệu ", info["so_hieu"], " trong metadata.")

    # --- Extract Content Sections (REVISED v28: Continuation Check) ---
    has_roman_numerals = False
    for line in filtered_lines:
        if ROMAN_NUMERAL_REGEX.match(line.strip()):
            has_roman_numerals = True
            break

    if has_roman_numerals:
        info["noi_dung_muc"] = []
    else:
        info["noi_dung_muc"] = {}

    current_main_section = None
    current_sub_section = None
    current_section_key = None
    current_content_lines = []
    current_title_lines = []
    is_collecting_title = False
    current_section_level = 0

    start_scan_index_filtered = 0
    if metadata_lines_indices_filtered:
        try:
            start_scan_index_filtered = max(metadata_lines_indices_filtered) + 1
        except ValueError:
            start_scan_index_filtered = 0
    while start_scan_index_filtered < len(filtered_lines) and not filtered_lines[start_scan_index_filtered].strip():
        start_scan_index_filtered += 1

    line_index = start_scan_index_filtered
    while line_index < len(filtered_lines):
        line = filtered_lines[line_index]
        line_stripped = line.strip()

        if line_index in metadata_lines_indices_filtered:
             line_index += 1
             continue

        match_roman = ROMAN_NUMERAL_REGEX.match(line)
        match_arabic = ARABIC_NUMERAL_REGEX.match(line)
        is_end_marker_line = END_MARKER_REGEX.match(line_stripped) or \
                             SIGNATURE_NAME_REGEX.match(line_stripped) or \
                             DOT_MARKER_REGEX.match(line_stripped)

        if is_collecting_title:
            # Logic for collecting title lines (largely unchanged from v26)
            is_content_start = CONTENT_START_REGEX.match(line)
            is_new_roman = ROMAN_NUMERAL_REGEX.match(line)
            is_new_arabic = ARABIC_NUMERAL_REGEX.match(line)
            is_new_section = is_new_roman or is_new_arabic
            is_blank_line = not line_stripped
            next_line_is_meaningful = False
            if is_blank_line and line_index + 1 < len(filtered_lines):
                 next_line_strip = filtered_lines[line_index+1].strip()
                 if next_line_strip:
                      next_line_is_meaningful = True

            stop_collecting_title = False
            if is_content_start or is_new_section or is_end_marker_line or (is_blank_line and next_line_is_meaningful):
                 stop_collecting_title = True

            if stop_collecting_title:
                full_title = " ".join([t.strip() for t in current_title_lines if t.strip()])
                full_title = re.sub(r"\s+", " ", full_title).strip()
                if has_roman_numerals:
                    if current_section_level == 1 and current_main_section:
                        num = current_main_section["_num"]
                        current_main_section["muc_chinh"] = f"{num}. {full_title}"
                    elif current_section_level == 2 and current_sub_section:
                        num = current_sub_section["_num"]
                        current_sub_section["muc_phu"] = f"{num}. {full_title}"
                else:
                    if current_section_key:
                        num = current_section_key["_num"]
                        current_section_key["key"] = f"{num}. {full_title}"
                        if current_section_key["key"] not in info["noi_dung_muc"]:
                             info["noi_dung_muc"][current_section_key["key"]] = ""
                is_collecting_title = False
                current_title_lines = []
                current_content_lines = []
                if is_new_section:
                    continue
                elif is_end_marker_line:
                    break
                elif is_content_start:
                    current_content_lines = [line]
            else:
                if line_stripped:
                    current_title_lines.append(line_stripped)

        else: # Not collecting title
            is_new_section_potential = match_roman or match_arabic

            if is_new_section_potential:
                # --- Check for continuation line (NEW v28) ---
                is_continuation = False
                # Apply check mainly for Arabic numerals when content exists
                if match_arabic and current_content_lines:
                    last_line_content = current_content_lines[-1].rstrip()
                    # Check if last line looks incomplete (no standard punctuation)
                    if not last_line_content.endswith(('.', ':', ';', ')', ']')):
                        potential_continuation_text = match_arabic.group(2).strip()
                        # Check if the text after the numeral looks like a continuation (starts lowercase, short)
                        if potential_continuation_text and (potential_continuation_text[0].islower() or len(potential_continuation_text.split()) <= 3):
                            # Avoid treating it as continuation if it's likely a new list item itself (e.g., starts with a, b, c)
                            if not re.match(r"^[a-z]\)\s", potential_continuation_text, re.IGNORECASE):
                                is_continuation = True
                                print(f"INFO: Treating line as continuation: {line_stripped}") # Debugging line

                if is_continuation:
                    # Treat as content continuation
                    current_content_lines.append(line)
                    # No need to increment line_index here, the main loop does it
                else:
                    # --- Original new section logic ---
                    # Finalize content of the PREVIOUS section
                    if current_content_lines:
                        finalized_prev_content = finalize_content(current_content_lines)
                        if has_roman_numerals:
                            if current_sub_section:
                                current_sub_section["noi_dung_phu"] = finalized_prev_content
                            elif current_main_section:
                                if "noi_dung_chinh" not in current_main_section or not current_main_section["noi_dung_chinh"]:
                                    current_main_section["noi_dung_chinh"] = finalized_prev_content
                        else:
                            if current_section_key and current_section_key.get("key"):
                                 if current_section_key["key"] in info["noi_dung_muc"] and not info["noi_dung_muc"][current_section_key["key"]]:
                                    info["noi_dung_muc"][current_section_key["key"]] = finalized_prev_content
                        current_content_lines = [] # Reset content lines

                    # Start the NEW section
                    initial_title_part = ""
                    section_number = ""
                    if match_roman and has_roman_numerals:
                        current_section_level = 1
                        section_number = match_roman.group(1)
                        initial_title_part = match_roman.group(2).strip()
                        current_main_section = {"_num": section_number, "muc_chinh": "", "noi_dung_chinh": "", "muc_con": []}
                        info["noi_dung_muc"].append(current_main_section)
                        current_sub_section = None
                    elif match_arabic:
                        section_number = match_arabic.group(1)
                        initial_title_part = match_arabic.group(2).strip()
                        if has_roman_numerals:
                            if current_main_section:
                                if not current_sub_section and ("noi_dung_chinh" not in current_main_section or not current_main_section["noi_dung_chinh"]):
                                    current_main_section["noi_dung_chinh"] = finalize_content(current_content_lines)
                                    current_content_lines = []
                                current_section_level = 2
                                current_sub_section = {"_num": section_number, "muc_phu": "", "noi_dung_phu": ""}
                                current_main_section["muc_con"].append(current_sub_section)
                            else:
                                 if not is_end_marker_line: current_content_lines.append(line)
                                 # Skip rest of new section logic for this line if no main section active
                                 line_index += 1
                                 continue
                        else:
                            current_section_level = 1
                            current_section_key = {"_num": section_number, "key": ""}

                    is_collecting_title = True
                    current_title_lines = [initial_title_part] if initial_title_part else []
                    # current_content_lines should be empty here

            elif is_end_marker_line:
                # Finalize content of the last section
                if current_content_lines:
                    finalized_last_content = finalize_content(current_content_lines)
                    if has_roman_numerals:
                        if current_sub_section:
                            current_sub_section["noi_dung_phu"] = finalized_last_content
                        elif current_main_section:
                             if "noi_dung_chinh" not in current_main_section or not current_main_section["noi_dung_chinh"]:
                                current_main_section["noi_dung_chinh"] = finalized_last_content
                    else:
                        if current_section_key and current_section_key.get("key"):
                             if current_section_key["key"] in info["noi_dung_muc"] and not info["noi_dung_muc"][current_section_key["key"]]:
                                info["noi_dung_muc"][current_section_key["key"]] = finalized_last_content
                current_content_lines = []
                break # End processing

            else:
                # Append content line
                current_content_lines.append(line)

        line_index += 1

    # --- Final Save Section Content (if loop finishes before end marker) ---
    if is_collecting_title:
        full_title = " ".join([t.strip() for t in current_title_lines if t.strip()])
        full_title = re.sub(r"\s+", " ", full_title).strip()
        if has_roman_numerals:
            if current_section_level == 1 and current_main_section:
                num = current_main_section["_num"]
                current_main_section["muc_chinh"] = f"{num}. {full_title}"
                current_main_section["noi_dung_chinh"] = finalize_content(current_content_lines)
            elif current_section_level == 2 and current_sub_section:
                num = current_sub_section["_num"]
                current_sub_section["muc_phu"] = f"{num}. {full_title}"
                current_sub_section["noi_dung_phu"] = finalize_content(current_content_lines)
        else:
             if current_section_key:
                num = current_section_key["_num"]
                key = f"{num}. {full_title}"
                if key not in info["noi_dung_muc"]:
                     info["noi_dung_muc"][key] = finalize_content(current_content_lines)

    elif current_content_lines:
         finalized_end_content = finalize_content(current_content_lines)
         if has_roman_numerals:
             if current_sub_section:
                 if "noi_dung_phu" not in current_sub_section or not current_sub_section["noi_dung_phu"]:
                     current_sub_section["noi_dung_phu"] = finalized_end_content
             elif current_main_section:
                 if "noi_dung_chinh" not in current_main_section or not current_main_section["noi_dung_chinh"]:
                     current_main_section["noi_dung_chinh"] = finalized_end_content
         else:
             if current_section_key and current_section_key.get("key"):
                  if current_section_key["key"] in info["noi_dung_muc"] and not info["noi_dung_muc"][current_section_key["key"]]:
                     info["noi_dung_muc"][current_section_key["key"]] = finalized_end_content

    # --- Clean up temporary keys and ensure structure --- (v24 logic retained)
    if has_roman_numerals:
        for main_sec in info.get("noi_dung_muc", []):
            if isinstance(main_sec, dict):
                 if "_num" in main_sec: del main_sec["_num"]
                 main_sec.setdefault("muc_chinh", "")
                 main_sec.setdefault("noi_dung_chinh", "")
                 main_sec.setdefault("muc_con", [])
                 for sub_sec in main_sec.get("muc_con", []):
                     if isinstance(sub_sec, dict):
                         if "_num" in sub_sec: del sub_sec["_num"]
                         sub_sec.setdefault("muc_phu", "")
                         sub_sec.setdefault("noi_dung_phu", "")
    else:
         if isinstance(info.get("noi_dung_muc"), dict):
             for key in list(info["noi_dung_muc"].keys()):
                 info["noi_dung_muc"].setdefault(key, "")

    return info


def save_to_json(documents, output_json_path):
    """
    Lưu danh sách thông tin tài liệu vào file JSON
    """
    try:
        output_dir = os.path.dirname(output_json_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(documents, f, ensure_ascii=False, indent=4)
        print(f"✅ Đã lưu dữ liệu vào file: {output_json_path}")
    except Exception as e:
        print(f"❌ Lỗi khi ghi file JSON: {str(e)}")


# --- Ví dụ sử dụng ---
if __name__ == "__main__":
    folder_path = "../data/CongThongTinDienTu/CongDien"
    output_json_path = "document_info_corrected.json"
    extracted_text_file = "extracted_text_layout.txt"
    medata_lookup = load_metadata("../data/CongThongTinDienTu/CongDien/metadata_congthongtindientu_congdien.jsonl")
    all_documents = []

    for file in os.listdir(folder_path):
        if file.endswith(".json") or not file.endswith(".pdf"):
            continue

        pdf_file_input = os.path.join(folder_path, file)

        if not os.path.exists(pdf_file_input):
            print(f"Lỗi: File PDF \"{pdf_file_input}\" không tồn tại!")
            continue

        try:
            print(f"\n--- Bắt đầu trích xuất thông tin văn bản từ \"{file}\" (phiên bản cuối cùng v9) ---")
            print(f"Đang trích xuất text từ \"{pdf_file_input}\" bằng pdftotext...")
            text_file_path = read_pdf_with_pdftotext(pdf_file_input, extracted_text_file)
            print(f"Đã trích xuất text vào: {text_file_path}")

            with open(text_file_path, "r", encoding="utf-8") as f:
                pdf_text_content = f.read()

            print("Đang phân tích nội dung text (xử lý tóm tắt, tiêu đề nhiều dòng, mục cuối, ngày ban hành v12)...")
            document_info = extract_document_info_from_text(pdf_text_content, medata_lookup)
            document_info["file_name"] = file  # Thêm tên file vào thông tin tài liệu

            print("\n=== KẾT QUẢ TRÍCH XUẤT THÔNG TIN (đã sửa lỗi tóm tắt, ngày ban hành v9) ===")
            print("Tên file:", document_info.get("file_name", "Không tìm thấy"))
            print("Số hiệu:", document_info.get("so_hieu", "Không tìm thấy"))
            print("Loại văn bản:", document_info.get("loai_van_ban", "Không tìm thấy"))
            print("Nơi ban hành:", document_info.get("noi_ban_hanh", "Không tìm thấy"))
            print("Ngày ban hành:", document_info.get("ngay_ban_hanh", "Không tìm thấy"))
            print("Tóm tắt:", document_info.get("tom_tat", "Không tìm thấy"))
            print("\nNội dung theo mục (đã loại bỏ xuống dòng):")
            noi_dung_muc = document_info.get("noi_dung_muc")
            if noi_dung_muc:
                if isinstance(noi_dung_muc, dict): # Flat structure (Arabic numerals only)
                    print("DEBUG: Structure type: Flat (dict)")
                    if not noi_dung_muc:
                         print("Nội dung mục rỗng.")
                    else:
                        for muc, content in noi_dung_muc.items():
                            print(f"\n--- {muc} ---")
                            print(content[:500] + ("..." if len(content) > 500 else ""))
                elif isinstance(noi_dung_muc, list): # Nested structure (Roman numerals present)
                    print("DEBUG: Structure type: Nested (list)")
                    if not noi_dung_muc:
                         print("Nội dung mục rỗng.")
                    else:
                        for main_section in noi_dung_muc:
                            print(f"\n--- {main_section.get('muc_chinh', 'Mục chính không có tiêu đề')} ---")
                            print(main_section.get('noi_dung_chinh', '')[:500] + ("..." if len(main_section.get('noi_dung_chinh', '')) > 500 else ""))
                            if main_section.get("muc_con"):
                                for sub_section in main_section["muc_con"]:
                                    print(f"\n  --- {sub_section.get('muc_phu', 'Mục phụ không có tiêu đề')} ---")
                                    print(f"  {sub_section.get('noi_dung_phu', '')[:498]}" + ("..." if len(sub_section.get('noi_dung_phu', '')) > 498 else ""))
                else:
                    print("DEBUG: Unknown structure type for noi_dung_muc:", type(noi_dung_muc))
            else:
                print("Không trích xuất được nội dung theo mục.")

            all_documents.append(document_info)

        except Exception as e:
            print(f"\n--- Đã xảy ra lỗi trong quá trình xử lý file \"{file}\" ---")
            print(str(e))

    if all_documents:
        print(f"\nĐang lưu kết quả của tất cả tài liệu vào file: {output_json_path}")
        save_to_json(all_documents, output_json_path)
        print("Đã lưu thành công!")
    else:
        print("\nKhông có tài liệu nào được xử lý thành công để lưu vào JSON.")