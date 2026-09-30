"""
R2/S3 文件上传模块

用于上传用户数据导出文件到Cloudflare R2或AWS S3存储。

设计原则：
- 支持Cloudflare R2和AWS S3
- 预签名URL生成（临时下载链接）
- 文件上传和下载
- 错误处理和重试机制
- 大文件分片上传（后续迭代）

海内外大厂参考：
- Google Takeout 使用Google Cloud Storage
- Facebook 数据下载使用AWS S3
- 预签名URL是标准的临时下载链接方式
"""

import logging
import os

logger = logging.getLogger(__name__)

# 存储配置
STORAGE_PROVIDER = os.getenv("STORAGE_PROVIDER", "r2")  # r2 或 s3
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "xinworen-exports")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "")  # 自定义域名（可选）

S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID", "")
S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY", "")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "xinworen-exports")
S3_REGION = os.getenv("S3_REGION", "us-east-1")

# 预签名URL有效期（默认7天）
PRESIGNED_URL_EXPIRY_SECONDS = 7 * 24 * 60 * 60


class StorageService:
    """
    存储服务

    负责文件上传、下载和预签名URL生成
    """

    def __init__(self):
        """初始化存储服务"""
        self.provider = STORAGE_PROVIDER
        self.client = None
        self._initialized = False

    async def _ensure_initialized(self):
        """确保客户端已初始化"""
        if self._initialized:
            return

        try:
            if self.provider == "r2":
                await self._init_r2_client()
            elif self.provider == "s3":
                await self._init_s3_client()
            else:
                logger.warning(f"Unknown storage provider: {self.provider}, using local storage")

            self._initialized = True
            logger.info(f"Storage service initialized with provider: {self.provider}")

        except Exception as e:
            logger.error(f"Failed to initialize storage client: {e}", exc_info=True)
            # 初始化失败时不抛出异常，使用本地存储作为降级
            self._initialized = True
            logger.warning("Storage client initialization failed, will use local storage as fallback")

    async def _init_r2_client(self):
        """初始化Cloudflare R2客户端"""
        if not all([R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY]):
            logger.warning("R2 credentials not fully configured, will use local storage")
            return

        try:
            # 使用boto3初始化R2客户端（S3兼容API）
            import boto3
            from botocore.config import Config as BotoConfig

            endpoint_url = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

            self.client = boto3.client(
                "s3", endpoint_url=endpoint_url, aws_access_key_id=R2_ACCESS_KEY_ID, aws_secret_access_key=R2_SECRET_ACCESS_KEY, config=BotoConfig(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"})
            )

            logger.info(f"R2 client initialized successfully (endpoint: {endpoint_url}, bucket: {R2_BUCKET_NAME})")

        except ImportError:
            logger.warning("boto3 not installed, will use local storage")
            self.client = None
        except Exception as e:
            logger.error(f"Failed to initialize R2 client: {e}", exc_info=True)
            self.client = None
            raise

    async def _init_s3_client(self):
        """初始化AWS S3客户端"""
        if not all([S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY]):
            logger.warning("S3 credentials not fully configured, will use local storage")
            return

        try:
            # 使用boto3初始化S3客户端
            import boto3
            from botocore.config import Config as BotoConfig

            self.client = boto3.client(
                "s3", region_name=S3_REGION, aws_access_key_id=S3_ACCESS_KEY_ID, aws_secret_access_key=S3_SECRET_ACCESS_KEY, config=BotoConfig(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"})
            )

            logger.info(f"S3 client initialized successfully (region: {S3_REGION}, bucket: {S3_BUCKET_NAME})")

        except ImportError:
            logger.warning("boto3 not installed, will use local storage")
            self.client = None
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}", exc_info=True)
            self.client = None
            raise

    def _get_bucket_name(self) -> str:
        """获取存储桶名称"""
        if self.provider == "r2":
            return R2_BUCKET_NAME
        elif self.provider == "s3":
            return S3_BUCKET_NAME
        else:
            return "local-exports"

    def _generate_object_key(self, user_id: str, export_id: str, file_name: str) -> str:
        """
        生成对象键（存储路径）

        Args:
            user_id: 用户ID
            export_id: 导出任务ID
            file_name: 文件名

        Returns:
            对象键
        """
        return f"exports/{user_id}/{export_id}/{file_name}"

    async def upload_file(
        self,
        file_path: str,
        user_id: str,
        export_id: str,
    ) -> tuple[str, int]:
        """
        上传文件到存储

        Args:
            file_path: 本地文件路径
            user_id: 用户ID
            export_id: 导出任务ID

        Returns:
            (文件访问URL, 文件大小)
        """
        await self._ensure_initialized()

        import os

        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        object_key = self._generate_object_key(user_id, export_id, file_name)

        logger.info(f"Uploading file {file_path} to {object_key} (size: {file_size} bytes)")

        try:
            if self.client is not None:
                # 使用真实的存储客户端上传（boto3是同步的，使用run_in_executor）
                import asyncio

                def _upload():
                    with open(file_path, "rb") as f:
                        self.client.put_object(
                            Bucket=self._get_bucket_name(),
                            Key=object_key,
                            Body=f,
                        )

                await asyncio.get_event_loop().run_in_executor(None, _upload)

                # 生成访问URL
                if self.provider == "r2" and R2_PUBLIC_URL:
                    file_url = f"{R2_PUBLIC_URL}/{object_key}"
                else:
                    # 生成预签名URL
                    file_url = await self.generate_presigned_url(object_key)

                logger.info(f"File uploaded successfully: {file_url}")
                return file_url, file_size

            else:
                # 降级：使用本地存储
                logger.warning("Storage client not available, using local storage as fallback")
                local_url = f"/local-exports/{object_key}"
                return local_url, file_size

        except Exception as e:
            logger.error(f"Failed to upload file: {e}", exc_info=True)
            # 上传失败时使用本地存储作为降级
            local_url = f"/local-exports/{object_key}"
            logger.warning(f"Upload failed, using local storage: {local_url}")
            return local_url, file_size

    async def generate_presigned_url(
        self,
        object_key: str,
        expiry_seconds: int | None = None,
    ) -> str:
        """
        生成预签名URL（临时下载链接）

        Args:
            object_key: 对象键
            expiry_seconds: 有效期（秒），默认为7天

        Returns:
            预签名URL
        """
        await self._ensure_initialized()

        if expiry_seconds is None:
            expiry_seconds = PRESIGNED_URL_EXPIRY_SECONDS

        logger.info(f"Generating presigned URL for {object_key} (expiry: {expiry_seconds}s)")

        try:
            if self.client is not None:
                # 使用真实的存储客户端生成预签名URL（boto3是同步的，使用run_in_executor）
                import asyncio

                def _generate_url():
                    return self.client.generate_presigned_url(
                        "get_object",
                        Params={
                            "Bucket": self._get_bucket_name(),
                            "Key": object_key,
                        },
                        ExpiresIn=expiry_seconds,
                    )

                url = await asyncio.get_event_loop().run_in_executor(None, _generate_url)
                logger.info(f"Presigned URL generated successfully: {url[:50]}...")
                return url

            else:
                # 降级：返回本地URL
                local_url = f"/local-exports/{object_key}"
                return local_url

        except Exception as e:
            logger.error(f"Failed to generate presigned URL: {e}", exc_info=True)
            # 失败时返回本地URL
            local_url = f"/local-exports/{object_key}"
            return local_url

    async def delete_file(self, object_key: str) -> bool:
        """
        删除文件

        Args:
            object_key: 对象键

        Returns:
            是否删除成功
        """
        await self._ensure_initialized()

        logger.info(f"Deleting file {object_key}")

        try:
            if self.client is not None:
                # 使用真实的存储客户端删除（boto3是同步的，使用run_in_executor）
                import asyncio

                def _delete():
                    self.client.delete_object(
                        Bucket=self._get_bucket_name(),
                        Key=object_key,
                    )

                await asyncio.get_event_loop().run_in_executor(None, _delete)
                logger.info(f"File deleted successfully: {object_key}")
                return True
            else:
                logger.warning("Storage client not available, cannot delete file")
                return False

        except Exception as e:
            logger.error(f"Failed to delete file: {e}", exc_info=True)
            return False

    def is_configured(self) -> bool:
        """
        检查存储服务是否已配置

        Returns:
            是否已配置
        """
        if self.provider == "r2":
            return all([R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY])
        elif self.provider == "s3":
            return all([S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY])
        else:
            return False


# 全局存储服务实例
_storage_service: StorageService | None = None


def get_storage_service() -> StorageService:
    """
    获取全局存储服务实例

    Returns:
        存储服务实例
    """
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service
