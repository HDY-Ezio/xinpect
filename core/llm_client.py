#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM调用抽象层 v2.0
- 支持OpenAI兼容格式（DeepSeek/智谱/通义/OpenAI都兼容）
- 支持多模型按大脑分配：每个大脑可使用不同的大模型（如火山引擎API）
- 统一的chat接口，自动处理超时、重试、错误降级
- 纯标准库urllib实现，零外部依赖
- 调用失败自动降级，不影响主流程
- 向后兼容：不传brain_id时行为与v1.0完全一致
"""

import json
import logging
from coze_workload_identity import requests as _coze_requests
import socket
import urllib.parse
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

def _validate_api_url(url: str) -> str:
    """SEC: validate API URL to prevent SSRF."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid API URL scheme: {parsed.scheme}")
    if not parsed.hostname:
        raise ValueError("API URL missing hostname")
    return url


class LLMClient:
    """LLM API客户端
    
    支持所有OpenAI兼容格式的LLM API服务。
    配置参数从qa_config.json的llm_enhancement段或brain_models段读取。
    每个大脑可通过brain_models配置使用不同的模型。
    """
    
    def __init__(
        self,
        api_base: str = "",
        api_key: str = "",
        model: str = "",
        timeout: int = 15,
        max_retries: int = 2,
    ):
        self.api_base = api_base.rstrip('/') if api_base else ""
        self.api_key = api_key or ""
        self.model = model or ""
        self.timeout = timeout or 15
        self.max_retries = max_retries if max_retries >= 0 else 2
        self._available = None  # None=未检测, True=可用, False=不可用
        self.last_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }  # 每次chat()后记录token用量
    
    @property
    def is_configured(self) -> bool:
        """是否已配置API Key"""
        return bool(self.api_base and self.api_key and self.model)
    
    @property
    def is_available(self) -> bool:
        """LLM服务是否可用（已配置且探测通过）"""
        if not self.is_configured:
            return False
        if self._available is None:
            # 首次访问时做一次轻量探测
            self._available = self._probe()
        return self._available
    
    def _probe(self) -> bool:
        """轻量探测：发一条极简消息验证连通性"""
        try:
            result = self.chat(
                messages=[{"role": "user", "content": "ping"}],
                timeout=5,
            )
            return result is not None
        except Exception as e:  # noqa: broad exception handling
            return False
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        timeout: int = None,
    ) -> Optional[str]:
        """发送聊天请求，返回回复文本
        
        Args:
            messages: 消息列表，格式 [{"role": "user"/"system", "content": "..."}]
            temperature: 采样温度，默认0.1（低创造性，适合代码分析）
            timeout: 超时时间（秒），不指定则使用默认值
            
        Returns:
            成功返回回复字符串，失败返回None
        """
        if not self.is_configured:
            return None
        
        actual_timeout = timeout or self.timeout
        
        # 构造请求 (SEC: validate URL)
        url = _validate_api_url(f"{self.api_base}/chat/completions")
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        
        api_req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(api_req, timeout=actual_timeout) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    # 提取 usage 信息
                    usage = data.get("usage", {})
                    self.last_usage = {
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                    }
                    if content:
                        # 标记为可用
                        if self._available is not True:
                            self._available = True
                        return content.strip()
                    return None
            except urllib.error.HTTPError as e:
                last_error = f"HTTP {e.code}: {e.reason}"
                # 4xx错误不重试（配置错误/权限错误）
                if 400 <= e.code < 500:
                    break
            except urllib.error.URLError as e:
                last_error = f"URL Error: {e.reason}"
            except socket.timeout:
                last_error = "Timeout"
            except json.JSONDecodeError as e:
                last_error = f"JSON Parse Error: {e}"
                break  # 解析错误不重试
            except Exception as e:  # noqa: intentional catch-all
                last_error = f"Error: {e}"
        
        # 失败后标记为不可用（避免后续调用继续浪费时间）
        self._available = False
        return None
    
    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        timeout: int = None,
    ) -> Optional[Dict[str, Any]]:
        """发送聊天请求，期望返回JSON格式
        
        Args:
            messages: 消息列表
            temperature: 采样温度
            timeout: 超时时间
            
        Returns:
            成功返回解析后的dict，失败返回None
        """
        content = self.chat(messages, temperature, timeout)
        if not content:
            return None
        
        # 尝试提取JSON（处理LLM可能输出markdown代码块的情况）
        json_str = self._extract_json(content)
        if not json_str:
            return None
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None
    
    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        """从文本中提取JSON字符串
        
        处理LLM可能返回的各种格式：
        - 纯JSON: {"key": "value"}
        - Markdown代码块: ```json {...} ```
        - 前后带文字: 好的，结果是 {...}
        """
        if not text:
            return None
        
        text = text.strip()
        
        # 情况1：本身就是JSON对象
        if text.startswith('{') and text.endswith('}'):
            return text
        # 情况1b：本身就是数组
        if text.startswith('[') and text.endswith(']'):
            return text
        
        # 情况2：Markdown代码块
        import re
        m = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL | re.IGNORECASE)
        if m:
            json_candidate = m.group(1).strip()
            if json_candidate:
                return json_candidate
        
        # 情况3：从文本中找到第一个{到最后一个}（对象优先）
        start_obj = text.find('{')
        end_obj = text.rfind('}')
        start_arr = text.find('[')
        end_arr = text.rfind(']')
        
        # 检查数组和对象都有的话，取更早开始的那个
        candidates = []
        if start_obj != -1 and end_obj != -1 and end_obj > start_obj:
            candidates.append((start_obj, end_obj, text[start_obj:end_obj + 1]))
        if start_arr != -1 and end_arr != -1 and end_arr > start_arr:
            candidates.append((start_arr, end_arr, text[start_arr:end_arr + 1]))
        
        if not candidates:
            return None
        
        # 选择开始位置更早的
        candidates.sort(key=lambda x: x[0])
        return candidates[0][2]


