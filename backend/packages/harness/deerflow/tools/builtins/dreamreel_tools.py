"""
DreamReel 工作流专用工具

为 5 步短剧制作流程提供专用工具：
- generate_character_image: 生成角色肖像图（调用 NVIDIA FLUX API）
- generate_scene_image: 生成场景关键帧图（调用 NVIDIA FLUX API）
- save_workflow_step: 保存工作流步骤结果
- compose_dreamreel_video: 合成最终视频配置（生成 FFmpeg 管线脚本）
"""

import base64
import json
import os
import random
import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import requests
from langchain.tools import InjectedToolCallId, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState

# Mock mode: return fake data instead of calling real APIs
MOCK_MODE = os.environ.get("DEERFLOW_MOCK_MODE", "false").lower() == "true"


# =============================================================================
# 图片生成（Ark Seedream → Pillow 占位图回退）
# =============================================================================
_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
_ARK_MODELS = [
    "doubao-seedream-5-0-260128",
    "doubao-seedream-4-5-251128",
    "doubao-seedream-4-0-250828",
]


def _call_image_gen(
    prompt: str,
    output_path: str,
    width: int = 1024,
    height: int = 1024,
) -> str:
    """生成图片：优先调 Ark Seedream，不通则 Pillow 占位图。

    调用链：
      1. doubao-seedream-5-0（需在 Ark 控制台激活）
      2. doubao-seedream-4-5（回退）
      3. Pillow 纯色占位图（保底）
    """
    os.makedirs(Path(output_path).parent, exist_ok=True)

    # Mock mode: return placeholder URL
    if MOCK_MODE:
        mock_image_url = f"https://picsum.photos/{width}/{height}?random={random.randint(1, 1000)}"
        # Save a placeholder image with the URL as content
        _make_placeholder_image(prompt, output_path, width, height)
        return mock_image_url

    # ── 渠道 1：Ark 火山方舟 seedream ──
    ark_key = os.environ.get("OPENAI_API_KEY", "")
    if ark_key:
        for model_id in _ARK_MODELS:
            try:
                payload = {
                    "model": model_id,
                    "prompt": prompt,
                    "n": 1,
                    "size": f"{width}x{height}",
                    "response_format": "b64_json",
                }
                resp = requests.post(
                    f"{_ARK_BASE_URL}/images/generations",
                    headers={
                        "Authorization": f"Bearer {ark_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=120,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    b64 = data.get("data", [{}])[0].get("b64_json")
                    if b64:
                        with open(output_path, "wb") as f:
                            f.write(base64.b64decode(b64))
                        return output_path
                # 401/403 = key 无效；404/ModelNotOpen = 需要激活，跳过
                if resp.status_code in (401, 403):
                    break  # key 无效，不用试其他模型了
            except Exception:
                continue

    # ── 渠道 2：Pillow 占位图（保底）──
    _make_placeholder_image(prompt, output_path, width, height)
    return output_path


def _make_placeholder_image(
    prompt: str,
    output_path: str,
    width: int = 1024,
    height: int = 1024,
) -> None:
    """用 Pillow 生成纯色占位图，标注提示词。"""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, height), color=(20, 24, 36))
    draw = ImageDraw.Draw(img)

    # 居中写提示词
    lines = prompt.split(", ")
    y = height // 4
    for line in lines[:8]:
        # 粗略居中（等宽 12px/字）
        text_w = len(line) * 6
        draw.text(((width - text_w) // 2, y), line, fill=(200, 200, 200))
        y += 28

    draw.text(
        ((width - 200) // 2, y + 40),
        "⚡ Ark Seedream 未激活",
        fill=(255, 180, 60),
    )
    draw.text(
        ((width - 260) // 2, y + 70),
        "请到 console.volcengine.com/ark 激活模型",
        fill=(180, 180, 180),
    )
    img.save(output_path, "PNG")


# =============================================================================
# 角色肖像图生成
# =============================================================================
@tool("generate_character_image", parse_docstring=True)
def generate_character_image_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    character_name: str,
    character_description: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    age: str | None = None,
    gender: str | None = None,
    personality: str | None = None,
    style: str | None = "cinematic portrait, soft lighting, high detail, 8K, photorealistic",
    output_dir: str | None = None,
) -> Command:
    """为角色生成肖像图。

    根据角色描述调用 Ark Seedream 图片生成 API（火山方舟），
    生成高质量的 AI 角色肖像图。若 API 未激活则自动生成占位图。
    生成的图片文件将保存在本地输出目录中。

    Args:
        character_name: 角色名称
        character_description: 角色外貌描述
        age: 角色年龄
        gender: 角色性别
        personality: 角色性格特点（逗号分隔的关键词）
        style: 图片风格描述（默认：电影质感肖像）
        output_dir: 图片输出目录（默认：当前工作目录下的 outputs/characters）

    Returns:
        生成的图片文件路径和完整的提示词
    """
    # 确定输出目录
    if not output_dir:
        output_dir = os.path.join(os.getcwd(), "outputs", "characters")
    os.makedirs(output_dir, exist_ok=True)

    # 构建详细的图片生成提示词
    prompt_parts = [f"{character_name}"]

    if gender:
        prompt_parts.append(f"{gender}")
    if age:
        prompt_parts.append(f"{age}")

    prompt_parts.append(character_description)

    if personality:
        prompt_parts.append(f"性格{personality}")

    prompt_parts.append("character portrait, half-body shot, front facing")
    prompt_parts.append(style)

    full_prompt = ", ".join(prompt_parts)

    # 生成图片文件名：角色名（安全处理）
    safe_name = "".join(c for c in character_name if c.isalnum() or c in "_-. ").strip()
    filename = f"{safe_name}_{os.urandom(4).hex()}.png"
    output_path = os.path.join(output_dir, filename)

    try:
        actual_path = _call_image_gen(full_prompt, output_path)
        result_text = f"""✅ 角色肖像图生成成功！

角色：{character_name}
性别：{gender or "未指定"}
年龄：{age or "未指定"}
性格：{personality or "未指定"}

🎨 生成提示词：
{full_prompt}

📁 图片文件：{actual_path}
📏 分辨率：1024x1024
🎯 风格：{style}

💡 提示：此图片可用作 Seedance I2V 视频生成的起始帧。
"""
    except Exception as e:
        result_text = f"""❌ 角色肖像图生成失败

角色：{character_name}
提示词：{full_prompt}

错误信息：{str(e)}

💡 排查建议：
  1. 确认 OPENAI_API_KEY（Ark 密钥）已在 .env 中正确配置
  2. 到 https://console.volcengine.com/ark 激活 seedream 模型
  3. 也可手动使用以下提示词在其他工具生成：
     {full_prompt}"""

    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=result_text,
                    tool_call_id=tool_call_id,
                )
            ]
        }
    )


