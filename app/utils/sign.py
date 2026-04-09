import hashlib
from typing import Dict, Any


def generate_sign(params: Dict[str, Any], apikey: str) -> str:
    """
    生成签名

    签名规则：
    1. 参数名按字母顺序排序
    2. 拼接参数值
    3. 结尾加apikey
    4. MD5加密后小写

    Args:
        params: 参数字典
        apikey: API密钥

    Returns:
        MD5签名（小写）
    """
    # 按参数名字母顺序排序
    sorted_keys = sorted(params.keys())

    # 拼接参数值
    values_str = "".join(str(params[key]) for key in sorted_keys)

    # 结尾加apikey
    sign_str = values_str + apikey

    # MD5加密后小写
    md5_hash = hashlib.md5(sign_str.encode('utf-8')).hexdigest().lower()

    return md5_hash