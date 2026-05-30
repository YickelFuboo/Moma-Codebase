from typing import Dict,List
from fastapi import APIRouter,Body,HTTPException,status
from app.code_analysis.services.repo_analysis_service import RepoAnalysisService


router = APIRouter(prefix="/repo-analysis")


@router.post("/{repo_id}/start-analysis")
async def start_repo_analysis(
    repo_id: str,
    target_rel_path: str | None = Body(default=None, embed=True),
) -> Dict[str, object]:
    """启动仓库源码分析。"""
    try:
        return await RepoAnalysisService.start_scan(
            repo_id=repo_id,
            target_rel_path=target_rel_path,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{repo_id}/summary")
async def get_repo_analysis_summary(repo_id: str) -> Dict[str, object]:
    """仓库扫描状态 + 各文件分析状态汇总。"""
    return await RepoAnalysisService.get_summary(repo_id)


@router.post("/{repo_id}/stop-scan")
async def stop_repo_scan(repo_id: str) -> Dict[str, object]:
    """停止仓库扫描（通过置 scan_status 触发协作取消）。"""
    try:
        return await RepoAnalysisService.stop_scan(repo_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail=str(e))


@router.delete("/{repo_id}/analysis-data")
async def clear_repo_analysis_data(repo_id: str) -> Dict[str, object]:
    """清空仓库的分析数据：文件分析状态 + 相关向量数据。"""
    try:
        await RepoAnalysisService.delete_repo_analysis_data(repo_id)
        return {"message":"清空分析数据成功"}
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail=str(e))
