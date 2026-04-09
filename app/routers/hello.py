from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def root():
    """Hello World接口"""
    return {"message": "Hello World"}


@router.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "healthy", "service": "ys-third-party-calls"}