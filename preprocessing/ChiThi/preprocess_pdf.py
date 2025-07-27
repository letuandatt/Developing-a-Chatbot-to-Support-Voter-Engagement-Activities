import os
import re
import json
import fitz  # PyMuPDF
from typing import Dict, List, Tuple
import logging


class PatternConfig:
    """Lớp lưu trữ các mẫu regex và cấu hình liên quan."""
    HEADER_FOOTER_PATTERNS = [
        re.compile(r"^\s*CÔNG BÁO/Số", re.IGNORECASE),
        re.compile(r"CÔNG\s*BÁO/Số\s*\d+\s*\+\s*\d+/[\s*Ngày]*", re.IGNORECASE),
        re.compile(r"^\s*\d+\s+CÔNG BÁO/Số", re.IGNORECASE),
        re.compile(r"^\s*Trang\s+\d+\s*/\s*\d+\s*$", re.IGNORECASE),
        re.compile(r"^\s*\d+\s*$"),
    ]

    SIGNATURE_PATTERNS = [
        re.compile(r"^\s*(KT\.|TM\.|TL\.)?\s*(THỦ TƯỚNG|BỘ TRƯỞNG|THỐNG ĐỐC)\s*$", re.IGNORECASE),
        re.compile(
            r"^\s*(Phạm Minh Chính|Nguyễn Xuân Phúc|Vũ Đức Đam|Nguyễn Tấn Dũng|Nguyễn Bắc Son|Nguyễn Văn Bình|Nguyễn Sinh Hùng)\s*$",
            re.IGNORECASE),
        re.compile(r"^\s*\./\.\s*$"),
    ]

    SECTION_PATTERNS = {
        "chuong": re.compile(r"^\s*([IVXLCDM]+)\.\s*(.*)", re.IGNORECASE),
        "muc": re.compile(r"^\s*(\d+)\.\s+([^\d].*)"),
        "khoan": re.compile(r"^\s*([a-zđ])\)\s*(.*)", re.IGNORECASE),
        "diem": re.compile(r"^\s*-\s+(.*)", re.IGNORECASE),
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
        re.compile(r"^\s*VĂN PHÒNG CHÍNH PHỦ XUẤT BẢN\s*$", re.IGNORECASE),
        re.compile(r"^\s*Địa chỉ:\s*$", re.IGNORECASE),
        re.compile(r"^\s*Số 1, Hoàng Hoa Thám, Ba Đình, Hà Nội\s*$", re.IGNORECASE),
        re.compile(r"^\s*Điện thoại: 080.44946 – 080.44417\s*$", re.IGNORECASE),
        re.compile(r"^\s*Fax:\s*$", re.IGNORECASE),
        re.compile(r"^\s*080.44517\s*$", re.IGNORECASE),
        re.compile(r"^\s*Email:\s*$", re.IGNORECASE),
        re.compile(r"^\s*congbao@chinhphu.vn\s*$", re.IGNORECASE),
        re.compile(r"^\s*Website:\s*$", re.IGNORECASE),
        re.compile(r"^\s*http://congbao.chinhphu.vn\s*$", re.IGNORECASE),
        re.compile(r"^\s*In tại:\s*$", re.IGNORECASE),
        re.compile(r"^\s*Xí nghiệp Bản đồ 1 - Bộ Quốc phòng\s*$", re.IGNORECASE),
        re.compile(r"^\s*Giá:\s*\d{1,3}(?:\.\d{3})*\s*đồng", re.IGNORECASE),
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


class Logger:
    """Lớp quản lý logging."""
    def __init__(self, log_file: str = "preprocess_pdf.log"):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            filename=log_file,
        )

    def info(self, message: str):
        logging.info(message)

    def error(self, message: str):
        logging.error(message)


class TextCleaner:
    """Lớp làm sạch văn bản và kiểm tra các dòng cần bỏ qua."""
    def __init__(self):
        self.patterns = PatternConfig()

    def remove_content_after_end_marker(self, text):
        """
        Loại bỏ tất cả nội dung sau dấu ./.
        """
        # Tìm vị trí của dấu ./. (có thể có nhiều cách viết)
        end_markers = ['./.', '. / .', './']

        for marker in end_markers:
            if marker in text:
                # Cắt text tại vị trí marker và chỉ lấy phần trước
                text = text.split(marker)[0] + marker
                break

        return text

    def clean_text(self, text: str) -> str:
        """Làm sạch văn bản, chuẩn hóa khoảng trắng và ký tự."""
        text = self.remove_content_after_end_marker(text)
        text = re.sub(r"\s+", " ", text.strip())
        text = re.sub(r"[\n\r]+", "\n", text)
        return text

    def is_header_footer(self, line: str) -> bool:
        """Kiểm tra xem dòng có phải là header/footer không."""
        line = line.strip()
        if not line:
            return False
        return any(pattern.search(line) for pattern in self.patterns.HEADER_FOOTER_PATTERNS)

    def is_signature(self, line: str) -> bool:
        """Kiểm tra xem dòng có phải là chữ ký hoặc kết thúc văn bản không."""
        line = line.strip()
        return any(pattern.match(line) for pattern in self.patterns.SIGNATURE_PATTERNS)

    def is_ignore_line(self, line: str) -> bool:
        """Kiểm tra xem dòng có phải là dòng cần bỏ qua không."""
        line = line.strip()
        if not line:
            return True
        return any(pattern.match(line) for pattern in self.patterns.IGNORE_PATTERNS)

    def is_bold_span(self, span: dict) -> bool:
        """Kiểm tra xem span có định dạng in đậm không."""
        font = span.get("font", "").lower()
        return (
            "timesnewromanps-boldmt" in font
            or "bold" in font
            or "-bd" in font
            or "ps-bold" in font
            or "timesnewroman,bold" in font
        )


class PDFReader:
    """Lớp đọc file PDF và trích xuất các block văn bản."""
    def __init__(self, logger: Logger):
        self.logger = logger
        self.text_cleaner = TextCleaner()

    def read_pdf(self, file_path: str) -> List[Dict]:
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
                                text = self.text_cleaner.clean_text(span["text"])
                                if text and not self.text_cleaner.is_ignore_line(text):
                                    blocks.append({
                                        "text": text,
                                        "font": span["font"],
                                        "size": span["size"],
                                        "flags": span["flags"],
                                        "bbox": span["bbox"],
                                        "page": page.number
                                    })
            doc.close()
            self.logger.info(f"Đã đọc {len(blocks)} blocks từ {file_path}")
            return blocks
        except Exception as e:
            self.logger.error(f"Lỗi đọc PDF {file_path}: {e}")
            raise


