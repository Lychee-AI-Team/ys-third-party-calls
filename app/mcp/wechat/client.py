"""微信支付 v3 API 客户端 — 纯支付工具，不包含订单/充值业务逻辑"""
import base64
import json
import logging
import os
import time
import uuid
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, utils
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

WECHAT_PAY_BASE_URL = "https://api.mch.weixin.qq.com"


def _resolve_path(file_path: str) -> str:
    """将相对路径解析为基于项目根目录的绝对路径"""
    if not file_path:
        return ""
    if not os.path.isabs(file_path):
        return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), file_path)
    return file_path


class WeChatPayClient:
    """微信支付 v3 API 客户端"""

    def __init__(self):
        self.appid = settings.wechat_appid
        self.mchid = settings.wechat_mchid
        self.serial_no = settings.wechat_serial_no
        self.api_v3_key = settings.wechat_api_v3_key.encode("utf-8")
        self.notify_url = settings.wechat_notify_url

        # 从文件读取商户私钥
        key_path = _resolve_path(settings.wechat_private_key)
        with open(key_path, "r") as f:
            private_key_pem = f.read()
        self._private_key = serialization.load_pem_private_key(
            private_key_pem.encode("utf-8"),
            password=None,
        )

        # 微信支付公钥（回调验签用）
        self._public_key = None
        if settings.wechat_public_key:
            pub_key_path = _resolve_path(settings.wechat_public_key)
            with open(pub_key_path, "r") as f:
                public_key_pem = f.read()
            self._public_key = serialization.load_pem_public_key(
                public_key_pem.encode("utf-8"),
            )

        # 平台证书缓存 {serial_no: certificate_pem}（兼容旧版平台证书模式）
        self._platform_certs: dict = {}

    def _sign(self, method: str, url: str, body: str = "") -> str:
        """生成 Authorization 签名

        微信 v3 签名格式：HTTP请求方法\\nURL\\n请求时间戳\\n请求随机串\\n请求体\\n
        """
        timestamp = str(int(time.time()))
        nonce_str = uuid.uuid4().hex

        sign_message = f"{method}\n{url}\n{timestamp}\n{nonce_str}\n{body}\n"

        signature = self._private_key.sign(
            sign_message.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )

        signature_b64 = base64.b64encode(signature).decode("utf-8")

        authorization = (
            f'WECHATPAY2-SHA256-RSA2048 '
            f'mchid="{self.mchid}",'
            f'nonce_str="{nonce_str}",'
            f'timestamp="{timestamp}",'
            f'serial_no="{self.serial_no}",'
            f'signature="{signature_b64}"'
        )
        return authorization

    async def _request(self, method: str, url: str, body: dict = None) -> dict:
        """通用请求方法"""
        full_url = f"{WECHAT_PAY_BASE_URL}{url}"
        body_str = json.dumps(body, ensure_ascii=False) if body else ""

        authorization = self._sign(method, url, body_str)

        headers = {
            "Authorization": authorization,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method=method,
                url=full_url,
                headers=headers,
                content=body_str,
            )

        if response.status_code >= 400:
            logger.error(f"[WeChatPay] 请求失败: method={method}, url={url}, status={response.status_code}, body={response.text}")
            return {"error": True, "status_code": response.status_code, "message": response.text}

        try:
            return response.json()
        except json.JSONDecodeError:
            return {"raw_text": response.text}

    async def create_native_order(
        self,
        out_trade_no: str,
        description: str,
        total: int,
        notify_url: str = None,
    ) -> dict:
        """调用微信 Native 下单 API

        Args:
            out_trade_no: 商户订单号
            description: 商品描述
            total: 金额（单位：分）
            notify_url: 支付结果通知地址（可选，默认使用配置中的地址）

        Returns:
            包含 code_url（二维码链接）的字典
        """
        url = "/v3/pay/transactions/native"
        body = {
            "appid": self.appid,
            "mchid": self.mchid,
            "description": description,
            "out_trade_no": out_trade_no,
            "notify_url": notify_url or self.notify_url,
            "amount": {
                "total": total,
                "currency": "CNY",
            },
        }
        return await self._request("POST", url, body)

    async def query_order(self, out_trade_no: str) -> dict:
        """查询微信支付订单

        Args:
            out_trade_no: 商户订单号

        Returns:
            包含 trade_state（SUCCESS/NOTPAY/CLOSED 等）的字典
        """
        url = f"/v3/pay/transactions/out-trade-no/{out_trade_no}?mchid={self.mchid}"
        return await self._request("GET", url)

    async def close_order(self, out_trade_no: str) -> dict:
        """关闭微信支付订单

        Args:
            out_trade_no: 商户订单号

        Returns:
            关闭结果
        """
        url = f"/v3/pay/transactions/out-trade-no/{out_trade_no}/close"
        body = {
            "mchid": self.mchid,
        }
        return await self._request("POST", url, body)

    async def _fetch_platform_certificates(self) -> dict:
        """获取微信平台证书（首次收到回调时调用）"""
        url = "/v3/certificates"
        result = await self._request("GET", url)

        if result.get("error"):
            logger.error(f"[WeChatPay] 获取平台证书失败: {result}")
            return {}

        certs = {}
        for cert_data in result.get("data", []):
            serial_no = cert_data.get("serial_no")
            encrypt_cert = cert_data.get("encrypt_certificate", {})
            certificate_pem = self._decrypt_certificate(encrypt_cert)
            if certificate_pem:
                certs[serial_no] = certificate_pem

        self._platform_certs.update(certs)
        return certs

    def _decrypt_certificate(self, encrypt_cert: dict) -> str:
        """解密平台证书"""
        try:
            nonce = encrypt_cert["nonce"].encode("utf-8")
            ciphertext = base64.b64decode(encrypt_cert["ciphertext"])
            associated_data = encrypt_cert.get("associated_data", "").encode("utf-8")

            aesgcm = AESGCM(self.api_v3_key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data)
            return plaintext.decode("utf-8")
        except Exception as e:
            logger.error(f"[WeChatPay] 解密平台证书失败: {e}")
            return ""

    def verify_and_decrypt_callback(self, headers: dict, body: str) -> dict:
        """验签 + 解密回调数据

        Args:
            headers: HTTP 请求头（包含 Wechatpay-Signature, Wechatpay-Timestamp, Wechatpay-Nonce, Wechatpay-Serial）
            body: HTTP 请求体（原始 JSON 字符串）

        Returns:
            解密后的回调数据字典，验签失败返回 None
        """
        signature = headers.get("Wechatpay-Signature", headers.get("wechatpay-signature", ""))
        timestamp = headers.get("Wechatpay-Timestamp", headers.get("wechatpay-timestamp", ""))
        nonce = headers.get("Wechatpay-Nonce", headers.get("wechatpay-nonce", ""))
        serial_no = headers.get("Wechatpay-Serial", headers.get("wechatpay-serial", ""))

        if not all([signature, timestamp, nonce, serial_no]):
            logger.error("[WeChatPay] 回调头信息不完整")
            return None

        # 验签消息
        sign_message = f"{timestamp}\n{nonce}\n{body}\n"
        signature_bytes = base64.b64decode(signature)

        # 优先使用微信支付公钥验签（serial_no 以 PUB_KEY_ID_ 开头）
        if serial_no.startswith("PUB_KEY_ID_"):
            if not self._public_key:
                logger.error(f"[WeChatPay] 回调使用微信支付公钥验签，但未配置 WECHAT_PUBLIC_KEY")
                return None
            try:
                self._public_key.verify(
                    signature_bytes,
                    sign_message.encode("utf-8"),
                    padding.PKCS1v15(),
                    hashes.SHA256(),
                )
            except Exception as e:
                logger.error(f"[WeChatPay] 微信支付公钥验签失败: {e}")
                return None
        else:
            # 兼容平台证书模式
            cert_pem = self._platform_certs.get(serial_no)
            if not cert_pem:
                logger.error(f"[WeChatPay] 未缓存平台证书 serial_no={serial_no}，验签失败")
                return None
            try:
                from cryptography import x509
                cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
                public_key = cert.public_key()
                public_key.verify(
                    signature_bytes,
                    sign_message.encode("utf-8"),
                    padding.PKCS1v15(),
                    hashes.SHA256(),
                )
            except Exception as e:
                logger.error(f"[WeChatPay] 平台证书验签失败: {e}")
                return None

        # 解密回调数据
        try:
            body_data = json.loads(body)
            resource = body_data.get("resource", {})
            nonce = resource["nonce"].encode("utf-8")
            ciphertext = base64.b64decode(resource["ciphertext"])
            associated_data = resource.get("associated_data", "").encode("utf-8")

            aesgcm = AESGCM(self.api_v3_key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data)
            return json.loads(plaintext.decode("utf-8"))
        except Exception as e:
            logger.error(f"[WeChatPay] 回调解密失败: {e}")
            return None


# 模块级单例
_wechat_client: WeChatPayClient = None


def get_wechat_client() -> WeChatPayClient:
    """获取微信支付客户端单例"""
    global _wechat_client
    if _wechat_client is None:
        _wechat_client = WeChatPayClient()
    return _wechat_client
