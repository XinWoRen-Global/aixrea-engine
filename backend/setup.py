"""Setup script for deer-flow.

显式指定 packages，避免 setuptools 自动发现时因多个顶级目录报错。
langgraph build 时需要此文件来正确构建可编辑安装。
"""

from setuptools import find_packages, setup

setup(
    name="deer-flow",
    version="2.1.0",
    # 显式只包含 app 包
    packages=find_packages(include=["app", "app.*"]),
    # 包含 app 下的非 Python 文件
    package_data={
        "app": ["**/*.json", "**/*.yaml", "**/*.yml", "**/*.txt"],
    },
    include_package_data=True,
    python_requires=">=3.12,<3.14",
)
