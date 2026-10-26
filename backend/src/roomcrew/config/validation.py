"""配置纯校验，不读取磁盘或调用模型。"""

from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from roomcrew.config.schema import ConfigurationError, ModelProfile


def validate_profile(values: dict[str, Any], previous: ModelProfile | None) -> ModelProfile:
    """因为用户输入不能直接交给 SDK，需要校验端点、凭据沿用和数值范围后建立不可变配置。"""
    # 1、检查端点和模型标识，不接受 URL 内嵌的认证信息。
    base_url = str(values.get("base_url", "")).strip().rstrip("/")
    model = str(values.get("model", "")).strip()
    label = str(values.get("label", "默认模型")).strip() or "默认模型"
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigurationError("Base URL 需要是完整接口地址，不能包含密钥、查询参数或片段")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ConfigurationError("远程接口必须使用 HTTPS；本机模型可以使用 HTTP")
    if not model or len(model) > 200 or len(label) > 80 or len(base_url) > 1000:
        raise ConfigurationError("请填写有效的模型 ID 和配置名称")
    # 2、空 Key 只允许沿用同一端点的现有凭据，避免改端点时误发旧凭据。
    key = str(values.get("api_key", "")).strip()
    if not key and previous and previous.base_url == base_url:
        key = previous.api_key
    if not key or len(key) > 4096 or "\n" in key or "\r" in key:
        raise ConfigurationError("请填写 API Key；更换接口地址时需要重新填写")
    try:
        timeout = int(values.get("timeout", 90))
        context_window = int(values.get("context_window", 32768))
    except (TypeError, ValueError) as error:
        raise ConfigurationError("超时和上下文窗口需要是整数") from error
    if not 10 <= timeout <= 600 or not 4096 <= context_window <= 2000000:
        raise ConfigurationError("超时范围为 10～600 秒，上下文窗口范围为 4096～2000000")
    proxy = str(values.get("proxy", "")).strip().rstrip("/")
    if proxy:
        proxy_url = urlsplit(proxy)
        if (
            proxy_url.scheme not in {"http", "https"}
            or not proxy_url.hostname
            or proxy_url.username
            or proxy_url.password
            or proxy_url.query
            or proxy_url.fragment
            or proxy_url.path
        ):
            raise ConfigurationError("代理地址需要是不含认证信息和路径的 HTTP(S) 地址")
    profile = ModelProfile(uuid4().hex, label, base_url, model, key, timeout, context_window, proxy)
    # 3、返回完整校验结果，文件存储由配置仓库负责。
    return profile
