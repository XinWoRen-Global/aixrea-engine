import json
import os
import time
from typing import Annotated

import requests
from langchain.tools import InjectedToolCallId, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState

# Mock mode: return fake data instead of calling real APIs
MOCK_MODE = os.environ.get("DEERFLOW_MOCK_MODE", "false").lower() == "true"


@tool("generate_video", parse_docstring=True)
def generate_video_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    prompt: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    image_url: str | None = None,
    duration: int | None = 5,
    camera_fixed: bool | None = False,
    watermark: bool | None = True,
    resolution: str | None = "1080p",
    api_key: str = "88ae5ea0-4c3b-4079-bbe7-029ece6b947d",
) -> Command:
    """Generate a video from text prompt and optional image.

    Use this tool to generate videos using the VolcEngine Ark API.
    Automatically selects Seedance 1.0 Pro (supports images) when image_url is provided,
    otherwise uses Seedance 1.5 Pro.

    Args:
        prompt: The text description for video generation. Can include parameters like --camerafixed, --watermark
        image_url: Optional image URL for image-to-video generation
        duration: Video duration in seconds (default: 5)
        camera_fixed: Whether to use fixed camera (default: False)
        watermark: Whether to add watermark (default: True)
        resolution: Video resolution for Seedance 1.0 Pro (default: 1080p)
        api_key: VolcEngine ARK API Key
    """
    # Mock mode: return fake video URL
    if MOCK_MODE:
        import random

        mock_video_url = f"https://assets.mixkit.co/videos/preview/mixkit-{random.randint(1000, 9999)}-large.mp4"
        return Command(
            update={"messages": [ToolMessage(f"Video generated successfully! URL: {mock_video_url}", tool_call_id=tool_call_id)]},
        )

    base_url = "https://ark.cn-beijing.volces.com/api/v3"

    model_config = {
        "Seedance 1.0 Pro": ("doubao-seedance-1-0-pro-fast-251015", os.getenv("ARK_API_KEY", "")),
        "Seedance 1.5 Pro": (os.getenv("ARK_MODEL_ID", "ep-20260518150840-v4j4h"), os.getenv("ARK_API_KEY", "")),
    }
    use_image = bool(image_url and image_url.strip())
    if use_image:
        model_id, api_key = model_config["Seedance 1.0 Pro"]
    else:
        model_id, api_key = model_config["Seedance 1.5 Pro"]

    content = []
    if use_image:
        text_parts = [prompt]
        text_parts.append(f"--resolution {resolution}")
        text_parts.append(f"--camerafixed {str(camera_fixed).lower()}")
        text_parts.append(f"--watermark {str(watermark).lower()}")
        content.append({"type": "text", "text": " ".join(text_parts)})
        content.append({"type": "image_url", "image_url": {"url": image_url.strip()}})
    else:
        content.append({"type": "text", "text": f"{prompt} --camerafixed {str(camera_fixed).lower()} --watermark {str(watermark).lower()}"})

    create_url = f"{base_url}/contents/generations/tasks"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

    payload = {"model": model_id, "content": content}

    try:
        # Create video generation task
        response = requests.post(create_url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()

        if "id" not in result:
            return Command(
                update={"messages": [ToolMessage(f"Error creating video task: {result}", tool_call_id=tool_call_id)]},
            )

        task_id = result["id"]
        status = result.get("status", "UNKNOWN")

        if status == "SUCCEEDED":
            video_url = result.get("output", {}).get("video_url", "")
            if video_url:
                return Command(
                    update={"messages": [ToolMessage(f"Video generated successfully! URL: {video_url}", tool_call_id=tool_call_id)]},
                )
            return Command(
                update={"messages": [ToolMessage(f"Task succeeded but no video URL found: {result}", tool_call_id=tool_call_id)]},
            )

        # Poll for completion (async task)
        max_poll_attempts = 60  # 5 minutes (60 * 5 seconds)
        poll_interval = 5  # seconds

        for attempt in range(max_poll_attempts):
            time.sleep(poll_interval)

            poll_url = f"{base_url}/contents/generations/tasks/{task_id}"
            response = requests.get(poll_url, headers=headers, timeout=60)
            response.raise_for_status()
            result = response.json()

            status = result.get("status", "UNKNOWN")

            if status == "SUCCEEDED":
                video_url = result.get("output", {}).get("video_url", "")
                if video_url:
                    return Command(
                        update={"messages": [ToolMessage(f"Video generated successfully! URL: {video_url}", tool_call_id=tool_call_id)]},
                    )
                return Command(
                    update={"messages": [ToolMessage(f"Task succeeded but no video URL found: {json.dumps(result, indent=2)}", tool_call_id=tool_call_id)]},
                )

            elif status == "FAILED":
                error_msg = result.get("error", {}).get("message", "Unknown error")
                return Command(
                    update={"messages": [ToolMessage(f"Video generation failed: {error_msg}", tool_call_id=tool_call_id)]},
                )

            elif status == "CANCELLED":
                return Command(
                    update={"messages": [ToolMessage("Video generation was cancelled", tool_call_id=tool_call_id)]},
                )

            # Continue polling for PENDING/RUNNING

        return Command(
            update={"messages": [ToolMessage(f"Video generation timed out after {max_poll_attempts * poll_interval} seconds. Task ID: {task_id}", tool_call_id=tool_call_id)]},
        )

    except requests.exceptions.RequestException as e:
        return Command(
            update={"messages": [ToolMessage(f"Error calling video generation API: {str(e)}", tool_call_id=tool_call_id)]},
        )
