from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.core.auth import AuthUser, get_current_user
from app.models.common import ok
from app.services import knowledge_base_service

router = APIRouter(prefix="/knowledge-base", tags=["knowledge-base"])


@router.get("")
async def get_overview(auth: AuthUser = Depends(get_current_user)) -> dict:
    overview = await knowledge_base_service.get_overview(auth.user_id)
    return ok(overview.model_dump())


@router.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    file_name: Optional[str] = Form(None),
    auth: AuthUser = Depends(get_current_user),
) -> dict:
    document = await knowledge_base_service.upload_document(
        auth.user_id, file, file_name=file_name
    )
    return ok(document.model_dump())


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str, auth: AuthUser = Depends(get_current_user)
) -> dict:
    await knowledge_base_service.delete_document(auth.user_id, doc_id)
    return ok(None)
