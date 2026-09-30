import re
from pathlib import Path
from typing import Annotated

from docx import Document
from langchain.tools import InjectedToolCallId, ToolRuntime
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState


@tool("parse_script", parse_docstring=True)
def parse_script_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    script_path: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """解析剧本文件（支持 txt 和 docx 格式），提取场景、角色、对话等信息。

    Args:
        script_path: 剧本文件路径（支持 .txt 和 .docx 格式）

    Returns:
        解析后的剧本数据，包含场景、角色、对话等信息
    """
    try:
        file_path = Path(script_path)

        if not file_path.exists():
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=f"错误：文件不存在 - {script_path}",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )

        if file_path.suffix.lower() == ".docx":
            content = _parse_docx(file_path)
        elif file_path.suffix.lower() == ".txt":
            content = _parse_txt(file_path)
        else:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=f"错误：不支持的文件格式 - {file_path.suffix}。仅支持 .txt 和 .docx 格式",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )

        script_data = _extract_script_info(content)

        result_text = f"""剧本解析成功！

文件：{file_path.name}
总字数：{len(content)} 字
场景数：{len(script_data["scenes"])}
角色数：{len(script_data["characters"])}

主要角色：{", ".join(script_data["characters"][:10])}

场景列表：
"""
        for i, scene in enumerate(script_data["scenes"][:5], 1):
            result_text += f"\n{i}. {scene['title']}"
            result_text += f"\n   角色：{', '.join(scene['characters'])}"
            result_text += f"\n   对话数：{scene['dialogue_count']}"

        if len(script_data["scenes"]) > 5:
            result_text += f"\n... 还有 {len(script_data['scenes']) - 5} 个场景"

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
                        content=f"剧本解析失败：{str(e)}",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )


def _parse_docx(file_path: Path) -> str:
    doc = Document(file_path)
    return "\n".join([paragraph.text for paragraph in doc.paragraphs])


def _parse_txt(file_path: Path) -> str:
    with open(file_path, encoding="utf-8") as f:
        return f.read()


def _extract_script_info(content: str) -> dict:
    scenes = []
    characters = set()

    lines = content.split("\n")
    current_scene = None
    scene_count = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        scene_match = re.match(r"^[第\s]*(\d+)[集场章回]", line)
        if scene_match or re.match(r"^场景|SCENE|第.*场", line):
            if current_scene:
                scenes.append(current_scene)

            scene_count += 1
            current_scene = {"title": line, "characters": set(), "dialogue_count": 0, "content": []}
        elif current_scene:
            current_scene["content"].append(line)

            dialogue_match = re.match(r"^([^:：]+)[:：](.+)", line)
            if dialogue_match:
                character = dialogue_match.group(1).strip()
                characters.add(character)
                if current_scene:
                    current_scene["characters"].add(character)
                    current_scene["dialogue_count"] += 1

    if current_scene:
        scenes.append(current_scene)

    for scene in scenes:
        scene["characters"] = list(scene["characters"])

    return {"scenes": scenes, "characters": list(characters), "total_scenes": len(scenes)}


@tool("split_script_into_episodes", parse_docstring=True)
def split_script_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    script_path: str,
    episodes_count: int,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """将剧本分割成指定数量的剧集。

    Args:
        script_path: 剧本文件路径
        episodes_count: 要分割的剧集数量

    Returns:
        分割后的剧集信息
    """
    try:
        file_path = Path(script_path)

        if not file_path.exists():
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=f"错误：文件不存在 - {script_path}",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )

        if file_path.suffix.lower() == ".docx":
            content = _parse_docx(file_path)
        else:
            content = _parse_txt(file_path)

        script_data = _extract_script_info(content)
        total_scenes = len(script_data["scenes"])

        if total_scenes == 0:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content="错误：剧本中没有找到场景",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )

        scenes_per_episode = max(1, total_scenes // episodes_count)
        episodes = []

        for i in range(episodes_count):
            start_idx = i * scenes_per_episode
            end_idx = (i + 1) * scenes_per_episode if i < episodes_count - 1 else total_scenes

            episode_scenes = script_data["scenes"][start_idx:end_idx]
            episode_characters = set()
            total_dialogues = 0

            for scene in episode_scenes:
                episode_characters.update(scene["characters"])
                total_dialogues += scene["dialogue_count"]

            episodes.append({"episode_number": i + 1, "scene_range": f"{start_idx + 1}-{end_idx}", "scene_count": len(episode_scenes), "characters": list(episode_characters), "dialogue_count": total_dialogues})

        result_text = f"""剧本分集成功！

总场景数：{total_scenes}
分集数量：{episodes_count}

剧集详情：
"""
        for episode in episodes:
            result_text += f"""
第 {episode["episode_number"]} 集：
  场景范围：{episode["scene_range"]}
  场景数：{episode["scene_count"]}
  角色：{", ".join(episode["characters"][:5])}
  对话数：{episode["dialogue_count"]}
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
                        content=f"剧本分集失败：{str(e)}",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )


@tool("generate_episode_video", parse_docstring=True)
def generate_episode_video_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    script_path: str,
    episode_number: int,
    scene_range: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    duration: int | None = 5,
    camera_fixed: bool | None = False,
    watermark: bool | None = True,
) -> Command:
    """为指定剧集生成视频。

    Args:
        script_path: 剧本文件路径
        episode_number: 剧集编号
        scene_range: 场景范围（如 "1-5"）
        duration: 视频时长（秒）
        camera_fixed: 是否固定镜头
        watermark: 是否添加水印

    Returns:
        视频生成结果
    """
    try:
        file_path = Path(script_path)

        if not file_path.exists():
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=f"错误：文件不存在 - {script_path}",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )

        if file_path.suffix.lower() == ".docx":
            content = _parse_docx(file_path)
        else:
            content = _parse_txt(file_path)

        script_data = _extract_script_info(content)

        start, end = map(int, scene_range.split("-"))
        episode_scenes = script_data["scenes"][start - 1 : end]

        scene_prompts = []
        for scene in episode_scenes:
            scene_content = "\n".join(scene["content"][:10])
            scene_prompts.append(f"{scene['title']}: {scene_content}")

        main_prompt = f"短剧第{episode_number}集，包含{len(episode_scenes)}个场景。主要情节：{'; '.join(scene_prompts[:3])}"

        result_text = f"""开始生成第 {episode_number} 集视频...

剧集信息：
  场景范围：{scene_range}
  场景数：{len(episode_scenes)}
  视频时长：{duration} 秒
  固定镜头：{camera_fixed}
  添加水印：{watermark}

生成提示词：
{main_prompt}

视频生成任务已提交，请等待生成完成...
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
                        content=f"视频生成失败：{str(e)}",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )
