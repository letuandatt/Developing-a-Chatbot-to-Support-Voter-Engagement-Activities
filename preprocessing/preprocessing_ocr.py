from io import BytesIO
import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import fitz  # PyMuPDF
from vietocr.tool.predictor import Predictor
from vietocr.tool.config import Cfg
import os
import matplotlib.pyplot as plt
import re
import json
from datetime import datetime
from collections import defaultdict, Counter
import logging

# Thiết lập logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def extract_images_from_pdf_pages(pdf_path, start_page=0, end_page=None, dpi=400):
    """
    Chuyển PDF thành ảnh với DPI cao cho OCR
    """
    try:
        doc = fitz.open(pdf_path)
        images = []

        if end_page is None:
            end_page = len(doc)

        for page_num in range(start_page, min(end_page, len(doc))):
            page = doc.load_page(page_num)
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("ppm")
            img = Image.open(BytesIO(img_data))

            images.append({
                'page_num': page_num + 1,
                'image': img,
                'width': img.width,
                'height': img.height
            })

        doc.close()
        return images
    except Exception as e:
        logger.error(f"Lỗi khi trích xuất ảnh từ PDF: {e}")
        return []

def advanced_preprocess_legal_document(image, debug_dir="debug_images"):
    """
    Tiền xử lý mạnh nhất cho tài liệu pháp lý, tối ưu cho VietOCR
    """
    os.makedirs(debug_dir, exist_ok=True)

    if isinstance(image, Image.Image):
        img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    else:
        img = image.copy()

    # 1. Chuyển sang grayscale
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()
    cv2.imwrite(os.path.join(debug_dir, "1_grayscale.png"), gray)

    # 2. Khử nhiễu mạnh
    denoised = cv2.bilateralFilter(gray, 11, 100, 100)
    cv2.imwrite(os.path.join(debug_dir, "2_denoised.png"), denoised)

    # 3. Tăng độ tương phản với CLAHE
    clahe = cv2.createCLAHE(clipLimit=4.5, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)
    cv2.imwrite(os.path.join(debug_dir, "3_enhanced.png"), enhanced)

    # 4. Làm mượt nhẹ
    smoothed = cv2.GaussianBlur(enhanced, (3, 3), 0)
    cv2.imwrite(os.path.join(debug_dir, "4_smoothed.png"), smoothed)

    # 5. Ngưỡng thích nghi
    thresh = cv2.adaptiveThreshold(
        smoothed, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 7, 3
    )
    cv2.imwrite(os.path.join(debug_dir, "5_threshold.png"), thresh)

    # 6. Làm sạch nhiễu
    kernel_noise = np.ones((2, 2), np.uint8)
    cleaned = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_noise)
    cv2.imwrite(os.path.join(debug_dir, "6_cleaned.png"), cleaned)

    # 7. Làm đậm văn bản
    kernel_dilate = np.ones((1, 1), np.uint8)
    cleaned = cv2.dilate(cleaned, kernel_dilate, iterations=2)
    cv2.imwrite(os.path.join(debug_dir, "7_dilated.png"), cleaned)

    # 8. Làm mỏng lại
    kernel_erode = np.ones((1, 1), np.uint8)
    cleaned = cv2.erode(cleaned, kernel_erode, iterations=1)
    cv2.imwrite(os.path.join(debug_dir, "8_eroded.png"), cleaned)

    return cleaned

def preprocess_with_pil_enhancement(image, debug_dir="debug_images"):
    """
    Tiền xử lý PIL tối ưu cho VietOCR
    """
    os.makedirs(debug_dir, exist_ok=True)

    if isinstance(image, np.ndarray):
        if len(image.shape) == 3:
            pil_img = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        else:
            pil_img = Image.fromarray(image)
    else:
        pil_img = image

    pil_img.save(os.path.join(debug_dir, "pil_original.png"))

    # Tăng độ sắc nét
    enhancer = ImageEnhance.Sharpness(pil_img)
    sharpened = enhancer.enhance(2.5)
    sharpened.save(os.path.join(debug_dir, "pil_sharpened.png"))

    # Tăng độ tương phản
    enhancer = ImageEnhance.Contrast(sharpened)
    contrasted = enhancer.enhance(1.8)
    contrasted.save(os.path.join(debug_dir, "pil_contrasted.png"))

    # Làm mịn nhẹ
    smoothed = contrasted.filter(ImageFilter.SMOOTH)
    smoothed.save(os.path.join(debug_dir, "pil_smoothed.png"))

    return smoothed

def ocr_with_vietocr(image, detector, page_num, debug_dir="debug_images"):
    """
    Thực hiện OCR với VietOCR, kiểm tra chất lượng văn bản
    """
    os.makedirs(debug_dir, exist_ok=True)

    try:
        text = detector.predict(image)
        if len(text.strip()) < 10:
            logger.warning(f"Trang {page_num}: Văn bản quá ngắn ({len(text)} ký tự)")
            return text, "vietocr_short"
        if not any(c.isalnum() for c in text):
            logger.warning(f"Trang {page_num}: Văn bản không chứa ký tự chữ/số")
            return text, "vietocr_invalid"
        return text, "vietocr"
    except Exception as e:
        logger.error(f"Trang {page_num}: VietOCR thất bại ({str(e)})")
        if isinstance(image, Image.Image):
            image.save(os.path.join(debug_dir, f"page_{page_num}_failed.png"))
        return "", "vietocr_failed"