def create_llm_client(config: dict, brain_id: str = "") -> LLMClient:
    """从配置创建LLM客户端
    
    支持按大脑分配不同模型。查找顺序：
    1. config["brain_models"][brain_id] → 大脑专属配置
    2. config["llm_enhancement"] → 全局默认配置
    
    Args:
        config: 完整的qa_config配置 或 llm_enhancement子配置
        brain_id: 大脑标识符，如 "brain1", "brain2" 等
        
    Returns:
        LLMClient实例
    """
    # 支持传入完整config或llm_enhancement子配置
    if isinstance(config, dict) and "llm_enhancement" in config:
        llm_cfg = config.get("llm_enhancement", {})
        brain_cfg = {}
        if brain_id:
            brain_models = config.get("brain_models", {})
            brain_cfg = brain_models.get(brain_id, {})
    else:
        llm_cfg = config if isinstance(config, dict) else {}
        brain_cfg = {}
    
    # 大脑配置覆盖全局配置
    return LLMClient(
        api_base=brain_cfg.get("api_base", llm_cfg.get("api_base", "")),
        api_key=brain_cfg.get("api_key", llm_cfg.get("api_key", "")),
        model=brain_cfg.get("model", llm_cfg.get("model", "")),
        timeout=int(brain_cfg.get("timeout", llm_cfg.get("timeout", 15))),
        max_retries=int(brain_cfg.get("max_retries", llm_cfg.get("max_retries", 2))),
    )


