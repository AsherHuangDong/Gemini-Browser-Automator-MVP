"""
Gemini API 客户端 - 使用 google-genai 库
支持多 API Key 循环容灾和文件上传
"""

import logging
import random
import pathlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict, Optional, Union

from google import genai
from google.genai import types

from exceptions import (
    APIKeyNotFoundError,
    APIKeyInvalidError,
    APIRateLimitError,
    APIQuotaExceededError,
    APINetworkError,
    APIServerError,
    APIResponseError,
    AllKeysExhaustedError,
)
from config import APIConfig


logger = logging.getLogger(__name__)


class KeyStatus(Enum):
    """API Key 健康状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    COOLDOWN = "cooldown"


@dataclass
class KeyHealth:
    """API Key 健康状态记录"""
    key: str
    key_hint: str = ""
    status: KeyStatus = KeyStatus.HEALTHY
    error_count: int = 0
    success_count: int = 0
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    cooldown_until: Optional[datetime] = None

    def __post_init__(self):
        if len(self.key) > 12:
            self.key_hint = f"{self.key[:8]}...{self.key[-4:]}"
        else:
            self.key_hint = "***"


class APIKeyPool:
    """API Key 循环容灾池"""
    
    def __init__(
        self,
        keys: List[str],
        strategy: str = "round_robin",
        error_threshold: int = 3,
        cooldown_seconds: int = 60,
    ):
        if not keys:
            raise APIKeyNotFoundError("API Key 列表为空")
        
        self.keys: List[KeyHealth] = [KeyHealth(key=key) for key in keys]
        self.strategy = strategy
        self.error_threshold = error_threshold
        self.cooldown_seconds = cooldown_seconds
        self.current_index = 0
        
        logger.info(f"APIKeyPool 初始化完成，共 {len(self.keys)} 个 Key，策略: {strategy}")
    
    def get_available_keys(self) -> List[KeyHealth]:
        """获取所有可用的 Key"""
        now = datetime.now()
        available = []
        
        for kh in self.keys:
            if kh.status == KeyStatus.UNHEALTHY:
                continue
            
            if kh.status == KeyStatus.COOLDOWN:
                if kh.cooldown_until and now >= kh.cooldown_until:
                    kh.status = KeyStatus.HEALTHY
                    kh.error_count = 0
                    logger.info(f"Key {kh.key_hint} 冷却结束，恢复使用")
                else:
                    continue
            
            available.append(kh)
        
        return available
    
    def get_available_key(self) -> str:
        """获取一个可用的 Key"""
        available = self.get_available_keys()
        
        if not available:
            raise AllKeysExhaustedError(f"所有 {len(self.keys)} 个 API Key 均不可用")
        
        if self.strategy == "round_robin":
            key_health = self._select_round_robin(available)
        elif self.strategy == "least_errors":
            key_health = self._select_least_errors(available)
        elif self.strategy == "random":
            key_health = self._select_random(available)
        else:
            key_health = available[0]
        
        logger.debug(f"选择 Key: {key_health.key_hint}")
        return key_health.key
    
    def _select_round_robin(self, available: List[KeyHealth]) -> KeyHealth:
        for _ in range(len(self.keys)):
            kh = self.keys[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.keys)
            if kh in available:
                return kh
        return available[0]
    
    def _select_least_errors(self, available: List[KeyHealth]) -> KeyHealth:
        return min(available, key=lambda k: k.error_count)
    
    def _select_random(self, available: List[KeyHealth]) -> KeyHealth:
        import random
        return random.choice(available)
    
    def report_success(self, key: str) -> None:
        """报告成功"""
        for kh in self.keys:
            if kh.key == key:
                kh.error_count = 0
                kh.success_count += 1
                kh.last_success_time = datetime.now()
                if kh.status == KeyStatus.DEGRADED:
                    kh.status = KeyStatus.HEALTHY
                    logger.info(f"Key {kh.key_hint} 恢复健康")
                logger.debug(f"Key {kh.key_hint} 请求成功")
                break
    
    def report_error(self, key: str, error: Exception) -> None:
        """报告错误"""
        for kh in self.keys:
            if kh.key == key:
                kh.error_count += 1
                kh.last_error = str(error)
                kh.last_error_time = datetime.now()
                
                if isinstance(error, APIKeyInvalidError):
                    kh.status = KeyStatus.UNHEALTHY
                    logger.warning(f"Key {kh.key_hint} 无效，已永久移出轮换")
                elif isinstance(error, APIQuotaExceededError):
                    kh.status = KeyStatus.COOLDOWN
                    kh.cooldown_until = datetime.now() + timedelta(seconds=self.cooldown_seconds)
                    logger.warning(f"Key {kh.key_hint} 配额用尽，进入冷却")
                elif isinstance(error, APIRateLimitError):
                    cooldown = error.retry_after or self.cooldown_seconds
                    kh.status = KeyStatus.COOLDOWN
                    kh.cooldown_until = datetime.now() + timedelta(seconds=cooldown)
                    logger.warning(f"Key {kh.key_hint} 触发速率限制，进入冷却")
                else:
                    if kh.error_count >= self.error_threshold:
                        if kh.error_count >= self.error_threshold * 2:
                            kh.status = KeyStatus.UNHEALTHY
                            logger.error(f"Key {kh.key_hint} 连续错误过多，已移出轮换")
                        else:
                            kh.status = KeyStatus.DEGRADED
                            logger.warning(f"Key {kh.key_hint} 已降级")
                break
    
    def get_pool_status(self) -> Dict:
        """获取池状态"""
        status_counts = {s.value: 0 for s in KeyStatus}
        key_details = []
        
        for kh in self.keys:
            status_counts[kh.status.value] += 1
            key_details.append({
                "key_hint": kh.key_hint,
                "status": kh.status.value,
                "error_count": kh.error_count,
                "success_count": kh.success_count,
                "last_error": kh.last_error,
            })
        
        return {
            "total_keys": len(self.keys),
            "status_counts": status_counts,
            "available_count": len(self.get_available_keys()),
            "strategy": self.strategy,
            "keys": key_details,
        }


class GeminiAPIClient:
    """Gemini API 客户端"""
    
    def __init__(self, key_pool: APIKeyPool, config: APIConfig):
        self.key_pool = key_pool
        self.config = config
        self._client_cache: Dict[str, genai.Client] = {}
    
    def _get_client(self, key: str) -> genai.Client:
        """获取客户端实例"""
        if key not in self._client_cache:
            self._client_cache[key] = genai.Client(api_key=key)
        return self._client_cache[key]
    
    def _handle_exception(self, e: Exception, key: str) -> None:
        """处理异常"""
        error_str = str(e).lower()
        
        if "api key" in error_str or "invalid" in error_str or "unauthorized" in error_str:
            raise APIKeyInvalidError(self._mask_key(key))
        elif "quota" in error_str or "resource exhausted" in error_str:
            raise APIQuotaExceededError(self._mask_key(key))
        elif "rate limit" in error_str or "too many requests" in error_str:
            raise APIRateLimitError()
        elif "timeout" in error_str or "network" in error_str:
            raise APINetworkError(str(e))
        elif "500" in error_str or "503" in error_str or "unavailable" in error_str:
            raise APIServerError(503)
        else:
            raise APIResponseError(f"错误: {e}")
    
    def chat(self, prompt: str, system_instruction: str = None) -> str:
        """发送对话请求"""
        max_attempts = len(self.key_pool.keys) * self.config.max_key_retries
        
        for attempt in range(max_attempts):
            key = self.key_pool.get_available_key()
            
            try:
                client = self._get_client(key)
                
                contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
                
                config_kwargs = {}
                if system_instruction:
                    config_kwargs["system_instruction"] = system_instruction
                
                response = client.models.generate_content(
                    model=self.config.model,
                    contents=contents,
                    config=types.GenerateContentConfig(**config_kwargs) if config_kwargs else None,
                )
                
                if response.text:
                    self.key_pool.report_success(key)
                    return response.text
                else:
                    raise APIResponseError("响应为空")
            
            except (APIKeyInvalidError, APIQuotaExceededError, APIRateLimitError) as e:
                self.key_pool.report_error(key, e)
                logger.info(f"切换 Key（原因: {type(e).__name__}）")
                continue
            
            except (APINetworkError, APIServerError) as e:
                wait_time = min(2 ** attempt, 10)
                logger.warning(f"临时错误，{wait_time}s 后重试: {e}")
                time.sleep(wait_time)
                continue
            
            except Exception as e:
                try:
                    self._handle_exception(e, key)
                except (APIKeyInvalidError, APIQuotaExceededError, APIRateLimitError) as ex:
                    self.key_pool.report_error(key, ex)
                    continue
                except (APINetworkError, APIServerError) as ex:
                    wait_time = min(2 ** attempt, 10)
                    time.sleep(wait_time)
                    continue
        
        raise AllKeysExhaustedError("所有 Key 均不可用")
    
    def stream_chat(self, prompt: str, system_instruction: str = None) -> str:
        """流式对话"""
        max_attempts = len(self.key_pool.keys) * self.config.max_key_retries
        
        for attempt in range(max_attempts):
            key = self.key_pool.get_available_key()
            
            try:
                client = self._get_client(key)
                
                contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
                
                config_kwargs = {}
                if system_instruction:
                    config_kwargs["system_instruction"] = system_instruction
                
                full_text = ""
                for chunk in client.models.generate_content_stream(
                    model=self.config.model,
                    contents=contents,
                    config=types.GenerateContentConfig(**config_kwargs) if config_kwargs else None,
                ):
                    if chunk.text:
                        print(chunk.text, end="", flush=True)
                        full_text += chunk.text
                
                print()
                self.key_pool.report_success(key)
                return full_text
            
            except (APIKeyInvalidError, APIQuotaExceededError, APIRateLimitError) as e:
                self.key_pool.report_error(key, e)
                continue
            
            except (APINetworkError, APIServerError) as e:
                wait_time = min(2 ** attempt, 10)
                logger.warning(f"临时错误，{wait_time}s 后重试: {e}")
                time.sleep(wait_time)
                continue
            
            except Exception as e:
                try:
                    self._handle_exception(e, key)
                except (APIKeyInvalidError, APIQuotaExceededError, APIRateLimitError) as ex:
                    self.key_pool.report_error(key, ex)
                    continue
                except (APINetworkError, APIServerError) as ex:
                    wait_time = min(2 ** attempt, 10)
                    time.sleep(wait_time)
                    continue
        
        raise AllKeysExhaustedError("流式请求失败")
    
    def upload_file(self, file_path: str) -> Dict:
        """上传文件"""
        path = pathlib.Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        key = self.key_pool.get_available_key()
        client = self._get_client(key)
        
        try:
            logger.info(f"正在上传文件: {path.name}")
            
            file_obj = client.files.upload(file=str(path))
            
            # 等待处理完成
            while file_obj.state == "PROCESSING":
                time.sleep(1)
                file_obj = client.files.get(name=file_obj.name)
            
            if file_obj.state == "FAILED":
                raise APIResponseError(f"文件处理失败: {file_obj.state}")
            
            self.key_pool.report_success(key)
            logger.info(f"文件上传成功: {file_obj.name}")
            
            return {
                "success": True,
                "file_name": path.name,
                "file_uri": file_obj.uri,
                "file_id": file_obj.name,
                "mime_type": file_obj.mime_type,
                "message": "文件上传成功",
            }
        
        except Exception as e:
            try:
                self._handle_exception(e, key)
            except Exception as ex:
                self.key_pool.report_error(key, ex)
                raise
            raise APIResponseError(f"上传失败: {e}")
    
    def chat_with_file(
        self,
        prompt: str,
        file_path: str = None,
        file_uri: str = None,
        system_instruction: str = None,
    ) -> str:
        """带文件的对话（流式输出）"""
        max_attempts = len(self.key_pool.keys) * self.config.max_key_retries
        
        for attempt in range(max_attempts):
            key = self.key_pool.get_available_key()
            
            try:
                client = self._get_client(key)
                
                # 处理文件
                file_obj = None
                if file_path:
                    path = pathlib.Path(file_path)
                    if path.exists():
                        logger.info(f"正在上传文件: {path.name}")
                        file_obj = client.files.upload(file=str(path))
                        logger.info(f"文件上传成功: {file_obj.name}")
                        
                        # 等待文件处理完成
                        while file_obj.state == "PROCESSING":
                            time.sleep(1)
                            file_obj = client.files.get(name=file_obj.name)
                            logger.debug(f"文件处理中: {file_obj.state}")
                        
                        if file_obj.state == "FAILED":
                            raise APIResponseError(f"文件处理失败: {file_obj.state}")
                        
                        logger.info(f"文件处理完成: {file_obj.state}")
                    else:
                        raise FileNotFoundError(f"文件不存在: {file_path}")
                elif file_uri:
                    # 通过 URI 获取文件（注意：必须是用同一个 Key 上传的）
                    file_obj = client.files.get(name=file_uri)
                    if file_obj.state == "PROCESSING":
                        while file_obj.state == "PROCESSING":
                            time.sleep(1)
                            file_obj = client.files.get(name=file_uri)
                            logger.debug(f"文件处理中: {file_obj.state}")
                
                # 构建内容
                parts = []
                if file_obj:
                    parts.append(types.Part(file_data=types.FileData(file_uri=file_obj.uri)))
                parts.append(types.Part(text=prompt))
                
                contents = [types.Content(role="user", parts=parts)]
                
                config_kwargs = {}
                if system_instruction:
                    config_kwargs["system_instruction"] = system_instruction
                
                # 使用流式输出
                full_text = ""
                for chunk in client.models.generate_content_stream(
                    model=self.config.model,
                    contents=contents,
                    config=types.GenerateContentConfig(**config_kwargs) if config_kwargs else None,
                ):
                    if chunk.text:
                        print(chunk.text, end="", flush=True)
                        full_text += chunk.text
                
                print()
                self.key_pool.report_success(key)
                return full_text
            
            except (APIKeyInvalidError, APIQuotaExceededError, APIRateLimitError) as e:
                self.key_pool.report_error(key, e)
                continue
            
            except (APINetworkError, APIServerError) as e:
                wait_time = min(2 ** attempt, 10)
                time.sleep(wait_time)
                continue
            
            except Exception as e:
                try:
                    self._handle_exception(e, key)
                except (APIKeyInvalidError, APIQuotaExceededError, APIRateLimitError) as ex:
                    self.key_pool.report_error(key, ex)
                    continue
                except (APINetworkError, APIServerError) as ex:
                    wait_time = min(2 ** attempt, 10)
                    time.sleep(wait_time)
                    continue
        
        raise AllKeysExhaustedError("请求失败")
    
    def list_files(self) -> List[Dict]:
        """列出已上传的文件"""
        key = self.key_pool.get_available_key()
        client = self._get_client(key)
        
        try:
            files = []
            for f in client.files.list():
                files.append({
                    "name": f.name,
                    "uri": f.uri,
                    "mime_type": f.mime_type,
                    "state": f.state,
                })
            return files
        except Exception as e:
            self._handle_exception(e, key)
    
    def delete_file(self, file_name: str) -> bool:
        """删除文件"""
        key = self.key_pool.get_available_key()
        client = self._get_client(key)
        
        try:
            client.files.delete(name=file_name)
            logger.info(f"文件已删除: {file_name}")
            return True
        except Exception as e:
            logger.error(f"删除文件失败: {e}")
            return False
    
    def _mask_key(self, key: str) -> str:
        if len(key) > 12:
            return f"{key[:8]}...{key[-4:]}"
        return "***"
    
    def get_pool_status(self) -> Dict:
        return self.key_pool.get_pool_status()
    
    def close(self) -> None:
        pass
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()