class LegalDocumentInfoExtractor:
    """
    Trích xuất thông tin có cấu trúc từ tài liệu pháp lý
    """

    def __init__(self):
        # Patterns cho các thông tin pháp lý
        self.patterns = {
            'law_number': [
                r'(?:Luật|Bộ luật|Nghị định|Thông tư|Quyết định)\s+(?:số\s*)?(\d+/\d+/[A-Z-]+)',
                r'(\d+/\d+/QH\d+)',
                r'(\d+/\d+/NĐ-CP)',
                r'(\d+/\d+/TT-[A-Z]+)'
            ],
            'dates': [
                r'ngày\s+(\d{1,2}/\d{1,2}/\d{4})',
                r'(\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4})',
                r'ban hành\s+(?:ngày\s+)?(\d{1,2}/\d{1,2}/\d{4})'
            ],
            'chapters': [
                r'CHƯƠNG\s+([IVX\d]+)[\s\n]+([^\n]+)',
                r'Chương\s+(\d+)[\s\.:]+([^\n]+)'
            ],
            'articles': [
                r'Điều\s+(\d+)[\s\.:]+([^\n]+)',
                r'ĐIỀU\s+(\d+)[\s\n]+([^\n]+)'
            ],
            'sections': [
                r'Mục\s+(\d+)[\s\.:]+([^\n]+)',
                r'Tiết\s+(\d+)[\s\.:]+([^\n]+)'
            ],
            'subjects': [
                r'(?:điều chỉnh|quy định về|liên quan đến)\s+([^\n.;]+)',
                r'Phạm vi điều chỉnh[:\n\s]*([^\n]+)'
            ],
            'effective_date': [
                r'có hiệu lực[^\d]*(\d{1,2}/\d{1,2}/\d{4})',
                r'thực hiện[^\d]*(\d{1,2}/\d{1,2}/\d{4})'
            ]
        }

    def extract_law_info(self, text):
        """
        Trích xuất thông tin cơ bản về luật
        """
        info = {
            'law_numbers': [],
            'dates': [],
            'title': '',
            'chapters': [],
            'articles': [],
            'sections': [],
            'subjects': [],
            'effective_dates': []
        }

        # Trích xuất số luật
        for pattern in self.patterns['law_number']:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                info['law_numbers'].append(match.group(1))

        # Trích xuất ngày tháng
        for pattern in self.patterns['dates']:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                info['dates'].append(match.group(1))

        # Trích xuất chương
        for pattern in self.patterns['chapters']:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                info['chapters'].append({
                    'number': match.group(1),
                    'title': match.group(2).strip()
                })

        # Trích xuất điều
        for pattern in self.patterns['articles']:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                info['articles'].append({
                    'number': match.group(1),
                    'title': match.group(2).strip()
                })

        # Trích xuất tiêu đề tài liệu (thường ở đầu)
        title_patterns = [
            r'(BỘ LUẬT[^\n]+)',
            r'(LUẬT[^\n]+)',
            r'(NGHỊ ĐỊNH[^\n]+)',
            r'(THÔNG TƯ[^\n]+)',
            r'(CHỈ THỊ[^\n]+)',
            r'(HIẾN PHÁP[^\n]+)',
            r'(QUYẾT ĐỊNH[^\n]+)',
            r'(PHÁP LỆNH[^\n]+)',
            r'(CHỈ THỊ[^\n]+)',
        ]

        for pattern in title_patterns:
            match = re.search(pattern, text[:500], re.IGNORECASE)
            if match:
                info['title'] = match.group(1).strip()
                break

        # Loại bỏ trùng lặp
        info['law_numbers'] = list(set(info['law_numbers']))
        info['dates'] = list(set(info['dates']))

        return info

    def extract_article_content(self, text):
        """
        Trích xuất nội dung chi tiết của từng điều
        """
        articles = []

        # Pattern để tìm điều và nội dung
        article_pattern = r'Điều\s+(\d+)[\s\.:]+([^\n]+)(?:\n((?:(?!Điều\s+\d+)[\s\S])*?))?'

        matches = re.finditer(article_pattern, text, re.IGNORECASE | re.DOTALL)

        for match in matches:
            article_num = match.group(1)
            article_title = match.group(2).strip()
            article_content = match.group(3).strip() if match.group(3) else ""

            # Trích xuất các khoản trong điều
            clauses = []
            if article_content:
                clause_pattern = r'(\d+)\.\s*([^\n]+(?:\n(?!\d+\.)[^\n]*)*)'
                clause_matches = re.finditer(clause_pattern, article_content)

                for clause_match in clause_matches:
                    clauses.append({
                        'number': clause_match.group(1),
                        'content': clause_match.group(2).strip()
                    })

            articles.append({
                'number': article_num,
                'title': article_title,
                'content': article_content,
                'clauses': clauses
            })

        return articles

    def extract_penalties(self, text):
        """
        Trích xuất thông tin về xử phạt
        """
        penalties = []

        penalty_patterns = [
            r'phạt tiền từ\s+([\d,.]+)\s*đến\s+([\d,.]+)\s*(?:đồng|VND)',
            r'phạt tiền\s+([\d,.]+)\s*(?:đồng|VND)',
            r'(?:bị phạt|phạt)\s+([^\n.;]+)',
            r'mức phạt[:\s]+([\d,.]+)\s*(?:đồng|VND)'
        ]

        for pattern in penalty_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                penalties.append(match.group(0).strip())

        return list(set(penalties))

    def extract_definitions(self, text):
        """
        Trích xuất các định nghĩa thuật ngữ
        """
        definitions = {}

        # Pattern cho định nghĩa
        definition_patterns = [
            r'([A-ZÀ-Ỹ][a-zà-ỹ\s]+)\s+là\s+([^.;]+[.;])',
            r'Trong\s+(?:Luật|Nghị định|Thông tư)\s+này[,\s]*([^"]+)"\s+được hiểu là\s+([^.;]+)',
            r'"([^"]+)"\s+(?:được hiểu là|có nghĩa là|là)\s+([^.;]+)'
        ]

        for pattern in definition_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                term = match.group(1).strip()
                definition = match.group(2).strip()
                definitions[term] = definition

        return definitions

    def search_content(self, text, query, context_chars=200):
        """
        Tìm kiếm nội dung với ngữ cảnh xung quanh
        """
        results = []
        query_lower = query.lower()
        text_lower = text.lower()

        start = 0
        while True:
            pos = text_lower.find(query_lower, start)
            if pos == -1:
                break

            # Lấy ngữ cảnh xung quanh
            context_start = max(0, pos - context_chars)
            context_end = min(len(text), pos + len(query) + context_chars)
            context = text[context_start:context_end]

            # Tìm điều chứa kết quả này
            article_match = re.search(r'Điều\s+(\d+)', text[:pos][::-1])
            article_num = article_match.group(1)[::-1] if article_match else "Không xác định"

            results.append({
                'position': pos,
                'context': context,
                'article': article_num,
                'match_text': text[pos:pos + len(query)]
            })

            start = pos + 1

        return results

    def find_related_articles(self, articles, keyword):
        """
        Tìm các điều liên quan đến từ khóa
        """
        related = []
        keyword_lower = keyword.lower()

        for article in articles:
            relevance_score = 0

            # Tìm trong tiêu đề
            if keyword_lower in article['title'].lower():
                relevance_score += 3

            # Tìm trong nội dung
            content_lower = article['content'].lower()
            keyword_count = content_lower.count(keyword_lower)
            relevance_score += keyword_count

            # Tìm trong các khoản
            for clause in article['clauses']:
                if keyword_lower in clause['content'].lower():
                    relevance_score += 2

            if relevance_score > 0:
                related.append({
                    'article': article,
                    'relevance_score': relevance_score
                })

        # Sắp xếp theo độ liên quan
        related.sort(key=lambda x: x['relevance_score'], reverse=True)
        return related

    def extract_cross_references(self, text):
        """
        Trích xuất các tham chiếu chéo giữa các điều
        """
        references = []

        # Pattern cho tham chiếu
        ref_patterns = [
            r'theo quy định tại Điều\s+(\d+)',
            r'được quy định tại Điều\s+(\d+)',
            r'căn cứ Điều\s+(\d+)',
            r'phù hợp với Điều\s+(\d+)',
            r'trừ trường hợp quy định tại Điều\s+(\d+)'
        ]

        for pattern in ref_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                # Tìm điều chứa tham chiếu này
                context_start = max(0, match.start() - 100)
                context_end = min(len(text), match.end() + 100)
                context = text[context_start:context_end]

                # Tìm điều nguồn
                source_match = re.search(r'Điều\s+(\d+)', text[:match.start()][::-1])
                source_article = source_match.group(1)[::-1] if source_match else "Không xác định"

                references.append({
                    'source_article': source_article,
                    'target_article': match.group(1),
                    'reference_type': pattern.split('\\s+')[0],
                    'context': context.strip()
                })

        return references

    def classify_article_types(self, articles):
        """
        Phân loại các điều theo chức năng
        """
        classification = {
            'definitions': [],  # Điều định nghĩa
            'principles': [],  # Điều nguyên tắc
            'procedures': [],  # Điều thủ tục
            'penalties': [],  # Điều xử phạt
            'rights': [],  # Điều quyền lợi
            'obligations': [],  # Điều nghĩa vụ
            'general': []  # Điều chung
        }

        # Từ khóa để phân loại
        keywords = {
            'definitions': ['định nghĩa', 'hiểu là', 'có nghĩa', 'được gọi là'],
            'principles': ['nguyên tắc', 'cơ bản', 'căn bản', 'chung'],
            'procedures': ['thủ tục', 'trình tự', 'quy trình', 'hồ sơ'],
            'penalties': ['phạt', 'xử phạt', 'vi phạm', 'chế tài'],
            'rights': ['quyền', 'được', 'có quyền'],
            'obligations': ['nghĩa vụ', 'phải', 'không được', 'bắt buộc']
        }

        for article in articles:
            article_text = (article['title'] + ' ' + article['content']).lower()
            scores = {}

            for category, category_keywords in keywords.items():
                score = sum(article_text.count(keyword) for keyword in category_keywords)
                scores[category] = score

            # Phân loại theo điểm cao nhất
            best_category = max(scores, key=scores.get) if max(scores.values()) > 0 else 'general'
            classification[best_category].append({
                'article': article,
                'confidence': scores[best_category]
            })

        return classification


