from typing import List

from pydantic import BaseModel, Field


class SimilarCodeSearchRequest(BaseModel):
    code_text: str = Field(..., description="用于相似检索的代码文本")
    top_k: int = Field(default=10, ge=1, le=100, description="返回结果条数")


class RelatedFilesSearchRequest(BaseModel):
    keywords: List[str] = Field(..., description="关键词或短语列表，分别向量化后取平均再检索")
    top_k: int = Field(default=10, ge=1, le=100, description="符号摘要与行块检索各取 top_k，合并后按文件路径与行号去重")