class MetadataExtractor:
    """Lớp trích xuất metadata từ các block văn bản."""
    def __init__(self, logger: Logger):
        self.logger = logger
        self.patterns = PatternConfig()
        self.text_cleaner = TextCleaner()

    def get_issuer(self, so_hieu: str) -> str:
        """Xác định nơi ban hành dựa trên số hiệu."""
        if not so_hieu:
            return "Không xác định"
        for key, issuer in self.patterns.ISSUER_MAP.items():
            if key in so_hieu:
                return issuer
        if "CP" in so_hieu: return "CHÍNH PHỦ"
        if "TTg" in so_hieu: return "THỦ TƯỚNG CHÍNH PHỦ"
        if "QH" in so_hieu: return "QUỐC HỘI"
        if "UBTVQH" in so_hieu: return "ỦY BAN THƯỜNG VỤ QUỐC HỘI"
        if "NNHN" in so_hieu: return "NGÂN HÀNG NHÀ NƯỚC"
        return "Không xác định"

    def extract_metadata(self, blocks: List[Dict], file_name: str) -> Dict:
        """Trích xuất metadata từ các block."""
        metadata = {
            "so_hieu": "",
            "loai_van_ban": "",
            "noi_ban_hanh": "",
            "ngay_ban_hanh": "",
            "ngay_hieu_luc": "",
            "ten_van_ban": "",
            "trich_yeu": "",
            "nguoi_ky": "",
            "chuc_vu_nguoi_ky": "",
            "file_name": file_name
        }

        type_found = False
        type_block_index = -1

        # Trích xuất số hiệu, loại văn bản, ngày ban hành
        for i, block in enumerate(blocks):
            line = block["text"].strip()
            if not line:
                continue

            if match := self.patterns.METADATA_PATTERNS["type"].match(line):
                if not metadata["loai_van_ban"]:
                    metadata["loai_van_ban"] = match.group(1).upper()
                    type_found = True
                    type_block_index = i
                    if metadata["so_hieu"]:
                        metadata["ten_van_ban"] = f"{match.group(1).title()} {metadata["so_hieu"]}"
                continue

            if match := self.patterns.METADATA_PATTERNS["so_hieu"].search(line):
                if not metadata["so_hieu"]:
                    metadata["so_hieu"] = match.group(1)
                    metadata["noi_ban_hanh"] = self.get_issuer(match.group(1))
                    if metadata["loai_van_ban"]:
                        metadata["ten_van_ban"] = f"{metadata["loai_van_ban"].title()} {match.group(1)}"
                continue

            input_file = "../../data/CongThongTinDienTu/ChiThi/metadata_congthongtindientu_chithi.jsonl"
            with open(input_file, 'r', encoding='utf-8') as f:
                for line in f:
                    data = json.loads(line)

                    if data["Số hiệu"] == metadata["so_hieu"]:
                        metadata["ngay_ban_hanh"] = data["Ngày ban hành"]
                        metadata["ngay_hieu_luc"] = data["Ngày hiệu lực"]
                        break

        # Trích xuất trích yếu
        if type_found and type_block_index != -1:
            trich_yeu_parts = []
            j = type_block_index + 1
            max_lookahead = 15
            count_lookahead = 0

            while j < len(blocks) and count_lookahead < max_lookahead:
                block = blocks[j]
                line = block["text"].strip()
                if not line or self.text_cleaner.is_header_footer(line) or self.text_cleaner.is_signature(line) or any(
                        p.match(line) for p in self.patterns.SECTION_PATTERNS.values()):
                    break
                if self.text_cleaner.is_ignore_line(line):
                    j += 1
                    count_lookahead += 1
                    continue
                if self.text_cleaner.is_bold_span(block):
                    trich_yeu_parts.append(line)
                j += 1
                count_lookahead += 1

            metadata["trich_yeu"] = " ".join(trich_yeu_parts).strip()
            # if not metadata["ten_van_ban"] and metadata["trich_yeu"]:
            #     metadata["ten_van_ban"] = metadata["trich_yeu"]

        # Trích xuất chữ ký
        scan_start_idx = max(0, len(blocks) - 50)
        potential_signatory_lines = []
        for block in blocks[scan_start_idx:]:
            line = block["text"].strip()
            if not line or self.text_cleaner.is_header_footer(line) or self.text_cleaner.is_ignore_line(line):
                continue
            potential_signatory_lines.append(line)

        signatory_name = ""
        signatory_title = ""
        title_pattern = re.compile(
            r"^(KT\.|TM\.|TL\.)?\s*(THỦ TƯỚNG|BỘ TRƯỞNG|THỐNG ĐỐC|CHỦ TỊCH QUỐC HỘI|CHỦ TỊCH NƯỚC|CHỦ TỊCH HỘI ĐỒNG NHÂN DÂN|CHỦ TỊCH ỦY BAN NHÂN DÂN|PHÓ THỦ TƯỚNG|PHÓ CHỦ TỊCH QUỐC HỘI|PHÓ CHỦ TỊCH NƯỚC|PHÓ CHỦ TỊCH HỘI ĐỒNG NHÂN DÂN|PHÓ CHỦ TỊCH ỦY BAN NHÂN DÂN)\s*$",
            re.IGNORECASE)
        name_pattern = re.compile(
            r"^[A-ZĐ][a-zđàáạảãăắằặẳẵâấầậẩẫèéẹẻẽêếềệểễìíịỉĩòóọỏõôốồộổỗơớờợởỡùúụủũưứừựửữýỳỵỷỹ]+\s+([A-ZĐ][a-zđàáạảãăắằặẳẵâấầậẩẫèéẹẻẽêếềệểễìíịỉĩòóọỏõôốồộổỗơớờợởỡùúụủũưứừựửữýỳỵỷỹ]+\s*){1,4}$",
            re.IGNORECASE)

        for line in reversed(potential_signatory_lines):
            title_match = title_pattern.match(line)
            if title_match and not signatory_title:
                signatory_title = title_match.group(2).strip().upper()
                continue
            name_match = name_pattern.match(line)
            if name_match and not signatory_name and 5 <= len(line) <= 50:
                signatory_name = line.strip()
                if signatory_title:
                    break

        metadata["chuc_vu_nguoi_ky"] = signatory_title
        metadata["nguoi_ky"] = signatory_name

        return metadata