def ocr_legal_document_with_extraction(pdf_path, output_dir="ocr_output"):
    """
    OCR tài liệu pháp lý với VietOCR, chỉ dùng tiền xử lý mạnh nhất
    """
    os.makedirs(output_dir, exist_ok=True)

    try:
        config = Cfg.load_config_from_name('vgg_transformer')
        config['device'] = 'cpu'
        config['predictor']['beamsearch'] = True
        detector = Predictor(config)
    except Exception as e:
        logger.error(f"Không thể khởi tạo VietOCR: {e}")
        return [], {}, ""

    extractor = LegalDocumentInfoExtractor()
    logger.info("📄 Đang chuyển PDF thành ảnh...")
    pdf_images = extract_images_from_pdf_pages(pdf_path, dpi=400)

    ocr_results = []
    all_text = ""

    for img_data in pdf_images:
        page_num = img_data['page_num']
        image = img_data['image']
        debug_dir = os.path.join(output_dir, f"debug_page_{page_num}")

        logger.info(f"🔍 Đang xử lý trang {page_num}...")

        img_array = np.array(image.convert('L'))
        if np.std(img_array) < 10:
            logger.warning(f"Trang {page_num} có vẻ trống, bỏ qua")
            ocr_results.append({
                'page': page_num,
                'best_method': 'none',
                'best_text': '',
                'all_results': {'none': ''}
            })
            continue

        processed = advanced_preprocess_legal_document(image, debug_dir=debug_dir)
        pil_processed = Image.fromarray(processed)
        text, method = ocr_with_vietocr(pil_processed, detector, page_num, debug_dir)

        page_result = {
            'page': page_num,
            'best_method': method,
            'best_text': text,
            'all_results': {method: text}
        }

        ocr_results.append(page_result)
        all_text += text + "\n\n"

        logger.info(f"Trang {page_num} hoàn thành - Phương pháp: {method}, Độ dài: {len(text)}")

    logger.info("🔬 Đang trích xuất thông tin pháp lý...")
    law_info = extractor.extract_law_info(all_text)
    articles = extractor.extract_article_content(all_text)
    penalties = extractor.extract_penalties(all_text)
    definitions = extractor.extract_definitions(all_text)

    extracted_info = {
        'document_info': law_info,
        'articles': articles,
        'penalties': penalties,
        'definitions': definitions,
        'statistics': {
            'total_pages': len(ocr_results),
            'total_characters': len(all_text),
            'total_articles': len(articles),
            'total_chapters': len(law_info['chapters']),
            'processing_methods_used': Counter([r['best_method'] for r in ocr_results])
        }
    }

    if not all_text.strip():
        logger.warning("Không trích xuất được văn bản. Kiểm tra hình ảnh debug trong thư mục đầu ra.")

    return ocr_results, extracted_info, all_text


