from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database import get_db
from app.repo_mgmt.schemes.git_auth_mgmt import GitAuthResponse, GitAuthListResponse, GitAuthProvider
from app.repo_mgmt.services.git_auth_service import GitAuthService


router = APIRouter(prefix="/git-auth")

@router.post("/{provider}", response_model=GitAuthResponse)
async def save_git_auth(
    provider: str,
    user_id: str,
    access_token: str,
    db: AsyncSession = Depends(get_db)
):
    try:
        # 判断provider是否合法
        if provider not in GitAuthProvider.values():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"provider不合法 {provider}, 合法值为: {GitAuthProvider.values()}"
            )

        # 判断token是否为空
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="access_token不能为空"
            )

        # 判断user_id是否为空
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="user_id不能为空"
            )

        # 保存认证信息
        git_auth = await GitAuthService.save_git_auth(
            db,
            user_id,
            provider,
            access_token
        )
        return GitAuthResponse.from_orm(git_auth)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"保存{provider}认证信息失败: {str(e)}"
        )


@router.delete("/{provider}")
async def delete_git_auth(
    provider: str,
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """删除Git认证信息"""
    try:
        success = await GitAuthService.delete_git_auth(db, user_id, provider)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"未找到{provider}的认证信息"
            )
        
        return {"message": f"成功删除{provider}认证信息"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除{provider}认证信息失败: {str(e)}"
        )


@router.get("/", response_model=GitAuthListResponse)
async def get_user_git_auths(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取用户的所有Git认证信息"""
    try:
        items = await GitAuthService.get_user_git_auths(db, user_id)
        return GitAuthListResponse(
            items=[GitAuthResponse.model_validate(x) for x in items],
            total=len(items)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取Git认证信息失败: {str(e)}"
        )