class ContentParser:
    """Lớp phân tích nội dung và tổ chức thành cấu trúc phân cấp."""
    def __init__(self, logger: Logger):
        self.logger = logger
        self.patterns = PatternConfig()
        self.text_cleaner = TextCleaner()

    def collect_title_lines(self, lines: List[str], start_idx: int, current_line: str) -> Tuple[str, int]:
        """Gộp các dòng tiếp theo để tạo tiêu đề hoàn chỉnh."""
        title_parts = [current_line.strip()]
        i = start_idx + 1
        while i < len(lines):
            next_line = lines[i].strip()
            if not next_line or self.text_cleaner.is_header_footer(next_line) or self.text_cleaner.is_signature(next_line):
                i += 1
                continue
            if any(p.match(next_line) for p in self.patterns.SECTION_PATTERNS.values()) or not next_line.strip():
                break
            title_parts.append(next_line)
            i += 1
        return " ".join(title_parts).strip(), i

    def parse_content(self, blocks: List[Dict], file_name: str) -> Dict:
        """Phân tích nội dung từ các block thành cấu trúc phân cấp."""
        result = {"chuong": []}
        cleaned_lines = [b["text"] for b in blocks if not self.text_cleaner.is_header_footer(b["text"])]

        current_chapter = None
        current_section = None
        current_subsection = None
        current_points = []
        content_started = False
        i = 0

        while i < len(cleaned_lines):
            line = cleaned_lines[i].strip()
            if not line:
                i += 1
                continue
            if not content_started and any(
                    p.match(line) for p in [self.patterns.SECTION_PATTERNS["chuong"], self.patterns.SECTION_PATTERNS["muc"]]):
                content_started = True
                break
            i += 1

        if not content_started:
            self.logger.info(f"Warning: Không xác định được điểm bắt đầu nội dung rõ ràng cho {file_name}")
            i = 0

        while i < len(cleaned_lines):
            line = cleaned_lines[i].strip()
            if not line:
                i += 1
                continue

            if self.text_cleaner.is_header_footer(line) or self.text_cleaner.is_ignore_line(line):
                i += 1
                continue

            if self.text_cleaner.is_signature(line):
                if current_points:
                    if current_subsection:
                        current_subsection["diem"] = current_points
                    elif current_section:
                        current_section["khoan"].append({"ten_khoan": "", "tieu_de": "", "diem": current_points})
                break

            if match := self.patterns.SECTION_PATTERNS["chuong"].match(line):
                if current_points:
                    if current_subsection:
                        current_subsection["diem"] = current_points
                    elif current_section:
                        current_section["khoan"].append({"ten_khoan": "", "tieu_de": "", "diem": current_points})
                    current_points = []
                title, new_i = self.collect_title_lines(cleaned_lines, i, match.group(2))
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

            if match := self.patterns.SECTION_PATTERNS["muc"].match(line):
                if current_points:
                    if current_subsection:
                        current_subsection["diem"] = current_points
                    elif current_section:
                        current_section["khoan"].append({"ten_khoan": "", "tieu_de": "", "diem": current_points})
                    current_points = []
                title, new_i = self.collect_title_lines(cleaned_lines, i, match.group(2))
                current_section = {
                    "ten_muc": f"Mục {match.group(1)}",
                    "tieu_de": title,
                    "khoan": []
                }
                if current_chapter:
                    current_chapter["muc"].append(current_section)
                else:
                    result["chuong"].append({
                        "ten_chuong": "",
                        "tieu_de": "",
                        "muc": [current_section]
                    })
                    current_chapter = result["chuong"][-1]
                current_subsection = None
                i = new_i
                continue

            if match := self.patterns.SECTION_PATTERNS["khoan"].match(line):
                if current_points:
                    if current_subsection:
                        current_subsection["diem"] = current_points
                    elif current_section:
                        current_section["khoan"].append({"ten_khoan": "", "tieu_de": "", "diem": current_points})
                    current_points = []
                title, new_i = self.collect_title_lines(cleaned_lines, i, match.group(2))
                current_subsection = {
                    "ten_khoan": f"Khoản {match.group(1)}",
                    "tieu_de": title,
                    "diem": []
                }
                if current_section:
                    current_section["khoan"].append(current_subsection)
                elif current_chapter:
                    if not current_chapter["muc"]:
                        current_chapter["muc"].append({"ten_muc": "", "tieu_de": "", "khoan": []})
                    current_chapter["muc"][-1]["khoan"].append(current_subsection)
                else:
                    result["chuong"].append({
                        "ten_chuong": "",
                        "tieu_de": "",
                        "muc": [{"ten_muc": "", "tieu_de": "", "khoan": [current_subsection]}]
                    })
                    current_chapter = result["chuong"][-1]
                    current_section = current_chapter["muc"][-1]
                i = new_i
                continue

            if match := self.patterns.SECTION_PATTERNS["diem"].match(line):
                current_points.append(match.group(1).strip())
                i += 1
                continue

            if content_started:
                if current_points:
                    current_points[-1] = f"{current_points[-1]} {line}"
                elif current_subsection:
                    current_subsection["tieu_de"] = f"{current_subsection["tieu_de"]} {line}"
                elif current_section:
                    current_section["tieu_de"] = f"{current_section["tieu_de"]} {line}"
                elif current_chapter:
                    current_chapter["tieu_de"] = f"{current_chapter["tieu_de"]} {line}"

            i += 1

        if current_points:
            if current_subsection:
                current_subsection["diem"] = current_points
            elif current_section:
                if not current_section["khoan"]:
                    current_section["khoan"].append({"ten_khoan": "", "tieu_de": "", "diem": []})
                current_section["khoan"][-1]["diem"] = current_points
            elif current_chapter:
                if not current_chapter["muc"]:
                    current_chapter["muc"].append(
                        {"ten_muc": "", "tieu_de": "", "khoan": [{"ten_khoan": "", "tieu_de": "", "diem": []}]})
                elif not current_chapter["muc"][-1]["khoan"]:
                    current_chapter["muc"][-1]["khoan"].append({"ten_khoan": "", "tieu_de": "", "diem": []})
                current_chapter["muc"][-1]["khoan"][-1]["diem"] = current_points

        return result


