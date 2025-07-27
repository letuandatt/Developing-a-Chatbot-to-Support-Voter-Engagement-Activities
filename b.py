import streamlit as st
import sys
import os
import re
import json
import uuid
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.chains import RetrievalQA
from langchain.schema import Document


IGNORE_PATTERNS = [
    re.compile(r"^\s*CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\s*$", re.IGNORECASE),
    re.compile(r"^\s*Độc lập - Tự do - Hạnh phúc\s*$", re.IGNORECASE),
    re.compile(r"^\s*THỦ TƯỚNG CHÍNH PHỦ\s*$", re.IGNORECASE),
    re.compile(r"^\s*Ký bởi: Cổng Thông tin điện tử Chính phủ\s*$", re.IGNORECASE),
    re.compile(r"^\s*Email: thongtinchinhphu@chinhphu\.vn\s*$", re.IGNORECASE),
    re.compile(r"^\s*Cơ quan: Văn phòng Chính phủ\s*$", re.IGNORECASE),
    re.compile(r"^\s*Thời gian ký: \d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2} \+\d{2}:\d{2}\s*$", re.IGNORECASE),
]

# Cấu hình giao diện
st.set_page_config(
    page_title="Legal RAG Assistant",
    page_icon="⚖️",
    layout="wide"
)


@st.cache_resource
def load_embedding_model():
    """Load và cache embedding model"""
    return HuggingFaceEmbeddings(
        model_name='bkai-foundation-models/vietnamese-bi-encoder',
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )


@st.cache_resource
def load_prebuilt_vectorstore(chunks_file_path: str, show_messages: bool = True):
    """Load vectorstore từ file chunks đã có sẵn"""
    try:
        if not os.path.exists(chunks_file_path):
            if show_messages:
                st.error(f"❌ Không tìm thấy file chunks: {chunks_file_path}")
            return None

        embeddings = load_embedding_model()
        if not embeddings:
            if show_messages:
                st.error("❌ Không thể load embedding model")
            return None

        # Đọc chunks từ file JSONL
        chunks = []
        with open(chunks_file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if line.strip():
                    try:
                        chunk = json.loads(line)
                        chunks.append(chunk)
                    except json.JSONDecodeError as e:
                        if show_messages:
                            st.warning(f"⚠️ Lỗi parse JSON ở dòng {line_num}: {str(e)}")
                        continue

        if not chunks:
            if show_messages:
                st.error("❌ File chunks rỗng hoặc không đọc được")
            return None

        if show_messages:
            st.info(f"📊 Đã đọc {len(chunks)} chunks từ file")

        # Tạo Documents cho Chroma
        documents = []
        for i, chunk in enumerate(chunks):
            try:
                doc = Document(
                    page_content=chunk.get('content', ''),
                    metadata={
                        'source': chunk.get('source', 'N/A'),
                        'location': chunk.get('location', 'N/A'),
                        'id': chunk.get('id', str(uuid.uuid4()))
                    }
                )
                documents.append(doc)
            except Exception as e:
                if show_messages:
                    st.warning(f"⚠️ Lỗi xử lý chunk {i}: {str(e)}")
                continue

        if not documents:
            if show_messages:
                st.error("❌ Không tạo được documents từ chunks")
            return None

        # Tạo vector store
        if show_messages:
            with st.spinner(f"🔄 Đang tạo vectorstore từ {len(documents)} documents..."):
                vectorstore = Chroma.from_documents(
                    documents=documents,
                    embedding=embeddings,
                    persist_directory=None  # In-memory store
                )
        else:
            vectorstore = Chroma.from_documents(
                documents=documents,
                embedding=embeddings,
                persist_directory=None
            )

        if show_messages:
            st.success(f"✅ Đã load {len(chunks)} chunks vào vectorstore")
        return vectorstore

    except Exception as e:
        if show_messages:
            st.error(f"❌ Lỗi load vectorstore: {str(e)}")
            import traceback
            st.error(f"Chi tiết lỗi: {traceback.format_exc()}")
        return None


def generate_response_prebuilt(prompt: str, vectorstore) -> str:
    """Tạo phản hồi từ pre-built RAG system"""
    try:
        if not vectorstore:
            return "❌ Vectorstore chưa được load. Vui lòng kiểm tra lại file chunks."

        # Tìm kiếm relevant documents
        retriever = vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 5}  # Lấy top 5 chunks liên quan nhất
        )

        relevant_docs = retriever.get_relevant_documents(prompt)

        if not relevant_docs:
            return "🤔 Không tìm thấy thông tin liên quan trong cơ sở dữ liệu để trả lời câu hỏi của bạn."

        # Tạo response từ relevant documents
        response_parts = [
            f"📋 **Trả lời cho câu hỏi:** {prompt}\n",
            "🔍 **Thông tin liên quan từ cơ sở dữ liệu pháp luật:**\n"
        ]

        for i, doc in enumerate(relevant_docs):
            source = doc.metadata.get('source', 'N/A')
            location = doc.metadata.get('location', 'N/A')
            content = doc.page_content

            # Giới hạn độ dài nội dung hiển thị
            if len(content) > 1000:
                content = content[:1000] + "..."

            response_parts.append(f"""
**{i + 1}. Từ {source} - {location}:**
{content}
""")

        response_parts.append(
            f"\n💡 **Ghi chú:** Thông tin được trích xuất từ {len(relevant_docs)} đoạn văn bản liên quan nhất trong cơ sở dữ liệu.")

        return "\n".join(response_parts)

    except Exception as e:
        return f"❌ Lỗi xử lý câu hỏi: {str(e)}"