def save_comprehensive_results(ocr_results, extracted_info, all_text, output_dir):
    """
    Lưu kết quả đầy đủ
    """
    with open(os.path.join(output_dir, "full_text.txt"), 'w', encoding='utf-8') as f:
        f.write(all_text)

    with open(os.path.join(output_dir, "extracted_info.json"), 'w', encoding='utf-8') as f:
        json.dump(extracted_info, f, ensure_ascii=False, indent=2)

    with open(os.path.join(output_dir, "detailed_report.txt"), 'w', encoding='utf-8') as f:
        f.write("=== BÁO CÁO PHÂN TÍCH TÀI LIỆU PHÁP LÝ ===\n\n")
        f.write("📊 THỐNG KÊ TỔNG QUAN:\n")
        stats = extracted_info['statistics']
        f.write(f"- Tổng số trang: {stats['total_pages']}\n")
        f.write(f"- Tổng ký tự: {stats['total_characters']:,}\n")
        f.write(f"- Số điều: {stats['total_articles']}\n")
        f.write(f"- Số chương: {stats['total_chapters']}\n\n")
        doc_info = extracted_info['document_info']
        f.write("📄 THÔNG TIN TÀI LIỆU:\n")
        if doc_info['title']:
            f.write(f"Tiêu đề: {doc_info['title']}\n")
        if doc_info['law_numbers']:
            f.write(f"Số hiệu: {', '.join(doc_info['law_numbers'])}\n")
        if doc_info['dates']:
            f.write(f"Ngày ban hành: {', '.join(doc_info['dates'])}\n\n")
        if doc_info['chapters']:
            f.write("📚 DANH SÁCH CHƯƠNG:\n")
            for chapter in doc_info['chapters']:
                f.write(f"- Chương {chapter['number']}: {chapter['title']}\n")
            f.write("\n")
        if extracted_info['articles']:
            f.write("📜 MỘT SỐ ĐIỀU QUAN TRỌNG:\n")
            for i, article in enumerate(extracted_info['articles'][:10]):
                f.write(f"\nĐiều {article['number']}: {article['title']}\n")
                if article['content']:
                    content_preview = article['content'][:200]
                    f.write(f"Nội dung: {content_preview}...\n")
                if article['clauses']:
                    f.write(f"Có {len(article['clauses'])} khoản\n")
        if extracted_info['penalties']:
            f.write(f"\n💰 THÔNG TIN XỬ PHẠT ({len(extracted_info['penalties'])} mục):\n")
            for penalty in extracted_info['penalties'][:10]:
                f.write(f"- {penalty}\n")
        if extracted_info['definitions']:
            f.write(f"\n📖 ĐỊNH NGHĨA THUẬT NGỮ ({len(extracted_info['definitions'])} thuật ngữ):\n")
            for term, definition in list(extracted_info['definitions'].items())[:10]:
                f.write(f"- {term}: {definition}\n")


