"""
KMS 加密服务 — API Key 安全存储
支持本地 AES-256-GCM（开发/测试）+ AWS KMS（生产）
Envelope Encryption: data_key 加密明文 → master_key 加密 data_key
"""
import os
import json
import base64
import hashlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict
from enum import Enum

from utils.logger import get_logger

logger = get_logger("kms")

# 可选依赖
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

try:
    import boto3
    from botocore.exceptions import ClientError
    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False


class KMSMode(Enum):
    LOCAL = "local"
    AWS = "aws"


@dataclass
class KMSConfig:
    mode: KMSMode = KMSMode.LOCAL
    aws_region: str = "us-east-1"
    aws_key_id: str = ""
    local_key_path: str = "data/.keys/master.key"
    key_rotation_days: int = 90


@dataclass
class EncryptedPayload:
    """KMS 加密后的数据包 (Envelope Encryption)"""
    ciphertext: str
    data_key_encrypted: str
    algorithm: str = "AES-256-GCM"
    key_id: str = ""
    iv: str = ""
    tag: str = ""


class IKMSProvider(ABC):
    @abstractmethod
    def encrypt(self, plaintext: str, context: Dict[str, str] = None) -> EncryptedPayload: ...
    @abstractmethod
    def decrypt(self, payload: EncryptedPayload) -> str: ...
    @abstractmethod
    def rotate_key(self) -> bool: ...


class LocalKMSProvider(IKMSProvider):
    """本地 AES-256-GCM，延迟 <1ms"""

    def __init__(self, config: KMSConfig):
        self.config = config
        self._master_key: Optional[bytes] = None
        self._key_id = f"local-{hashlib.sha256(str(time.time()).encode()).hexdigest()[:16]}"
        self._load_or_create_master_key()

    def _load_or_create_master_key(self):
        key_file = self.config.local_key_path
        os.makedirs(os.path.dirname(key_file) or ".", exist_ok=True)
        if os.path.exists(key_file):
            with open(key_file, "rb") as f:
                self._master_key = f.read()
        else:
            if not CRYPTO_AVAILABLE:
                # 降级: 用 os.urandom 生成 key
                self._master_key = os.urandom(32)
                logger.warning("cryptography 未安装，使用 os.urandom 降级")
            else:
                self._master_key = AESGCM.generate_key(bit_length=256)
            with open(key_file, "wb") as f:
                f.write(self._master_key)
            os.chmod(key_file, 0o600)

    def encrypt(self, plaintext: str, context: Dict[str, str] = None) -> EncryptedPayload:
        if not CRYPTO_AVAILABLE:
            # 降级: base64 编码（不安全，仅开发用）
            logger.warning("KMS 降级模式: 无加密，仅 base64 编码")
            return EncryptedPayload(
                ciphertext=base64.b64encode(plaintext.encode()).decode(),
                data_key_encrypted="",
                algorithm="base64-fallback",
                key_id=self._key_id,
            )
        data_key = AESGCM.generate_key(bit_length=256)
        aesgcm_data = AESGCM(data_key)
        nonce_data = os.urandom(12)
        ciphertext = aesgcm_data.encrypt(nonce_data, plaintext.encode("utf-8"), None)
        aesgcm_master = AESGCM(self._master_key)
        nonce_master = os.urandom(12)
        encrypted_data_key = aesgcm_master.encrypt(nonce_master, data_key, None)
        return EncryptedPayload(
            ciphertext=base64.b64encode(ciphertext).decode(),
            data_key_encrypted=base64.b64encode(encrypted_data_key).decode(),
            algorithm="AES-256-GCM",
            key_id=self._key_id,
            iv=base64.b64encode(nonce_data).decode(),
            tag=base64.b64encode(nonce_master).decode(),
        )

    def decrypt(self, payload: EncryptedPayload) -> str:
        if payload.algorithm == "base64-fallback":
            return base64.b64decode(payload.ciphertext).decode("utf-8")
        if not CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography 未安装，无法解密")
        aesgcm_master = AESGCM(self._master_key)
        nonce_master = base64.b64decode(payload.tag)
        encrypted_data_key_bytes = base64.b64decode(payload.data_key_encrypted)
        data_key = aesgcm_master.decrypt(nonce_master, encrypted_data_key_bytes, None)
        aesgcm_data = AESGCM(data_key)
        nonce_data = base64.b64decode(payload.iv)
        ciphertext = base64.b64decode(payload.ciphertext)
        return aesgcm_data.decrypt(nonce_data, ciphertext, None).decode("utf-8")

    def rotate_key(self) -> bool:
        if not CRYPTO_AVAILABLE:
            return False
        self._master_key = AESGCM.generate_key(bit_length=256)
        self._key_id = f"local-{hashlib.sha256(str(time.time()).encode()).hexdigest()[:16]}"
        with open(self.config.local_key_path, "wb") as f:
            f.write(self._master_key)
        os.chmod(self.config.local_key_path, 0o600)
        logger.info("KMS master key 已轮换")
        return True


