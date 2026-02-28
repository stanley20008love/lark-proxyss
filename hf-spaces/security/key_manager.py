"""
密钥管理模块 (Key Manager)

安全存储和管理私钥、API 密钥等敏感信息

安全架构:
1. 环境变量存储 - 不硬编码
2. 内存加密 - 运行时保护
3. 访问日志 - 审计追踪
4. 密钥轮换 - 定期更新
"""
import os
import hashlib
import base64
import json
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class KeyType(Enum):
    """密钥类型"""
    PRIVATE_KEY = "private_key"
    API_KEY = "api_key"
    API_SECRET = "api_secret"
    LARK_APP_ID = "lark_app_id"
    LARK_APP_SECRET = "lark_app_secret"
    NVIDIA_API_KEY = "nvidia_api_key"
    PREDICT_API_KEY = "predict_api_key"


@dataclass
class KeyMetadata:
    """密钥元数据"""
    key_type: KeyType
    created_at: datetime
    last_accessed: datetime
    access_count: int = 0
    expires_at: Optional[datetime] = None
    rotation_interval_days: int = 90


class SecureKeyStorage:
    """
    安全密钥存储
    
    特性:
    - 从环境变量加载，不硬编码
    - 内存中加密存储
    - 访问审计日志
    - 支持密钥轮换提醒
    """
    
    # 敏感密钥列表 - 这些密钥必须从环境变量获取
    SENSITIVE_KEYS = [
        "PRIVATE_KEY",
        "POLYMARKET_PRIVATE_KEY",
        "API_SECRET",
        "LARK_APP_SECRET",
        "NVIDIA_API_KEY",
        "PREDICT_API_KEY",
        "HF_TOKEN",
        "GITHUB_TOKEN"
    ]
    
    def __init__(self, encryption_key: Optional[str] = None):
        """
        初始化安全存储
        
        Args:
            encryption_key: 可选的加密密钥 (用于内存加密)
        """
        self._keys: Dict[str, str] = {}
        self._metadata: Dict[str, KeyMetadata] = {}
        self._access_log: list = []
        self._encryption_key = encryption_key or self._generate_encryption_key()
        self._initialized = False
        
    def _generate_encryption_key(self) -> str:
        """生成内存加密密钥"""
        return base64.b64encode(os.urandom(32)).decode()
    
    def _encrypt_value(self, value: str) -> str:
        """简单加密 (XOR + Base64)"""
        key_bytes = self._encryption_key.encode()
        value_bytes = value.encode()
        encrypted = bytes([b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(value_bytes)])
        return base64.b64encode(encrypted).decode()
    
    def _decrypt_value(self, encrypted: str) -> str:
        """解密"""
        key_bytes = self._encryption_key.encode()
        encrypted_bytes = base64.b64decode(encrypted.encode())
        decrypted = bytes([b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(encrypted_bytes)])
        return decrypted.decode()
    
    def load_from_env(self) -> Dict[str, bool]:
        """
        从环境变量加载所有密钥
        
        Returns:
            加载状态字典
        """
        status = {}
        
        # 加载必需的密钥
        env_mappings = {
            "LARK_APP_ID": KeyType.LARK_APP_ID,
            "LARK_APP_SECRET": KeyType.LARK_APP_SECRET,
            "NVIDIA_API_KEY": KeyType.NVIDIA_API_KEY,
            "PRIVATE_KEY": KeyType.PRIVATE_KEY,
            "POLYMARKET_API_KEY": KeyType.API_KEY,
            "POLYMARKET_API_SECRET": KeyType.API_SECRET,
            "PREDICT_API_KEY": KeyType.PREDICT_API_KEY,
        }
        
        for env_key, key_type in env_mappings.items():
            value = os.getenv(env_key)
            if value:
                self._store_key(env_key, value, key_type)
                status[env_key] = True
                logger.info(f"✅ 已加载密钥: {env_key}")
            else:
                status[env_key] = False
                if env_key in ["LARK_APP_ID", "LARK_APP_SECRET"]:
                    logger.warning(f"⚠️ 密钥未配置: {env_key}")
        
        self._initialized = True
        return status
    
    def _store_key(self, name: str, value: str, key_type: KeyType):
        """存储密钥"""
        encrypted = self._encrypt_value(value)
        self._keys[name] = encrypted
        self._metadata[name] = KeyMetadata(
            key_type=key_type,
            created_at=datetime.now(),
            last_accessed=datetime.now(),
            rotation_interval_days=90
        )
    
    def get_key(self, name: str) -> Optional[str]:
        """
        获取密钥
        
        Args:
            name: 密钥名称
            
        Returns:
            解密后的密钥值
        """
        if name not in self._keys:
            # 尝试从环境变量获取
            value = os.getenv(name)
            if value:
                return value
            return None
        
        # 记录访问
        self._log_access(name)
        
        # 解密返回
        encrypted = self._keys[name]
        return self._decrypt_value(encrypted)
    
    def _log_access(self, name: str):
        """记录访问日志"""
        self._access_log.append({
            "key": name,
            "timestamp": datetime.now().isoformat(),
            "action": "access"
        })
        
        if name in self._metadata:
            self._metadata[name].last_accessed = datetime.now()
            self._metadata[name].access_count += 1
    
    def check_rotation_needed(self) -> Dict[str, bool]:
        """检查是否需要轮换密钥"""
        needs_rotation = {}
        now = datetime.now()
        
        for name, meta in self._metadata.items():
            days_since_created = (now - meta.created_at).days
            needs_rotation[name] = days_since_created >= meta.rotation_interval_days
            
            if needs_rotation[name]:
                logger.warning(f"⚠️ 密钥需要轮换: {name} (已使用 {days_since_created} 天)")
        
        return needs_rotation
    
    def mask_key(self, key: str, visible_chars: int = 4) -> str:
        """
        遮蔽密钥显示
        
        Args:
            key: 原始密钥
            visible_chars: 可见字符数
            
        Returns:
            遮蔽后的密钥
        """
        if not key or len(key) <= visible_chars * 2:
            return "***"
        return f"{key[:visible_chars]}...{key[-visible_chars:]}"
    
    def get_access_log(self, limit: int = 100) -> list:
        """获取访问日志"""
        return self._access_log[-limit:]
    
    def get_security_status(self) -> Dict[str, Any]:
        """获取安全状态"""
        return {
            "initialized": self._initialized,
            "keys_loaded": len(self._keys),
            "total_accesses": len(self._access_log),
            "keys_needing_rotation": sum(1 for v in self.check_rotation_needed().values() if v),
            "last_access": self._access_log[-1] if self._access_log else None
        }


class KeyManager:
    """
    密钥管理器
    
    统一管理所有密钥的访问
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._storage = SecureKeyStorage()
            cls._instance._storage.load_from_env()
        return cls._instance
    
    @classmethod
    def get(cls, key_name: str) -> Optional[str]:
        """获取密钥"""
        instance = cls()
        return instance._storage.get_key(key_name)
    
    @classmethod
    def get_masked(cls, key_name: str) -> str:
        """获取遮蔽的密钥 (用于日志显示)"""
        instance = cls()
        value = instance._storage.get_key(key_name)
        if value:
            return instance._storage.mask_key(value)
        return "***未配置***"
    
    @classmethod
    def get_status(cls) -> Dict:
        """获取安全状态"""
        instance = cls()
        return instance._storage.get_security_status()
    
    @classmethod
    def check_rotation(cls) -> Dict[str, bool]:
        """检查密钥轮换"""
        instance = cls()
        return instance._storage.check_rotation_needed()


# 全局单例
key_manager = KeyManager()
