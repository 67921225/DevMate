import os, time
import chromadb
from chromadb.utils import embedding_functions
from ..config import BASE_DIR

# 国内访问 HuggingFace 常超时，改用镜像站加载 bge 模型。
# 必须在创建 embedding 函数之前设置：sentence_transformers 加载/校验模型时
# 会访问 HF，不设镜像会直连 huggingface.co 而卡住（WinError 10060 超时）。
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

path = os.path.join(BASE_DIR, 'chroma')  # 指定存储路径

_embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="BAAI/bge-small-zh-v1.5"
)

# 普通的 Client 数据存在内存里， PersistentClient 数据存在磁盘里
_client = chromadb.PersistentClient(
    path = path,           
    )

_collection = _client.get_or_create_collection(
    name = "experiences",
    embedding_function = _embed_fn
    )

# 写入函数
def add_experience(task_id: int, description: str):
    _collection.upsert(            
        ids=[str(task_id)],
        documents=[description],
        metadatas=[{"task_id": task_id, "created_at": time.time()}],
    )

# 查询函数
def retrieve_experiences(query: str, k: int = 3) -> list[dict]:
    res = _collection.query(query_texts=[query], n_results=k)
    ids = res["ids"][0]
    documents = res["documents"][0]
    metadatas = res["metadatas"][0]
    
    result = []
    for i in range(len(ids)):
        result.append({
            "description": documents[i],
            "task_id": metadatas[i]["task_id"]
        })
    return result

def cleanup_expired(days: int = 30):
    """删除超过 days 天的记忆"""
    cutoff = time.time() - days * 86400
    _collection.delete(where={"created_at": {"$lt": cutoff}})