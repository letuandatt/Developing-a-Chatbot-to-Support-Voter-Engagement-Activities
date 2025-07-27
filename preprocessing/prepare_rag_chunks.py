import json
import os
import uuid
import torch

from langchain_experimental.text_splitter import SemanticChunker
from langchain_community.embeddings import HuggingFaceEmbeddings


def create_semantic_chunks(structured_doc: dict) -> list:
    """
    Bước 1: Tạo các chunk giàu ngữ nghĩa từ cấu trúc JSON.
    """
    metadata = {key: value for key, value in structured_doc.items() if key != "chuong"}
    content_tree = structured_doc.get("chuong", [])
    semantic_chunks = []

    for chapter in content_tree:
        # Bắt đầu với đường dẫn ngữ cảnh là tên văn bản
        _recursive_chunker(
            node=chapter,
            context_path=[metadata.get("ten_van_ban", metadata.get("file_name"))],
            citation_path=[],
            metadata=metadata,
            chunks_list=semantic_chunks
        )
    return semantic_chunks


def _recursive_chunker(node: dict, context_path: list, citation_path: list, metadata: dict, chunks_list: list):
    """Hàm đệ quy để duyệt cây JSON và tạo chunk."""
    current_id, current_title = "", ""
    if "ten_chuong" in node and node["ten_chuong"]:
        current_id, current_title = node["ten_chuong"], node["tieu_de"]
    elif "ten_muc" in node and node["ten_muc"]:
        current_id, current_title = node["ten_muc"], node["tieu_de"]
    elif "ten_khoan" in node and node["ten_khoan"]:
        current_id, current_title = node["ten_khoan"], node["tieu_de"]

    new_context_path = context_path + [current_title] if current_title else context_path
    new_citation_path = citation_path + [current_id] if current_id else citation_path

    children_keys = ["muc", "khoan", "diem"]
    found_children = False

    for key in children_keys:
        if key in node and node[key]:
            found_children = True
            if key == "diem":
                for point_content in node[key]:
                    final_citation = ", ".join(new_citation_path)
                    final_context = ". ".join(new_context_path) + f". Nội dung: {point_content}"
                    chunks_list.append({
                        "id": str(uuid.uuid4()), "source": metadata.get("file_name", "N/A"),
                        "location": final_citation, "content": final_context.strip(),
                        "issue_date": metadata.get("ngay_ban_hanh", "N/A"),
                        "effective_date": metadata.get("ngay_hieu_luc", "N/A"),
                        "signatory": metadata.get("nguoi_ky", "N/A"),
                        "signatory_position": metadata.get("chuc_vu_nguoi_ky", "N/A"),
                    })
            else:
                for child_node in node[key]:
                    _recursive_chunker(child_node, new_context_path, new_citation_path, metadata, chunks_list)

    if not found_children and current_title:
        final_citation = ", ".join(new_citation_path)
        final_context = ". ".join(new_context_path)
        chunks_list.append({
            "id": str(uuid.uuid4()),
            "source": metadata.get("file_name", "N/A"),
            "location": final_citation,
            "content": final_context.strip(),
            "issue_date": metadata.get("ngay_ban_hanh", "N/A"),
            "effective_date": metadata.get("ngay_hieu_luc", "N/A"),
            "signatory": metadata.get("nguoi_ky", "N/A"),
            "signatory_position": metadata.get("chuc_vu_nguoi_ky", "N/A"),
        })


def refine_chunks_semantically(semantic_chunks: list, semantic_splitter) -> list:
    """
    Sử dụng SemanticChunker để cắt nhỏ các chunk quá dài một cách thông minh.
    """
    refined_chunks = []
    print("\n--- [Bước 2] Bắt đầu tinh chỉnh kích thước chunk bằng SemanticChunker... ---")

    for chunk in semantic_chunks:
        content = chunk['content']

        # SemanticChunker không có ngưỡng `chunk_size` cố định.
        # Nó sẽ tự động tìm điểm ngắt. Có thể đặt một ngưỡng mềm để quyết định
        # khi nào cần áp dụng nó, ví dụ, với các chunk có độ dài lớn hơn 500 ký tự.
        if len(content) < 600:  # Ngưỡng này có thể điều chỉnh
            refined_chunks.append(chunk)
        else:
            print(f"(!) Chunk từ '{chunk['source']}' quá dài ({len(content)} ký tự), đang cắt theo ngữ nghĩa...")

            # Dùng semantic_splitter để cắt phần content
            sub_contents = semantic_splitter.split_text(content)

            # Tạo ra các chunk con, mỗi chunk con vẫn giữ lại metadata của chunk cha
            for i, sub_content in enumerate(sub_contents):
                refined_chunks.append({
                    "id": str(uuid.uuid4()),
                    "source": chunk['source'],
                    "location": f"{chunk['location']} (phần {i + 1})",
                    "content": sub_content,
                    "issue_date": chunk['issue_date'],
                    "effective_date": chunk['effective_date'],
                    "signatory": chunk['signatory'],
                    "signatory_position": chunk['signatory_position'],
                })

    print(f"--- [Bước 2] Hoàn thành, tổng số chunk cuối cùng: {len(refined_chunks)} ---")
    return refined_chunks


# --- HÀM CHÍNH ĐIỀU PHỐI ---
if __name__ == "__main__":
    structured_json_file = "ChiThi/processed_documents_chithi.json"
    output_filename = "ChiThi/final_chunks_for_embedding_semantic.jsonl"

    # --- KHỞI TẠO CÁC CÔNG CỤ MỘT LẦN ---
    print(">>> Đang khởi tạo mô hình embedding cho SemanticChunker...")
    embeddings_model = HuggingFaceEmbeddings(
        model_name='bkai-foundation-models/vietnamese-bi-encoder',
        model_kwargs={'device': 'cuda' if torch.cuda.is_available() else 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )

    # Khởi tạo SemanticChunker với mô hình embedding
    # breakpoint_threshold_type="percentile" là một lựa chọn phổ biến và ổn định.
    # Nó sẽ tìm điểm ngắt ở những chỗ mà sự thay đổi ngữ nghĩa lớn hơn 95% các chỗ khác.
    semantic_splitter = SemanticChunker(
        embeddings=embeddings_model,
        breakpoint_threshold_type="percentile"
    )
    print(">>> SemanticChunker đã sẵn sàng.")

    # --- CHẠY QUY TRÌNH ---
    if not os.path.exists(structured_json_file):
        print(f"Lỗi: Không tìm thấy file {structured_json_file}")
    else:
        with open(structured_json_file, 'r', encoding='utf-8') as f:
            documents = json.load(f)

        all_semantic_chunks = []
        print("\n--- [Bước 1] Bắt đầu tạo các chunk ngữ nghĩa... ---")
        for doc in documents:
            # create_semantic_chunks là hàm bạn đã có từ file trước
            # để biến JSON cấu trúc thành các chunk giàu ngữ cảnh
            chunks = create_semantic_chunks(doc)
            all_semantic_chunks.extend(chunks)
        print(f"--- [Bước 1] Hoàn thành, tạo được {len(all_semantic_chunks)} chunk ngữ nghĩa. ---")

        # Áp dụng bước tinh chỉnh bằng SemanticChunker
        final_chunks = refine_chunks_semantically(
            semantic_chunks=all_semantic_chunks,
            semantic_splitter=semantic_splitter
        )

        # Lưu kết quả cuối cùng
        with open(output_filename, 'w', encoding='utf-8') as f:
            for chunk in final_chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

        print(f"\n>>> Đã lưu toàn bộ các chunk đã tối ưu vào file: {output_filename}")