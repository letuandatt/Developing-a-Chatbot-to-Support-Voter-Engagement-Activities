# Quy trình xây dựng trợ lý ảo hỗ trợ tiếp xúc cử tri

## 1. Thu thập dữ liệu
- **Nguồn**: Thu thập file PDF từ Công báo và Cơ sở dữ liệu quốc gia.
- **Loại văn bản**: Chỉ thị, Thông tư, Quyết định, Công văn, Công điện, Luật, v.v.
- **Định dạng**: Xử lý cả PDF text-based và image-based (sử dụng OCR cho image-based).
- **Công cụ**: Sử dụng thư viện như `requests`, `BeautifulSoup`, hoặc `scrapy` để cào dữ liệu.
- **Lưu trữ**: Lưu file PDF vào thư mục có cấu trúc (ví dụ: `data/Chỉ thị`, `data/Thông tư`).

## 2. Tiền xử lý PDF
- **Mục tiêu**: Trích xuất nội dung và metadata từ file PDF.
- **Các bước**:
  - **Đọc PDF**:
    - Text-based: Sử dụng PyMuPDF (`fitz`) để trích xuất văn bản và định dạng.
    - Image-based (tạm bỏ qua): Sử dụng `pytesseract` và `pdf2image` để OCR.
  - **Làm sạch văn bản**:
    - Loại bỏ header/footer, chữ ký, và các dòng không cần thiết (dùng regex trong `preprocess_pdf.py`).
    - Chuẩn hóa khoảng trắng, ký tự Unicode, và lỗi chính tả (dùng thư viện như `unicodedata` hoặc `pyvi`).
  - **Trích xuất metadata**:
    - Các trường: `so_hieu`, `loai_van_ban`, `noi_ban_hanh`, `ngay_ban_hanh`, `ten_van_ban`, `trich_yeu` (tùy chọn), `chuc_vu_nguoi_ky`, `nguoi_ky`.
    - Thêm trường `ngay_hieu_luc` từ dữ liệu cào web (nếu có).
  - **Phân tích cấu trúc**:
    - Chia văn bản thành chương, mục, khoản, điểm (dùng regex và logic trong `preprocess_pdf.py`).
  - **Lưu kết quả**: Lưu vào file JSON (ví dụ: `processed_documents_chithi.json`).

## 3. Chunking văn bản
- **Mục tiêu**: Chia văn bản thành các đoạn nhỏ (chunk) để embedding và truy vấn RAG.
- **Các bước**:
  - **Chuyển đổi cấu trúc phân cấp**:
    - Đọc file JSON từ bước tiền xử lý.
    - Chuyển cấu trúc phân cấp (chương/mục/khoản/điểm) thành danh sách chunk phẳng (dùng `prepare_rag_chunks.py`).
  - **Tối ưu chunk**:
    - Gộp chunk ngắn (<50 ký tự) với nội dung cha.
    - Chia chunk dài (>500 ký tự) thành các đoạn nhỏ dựa trên dấu câu.
    - Thêm ngữ cảnh bổ sung (chapter_title, section_title, v.v.) vào nội dung chunk.
  - **Kiểm tra chất lượng**:
    - Loại bỏ chunk rỗng hoặc quá ngắn.
    - Ghi log các chunk bị bỏ qua.
  - **Lưu kết quả**: Lưu vào file JSON (ví dụ: `processed_documents_for_rag.json`).

## 4. Embedding và tạo vector database
- **Mục tiêu**: Chuyển các chunk thành vector và lưu vào cơ sở dữ liệu vector để truy vấn.
- **Các bước**:
  - **Load embedding model**: Sử dụng mô hình như `huyydangg/DEk21_hcmute_embedding` (HuggingFace).
  - **Embedding chunks**:
    - Sử dụng batch processing để tăng hiệu suất (dùng `prepare_vector_db.py`).
    - Lưu metadata kèm theo mỗi chunk (so_hieu, loai_van_ban, v.v.).
  - **Lưu vector database**:
    - Sử dụng Chroma (hoặc Faiss/Milvus cho khối lượng lớn).
    - Kiểm tra số lượng document trong database sau khi lưu.
  - **Kiểm tra truy vấn**:
    - Dùng hàm `test_vectordb_search` để kiểm tra kết quả truy vấn.
    - Thêm bộ lọc metadata (ví dụ: lọc theo `loai_van_ban` hoặc `ngay_ban_hanh`).

## 5. Xây dựng chatbot RAG
- **Mục tiêu**: Tích hợp vector database với mô hình ngôn ngữ lớn (LLM) để trả lời câu hỏi.
- **Các bước**:
  - **Chọn LLM**: Sử dụng Grok (xAI) hoặc mô hình open-source như Mistral, LLaMA.
  - **Tích hợp RAG**:
    - Truy xuất các chunk liên quan từ vector database.
    - Tạo prompt kết hợp context từ chunk và câu hỏi người dùng.
  - **Xây dựng giao diện**:
    - Sử dụng Gradio, Streamlit, hoặc Flask để tạo giao diện người dùng.
    - Hỗ trợ nhập câu hỏi và hiển thị kết quả kèm metadata (so_hieu, ngay_ban_hanh, v.v.).
  - **Tối ưu hóa truy vấn**:
    - Áp dụng kỹ thuật multi-query hoặc reranking (xem chi tiết ở câu hỏi 5).
    - Sử dụng xử lý ngôn ngữ tự nhiên (NLP) để phân tích câu hỏi tiếng Việt (dùng `spaCy` hoặc `VNCoreNLP`).

## 6. Đánh giá và triển khai
- **Đánh giá**:
  - Tạo bộ câu hỏi kiểm tra (test queries) dựa trên các văn bản pháp luật.
  - Đánh giá độ chính xác (precision, recall) và độ phù hợp của câu trả lời.
  - Thu thập phản hồi từ người dùng (cử tri, cán bộ).
- **Triển khai**:
  - Triển khai trên nền tảng như grok.com, ứng dụng di động, hoặc web app.
  - Cập nhật dữ liệu định kỳ từ Công báo và Cơ sở dữ liệu quốc gia.
- **Bảo trì**:
  - Ghi log lỗi và hiệu suất để cải thiện pipeline.
  - Thêm tính năng như gợi ý câu hỏi liên quan, sửa lỗi chính tả trong câu hỏi.