class AWSKMSProvider(IKMSProvider):
    """AWS KMS Envelope Encryption — 生产环境"""

    def __init__(self, config: KMSConfig):
        if not AWS_AVAILABLE:
            raise ImportError("请安装 boto3: pip install boto3")
        self.config = config
        self._client = boto3.client("kms", region_name=config.aws_region)
        self._key_id = config.aws_key_id

    def encrypt(self, plaintext: str, context: Dict[str, str] = None) -> EncryptedPayload:
        """AWS KMS GenerateDataKey + 本地 AES-GCM 加密"""
        if not CRYPTO_AVAILABLE:
            raise RuntimeError("AWS KMS 需要 cryptography 库")

        # 1. 生成数据密钥
        kms_params = {"KeyId": self._key_id, "KeySpec": "AES_256"}
        if context:
            kms_params["EncryptionContext"] = context
        response = self._client.generate_data_key(**kms_params)

        data_key = response["Plaintext"]       # 明文数据密钥
        encrypted_data_key = response["CiphertextBlob"]  # 加密的数据密钥

        # 2. 用数据密钥加密明文
        aesgcm = AESGCM(data_key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

        return EncryptedPayload(
            ciphertext=base64.b64encode(ciphertext).decode(),
            data_key_encrypted=base64.b64encode(encrypted_data_key).decode(),
            algorithm="AWS-KMS-AES-256-GCM",
            key_id=self._key_id,
            iv=base64.b64encode(nonce).decode(),
        )

    def decrypt(self, payload: EncryptedPayload) -> str:
        """AWS KMS Decrypt + 本地 AES-GCM 解密"""
        if not CRYPTO_AVAILABLE:
            raise RuntimeError("AWS KMS 需要 cryptography 库")

        # 1. 解密数据密钥
        kms_params = {"CiphertextBlob": base64.b64decode(payload.data_key_encrypted)}
        response = self._client.decrypt(**kms_params)
        data_key = response["Plaintext"]

        # 2. 用数据密钥解密密文
        aesgcm = AESGCM(data_key)
        nonce = base64.b64decode(payload.iv)
        ciphertext = base64.b64decode(payload.ciphertext)
        return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")

    def rotate_key(self) -> bool:
        """AWS KMS 自动密钥轮换（需在 AWS 控制台启用）"""
        try:
            self._client.enable_key_rotation(KeyId=self._key_id)
            logger.info(f"AWS KMS 密钥轮换已启用: {self._key_id}")
            return True
        except ClientError as e:
            logger.error(f"AWS KMS 密钥轮换失败: {e}")
            return False


class KMSService:
    """统一 KMS 服务入口（单例）"""
    _instance: Optional["KMSService"] = None

    def __new__(cls, config: KMSConfig = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config: KMSConfig = None):
        if self._initialized:
            return
        self.config = config or KMSConfig()
        if self.config.mode == KMSMode.AWS and AWS_AVAILABLE:
            try:
                self.provider: IKMSProvider = AWSKMSProvider(self.config)
                logger.info("KMS: AWS 模式")
            except Exception as e:
                logger.warning(f"AWS KMS 初始化失败，降级到本地: {e}")
                self.provider = LocalKMSProvider(self.config)
        else:
            self.provider = LocalKMSProvider(self.config)
            if self.config.mode == KMSMode.AWS:
                logger.warning("KMS: boto3 未安装，降级到本地模式")
        self._initialized = True

    def encrypt(self, plaintext: str, context: Dict[str, str] = None) -> EncryptedPayload:
        return self.provider.encrypt(plaintext, context)

    def decrypt(self, payload: EncryptedPayload) -> str:
        return self.provider.decrypt(payload)

    def rotate_key(self) -> bool:
        return self.provider.rotate_key()

    def get_mode(self) -> str:
        return self.config.mode.value

    @classmethod
    def reset(cls):
        cls._instance = None
