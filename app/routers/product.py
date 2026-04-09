from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.database import get_db
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate, ProductResponse, ProductListResponse

router = APIRouter(prefix="/products", tags=["商品管理"])


@router.post("/addProduct", response_model=ProductResponse, summary="新增商品")
def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    """新增商品（name、third_party_code 必填）"""
    # 检查第三方产品编码是否已存在
    if db.query(Product).filter(Product.third_party_code == product.third_party_code).first():
        raise HTTPException(status_code=400, detail="第三方产品编码已存在")

    db_product = Product(
        name=product.name,
        third_party_code=product.third_party_code,
        description=product.description,
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product


@router.get("/listProduct", response_model=ProductListResponse, summary="查询商品列表")
def list_products(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    keyword: Optional[str] = Query(None, description="搜索关键词（商品名称/第三方产品编码）"),
    is_published: Optional[bool] = Query(None, description="上架状态"),
    db: Session = Depends(get_db),
):
    """查询商品列表（支持分页、搜索、上架状态筛选）"""
    query = db.query(Product)

    # 关键词搜索
    if keyword:
        query = query.filter(
            or_(
                Product.name.contains(keyword),
                Product.third_party_code.contains(keyword),
            )
        )

    # 上架状态过滤
    if is_published is not None:
        query = query.filter(Product.is_published == is_published)

    # 统计总数
    total = query.count()

    # 分页查询
    products = query.order_by(Product.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return ProductListResponse(
        total=total,
        page=page,
        page_size=page_size,
        products=products,
    )


@router.get("/getProduct/{product_id}", response_model=ProductResponse, summary="查询单个商品")
def get_product(product_id: int, db: Session = Depends(get_db)):
    """根据ID查询商品"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    return product


@router.put("/updateProduct/{product_id}", response_model=ProductResponse, summary="修改商品")
def update_product(product_id: int, product: ProductUpdate, db: Session = Depends(get_db)):
    """修改商品信息"""
    db_product = db.query(Product).filter(Product.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="商品不存在")

    # 更新字段
    update_data = product.model_dump(exclude_unset=True)

    # 检查第三方产品编码是否重复
    if "third_party_code" in update_data and update_data["third_party_code"]:
        existing = db.query(Product).filter(Product.third_party_code == update_data["third_party_code"]).first()
        if existing and existing.id != product_id:
            raise HTTPException(status_code=400, detail="第三方产品编码已存在")

    for key, value in update_data.items():
        setattr(db_product, key, value)

    db.commit()
    db.refresh(db_product)
    return db_product


@router.put("/publishProduct/{product_id}", response_model=ProductResponse, summary="上架/下架商品")
def toggle_publish_product(product_id: int, db: Session = Depends(get_db)):
    """切换商品上架状态（True/False 切换）"""
    db_product = db.query(Product).filter(Product.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="商品不存在")

    # 切换上架状态
    db_product.is_published = not db_product.is_published

    db.commit()
    db.refresh(db_product)
    return db_product


@router.delete("/deleteProduct/{product_id}", summary="删除商品")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    """删除商品"""
    db_product = db.query(Product).filter(Product.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="商品不存在")

    db.delete(db_product)
    db.commit()
    return {"message": "商品删除成功"}