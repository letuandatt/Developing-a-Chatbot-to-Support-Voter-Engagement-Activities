import json
import uuid


def load_document_from_json(json_file):
    with open(json_file, 'r', encoding="utf-8") as json_f:
        documents = json.load(json_f)
    return documents


def save_document_for_rag(chunks, output_f):
    with open(output_f, 'w', encoding='utf-8') as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)


def flatten_document_for_rag(document):
    """
    Flatten a hierarchical document structure into a list of chunks suitable for RAG embedding.
    Each chunk contains the content, metadata, and hierarchical context.
    """
    metadata = document["metadata"]
    chunks = []

    # Process each chapter
    for chapter_idx, chapter in enumerate(document["chuong"]):
        chapter_id = chapter.get("ten_chuong", f"Chương {chapter_idx + 1}")
        chapter_title = chapter.get("tieu_de", "")

        # If chapter has direct content (title), create a chunk for it
        if chapter_title:
            chunk = {
                "chunk_id": str(uuid.uuid4()),
                "content": chapter_title,
                "metadata": metadata.copy(),
                "context": {
                    "level": "chuong",
                    "id": chapter_id,
                    "title": chapter_title,
                    "parent_id": None,
                    "parent_title": None
                }
            }
            chunks.append(chunk)

        # Process each section in the chapter
        for section_idx, section in enumerate(chapter.get("muc", [])):
            section_id = section.get("ten_muc", f"Mục {section_idx + 1}")
            section_title = section.get("tieu_de", "")

            # If section has direct content (title), create a chunk for it
            if section_title:
                chunk = {
                    "chunk_id": str(uuid.uuid4()),
                    "content": section_title,
                    "metadata": metadata.copy(),
                    "context": {
                        "level": "muc",
                        "id": section_id,
                        "title": section_title,
                        "parent_id": chapter_id,
                        "parent_title": chapter_title
                    }
                }
                chunks.append(chunk)

            # Process each clause in the section
            for clause_idx, clause in enumerate(section.get("khoan", [])):
                clause_id = clause.get("ten_khoan", f"Khoản {clause_idx + 1}")
                clause_title = clause.get("tieu_de", "")

                # If clause has direct content (title), create a chunk for it
                if clause_title:
                    chunk = {
                        "chunk_id": str(uuid.uuid4()),
                        "content": clause_title,
                        "metadata": metadata.copy(),
                        "context": {
                            "level": "khoan",
                            "id": clause_id,
                            "title": clause_title,
                            "parent_id": section_id,
                            "parent_title": section_title,
                            "chapter_id": chapter_id,
                            "chapter_title": chapter_title
                        }
                    }
                    chunks.append(chunk)

                # Process each point in the clause
                for point_idx, point in enumerate(clause.get("diem", [])):
                    # Points are directly content strings
                    if point:
                        chunk = {
                            "chunk_id": str(uuid.uuid4()),
                            "content": point,
                            "metadata": metadata.copy(),
                            "context": {
                                "level": "diem",
                                "id": f"Điểm {point_idx + 1}",
                                "parent_id": clause_id,
                                "parent_title": clause_title,
                                "section_id": section_id,
                                "section_title": section_title,
                                "chapter_id": chapter_id,
                                "chapter_title": chapter_title
                            }
                        }
                        chunks.append(chunk)

    return chunks


def process_document_for_rag(input_f, output_f):
    # Read the processed documents
    documents = load_document_from_json(input_f)

    all_chunks = []
    for doc_idx, document in enumerate(documents):
        print(f"Processing document {doc_idx + 1}/{len(documents)}")
        chunks = flatten_document_for_rag(document)
        all_chunks.extend(chunks)

    # Save the processed chunks
    save_document_for_rag(all_chunks, output_f)

    print(f"Processed {len(documents)} documents into {len(all_chunks)} chunks")
    print(f"Output saved to {output_file}")

    return len(all_chunks)


if __name__ == '__main__':
    input_file = "processed_documents.json"
    output_file = "processed_documents_for_rag.json"

    process_document_for_rag(input_file, output_file)
