"""Image validation and private storage (Supabase Storage + local fallback).

Only the generated storage key is ever stored in the database; the browser
supplied filename is never trusted. Two interchangeable backends implement the
same tiny interface:

* ``SupabaseImageStorage`` - uploads to the private ``complaint-photos``
  bucket using the server-side service-role key. Complaint photos are never
  public; the React app receives temporary signed URLs from the API instead.
* ``LocalImageStorage`` - filesystem fallback used by the test suite and for
  offline development (keeps the API working without a Supabase project).

Keys look like ``complaints/{complaint_id}/{uuid}.{ext}`` - complaint-scoped,
unique, and free of anything the browser sent.
"""

import logging
import uuid
from pathlib import Path
from typing import ClassVar, Protocol

from fastapi import HTTPException, UploadFile

from app.core.config import settings

logger = logging.getLogger(__name__)

# Canonical MIME types plus the common non-canonical alias some browsers send.
MIME_TO_EXTENSION: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
EXTENSION_TO_MIME: dict[str, str] = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


class ImageValidationError(Exception):
    pass


class StorageUnavailableError(Exception):
    """Raised when the storage backend cannot be reached during upload/download."""


def sniff_image_type(content: bytes) -> str | None:
    """Magic-byte sniffing so a renamed executable posing as .jpg is rejected."""
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def read_and_validate_upload(upload: UploadFile) -> tuple[bytes, str, str]:
    """Read the upload fully; return ``(content, mime_type, extension)``.

    The sniffed magic bytes are the source of truth for the extension; the
    declared Content-Type is only cross-checked, never trusted.
    """
    content = upload.file.read()
    upload.file.seek(0)

    if not content:
        raise ImageValidationError("The uploaded photo is empty.")
    if len(content) > settings.max_image_size_bytes:
        raise ImageValidationError(
            f"Photo is too large. Maximum allowed size is {settings.max_image_size_mb:g} MB."
        )

    sniffed = sniff_image_type(content)
    if sniffed is None:
        raise ImageValidationError("Photo content is not a valid JPEG, PNG or WebP image.")

    declared = (upload.content_type or "").lower()
    if declared and declared not in MIME_TO_EXTENSION and declared != "application/octet-stream":
        raise ImageValidationError("Photo must be a JPEG, PNG or WebP file.")
    if declared in MIME_TO_EXTENSION and MIME_TO_EXTENSION[declared] != MIME_TO_EXTENSION[sniffed]:
        raise ImageValidationError("Photo content does not match its declared file type.")

    return content, sniffed, MIME_TO_EXTENSION[sniffed]


def validate_upload_or_400(upload: UploadFile) -> tuple[bytes, str, str]:
    """Service-facing wrapper that turns validation errors into HTTP 400."""
    try:
        return read_and_validate_upload(upload)
    except ImageValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class ImageStorageBackend(Protocol):
    """Interface shared by the Supabase and local backends."""

    supports_signed_urls: ClassVar[bool]

    def save(self, complaint_id: int, content: bytes, extension: str) -> str:
        """Store validated content; return the storage key to persist."""

    def open_bytes(self, storage_key: str) -> bytes:
        """Read the stored object back as bytes."""

    def create_signed_url(self, storage_key: str, expires_in: int) -> str:
        """Temporary read URL for displaying a private photo."""


class LocalImageStorage:
    """Filesystem fallback used by tests and offline development."""

    supports_signed_urls: ClassVar[bool] = False

    def __init__(self) -> None:
        self.root = Path(settings.upload_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, complaint_id: int, content: bytes, extension: str) -> str:
        storage_key = self.build_key(complaint_id, extension)
        destination = self.resolve(storage_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        logger.info("Stored image locally %s (%d bytes)", storage_key, len(content))
        return storage_key

    @staticmethod
    def build_key(complaint_id: int, extension: str) -> str:
        return f"complaints/{complaint_id}/{uuid.uuid4().hex}.{extension}"

    def resolve(self, storage_key: str) -> Path:
        candidate = (self.root / storage_key).resolve()
        if self.root.resolve() not in candidate.parents:
            raise ValueError(f"Invalid storage key: {storage_key}")
        return candidate

    def open_bytes(self, storage_key: str) -> bytes:
        path = self.resolve(storage_key)
        if not path.exists():
            raise FileNotFoundError(storage_key)
        return path.read_bytes()

    def create_signed_url(self, storage_key: str, expires_in: int) -> str:
        raise NotImplementedError("Signed URLs require Supabase Storage.")


class SupabaseImageStorage:
    """Private Supabase Storage via the service-role key (server-side only)."""

    supports_signed_urls: ClassVar[bool] = True

    def __init__(self, client, bucket: str) -> None:  # noqa: ANN001 - supabase Client
        self._client = client
        self._bucket = bucket
        self._files = client.storage.from_(bucket)

    @staticmethod
    def build_key(complaint_id: int, extension: str) -> str:
        return f"complaints/{complaint_id}/{uuid.uuid4().hex}.{extension}"

    def save(self, complaint_id: int, content: bytes, extension: str) -> str:
        storage_key = self.build_key(complaint_id, extension)
        try:
            self._files.upload(
                storage_key,
                content,
                {"content-type": EXTENSION_TO_MIME[extension], "upsert": "false"},
            )
        except Exception as exc:  # storage3 raises Storage subclasses; keep generic
            raise StorageUnavailableError(f"Supabase Storage upload failed: {exc}") from exc
        logger.info("Uploaded %s to Supabase Storage (%d bytes)", storage_key, len(content))
        return storage_key

    def open_bytes(self, storage_key: str) -> bytes:
        try:
            return self._files.download(storage_key)
        except Exception as exc:
            raise FileNotFoundError(storage_key) from exc

    def create_signed_url(self, storage_key: str, expires_in: int) -> str:
        response = self._files.create_signed_url(storage_key, expires_in)
        if isinstance(response, dict):
            url = (
                response.get("signedURL")
                or response.get("signedUrl")
                or response.get("signed_url")
            )
        else:
            url = getattr(response, "signed_url", None) or getattr(response, "signedURL", None)
        if not url:
            raise StorageUnavailableError("Supabase did not return a signed URL.")
        if url.startswith("/"):
            url = f"{self._client.supabase_url.rstrip('/')}{url}"
        return url


_storage_instance: ImageStorageBackend | None = None


def get_image_storage() -> ImageStorageBackend:
    """Backend selected once per process: Supabase when configured, else local."""
    global _storage_instance
    if _storage_instance is None:
        if settings.supabase_configured:
            from supabase import create_client  # imported lazily: only needed here

            client = create_client(settings.supabase_url, settings.supabase_service_role_key)
            _storage_instance = SupabaseImageStorage(client, settings.supabase_storage_bucket)
            logger.info(
                "Supabase Storage ready (bucket=%s)", settings.supabase_storage_bucket
            )
        else:
            _storage_instance = LocalImageStorage()
            logger.info("Supabase not configured - using local storage fallback.")
    return _storage_instance


def reset_image_storage() -> None:
    """Test helper: forces the factory to rebuild the backend on next use."""
    global _storage_instance
    _storage_instance = None
