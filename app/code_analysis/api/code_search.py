from typing import Dict,List
from fastapi import APIRouter, Body, HTTPException, status
from app.code_analysis.schemes.code_search import RelatedFilesSearchRequest, SimilarCodeSearchRequest
from app.code_analysis.services.code_search_service import CodeSearchService
from app.code_analysis.services.codegraph.graph_search import CodeGraphSearch


router = APIRouter(prefix="/code-search")


@router.post("/{repo_id}/similar-code")
async def search_similar_code(
    repo_id: str,
    payload: SimilarCodeSearchRequest,
) -> Dict[str, object]:
    """输入代码文本，在行块向量索引中做相似检索。"""
    try:
        return await CodeSearchService.search_similar_code(
            repo_id=repo_id,
            code_text=payload.code_text,
            top_k=payload.top_k,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{repo_id}/related-files")
async def search_related_files(
    repo_id: str,
    payload: RelatedFilesSearchRequest,
) -> Dict[str, object]:
    """用关键词在符号摘要向量与行块向量中检索，合并结果并按文件路径与行号去重。"""
    try:
        return await CodeSearchService.search_related_files(
            repo_id=repo_id,
            keywords=payload.keywords,
            top_k=payload.top_k,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{repo_id}/code-graph/dependents")
async def get_file_dependents(repo_id: str, file_path: str) -> Dict[str, object]:
    """查询依赖本文件的其他文件列表。"""
    with CodeGraphSearch() as q:
        res = await q.query_dependents_of_file(repo_id, file_path)
    if not res.result:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail=res.message or "query dependents failed")
    return res.content


@router.get("/{repo_id}/code-graph/dependented")
async def get_file_dependented(repo_id: str, file_path: str) -> Dict[str, object]:
    """查询本文件依赖的其他文件列表。"""
    with CodeGraphSearch() as q:
        res = await q.query_dependented_of_file(repo_id, file_path)
    if not res.result:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail=res.message or "query dependented failed")
    return res.content


@router.post("/{repo_id}/code-graph/file-summary")
async def get_files_summary(repo_id: str, file_paths: List[str] = Body(...,embed=True)) -> Dict[str, object]:
    """查询文件 summary（包含类/方法/顶层函数清单）。"""
    with CodeGraphSearch() as q:
        res = await q.query_file_summary(repo_id, file_paths)
    if not res.result:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail=res.message or "query file summary failed")
    return res.content