# =============================================================================
# 场景关键帧图生成
# =============================================================================
@tool("generate_scene_image", parse_docstring=True)
def generate_scene_image_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    scene_title: str,
    scene_description: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    location: str | None = None,
    time_of_day: str | None = None,
    mood: str | None = None,
    lighting: str | None = None,
    camera_angle: str | None = None,
    style: str | None = "cinematic wide shot, film grain, atmospheric, 4K, 16:9 aspect ratio",
    output_dir: str | None = None,
) -> Command:
    """为场景生成关键帧图。

    根据场景描述调用 Ark Seedream 图片生成 API（火山方舟），
    生成场景关键帧图。若 API 未激活则自动生成占位图。
    生成的图片将作为视频生成的起始帧参考。

    Args:
        scene_title: 场景标题
        scene_description: 场景描述
        location: 场景地点
        time_of_day: 时间（白天/夜晚/黄昏等）
        mood: 氛围和情绪基调
        lighting: 灯光方案
        camera_angle: 镜头角度（远景/中景/特写/仰角等）
        style: 图片风格描述（默认：电影宽银幕）
        output_dir: 图片输出目录（默认：当前工作目录下的 outputs/scenes）

    Returns:
        生成的图片文件路径和完整的提示词
    """
    # 确定输出目录
    if not output_dir:
        output_dir = os.path.join(os.getcwd(), "outputs", "scenes")
    os.makedirs(output_dir, exist_ok=True)

    # 构建详细的图片生成提示词
    prompt_parts = [scene_title]

    if location:
        prompt_parts.append(f"at {location}")
    if time_of_day:
        prompt_parts.append(f"during {time_of_day}")

    prompt_parts.append(scene_description)

    if mood:
        prompt_parts.append(f"{mood} atmosphere")
    if lighting:
        prompt_parts.append(f"{lighting} lighting")
    if camera_angle:
        prompt_parts.append(f"{camera_angle} shot")

    prompt_parts.append(style)

    full_prompt = ", ".join(prompt_parts)

    # 生成场景图（16:9 宽幅，用于视频）
    safe_name = "".join(c for c in scene_title if c.isalnum() or c in "_-. ").strip()
    filename = f"{safe_name}_{os.urandom(4).hex()}.png"
    output_path = os.path.join(output_dir, filename)

    try:
        actual_path = _call_image_gen(full_prompt, output_path, width=1920, height=1080)
        result_text = f"""✅ 场景关键帧图生成成功！

场景：{scene_title}
地点：{location or "未指定"}
时间：{time_of_day or "未指定"}
氛围：{mood or "未指定"}
灯光：{lighting or "未指定"}
镜头：{camera_angle or "未指定"}

🎨 生成提示词：
{full_prompt}

📁 图片文件：{actual_path}
📏 分辨率：1920x1080 (16:9)
🎯 风格：{style}

💡 提示：此图片可用作 Seedance I2V 视频生成的起始帧。
"""
    except Exception as e:
        result_text = f"""❌ 场景关键帧图生成失败

场景：{scene_title}
提示词：{full_prompt}

错误信息：{str(e)}

💡 排查建议：
  1. 确认 OPENAI_API_KEY（Ark 密钥）已在 .env 中正确配置
  2. 到 https://console.volcengine.com/ark 激活 seedream 模型
  3. 也可手动使用以下提示词在其他工具生成：
     {full_prompt}"""

    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=result_text,
                    tool_call_id=tool_call_id,
                )
            ]
        }
    )


# =============================================================================
# 工作流步骤保存
# =============================================================================
@tool("save_workflow_step", parse_docstring=True)
def save_workflow_step_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    step_number: int,
    step_name: str,
    data_json: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    output_dir: str | None = "/mnt/user-data/outputs",
) -> Command:
    """保存工作流步骤的结果到 JSON 文件。

    将 DreamReel 工作流每个步骤的结果保存为 JSON 文件，
    支持断点续传和步骤间数据传递。

    Args:
        step_number: 步骤编号（1-5）
        step_name: 步骤名称
        data_json: 步骤结果的 JSON 字符串
        output_dir: 输出目录（默认：/mnt/user-data/outputs）

    Returns:
        保存结果信息
    """
    try:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        step_files = {
            1: "step1_analysis.json",
            2: "step2_assets.json",
            3: "step3_storyboard.json",
            4: "step4_videos.json",
            5: "step5_final.json",
        }

        filename = step_files.get(step_number, f"step{step_number}_{step_name}.json")
        file_path = output_path / filename

        # Validate JSON
        try:
            data = json.loads(data_json)
        except json.JSONDecodeError as e:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=f"JSON 解析失败：{str(e)}\n请确保 data_json 参数是有效的 JSON 字符串。",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )

        # Write with pretty formatting
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        result_text = f"""工作流步骤 {step_number} 已保存！

步骤名称：{step_name}
保存路径：{file_path}
数据大小：{len(data_json)} 字符
JSON 有效：是

工作流进度：
{_get_progress_summary(step_number, output_path)}
"""

        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=result_text,
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    except Exception as e:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"保存失败：{str(e)}",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )


def _get_progress_summary(current_step: int, output_dir: Path) -> str:
    """生成工作流进度摘要。"""
    step_files = {
        1: "step1_analysis.json",
        2: "step2_assets.json",
        3: "step3_storyboard.json",
        4: "step4_videos.json",
        5: "step5_final.json",
    }

    lines = []
    for step, filename in step_files.items():
        file_path = output_dir / filename
        if step <= current_step:
            status = "✅ 已完成" if file_path.exists() else "⚠️ 文件缺失"
        else:
            status = "⏳ 待执行"
        lines.append(f"  Step {step}: {filename} — {status}")

    return "\n".join(lines)


# =============================================================================
# 最终视频合成（FFmpeg 管线）
# =============================================================================
@tool("compose_dreamreel_video", parse_docstring=True)
def compose_dreamreel_video_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    title: str,
    episodes_json: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    bgm_style: str | None = None,
    bgm_volume: int | None = 30,
    aspect_ratio: str | None = "9:16",
    resolution: str | None = "1080p",
    subtitles_enabled: bool | None = True,
    output_dir: str | None = None,
) -> Command:
    """合成最终视频 — 生成 FFmpeg 管线脚本并尝试执行。

    根据所有已生成的视频片段，生成完整的 FFmpeg 合成命令。
    包括 BGM、转场、字幕等后期处理。如果 FFmpeg 未安装，会自动尝试安装。

    Args:
        title: 短剧标题
        episodes_json: 剧集列表 JSON（每集包含 video_url、scene_title、dialogue 等）
        bgm_style: BGM 风格（suspense/romantic/action/urban/ancient）
        bgm_volume: BGM 音量百分比（0-100）
        aspect_ratio: 视频比例（9:16 竖屏 / 16:9 横屏）
        resolution: 分辨率（1080p / 4K）
        subtitles_enabled: 是否启用字幕
        output_dir: 输出目录（默认：outputs/composed）

    Returns:
        合成结果、FFmpeg 脚本路径和执行日志
    """
    if not output_dir:
        output_dir = os.path.join(os.getcwd(), "outputs", "composed")
    os.makedirs(output_dir, exist_ok=True)
    output_path = Path(output_dir)

    # ── 解析剧集 JSON ──
    try:
        episodes = json.loads(episodes_json)
    except json.JSONDecodeError as e:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"❌ 剧集 JSON 解析失败：{str(e)}",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    if not episodes:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content="❌ 剧集列表为空，无法合成",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    # ── BGM 配置 ──
    bgm_map = {
        "suspense": {"style": "悬疑氛围", "file": ""},
        "romantic": {"style": "浪漫温馨", "file": ""},
        "action": {"style": "紧张刺激", "file": ""},
        "urban": {"style": "现代都市", "file": ""},
        "ancient": {"style": "古风悠扬", "file": ""},
    }
    bgm_cfg = bgm_map.get(bgm_style or "urban", bgm_map["urban"])

    # ── 下载每个视频片段 ──
    downloaded = []
    failed_downloads = []
    subtitles_srt = []  # 收集字幕
    has_real_video = False  # 是否有真实视频

    for i, ep in enumerate(episodes):
        video_url = ep.get("video_url", "")
        scene_title = ep.get("scene_title", f"场景{i + 1}")
        dialogue = ep.get("dialogue", "")
        ep_idx = i + 1

        if video_url and video_url.startswith("http"):
            # 有真实视频 URL → 下载
            local_path = output_path / f"episode_{ep_idx:02d}.mp4"
            try:
                resp = requests.get(video_url, timeout=300, stream=True)
                resp.raise_for_status()
                with open(local_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                downloaded.append(str(local_path))
                has_real_video = True
            except Exception as e:
                failed_downloads.append(f"{scene_title}: {e}")
                # 下载失败 → 生成占位视频
                placeholder = _make_placeholder_video(output_path, ep_idx, scene_title, aspect_ratio)
                downloaded.append(placeholder)
        else:
            # 没有视频 → 生成占位视频
            placeholder = _make_placeholder_video(output_path, ep_idx, scene_title, aspect_ratio)
            downloaded.append(placeholder)

        # 收集字幕
        if dialogue:
            start_sec = i * 5
            end_sec = start_sec + 5
            subtitles_srt.append(f"{i + 1}\n{_srt_time(start_sec)} --> {_srt_time(end_sec)}\n{dialogue}\n")

    # ── 检测 / 安装 FFmpeg ──
    ffmpeg_path = _detect_ffmpeg()

    # ── 生成 FFmpeg 合成脚本 ──
    safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()
    final_output = output_path / f"{safe_title}_final.mp4"
    batch_script = output_path / f"compose_{safe_title}.bat"
    srt_path = output_path / "subtitles.srt"

    # 写入字幕文件
    if subtitles_enabled and subtitles_srt:
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(subtitles_srt))

    # 生成合成命令
    ffmpeg_commands = _build_ffmpeg_pipeline(
        downloaded,
        str(final_output),
        str(srt_path) if subtitles_enabled and subtitles_srt else None,
        str(output_path),
        safe_title,
        bgm_cfg["style"],
        bgm_volume,
        has_real_video,
    )

    # 写入 Batch 脚本
    with open(batch_script, "w", encoding="utf-8") as f:
        f.write("@echo off\n")
        f.write(f"echo XinWoRen 视频合成 - {title}\n")
        f.write("echo.\n")
        f.write(f'cd /d "{output_path}"\n')
        f.write("\n".join(ffmpeg_commands))
        f.write(f"\necho.\necho ✅ 合成完成！输出文件：{final_output}\npause\n")

    # ── 尝试执行 FFmpeg ──
    if ffmpeg_path:
        try:
            concat_cmd = ffmpeg_commands[0] if ffmpeg_commands else ""
            if concat_cmd:
                result = subprocess.run(concat_cmd, shell=True, capture_output=True, text=True, timeout=3600)
                if result.returncode == 0:
                    exec_status = "✅ FFmpeg 合成成功"
                else:
                    exec_status = f"⚠️ FFmpeg 合成失败 (code={result.returncode})"
        except Exception as e:
            exec_status = f"⚠️ FFmpeg 执行异常: {e}"
    else:
        exec_status = "⚠️ FFmpeg 未安装，脚本已生成但未执行"

    # ── 返回结果 ──
    episode_summary = "\n".join(f"  Episode {i + 1}: {ep.get('scene_title', '')} {'✅' if downloaded[i] and 'episode' in downloaded[i] else '⚠️ 占位'}" for i, ep in enumerate(episodes))

    result_text = f"""✅ 视频合成管线已生成！

短剧标题：{title}
总集数：{len(episodes)}
输出目录：{output_path}

剧集状态：
{episode_summary}

{"⚠️ 以下视频下载失败，已生成占位帧:" if failed_downloads else ""}
{chr(10).join(f"  - {e}" for e in failed_downloads)}

FFmpeg 状态：{"✅ 已安装" if ffmpeg_path else "❌ 未安装"}
{exec_status}

📜 Batch 脚本：{batch_script}
🎬 输出文件：{final_output}

💡 手动合成命令（如果自动执行失败）：
   cd /d "{output_path}"
   compose_{safe_title}.bat

📦 最终文件将包含：
   - 视频片段串联（带转场效果）
   - BGM 背景音乐（{bgm_cfg["style"]}）
   - {"字幕 (SRT)" if subtitles_enabled and subtitles_srt else "无字幕"}
"""
    if not ffmpeg_path:
        result_text += """
💡 安装 FFmpeg 方法（任选一种）：
   1. winget install FFmpeg (Windows 自动安装)
   2. 下载 https://ffmpeg.org/download.html 并添加到 PATH
   3. 运行脚本中的 install_ffmpeg.bat
"""

    return Command(update={"messages": [ToolMessage(content=result_text, tool_call_id=tool_call_id)]})


