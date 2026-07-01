from openai import OpenAI


def build_openai_client(api_base: str | None, api_key: str | None, timeout: float) -> OpenAI:
    if not api_base:
        raise RuntimeError("模型 API_BASE 未配置")
    return OpenAI(
        api_key=api_key or "EMPTY",
        base_url=api_base.rstrip("/"),
        timeout=timeout,
    )


def post_openai_compatible_json(
    api_base: str | None,
    api_key: str | None,
    timeout: float,
    path: str,
    body: dict,
) -> dict:
    client = build_openai_client(api_base, api_key, timeout)
    headers = {
        key: value
        for key, value in client.default_headers.items()
        if isinstance(value, str) and key.lower() not in {"content-length"}
    }
    response = client._client.post(
        str(client.base_url).rstrip("/") + "/" + path.lstrip("/"),
        headers=headers,
        json=body,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("模型接口返回格式不正确")
    return payload