def create_interactive_search_system(extracted_info, all_text):
    """
    Tạo hệ thống tìm kiếm tương tác
    """
    extractor = LegalDocumentInfoExtractor()

    def search_interface():
        print("\n🔍 HỆ THỐNG TÌM KIẾM TÀI LIỆU PHÁP LÝ")
        print("=" * 50)

        while True:
            print("\nCác lựa chọn:")
            print("1. Tìm kiếm từ khóa")
            print("2. Tra cứu điều cụ thể")
            print("3. Tìm điều liên quan")
            print("4. Xem tham chiếu chéo")
            print("5. Phân loại điều theo chức năng")
            print("6. Thống kê tài liệu")
            print("0. Thoát")

            choice = input("\nNhập lựa chọn (0-6): ").strip()

            if choice == "0":
                break
            elif choice == "1":
                keyword = input("Nhập từ khóa cần tìm: ").strip()
                if keyword:
                    results = extractor.search_content(all_text, keyword)
                    print(f"\n🎯 Tìm thấy {len(results)} kết quả cho '{keyword}':")
                    for i, result in enumerate(results[:5], 1):
                        print(f"\n{i}. Trong Điều {result['article']}:")
                        print(f"   ...{result['context']}...")

            elif choice == "2":
                try:
                    article_num = input("Nhập số điều cần tra: ").strip()
                    found_article = next((a for a in extracted_info['articles']
                                          if a['number'] == article_num), None)
                    if found_article:
                        print(f"\n📜 ĐIỀU {found_article['number']}: {found_article['title']}")
                        print(f"\nNội dung:\n{found_article['content']}")
                        if found_article['clauses']:
                            print(f"\nCác khoản ({len(found_article['clauses'])}):")
                            for clause in found_article['clauses']:
                                print(f"  {clause['number']}. {clause['content']}")
                    else:
                        print(f"❌ Không tìm thấy Điều {article_num}")
                except:
                    print("❌ Số điều không hợp lệ")

            elif choice == "3":
                keyword = input("Nhập từ khóa để tìm điều liên quan: ").strip()
                if keyword:
                    related = extractor.find_related_articles(extracted_info['articles'], keyword)
                    print(f"\n🔗 Các điều liên quan đến '{keyword}':")
                    for i, item in enumerate(related[:10], 1):
                        article = item['article']
                        score = item['relevance_score']
                        print(f"{i}. Điều {article['number']}: {article['title']} (điểm: {score})")

            elif choice == "4":
                references = extractor.extract_cross_references(all_text)
                print(f"\n🔄 Tham chiếu chéo ({len(references)} tham chiếu):")
                for ref in references[:20]:
                    print(f"Điều {ref['source_article']} → Điều {ref['target_article']}")
                    print(f"   Ngữ cảnh: {ref['context'][:100]}...")
                    print()

            elif choice == "5":
                classification = extractor.classify_article_types(extracted_info['articles'])
                print("\n📊 PHÂN LOẠI ĐIỀU LẬT:")
                for category, articles in classification.items():
                    if articles:
                        print(f"\n{category.upper()} ({len(articles)} điều):")
                        for item in articles[:5]:
                            article = item['article']
                            print(f"  - Điều {article['number']}: {article['title']}")

            elif choice == "6":
                stats = extracted_info['statistics']
                doc_info = extracted_info['document_info']
                print("\n📈 THỐNG KÊ TÀI LIỆU:")
                print(f"📄 Tổng trang: {stats['total_pages']}")
                print(f"📝 Tổng ký tự: {stats['total_characters']:,}")
                print(f"📋 Số chương: {stats['total_chapters']}")
                print(f"📜 Số điều: {stats['total_articles']}")
                print(f"💰 Thông tin xử phạt: {len(extracted_info['penalties'])}")
                print(f"📖 Định nghĩa: {len(extracted_info['definitions'])}")
                if doc_info['law_numbers']:
                    print(f"🏷️  Số hiệu: {', '.join(doc_info['law_numbers'])}")

            else:
                print("❌ Lựa chọn không hợp lệ")

    return search_interface