def generate_response_upload(prompt: str) -> str:
    """Placeholder cho chế độ upload file"""
    return ("📄 **Chế độ Upload File**\n\nTính năng này đang được phát triển. Hiện tại bạn có thể sử dụng chế độ "
            "'Pre-built Database' để test các câu hỏi với dữ liệu đã có sẵn.")


# Khởi tạo session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "mode" not in st.session_state:
    st.session_state.mode = "prebuilt"
if "vectorstore" not in st.session_state:
    # Auto-load vectorstore khi khởi động
    default_chunks_path = "ChiThi/final_chunks_for_embedding_semantic.jsonl"
    with st.spinner("🔄 Đang khởi tạo hệ thống..."):
        st.session_state.vectorstore = load_prebuilt_vectorstore(default_chunks_path, show_messages=False)

# Sidebar cho cấu hình
with st.sidebar:
    st.title("⚙️ Configuration")

    # Mode selection
    mode = st.radio(
        "Chọn chế độ hoạt động:",
        ["prebuilt", "upload"],
        format_func=lambda x: "🗂️ Pre-built Database" if x == "prebuilt" else "📁 Upload Files",
        index=0 if st.session_state.mode == "prebuilt" else 1
    )

    # Cập nhật mode nếu thay đổi
    if mode != st.session_state.mode:
        st.session_state.mode = mode
        st.session_state.messages = []  # Clear chat history khi đổi mode
        st.rerun()

    st.markdown("---")

    if mode == "prebuilt":
        st.markdown("### 🗂️ Pre-built Database")
        st.info("Sử dụng cơ sở dữ liệu pháp luật đã được xử lý sẵn")

        # Input path cho chunks file
        chunks_file_path = st.text_input(
            "Đường dẫn file chunks (JSONL):",
            value="db/chroma_db",
            help="Nhập đường dẫn tới file JSONL chứa các chunks đã xử lý"
        )

        # Load vectorstore button
        if st.button("🔄 Reload Vectorstore", type="primary"):
            with st.spinner("🔄 Đang reload vectorstore..."):
                vectorstore = load_prebuilt_vectorstore(chunks_file_path, show_messages=True)
                st.session_state.vectorstore = vectorstore
                if vectorstore:
                    st.success("✅ Vectorstore đã được reload thành công!")

        # Thông tin về vectorstore hiện tại
        if st.session_state.vectorstore:
            st.success("✅ Vectorstore đã sẵn sàng")
        else:
            st.warning("⚠️ Vectorstore không khả dụng")
            st.info("Có thể file chunks không tồn tại hoặc có lỗi khi load")

    else:  # upload mode
        st.markdown("### 📁 Upload Files")
        st.info("Upload file PDF để phân tích (Đang phát triển)")

        uploaded_file = st.file_uploader(
            "Upload PDF Document",
            type="pdf",
            help="Tính năng này đang được phát triển",
            disabled=True
        )
        st.markdown("*Tính năng này sẽ được hoàn thiện trong phiên bản tiếp theo*")

# Main interface
st.title("🔍 Legal RAG Assistant")
st.markdown("*Hệ thống hỏi đáp thông minh về văn bản pháp luật*")

# Hiển thị trạng thái dựa vào mode
if st.session_state.mode == "prebuilt":
    if st.session_state.vectorstore:
        st.success("✅ Hệ thống đã sẵn sàng! Bạn có thể đặt câu hỏi về các văn bản pháp luật.")
    else:
        st.error("❌ Không thể khởi tạo vectorstore. Vui lòng kiểm tra file chunks hoặc reload ở sidebar.")
else:
    st.info("📁 Chế độ Upload Files (Đang phát triển)")

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("Hỏi về văn bản pháp luật..."):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate response based on mode
    with st.chat_message("assistant"):
        with st.spinner("🤔 Đang tìm kiếm và phân tích..."):
            if st.session_state.mode == "prebuilt":
                response = generate_response_prebuilt(prompt, st.session_state.vectorstore)
            else:
                response = generate_response_upload(prompt)

        st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})

# Footer với hướng dẫn
st.markdown("---")
if st.session_state.mode == "prebuilt":
    st.markdown(
        "💡 **Hướng dẫn:** Hệ thống đã tự động load dữ liệu. Bạn có thể đặt câu hỏi ngay hoặc reload với file khác ở sidebar.")
else:
    st.markdown("💡 **Hướng dẫn:** Chế độ Upload đang được phát triển. Vui lòng sử dụng chế độ 'Pre-built Database'.")

# Ví dụ câu hỏi mẫu
with st.expander("💬 Ví dụ câu hỏi"):
    st.markdown("""
    **Ví dụ các câu hỏi bạn có thể thử:**
    - Chỉ thị 1722 nói về vấn đề gì?
    - Các quy định về kiểm soát thủ tục hành chính là gì?
    - Mức chuẩn nghèo áp dụng cho giai đoạn 2011-2015 như thế nào?
    - Ai là người ký Chỉ thị 1752?
    - Thời gian điều tra hộ nghèo được thực hiện khi nào?
    - Quy định về xử lý vi phạm trong lĩnh vực xây dựng?
    - Trách nhiệm của các bộ, ngành trong thực hiện chỉ thị?
    """)

# Clear chat button
if st.button("🗑️ Xóa lịch sử chat", key="clear_chat"):
    st.session_state.messages = []
    st.rerun()