from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile

import httpx

from app.core.config import settings
from app.services.http_retry import request_with_retry, run_with_http_retry


DONE_STATES = {"done"}
FAILED_STATES = {"failed"}
RUNNING_STATES = {"waiting-file", "pending", "running", "converting"}
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
RESULT_DOWNLOAD_HEADERS = {"User-Agent": "zxgj-knowledge-import/1.0"}


@dataclass
class MinerUResult:
    file_name: str
    state: str
    full_zip_url: str | None = None
    err_msg: str | None = None


class MinerUClient:
    def __init__(
        self,
        token: str | None = None,
        api_base: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.token = token or settings.mineru_api_token
        if not self.token:
            raise RuntimeError("MINERU_API_TOKEN 未配置")
        self.api_base = (api_base or settings.mineru_api_base).rstrip("/")
        self.timeout_seconds = timeout_seconds or settings.mineru_timeout_seconds
        self.download_timeout_seconds = settings.mineru_download_timeout_seconds
        self.retry_attempts = settings.mineru_retry_attempts
        self.retry_backoff_seconds = settings.mineru_retry_backoff_seconds
        self.download_retry_attempts = settings.mineru_download_retry_attempts
        self.download_retry_backoff_seconds = settings.mineru_download_retry_backoff_seconds

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def create_upload_batch(
        self,
        files: list[Path],
        *,
        model_version: str | None = None,
        is_ocr: bool = False,
        enable_formula: bool = True,
        enable_table: bool = True,
        language: str = "ch",
    ) -> tuple[str, list[str]]:
        payload = {
            "files": [
                {
                    "name": path.name,
                    "data_id": path.stem[:128],
                    "is_ocr": is_ocr,
                    "enable_formula": enable_formula,
                    "enable_table": enable_table,
                    "language": language,
                    "model_version": model_version or settings.mineru_model_version,
                }
                for path in files
            ],
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = request_with_retry(
                client,
                "POST",
                f"{self.api_base}/api/v4/file-urls/batch",
                operation="MinerU 申请上传 URL",
                attempts=self.retry_attempts,
                backoff_seconds=self.retry_backoff_seconds,
                headers=self.headers,
                json=payload,
            )
            result = response.json()
        if result.get("code") != 0:
            raise RuntimeError(f"MinerU 申请上传 URL 失败：{result}")
        data = result.get("data") or {}
        batch_id = data.get("batch_id")
        file_urls = data.get("file_urls") or []
        if not batch_id or len(file_urls) != len(files):
            raise RuntimeError(f"MinerU 返回上传信息不完整：{result}")
        return batch_id, file_urls

    def upload_files(self, files: list[Path], upload_urls: list[str]) -> None:
        with httpx.Client(timeout=self.timeout_seconds) as client:
            for path, upload_url in zip(files, upload_urls, strict=True):

                def upload() -> None:
                    with path.open("rb") as file:
                        response = client.put(upload_url, content=file)
                    if response.status_code not in {200, 201}:
                        raise httpx.HTTPStatusError(
                            f"Unexpected status code {response.status_code}",
                            request=response.request,
                            response=response,
                        )

                run_with_http_retry(
                    f"MinerU 上传文件 {path.name}",
                    upload,
                    attempts=self.retry_attempts,
                    backoff_seconds=self.retry_backoff_seconds,
                )

    def poll_batch(
        self,
        batch_id: str,
        *,
        poll_interval_seconds: float | None = None,
        poll_timeout_seconds: float | None = None,
    ) -> list[MinerUResult]:
        interval = poll_interval_seconds or settings.mineru_poll_interval_seconds
        timeout = poll_timeout_seconds or settings.mineru_poll_timeout_seconds
        deadline = time.monotonic() + timeout
        last_results: list[MinerUResult] = []
        while time.monotonic() < deadline:
            last_results = self.get_batch_results(batch_id)
            if last_results and all(result.state in DONE_STATES | FAILED_STATES for result in last_results):
                return last_results
            time.sleep(interval)
        states = ", ".join(f"{result.file_name}:{result.state}" for result in last_results) or "无结果"
        raise TimeoutError(f"MinerU 解析超时，batch_id={batch_id}，当前状态：{states}")

    def get_batch_results(self, batch_id: str) -> list[MinerUResult]:
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = request_with_retry(
                client,
                "GET",
                f"{self.api_base}/api/v4/extract-results/batch/{batch_id}",
                operation=f"MinerU 查询解析结果 batch_id={batch_id}",
                attempts=self.retry_attempts,
                backoff_seconds=self.retry_backoff_seconds,
                headers=self.headers,
            )
            result = response.json()
        if result.get("code") != 0:
            raise RuntimeError(f"MinerU 查询结果失败：{result}")
        extract_results = (result.get("data") or {}).get("extract_result") or []
        return [
            MinerUResult(
                file_name=item.get("file_name") or "",
                state=item.get("state") or "",
                full_zip_url=item.get("full_zip_url"),
                err_msg=item.get("err_msg"),
            )
            for item in extract_results
        ]

    def download_markdown(self, full_zip_url: str, output_dir: Path, output_name: str) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        zip_path = output_dir / f"{Path(output_name).stem}.zip"
        self._download_result_zip(full_zip_url, zip_path, output_name)

        with zipfile.ZipFile(zip_path) as archive:
            markdown_name = next((name for name in archive.namelist() if name.endswith("full.md")), None)
            if markdown_name is None:
                raise RuntimeError(f"MinerU 结果 zip 中未找到 full.md：{full_zip_url}")
            markdown = archive.read(markdown_name).decode("utf-8", errors="replace")

        output_path = output_dir / output_name
        output_path.write_text(markdown, encoding="utf-8")
        return output_path

    def _download_result_zip(self, full_zip_url: str, zip_path: Path, output_name: str) -> None:
        operation = f"MinerU 下载解析结果 {output_name}"
        tmp_path = zip_path.with_name(f"{zip_path.name}.download")

        def download() -> None:
            tmp_path.unlink(missing_ok=True)
            try:
                self._download_result_zip_httpx(full_zip_url, tmp_path)
            except httpx.TransportError:
                tmp_path.unlink(missing_ok=True)
                self._download_result_zip_urllib(full_zip_url, tmp_path)
            self._ensure_valid_zip(tmp_path, full_zip_url)
            tmp_path.replace(zip_path)

        try:
            run_with_http_retry(
                operation,
                download,
                attempts=self.download_retry_attempts,
                backoff_seconds=self.download_retry_backoff_seconds,
            )
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def _download_result_zip_httpx(self, full_zip_url: str, tmp_path: Path) -> None:
        timeout = httpx.Timeout(self.download_timeout_seconds, connect=30.0)
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=RESULT_DOWNLOAD_HEADERS) as client:
            with client.stream("GET", full_zip_url) as response:
                response.raise_for_status()
                with tmp_path.open("wb") as file:
                    for chunk in response.iter_bytes():
                        if chunk:
                            file.write(chunk)

    def _download_result_zip_urllib(self, full_zip_url: str, tmp_path: Path) -> None:
        request = Request(full_zip_url, headers=RESULT_DOWNLOAD_HEADERS)
        httpx_request = httpx.Request("GET", full_zip_url)
        try:
            with urlopen(request, timeout=self.download_timeout_seconds) as response:
                with tmp_path.open("wb") as file:
                    shutil.copyfileobj(response, file, DOWNLOAD_CHUNK_SIZE)
        except HTTPError as exc:
            detail = exc.read(500) if hasattr(exc, "read") else b""
            raise httpx.HTTPStatusError(
                f"HTTP {exc.code}",
                request=httpx_request,
                response=httpx.Response(exc.code, content=detail, request=httpx_request),
            ) from exc
        except (URLError, TimeoutError, OSError, ssl.SSLError) as exc:
            raise httpx.TransportError(str(exc), request=httpx_request) from exc

    def _ensure_valid_zip(self, tmp_path: Path, full_zip_url: str) -> None:
        request = httpx.Request("GET", full_zip_url)
        if not tmp_path.exists() or tmp_path.stat().st_size == 0:
            raise httpx.TransportError("下载结果为空", request=request)
        if not zipfile.is_zipfile(tmp_path):
            raise httpx.TransportError("下载结果不是有效 zip 文件", request=request)

    def parse_local_files(self, files: list[Path], output_dir: Path) -> list[Path]:
        batch_id, upload_urls = self.create_upload_batch(files)
        self.upload_files(files, upload_urls)
        results = self.poll_batch(batch_id)
        print(results)
        by_name = {result.file_name: result for result in results}
        output_paths: list[Path] = []
        for path in files:
            result = by_name.get(path.name)
            if result is None:
                raise RuntimeError(f"MinerU 未返回文件结果：{path.name}")
            if result.state != "done" or not result.full_zip_url:
                raise RuntimeError(f"MinerU 解析失败：{path.name} state={result.state} err={result.err_msg}")
            output_paths.append(self.download_markdown(result.full_zip_url, output_dir, f"{path.stem}.md"))
        return output_paths