def generate_summary_report(extracted_info, all_text):
    """
    Tạo báo cáo tóm tắt thông minh (phiên bản hoàn chỉnh)
    """
    extractor = LegalDocumentInfoExtractor()

    # Phân tích nâng cao
    references = extractor.extract_cross_references(all_text)
    classification = extractor.classify_article_types(extracted_info['articles'])
    structure_analysis = analyze_document_structure(extracted_info)

    summary = {
        'executive_summary': '',
        'key_highlights': [],
        'structure_analysis': structure_analysis,
        'important_articles': [],
        'penalty_summary': [],
        'cross_reference_analysis': {},
        'recommendations': []
    }

    # Tóm tắt điều hành
    doc_info = extracted_info['document_info']
    stats = extracted_info['statistics']

    summary['executive_summary'] = f"""
Tài liệu '{doc_info.get('title', 'Không xác định')}' ({structure_analysis['document_type']}) 
là văn bản pháp lý gồm {stats['total_articles']} điều được tổ chức thành {stats['total_chapters']} chương.
Độ phức tạp: {structure_analysis['complexity_score']:.1f}/10. 
Tài liệu có {len(extracted_info['penalties'])} quy định xử phạt và 
{len(extracted_info['definitions'])} định nghĩa thuật ngữ.
Chất lượng tổ chức: {structure_analysis['organization_quality']}.
    """.strip()

    # Điểm nổi bật
    summary['key_highlights'] = [
        f"Loại tài liệu: {structure_analysis['document_type']}",
        f"Độ phức tạp: {structure_analysis['complexity_score']:.1f}/10",
        f"Có {len(references)} tham chiếu chéo giữa các điều",
        f"Mật độ nội dung: {structure_analysis['content_density']} điều/1000 ký tự",
        f"Sức khỏe cấu trúc: {structure_analysis['structural_health']}"
    ]

    # Phân tích các điều quan trọng
    important_articles = []
    for article in extracted_info['articles'][:10]:  # Top 10 điều đầu tiên
        importance_score = 0

        # Điều có nhiều khoản thường quan trọng
        importance_score += len(article['clauses']) * 0.5

        # Điều dài thường có nội dung quan trọng
        importance_score += len(article['content']) / 1000

        # Điều có từ khóa quan trọng
        important_keywords = ['nguyên tắc', 'cơ bản', 'quyền', 'nghĩa vụ', 'cấm', 'phạt']
        content_lower = (article['title'] + ' ' + article['content']).lower()
        for keyword in important_keywords:
            if keyword in content_lower:
                importance_score += 1

        if importance_score > 2:
            important_articles.append({
                'article': article,
                'importance_score': importance_score
            })

    important_articles.sort(key=lambda x: x['importance_score'], reverse=True)
    summary['important_articles'] = important_articles[:5]

    # Tóm tắt xử phạt
    penalty_analysis = {
        'total_penalties': len(extracted_info['penalties']),
        'penalty_types': [],
        'fine_ranges': []
    }

    for penalty in extracted_info['penalties']:
        penalty_lower = penalty.lower()
        if 'phạt tiền' in penalty_lower:
            penalty_analysis['penalty_types'].append('Phạt tiền')
        if 'tước quyền' in penalty_lower:
            penalty_analysis['penalty_types'].append('Tước quyền')
        if 'đình chỉ' in penalty_lower:
            penalty_analysis['penalty_types'].append('Đình chỉ')

    penalty_analysis['penalty_types'] = list(set(penalty_analysis['penalty_types']))
    summary['penalty_summary'] = penalty_analysis

    # Phân tích tham chiếu chéo
    if references:
        ref_network = defaultdict(list)
        for ref in references:
            ref_network[ref['source_article']].append(ref['target_article'])

        # Tìm điều được tham chiếu nhiều nhất
        target_counts = Counter()
        for ref in references:
            target_counts[ref['target_article']] += 1

        summary['cross_reference_analysis'] = {
            'total_references': len(references),
            'articles_with_references': len(ref_network),
            'most_referenced_articles': target_counts.most_common(5),
            'reference_density': len(references) / stats['total_articles'] if stats['total_articles'] > 0 else 0
        }

    # Khuyến nghị
    recommendations = []

    if structure_analysis['complexity_score'] > 7:
        recommendations.append("Tài liệu có độ phức tạp cao, nên có hệ thống tra cứu hỗ trợ")

    if structure_analysis['organization_quality'] == 'Có thể quá phức tạp':
        recommendations.append("Cân nhắc tái cấu trúc để giảm số điều mỗi chương")

    if len(extracted_info['definitions']) < 10 and stats['total_articles'] > 50:
        recommendations.append("Nên bổ sung thêm định nghĩa thuật ngữ để tăng tính rõ ràng")

    if summary['cross_reference_analysis'].get('reference_density', 0) < 0.1:
        recommendations.append("Mật độ tham chiếu thấp, có thể cần liên kết giữa các điều")

    summary['recommendations'] = recommendations

    return summary