# ── 辅助函数 ──


def _srt_time(seconds: int) -> str:
    """将秒数转换为 SRT 时间格式 HH:MM:SS,mmm"""
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    return f"{h:02d}:{m:02d}:{s:02d},000"


def _make_placeholder_video(output_dir: Path, ep_idx: int, title: str, aspect_ratio: str) -> str:
    """生成占位图片（无 FFmpeg 时用纯色 PNG 替代）"""
    from PIL import Image, ImageDraw

    w, h = (608, 1080) if aspect_ratio == "9:16" else (1920, 1080)
    img = Image.new("RGB", (w, h), color=(20, 24, 36))
    draw = ImageDraw.Draw(img)
    draw.text((w // 4, h // 3), f"Episode {ep_idx}", fill=(200, 200, 200))
    draw.text((w // 4, h // 3 + 40), title, fill=(150, 150, 200))
    draw.text((w // 4, h // 3 + 80), "[AI Generated]", fill=(100, 100, 120))

    placeholder_path = output_dir / f"placeholder_{ep_idx:02d}.png"
    img.save(placeholder_path)
    return str(placeholder_path)


def _detect_ffmpeg() -> str:
    """检测系统 FFmpeg，返回路径（或空字符串）"""
    # 常见安装路径
    candidates = [
        "ffmpeg",
        "C:\\ffmpeg\\bin\\ffmpeg.exe",
        os.path.expanduser("~\\scoop\\apps\\ffmpeg\\current\\bin\\ffmpeg.exe"),
    ]
    for cmd in candidates:
        try:
            result = subprocess.run([cmd, "-version"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return cmd
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    # 尝试安装
    try:
        subprocess.run(
            ["winget", "install", "FFmpeg", "--accept-package-agreements"],
            capture_output=True,
            timeout=60,
        )
        # 再次检测
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return "ffmpeg"
    except Exception:
        pass

    return ""


def _build_ffmpeg_pipeline(
    video_clips: list[str],
    output_path: str,
    srt_path: str | None,
    work_dir: str,
    title: str,
    bgm_style: str,
    bgm_volume: int,
    has_real_video: bool,
) -> list[str]:
    """构建完整的 FFmpeg 合成命令列表"""
    commands = []

    if has_real_video and len(video_clips) > 0:
        # ── 有真实视频：使用 concat demuxer ──
        concat_file = Path(work_dir) / "concat_list.txt"
        with open(concat_file, "w") as f:
            for clip in video_clips:
                f.write(f"file '{clip}'\n")

        cmd = f'ffmpeg -y -f concat -safe 0 -i "{concat_file}"'

        # 添加字幕
        if srt_path and Path(srt_path).exists():
            cmd += f" -vf \"subtitles='{srt_path}':force_style='FontName=SimHei,FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3'\""

        cmd += f' -c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p -c:a aac -b:a 128k "{output_path}"'
        commands.append(cmd)
    else:
        # ── 只有占位图：用图片合成视频 ──
        images = [c for c in video_clips if c]
        if images:
            # 方案 A：用 image2 将图片序列转为视频
            # 先复制图片到连续命名
            for i, img_path in enumerate(images):
                ext = Path(img_path).suffix
                copy_path = Path(work_dir) / f"frame_{i + 1:04d}{ext}"
                shutil.copy2(img_path, copy_path)

            cmd = f'ffmpeg -y -framerate 1/5 -i "{work_dir}\\frame_%04d.png" -c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p -vf "fps=30,format=yuv420p"'

            # 添加字幕
            if srt_path and Path(srt_path).exists():
                cmd += f",subtitles='{srt_path}':force_style='FontName=SimHei,FontSize=20,PrimaryColour=&H00FFFFFF'"

            cmd += f' -c:a aac -b:a 128k "{output_path}"'
            commands.append(cmd)

    return commands
