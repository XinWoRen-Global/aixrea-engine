"""
邮件服务模块

用于通过HTTP调用frontend的邮件服务API，发送各种通知邮件。

设计原则：
- 复用frontend已有的Resend邮件服务
- 通过HTTP API调用，避免重复实现邮件发送逻辑
- 支持重试机制和错误处理
- 海内外大厂参考：
  - Google Takeout 使用Google Workspace邮件服务
  - Facebook 数据下载使用AWS SES
  - 统一的邮件服务API是标准做法
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

# 邮件服务配置
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000")
EMAIL_SERVICE_API_KEY = os.getenv("EMAIL_SERVICE_API_KEY", "")
EMAIL_SERVICE_TIMEOUT = 30  # 秒
EMAIL_SERVICE_MAX_RETRIES = 3


class EmailService:
    """
    邮件服务

    通过HTTP调用frontend的邮件服务API，发送各种通知邮件。
    """

    def __init__(self):
        """初始化邮件服务"""
        self.base_url = FRONTEND_BASE_URL.rstrip("/")
        self.api_key = EMAIL_SERVICE_API_KEY
        self.timeout = EMAIL_SERVICE_TIMEOUT
        self.max_retries = EMAIL_SERVICE_MAX_RETRIES
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """获取HTTP客户端"""
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout,
            )

        return self._client

    async def send_email(
        self,
        to: str,
        subject: str,
        html: str,
        text: str | None = None,
        from_email: str | None = None,
        from_name: str | None = None,
        template_id: str | None = None,
        template_vars: dict[str, str] | None = None,
        locale: str = "en",
    ) -> bool:
        """
        发送邮件

        Args:
            to: 收件人邮箱
            subject: 邮件主题
            html: HTML格式的邮件内容
            text: 纯文本格式的邮件内容（可选）
            from_email: 发件人邮箱（可选）
            from_name: 发件人名称（可选）
            template_id: 邮件模板ID（可选）
            template_vars: 模板变量（可选）

        Returns:
            是否发送成功
        """
        logger.info(f"Sending email to {to}: {subject}")

        payload = {
            "to": to,
            "subject": subject,
            "html": html,
        }

        if text:
            payload["text"] = text
        if from_email:
            payload["from"] = from_email
        if from_name:
            payload["from_name"] = from_name
        if template_id:
            payload["template_id"] = template_id
        if template_vars:
            payload["template_vars"] = template_vars
        if locale and locale != "en":
            payload["locale"] = locale

        for attempt in range(self.max_retries):
            try:
                client = await self._get_client()
                response = await client.post(
                    "/api/email/send",
                    json=payload,
                )

                if response.status_code == 200:
                    result = response.json()
                    if result.get("success", False):
                        logger.info(f"Email sent successfully to {to}")
                        return True
                    else:
                        logger.warning(f"Email service returned error: {result.get('error', 'Unknown error')}")
                else:
                    logger.warning(f"Email service returned status {response.status_code}: {response.text}")

            except httpx.TimeoutException:
                logger.warning(f"Email service timeout (attempt {attempt + 1}/{self.max_retries})")
            except httpx.ConnectError:
                logger.warning(f"Email service connection error (attempt {attempt + 1}/{self.max_retries})")
            except Exception as e:
                logger.error(f"Failed to send email: {e}", exc_info=True)
                break

            if attempt < self.max_retries - 1:
                import asyncio

                await asyncio.sleep(2**attempt)  # 指数退避

        logger.error(f"Failed to send email to {to} after {self.max_retries} attempts")
        return False

    async def send_export_completion_email(
        self,
        to: str,
        export_id: str,
        file_url: str,
        file_size_str: str,
        user_name: str | None = None,
    ) -> bool:
        """
        发送数据导出完成通知邮件

        Args:
            to: 收件人邮箱
            export_id: 导出任务ID
            file_url: 文件下载链接
            file_size_str: 文件大小（格式化后的字符串）
            user_name: 用户名称（可选）

        Returns:
            是否发送成功
        """
        subject = "您的数据导出已完成 - 新我人"

        greeting = f"尊敬的{user_name}，您好！" if user_name else "尊敬的用户，您好！"

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px 10px 0 0; text-align: center; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                .info-box {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #667eea; }}
                .download-btn {{ display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; font-weight: bold; margin: 20px 0; }}
                .footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 30px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>数据导出完成</h1>
            </div>
            <div class="content">
                <p>{greeting}</p>
                <p>您请求的数据导出已完成，请点击下方按钮下载您的数据。</p>
                <div class="info-box">
                    <p><strong>导出任务ID：</strong>{export_id}</p>
                    <p><strong>文件大小：</strong>{file_size_str}</p>
                    <p><strong>有效期：</strong>7天</p>
                </div>
                <p style="text-align: center;">
                    <a href="{file_url}" class="download-btn">下载数据文件</a>
                </p>
                <p style="color: #666; font-size: 14px;">请注意：下载链接有效期为7天，请及时下载。如有任何问题，请联系客服。</p>
            </div>
            <div class="footer">
                <p>新我人团队 | XinWoRen</p>
                <p>此邮件由系统自动发送，请勿直接回复。</p>
            </div>
        </body>
        </html>
        """

        return await self.send_email(to=to, subject=subject, html=html)

    async def send_account_deletion_confirmation_email(
        self,
        to: str,
        confirmation_url: str,
        user_name: str | None = None,
    ) -> bool:
        """
        发送账户删除确认邮件

        Args:
            to: 收件人邮箱
            confirmation_url: 确认删除链接
            user_name: 用户名称（可选）

        Returns:
            是否发送成功
        """
        subject = "请确认您的账户删除请求 - 新我人"

        greeting = f"尊敬的{user_name}，您好！" if user_name else "尊敬的用户，您好！"

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; padding: 30px; border-radius: 10px 10px 0 0; text-align: center; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                .warning-box {{ background: #fff3cd; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #ffc107; }}
                .confirm-btn {{ display: inline-block; background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; font-weight: bold; margin: 20px 0; }}
                .footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 30px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>账户删除确认</h1>
            </div>
            <div class="content">
                <p>{greeting}</p>
                <p>我们收到了您的账户删除请求。为了确保是您本人操作，请点击下方按钮确认删除。</p>
                <div class="warning-box">
                    <p><strong>⚠️ 重要提示：</strong></p>
                    <ul>
                        <li>确认后，您的账户将在7天后被永久删除</li>
                        <li>删除后，您的所有数据将无法恢复</li>
                        <li>在7天内，您可以随时登录取消删除请求</li>
                    </ul>
                </div>
                <p style="text-align: center;">
                    <a href="{confirmation_url}" class="confirm-btn">确认删除账户</a>
                </p>
                <p style="color: #666; font-size: 14px;">如果您没有发起此请求，请忽略此邮件，您的账户不会受到影响。</p>
            </div>
            <div class="footer">
                <p>新我人团队 | XinWoRen</p>
                <p>此邮件由系统自动发送，请勿直接回复。</p>
            </div>
        </body>
        </html>
        """

        return await self.send_email(to=to, subject=subject, html=html)

    async def close(self):
        """关闭HTTP客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None


# 全局邮件服务实例
_email_service: EmailService | None = None


def get_email_service() -> EmailService:
    """获取全局邮件服务实例"""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service


async def close_email_service():
    """关闭全局邮件服务实例"""
    global _email_service
    if _email_service:
        await _email_service.close()
        _email_service = None