def analyze_document_structure(extracted_info):
    """
    Phân tích cấu trúc tài liệu
    """
    analysis = {
        'document_type': 'unknown',
        'complexity_score': 0,
        'organization_quality': 'unknown',
        'content_density': 0,
        'structural_health': 'unknown',
        'reference_network': {},
        'content_distribution': {}
    }

    doc_info = extracted_info['document_info']
    stats = extracted_info['statistics']

    # Xác định loại tài liệu
    if doc_info['title']:
        title = doc_info['title'].upper()
        if 'BỘ LUẬT' in title:
            analysis['document_type'] = 'Bộ luật'
        elif 'LUẬT' in title:
            analysis['document_type'] = 'Luật'
        elif 'NGHỊ ĐỊNH' in title:
            analysis['document_type'] = 'Nghị định'
        elif 'THÔNG TƯ' in title:
            analysis['document_type'] = 'Thông tư'
        elif 'QUYẾT ĐỊNH' in title:
            analysis['document_type'] = 'Quyết định'

    # Tính điểm phức tạp (thang 10)
    complexity_factors = [
        min(stats['total_articles'] * 0.05, 3),  # Số điều (tối đa 3 điểm)
        min(stats['total_chapters'] * 0.3, 2),  # Số chương (tối đa 2 điểm)
        min(len(extracted_info['penalties']) * 0.1, 2),  # Xử phạt (tối đa 2 điểm)
        min(len(extracted_info['definitions']) * 0.05, 1.5),  # Định nghĩa (tối đa 1.5 điểm)
        min(stats['total_characters'] / 50000, 1.5)  # Độ dài (tối đa 1.5 điểm)
    ]
    analysis['complexity_score'] = min(sum(complexity_factors), 10)

    # Đánh giá chất lượng tổ chức
    if stats['total_chapters'] > 0 and stats['total_articles'] > 0:
        avg_articles_per_chapter = stats['total_articles'] / stats['total_chapters']
        if 3 <= avg_articles_per_chapter <= 20:
            analysis['organization_quality'] = 'Tốt'
        elif avg_articles_per_chapter < 3:
            analysis['organization_quality'] = 'Có thể thiếu chi tiết'
        else:
            analysis['organization_quality'] = 'Có thể quá phức tạp'
    else:
        analysis['organization_quality'] = 'Không có cấu trúc chương'

    # Mật độ nội dung (điều/1000 ký tự)
    if stats['total_characters'] > 0:
        analysis['content_density'] = round(stats['total_articles'] / (stats['total_characters'] / 1000), 2)

    # Đánh giá sức khỏe cấu trúc
    structure_score = 0
    if stats['total_chapters'] > 0:
        structure_score += 2
    if stats['total_articles'] > 10:
        structure_score += 2
    if len(extracted_info['definitions']) > 5:
        structure_score += 1
    if doc_info['law_numbers']:
        structure_score += 1

    if structure_score >= 5:
        analysis['structural_health'] = 'Tốt'
    elif structure_score >= 3:
        analysis['structural_health'] = 'Trung bình'
    else:
        analysis['structural_health'] = 'Cần cải thiện'

    # Phân tích phân bố nội dung
    article_lengths = []
    for article in extracted_info['articles']:
        content_length = len(article['content']) + len(article['title'])
        article_lengths.append(content_length)

    if article_lengths:
        avg_length = sum(article_lengths) / len(article_lengths)
        analysis['content_distribution'] = {
            'average_article_length': round(avg_length),
            'shortest_article': min(article_lengths),
            'longest_article': max(article_lengths),
            'length_variance': 'High' if max(article_lengths) > avg_length * 3 else 'Normal'
        }

    return analysis


