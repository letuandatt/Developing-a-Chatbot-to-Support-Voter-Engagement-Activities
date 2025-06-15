import json
import os

from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.schema import Document

# Khai báo biến
input_json_path = "ChiThi/processed_documents_for_rag.json"
vector_db_path = "vectorstores/Chroma"

# Hàm đọc file chunk từ file json
def load_json_chunks(input_path):
    print(f"Đang đọc dữ liệu file {input_path}")
    with open(input_path, 'r', encoding="utf-8") as f:
        chunks = json.load(f)
    print(f"Đã đọc xong dữ liệu.")
    return chunks

# Hàm tạo đối tượng Document từ các
def create_document_from_rag_chunks():
    """
    Tạo document từ các chunk RAG-ready
    :return: document
    """
    # Đọc file JSon chứa các chunk đã chuẩn bị cho RAG
    chunks = load_json_chunks(input_json_path)

    # Chuyển đổi các chunk thành đối tượng Document
    documents = []
    for chunk in chunks:
        # Tạo metadata từ metadata và context của file json
        metadata = {
            # Metadata chung của văn bản
            "so_hieu": chunk["metadata"].get("so_hieu", ""),
            "loai_van_ban": chunk["metadata"].get("loai_van_ban", ""),
            "noi_ban_hanh": chunk["metadata"].get("noi_ban_hanh", ""),
            "ngay_ban_hanh": chunk["metadata"].get("ngay_ban_hanh", ""),
            "ten_van_ban": chunk["metadata"].get("ten_van_ban", ""),
            "trich_yeu": chunk["metadata"].get("trich_yeu", ""),
            "file_name": chunk["metadata"].get("file_name", ""),

            # Thông tin ngữ cảnh (context) của chunk
            "level": chunk["context"].get("level", ""),
            "id": chunk["context"].get("id", ""),
            "title": chunk["context"].get("title", ""),
            "chunk_id": chunk.get("chunk_id", "")
        }

        # Thêm thông tin parent nếu có
        if "parent_id" in chunk["context"] and chunk["context"]["parent_id"]:
            metadata["parent_id"] = chunk["context"].get("parent_id", "")
            metadata["parent_title"] = chunk["context"].get("parent_title", "")

        # Thêm thông tin chapter nếu có
        if "chapter_id" in chunk["context"] and chunk["context"]["chapter_id"]:
            metadata["chapter_id"] = chunk["context"].get("chapter_id", "")
            metadata["chapter_title"] = chunk["context"].get("chapter_title", "")

        # Thêm thông tin section nếu có
        if "section_id" in chunk["context"] and chunk["context"]["section_id"]:
            metadata["section_id"] = chunk["context"].get("section_id", "")
            metadata["section_title"] = chunk["context"].get("section_title", "")

        # Tạo Document với nội dung và metadata
        doc = Document(
            page_content=chunk["content"],
            metadata=metadata,
        )
        documents.append(doc)

    print(f"Đã chuyển đổi thành {len(documents)} Document objects")

    return documents

# Hàm khởi tạo model embedding
def load_embedding_model():
    embedding_model = HuggingFaceEmbeddings(
        model_name="huyydangg/DEk21_hcmute_embedding",
    )
    return embedding_model

# Hàm tạo vectordb Chroma
def create_vector_db(documents):
    print("Đang tạo embedding và lưu vào Chroma")
    embedding_model = load_embedding_model()

    Chroma.from_documents(
        documents=documents,
        embedding=embedding_model,
        persist_directory=vector_db_path
    )

    print(f"Vector DB đã được lưu vào {vector_db_path}")

# Hàm test truy vấn từ vectordb đã tạo
def test_vectordb_search(query, k=3):
    print(f"Đang load model embedding")
    embedding_model = load_embedding_model()

    print(f"Đang lấy dl từ vectordb")
    db = Chroma(
        persist_directory=vector_db_path,
        embedding_function=embedding_model
    )

    print(f"Đang tìm kiếm kết quả")
    results = db.similarity_search(query, k=k)

    print(f"Kết quả tìm kiếm (top {k}):")
    for i, (doc, score) in enumerate(results):
        print(f"\n--- Kết quả #{i + 1} (Độ tương đồng: {1 - score:.4f}) ---")
        print(f"Nội dung: {doc.page_content}")
        print(f"Metadata:")
        print(f"  - Số hiệu: {doc.metadata.get('so_hieu')}")
        print(f"  - Loại văn bản: {doc.metadata.get('loai_van_ban')}")
        print(f"  - Ngày ban hành: {doc.metadata.get('ngay_ban_hanh')}")
        print(f"  - Cấp độ: {doc.metadata.get('level')} - {doc.metadata.get('id')}")
        if 'parent_id' in doc.metadata:
            print(f"  - Thuộc: {doc.metadata.get('parent_id')} - {doc.metadata.get('parent_title')}")


if __name__ == '__main__':
    documents = create_document_from_rag_chunks()
    # print(documents)
    #
    create_vector_db(documents)

    query = input("Query: ")
    test_vectordb_search(query)
