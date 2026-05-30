from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database import get_db
from app.repo_mgmt.schemes.git_repo_mgmt import CreateRepositoryFromUrl, UpdateRepository, RepositoryInfo
from app.repo_mgmt.services.git_repo_service import GitRepositoryService
from app.repo_mgmt.services.repo_resolver import RepoResolver

router = APIRouter(prefix="/git-repos")


@router.post("/create/url", response_model=RepositoryInfo)
async def create_repository_from_url(
    create_data: CreateRepositoryFromUrl,
    user_id: str = Query(..., description="用户ID"),
    db: AsyncSession = Depends(get_db)
):
    """通过Git URL创建仓库"""
    try:
        repository = await GitRepositoryService.create_repository_from_url(
            db, user_id, create_data
        )
        return repository
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("/create/package", response_model=RepositoryInfo)
async def create_repository_from_package(
    file: UploadFile = File(..., description="压缩包文件"),
    name: str = Form(..., description="仓库名称"),
    description: str = Form("", description="仓库描述"),
    user_id: str = Form(..., description="用户ID"),
    db: AsyncSession = Depends(get_db)
):
    """通过上传压缩包创建仓库"""
    try:
        # 验证文件类型
        if not file.filename.endswith(('.zip', '.tar.gz', '.tar')):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="只支持zip、tar.gz、tar格式的压缩包"
            )
        
        # 处理上传文件
        repository = await GitRepositoryService.create_repository_from_package(
            db, user_id, name, description, file
        )
        return repository
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("/create/path", response_model=RepositoryInfo)
async def create_repository_from_path(
    name: str = Form(..., description="仓库名称"),
    description: str = Form("", description="仓库描述"),
    folder_path: str = Form(..., description="服务端路径"),
    git_url: str = Form(..., description="Git URL地址"),
    user_id: str = Form(..., description="用户ID"),
    db: AsyncSession = Depends(get_db)
):
    """通过指定服务端路径创建仓库"""
    try:
        # 处理路径创建
        repository = await GitRepositoryService.create_repository_from_path(
            db, user_id, name, description, folder_path, git_url
        )
        return repository
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/list", response_model=List[RepositoryInfo])
async def get_repository_list(
    user_id: str = Query(..., description="用户ID"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    keyword: str = Query(None, description="搜索关键词"),
    db: AsyncSession = Depends(get_db)
):
    """获取仓库列表"""
    try:    
        repositories, total = await GitRepositoryService.get_repository_list(
            db, user_id, page, page_size, keyword
        )
        return repositories
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取仓库列表失败: {str(e)}"
        )

@router.get("/by-path", response_model=RepositoryInfo)
async def get_repository_by_path(
    repo_path: str = Query(..., description="代码仓本地路径"),
    user_id: str = Query(..., description="用户ID"),
    db: AsyncSession = Depends(get_db)
):
    """按本地路径获取仓库详情"""
    try:
        repository = await RepoResolver.get_by_path(db, repo_path)
        if not repository:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="仓库不存在"
            )
        if repository.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限获取仓库"
            )
        return repository
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取仓库失败: {str(e)}"
        )

@router.get("/{repository_id}", response_model=RepositoryInfo)
async def get_repository(
    repository_id: str,
    user_id: str = Query(..., description="用户ID"),
    db: AsyncSession = Depends(get_db)
):
    """获取仓库详情"""
    try:
        repository = await GitRepositoryService.get_repository_by_id(db, repository_id)
        if not repository:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="仓库不存在"
            )
        
        if repository.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限获取仓库"
            )
        
        return repository
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取仓库失败: {str(e)}"
        )

@router.put("/{repository_id}", response_model=RepositoryInfo)
async def update_repository(
    repository_id: str,
    update_data: UpdateRepository,
    user_id: str = Query(..., description="用户ID"),
    db: AsyncSession = Depends(get_db)
):
    """更新仓库"""
    try:
        repository = await GitRepositoryService.update_repository(db, repository_id, user_id, update_data)
        if not repository:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="仓库不存在"
            )
        
        return repository
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新仓库失败: {str(e)}"
        )

@router.delete("/{repository_id}")
async def delete_repository(
    repository_id: str,
    user_id: str = Query(..., description="用户ID"),
    delete_local: bool = Query(False, description="是否同步删除本地git目录内容"),
    db: AsyncSession = Depends(get_db)
):
    """删除仓库"""
    try:
        success = await GitRepositoryService.delete_repository(db, repository_id, user_id, delete_local=delete_local)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="仓库不存在"
            )
        
        return {"message": "仓库删除成功"} 
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除仓库失败: {str(e)}"
        )