def create_detailed_analysis_report(extracted_info, all_text, output_dir):
    """
    Tạo báo cáo phân tích chi tiết với nhiều góc độ
    """
    # Phân tích cấu trúc
    structure_analysis = analyze_document_structure(extracted_info)

    # Báo cáo tóm tắt
    summary_report = generate_summary_report(extracted_info, all_text)

    # Tạo file báo cáo HTML đẹp
    html_report = f"""
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Báo Cáo Phân Tích Tài Liệu Pháp Lý</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        h2 {{ color: #34495e; margin-top: 30px; }}
        .summary-box {{ background: #ecf0f1; padding: 20px; border-radius: 6px; border-left: 4px solid #3498db; margin: 20px 0; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
        .stat-card {{ background: #fff; padding: 15px; border-radius: 6px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); text-align: center; }}
        .stat-number {{ font-size: 24px; font-weight: bold; color: #e74c3c; }}
        .stat-label {{ color: #7f8c8d; font-size: 14px; }}
        .article-list {{ background: #f9f9f9; padding: 15px; border-radius: 6px; }}
        .article-item {{ margin: 10px 0; padding: 10px; background: white; border-radius: 4px; }}
        .highlight {{ background: #fff3cd; padding: 2px 4px; border-radius: 3px; }}
        .recommendation {{ background: #d1ecf1; padding: 10px; margin: 5px 0; border-radius: 4px; border-left: 3px solid #bee5eb; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Báo Cáo Phân Tích Tài Liệu Pháp Lý</h1>

        <div class="summary-box">
            <h2>📋 Tóm Tắt Điều Hành</h2>
            <p>{summary_report['executive_summary']}</p>
        </div>

        <h2>📈 Thống Kê Tổng Quan</h2>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">{extracted_info['statistics']['total_pages']}</div>
                <div class="stat-label">Tổng số trang</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{extracted_info['statistics']['total_articles']}</div>
                <div class="stat-label">Số điều</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{extracted_info['statistics']['total_chapters']}</div>
                <div class="stat-label">Số chương</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{len(extracted_info['penalties'])}</div>
                <div class="stat-label">Quy định xử phạt</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{structure_analysis['complexity_score']:.1f}/10</div>
                <div class="stat-label">Độ phức tạp</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{structure_analysis['content_density']}</div>
                <div class="stat-label">Mật độ nội dung</div>
            </div>
        </div>

        <h2>🎯 Điểm Nổi Bật</h2>
        <ul>
            {''.join([f'<li>{highlight}</li>' for highlight in summary_report['key_highlights']])}
        </ul>

        <h2>📜 Các Điều Quan Trọng</h2>
        <div class="article-list">
            {''.join([f'''
            <div class="article-item">
                <strong>Điều {item['article']['number']}: {item['article']['title']}</strong><br>
                <small>Điểm quan trọng: {item['importance_score']:.1f} | Số khoản: {len(item['article']['clauses'])}</small>
            </div>
            ''' for item in summary_report['important_articles']])}
        </div>

        <h2>💰 Phân Tích Xử Phạt</h2>
        <p>Tổng số quy định xử phạt: <span class="highlight">{summary_report['penalty_summary']['total_penalties']}</span></p>
        <p>Các loại xử phạt: {', '.join(summary_report['penalty_summary']['penalty_types']) if summary_report['penalty_summary']['penalty_types'] else 'Chưa phân loại'}</p>

        <h2>🔗 Phân Tích Tham Chiếu</h2>
        {f'''
        <p>Tổng số tham chiếu: <span class="highlight">{summary_report['cross_reference_analysis']['total_references']}</span></p>
        <p>Mật độ tham chiếu: <span class="highlight">{summary_report['cross_reference_analysis']['reference_density']:.2f}</span> tham chiếu/điều</p>
        ''' if 'cross_reference_analysis' in summary_report and summary_report['cross_reference_analysis'] else '<p>Không có dữ liệu tham chiếu</p>'}

        <h2>💡 Khuyến Nghị</h2>
        {''.join([f'<div class="recommendation">• {rec}</div>' for rec in summary_report['recommendations']]) if summary_report['recommendations'] else '<p>Không có khuyến nghị đặc biệt</p>'}

        <hr style="margin: 30px 0;">
        <p style="text-align: center; color: #7f8c8d;">
            Báo cáo được tạo tự động bởi Hệ thống Phân tích Tài liệu Pháp lý<br>
            Thời gian: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
        </p>
    </div>
</body>
</html>
    """

    # Lưu báo cáo HTML
    with open(os.path.join(output_dir, "analysis_report.html"), 'w', encoding='utf-8') as f:
        f.write(html_report)

    # Lưu báo cáo JSON chi tiết
    detailed_report = {
        'structure_analysis': structure_analysis,
        'summary_report': summary_report,
        'timestamp': datetime.now().isoformat(),
        'metadata': {
            'total_processing_time': 'N/A',
            'ocr_accuracy_estimate': 'N/A',
            'document_confidence': 'High' if structure_analysis['complexity_score'] < 8 else 'Medium'
        }
    }

    with open(os.path.join(output_dir, "detailed_analysis.json"), 'w', encoding='utf-8') as f:
        json.dump(detailed_report, f, ensure_ascii=False, indent=2)

    return detailed_report


if __name__ == "__main__":
    pdf_path = "../data/CSDLQG/Bộ luật 45_2019_QH14.pdf"
    output_dir = "legal_analysis_output"

    if os.path.exists(pdf_path):
        logger.info("🚀 Bắt đầu OCR và phân tích tài liệu pháp lý...")
        ocr_results, extracted_info, all_text = ocr_legal_document_with_extraction(pdf_path, output_dir)
        save_comprehensive_results(ocr_results, extracted_info, all_text, output_dir)

        logger.info(f"\n✅ Hoàn thành!")
        logger.info(f"📄 Đã xử lý {extracted_info['statistics']['total_pages']} trang")
        logger.info(f"📊 Trích xuất được:")
        logger.info(f"   - {extracted_info['statistics']['total_articles']} điều")
        logger.info(f"   - {extracted_info['statistics']['total_chapters']} chương")
        logger.info(f"   - {len(extracted_info['penalties'])} thông tin xử phạt")
        logger.info(f"   - {len(extracted_info['definitions'])} định nghĩa thuật ngữ")
        logger.info(f"💾 Kết quả lưu trong: {output_dir}")

        if extracted_info['document_info']['title']:
            logger.info(f"\n📋 Tiêu đề: {extracted_info['document_info']['title']}")

        if extracted_info['articles']:
            logger.info(
                f"\n📜 Điều đầu tiên: Điều {extracted_info['articles'][0]['number']} - {extracted_info['articles'][0]['title']}")

        use_search = input("\n❓ Bạn có muốn sử dụng hệ thống tìm kiếm tương tác? (y/n): ").strip().lower()
        if use_search in ['y', 'yes', 'có']:
            search_system = create_interactive_search_system(extracted_info, all_text)
            search_system()

        logger.info("\n🎉 Cảm ơn bạn đã sử dụng hệ thống phân tích tài liệu pháp lý!")
    else:
        logger.error(f"❌ Không tìm thấy file: {pdf_path}")
        logger.error("Vui lòng đặt file PDF trong đường dẫn chính xác")