class PDFProcessor:
    """Lớp điều phối quá trình xử lý PDF."""
    def __init__(self):
        self.logger = Logger()
        self.pdf_reader = PDFReader(self.logger)
        self.metadata_extractor = MetadataExtractor(self.logger)
        self.content_parser = ContentParser(self.logger)

    def process_pdf(self, pdf_path: str, file_name: str) -> Dict:
        """Xử lý một file PDF và trả về cấu trúc dữ liệu."""
        blocks = self.pdf_reader.read_pdf(pdf_path)
        if not blocks:
            self.logger.info(f"Cảnh báo: Không trích xuất được block nào từ {file_name}")
            return {}

        metadata = self.metadata_extractor.extract_metadata(blocks, file_name)
        content = self.content_parser.parse_content(blocks, file_name)
        return {**metadata, **content}


class MainProcessor:
    """Lớp xử lý toàn bộ thư mục chứa các file PDF."""
    def __init__(self):
        self.logger = Logger()
        self.pdf_processor = PDFProcessor()

    def save_to_json(self, data: List[Dict], output_path: str):
        """Lưu danh sách tài liệu vào file JSON."""
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        self.logger.info(f"Đã lưu vào: {output_path}")

    def process_folder(self, folder_path: str, output_json: str):
        """Xử lý tất cả file PDF trong thư mục."""
        if not os.path.isdir(folder_path):
            self.logger.error(f"Lỗi: Thư mục không tồn tại: {folder_path}")
            return

        documents = []
        for file in os.listdir(folder_path):
            if not file.lower().endswith(".pdf"):
                continue
            pdf_path = os.path.join(folder_path, file)
            try:
                self.logger.info(f"Đang xử lý: {file}")
                doc_info = self.pdf_processor.process_pdf(pdf_path, file)
                if doc_info.get("chuong"):
                    documents.append(doc_info)
            except Exception as e:
                self.logger.error(f"Lỗi xử lý {file}: {e}")
                import traceback
                traceback.print_exc()

        if documents:
            self.save_to_json(documents, output_json)
        else:
            self.logger.info("Không có tài liệu nào được xử lý thành công.")


if __name__ == "__main__":
    main_processor = MainProcessor()
    folder_to_process = "../../data/CongThongTinDienTu"
    folder_to_save = "../../preprocessing/"

    for folder_name in os.listdir(folder_to_process):
        if folder_name.endswith("zip"):
            continue
        if folder_name == "ChiThi":
            folder_path = os.path.join(folder_to_process, folder_name)
            output_folder_to_save = os.path.join(folder_to_save, folder_name)
            os.makedirs(output_folder_to_save, exist_ok=True)
            output_file_to_save = os.path.join(output_folder_to_save, f"processed_documents_{folder_name.lower()}.json")
            main_processor.process_folder(folder_path, output_file_to_save)