class SmartRouter:
    """智能路由 - 根据任务复杂度自动选择不同价位的模型
    
    内部持有多个 LLMClient 实例（按 tier 分层），
    调用方通过 tier 名称选择对应的 LLMClient。
    
    降级策略：
    - 请求的 tier 未配置 → 降级到 standard
    - standard 也未配置 → 降级到任意可用模型
    - 完全无多层级配置 → 所有 tier 使用同一模型（向后兼容）
    
    使用方式：
        router = create_smart_router(config)
        fast_client = router.get_client("fast")
        response = router.chat("fast", messages=[...])
    """
    
    DEFAULT_FALLBACK_CHAIN = ("standard", "fast", "strong")
    
    def __init__(self, tiers: Dict[str, LLMClient]):
        """初始化智能路由器
        
        Args:
            tiers: tier名称 -> LLMClient 映射
                   典型键: "fast", "standard", "strong"
        """
        self._tiers: Dict[str, LLMClient] = tiers
        self._route_log: List[Dict[str, str]] = []
        # 确定默认降级目标
        self._default_tier = "standard" if "standard" in tiers else next(iter(tiers), "")
    
    @property
    def available_tiers(self) -> List[str]:
        """当前可用的 tier 列表"""
        return list(self._tiers.keys())
    
    @property
    def is_multi_tier(self) -> bool:
        """是否配置了多层级（true=智能路由, false=单模型降级）"""
        return len(self._tiers) > 1
    
    def get_client(self, tier: str = "standard") -> Optional[LLMClient]:
        """获取指定 tier 的 LLMClient
        
        降级链: tier → standard → 任意可用
        如果指定 tier 存在但不可用（未配置），仍然返回该 client（由调用方判断 is_available）
        如果指定 tier 完全不存在于路由表中，执行降级。
        
        Args:
            tier: 层级名称，如 "fast", "standard", "strong"
            
        Returns:
            LLMClient 实例，无可用模型时返回 None
        """
        # 直接命中
        if tier in self._tiers:
            self._log_route(tier, tier, "direct")
            return self._tiers[tier]
        
        # 降级1: 尝试 standard
        reason = f"tier '{tier}' not configured"
        if "standard" in self._tiers:
            self._log_route(tier, "standard", reason)
            return self._tiers["standard"]
        
        # 降级2: 遍历 fallback chain
        for fallback in self.DEFAULT_FALLBACK_CHAIN:
            if fallback in self._tiers and fallback != "standard":
                self._log_route(tier, fallback, reason)
                return self._tiers[fallback]
        
        # 降级3: 任意可用
        for t_name, client in self._tiers.items():
            self._log_route(tier, t_name, reason)
            return client
        
        return None
    
    def _log_route(self, requested: str, actual: str, reason: str):
        """记录路由决策日志"""
        entry = {"requested": requested, "actual": actual, "reason": reason}
        self._route_log.append(entry)
        if requested != actual:
            logger.info(f"SmartRouter: '{requested}' → '{actual}' (fallback: {reason})")
        else:
            logger.debug(f"SmartRouter: '{requested}' → '{actual}' (direct)")
    
    def chat(
        self,
        tier: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        timeout: int = None,
    ) -> Optional[str]:
        """向指定 tier 的模型发送聊天请求（便捷方法）
        
        Args:
            tier: 模型层级
            messages: 消息列表
            temperature: 采样温度
            timeout: 超时时间
            
        Returns:
            成功返回回复字符串，失败返回 None
        """
        client = self.get_client(tier)
        if not client or not client.is_available:
            return None
        return client.chat(messages, temperature, timeout)
    
    def chat_json(
        self,
        tier: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        timeout: int = None,
    ) -> Optional[Dict[str, Any]]:
        """向指定 tier 的模型发送请求，期望返回 JSON（便捷方法）
        
        Args:
            tier: 模型层级
            messages: 消息列表
            temperature: 采样温度
            timeout: 超时时间
            
        Returns:
            成功返回解析后的 dict，失败返回 None
        """
        client = self.get_client(tier)
        if not client or not client.is_available:
            return None
        return client.chat_json(messages, temperature, timeout)
    
    def get_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取各层级使用统计
        
        Returns:
            {
                "fast": {"model": "...", "available": True, "last_usage": {...}},
                "standard": {...},
                ...
            }
        """
        stats = {}
        for tier_name, client in self._tiers.items():
            stats[tier_name] = {
                "model": client.model,
                "available": client.is_available,
                "configured": client.is_configured,
                "last_usage": dict(client.last_usage),
            }
        return stats
    
    def get_routing_info(self) -> Dict[str, str]:
        """获取路由表信息（用于日志/报告展示）
        
        Returns:
            {"fast": "model_name", "standard": "model_name", ...}
        """
        return {
            tier: client.model
            for tier, client in self._tiers.items()
        }


def create_smart_router(config: dict) -> SmartRouter:
    """从配置创建智能路由器
    
    读取 config["llm_enhancement"]["model_tiers"] 创建多层级路由。
    如果未配置 model_tiers，则降级为单模型（所有 tier 指向同一 LLMClient）。
    
    Args:
        config: 完整的 qa_config 配置 或 llm_enhancement 子配置
        
    Returns:
        SmartRouter 实例
    """
    # 支持传入完整 config 或 llm_enhancement 子配置
    if isinstance(config, dict) and "llm_enhancement" in config:
        llm_cfg = config["llm_enhancement"]
    else:
        llm_cfg = config if isinstance(config, dict) else {}
    
    model_tiers = llm_cfg.get("model_tiers", {})
    
    # 无多层级配置 → 降级为单模型（向后兼容）
    if not model_tiers:
        fallback_client = create_llm_client(config)
        return SmartRouter({
            "fast": fallback_client,
            "standard": fallback_client,
            "strong": fallback_client,
        })
    
    # 构建各层级的 LLMClient
    # 每个 tier 可以覆盖 api_base / api_key / model / timeout / max_retries
    # 未配置的字段从 llm_enhancement 全局配置继承
    tiers: Dict[str, LLMClient] = {}
    for tier_name in ("fast", "standard", "strong"):
        tier_cfg = model_tiers.get(tier_name, {})
        if not tier_cfg:
            continue
        
        api_base = tier_cfg.get("api_base") or llm_cfg.get("api_base", "")
        api_key = tier_cfg.get("api_key") or llm_cfg.get("api_key", "")
        model = tier_cfg.get("model") or llm_cfg.get("model", "")
        timeout = int(tier_cfg.get("timeout", llm_cfg.get("timeout", 15)))
        max_retries = int(tier_cfg.get("max_retries", llm_cfg.get("max_retries", 2)))
        
        if api_base and api_key and model:
            tiers[tier_name] = LLMClient(
                api_base=api_base,
                api_key=api_key,
                model=model,
                timeout=timeout,
                max_retries=max_retries,
            )
    
    # 如果解析出的层级不足，用全局配置补齐缺失 tier
    if not tiers:
        fallback_client = create_llm_client(config)
        return SmartRouter({
            "fast": fallback_client,
            "standard": fallback_client,
            "strong": fallback_client,
        })
    
    # 补齐未配置的 tier（指向已存在的最接近 tier 的 client）
    existing_clients = list(tiers.values())
    for tier_name in ("fast", "standard", "strong"):
        if tier_name not in tiers:
            # 复用第一个可用的 client
            tiers[tier_name] = existing_clients[0]
    
    router = SmartRouter(tiers)
    logger.info(f"SmartRouter created: {router.get_routing_info()}")
    return router


def is_llm_enabled(config: dict) -> bool:
    """检查LLM增强是否已启用且配置有效
    
    Args:
        config: 完整的qa_config配置
        
    Returns:
        True表示启用且配置了API Key
    """
    if not config:
        return False
    llm_cfg = config.get("llm_enhancement", {})
    if not llm_cfg.get("enabled", False):
        return False
    return bool(
        llm_cfg.get("api_base") 
        and llm_cfg.get("api_key") 
        and llm_cfg.get("model")
    )
