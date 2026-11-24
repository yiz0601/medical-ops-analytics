"""文档完整性回归测试（防止批量替换误伤 Markdown 表格）。

校验 docs/ 下 10 份交付文档与根目录 README/CONTRIBUTING：
    1. 文件存在且非空
    2. 至少包含一个 Markdown 表格（竖线数量下限）——曾出现批量替换把整份文档竖线删空的事故
    3. 表格每个区块的列数一致（含 `\\|` 转义竖线的处理）
    4. docs/ 内部相对链接可解析
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = PROJECT_ROOT / "docs"

EXPECTED_DOCS = [
    "项目说明.md",
    "项目开发流程.md",
    "培养目标.md",
    "需求规格说明书.md",
    "概要设计.md",
    "详细设计.md",
    "指标口径手册.md",
    "测试计划与报告.md",
    "部署运维手册.md",
    "用户操作手册.md",
    # 阶段六/七新增文档
    "大模型应用设计说明.md",
    "试运行报告.md",
    "验收报告.md",
    "项目总结报告.md",
    "成果物清单.md",
    "代码评审记录.md",
]

# 每份文档的竖线数量下限（远低于实际值，只用于发现"表格被清空"这类事故）
MIN_PIPES = 30


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _count_pipes(line: str) -> int:
    """统计未转义竖线数量（跳过 `\\|`）。"""
    count = 0
    for index, char in enumerate(line):
        if char == "|" and (index == 0 or line[index - 1] != "\\"):
            count += 1
    return count


def _table_blocks(text: str) -> list[list[str]]:
    """切分 Markdown 表格区块（跳过代码围栏内的伪表格）。"""
    blocks: list[list[str]] = []
    current: list[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if re.match(r"^\s*\|", line):
            current.append(line)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


@pytest.mark.parametrize("doc_name", EXPECTED_DOCS)
def test_doc_exists_and_has_tables(doc_name):
    """每份文档存在、非空，且保留至少一个表格（竖线数量下限）。"""
    path = DOCS_DIR / doc_name
    assert path.exists(), f"文档缺失：{doc_name}"
    text = _read(path)
    assert text.strip(), f"文档为空：{doc_name}"
    pipes = _count_pipes(text)
    assert pipes >= MIN_PIPES, f"{doc_name} 竖线仅 {pipes} 个（<{MIN_PIPES}），表格可能被破坏"


@pytest.mark.parametrize("doc_name", EXPECTED_DOCS)
def test_doc_tables_consistent(doc_name):
    """表格区块列数一致（表头与每行列数相同）。"""
    text = _read(DOCS_DIR / doc_name)
    problems: list[str] = []
    for block in _table_blocks(text):
        header_cols = _count_pipes(block[0])
        for offset, line in enumerate(block[2:], start=3):
            if _count_pipes(line) != header_cols:
                problems.append(f"第 {offset} 行：列数 {_count_pipes(line)} ≠ 表头 {header_cols}")
    assert not problems, f"{doc_name} 表格列数不一致：{problems[:5]}"


@pytest.mark.parametrize("doc_name", EXPECTED_DOCS)
def test_doc_internal_links(doc_name):
    """文档内部相对链接（*.md）均可解析。"""
    path = DOCS_DIR / doc_name
    text = _read(path)
    broken: list[str] = []
    for match in re.finditer(r"\[[^\]]*\]\(([^)]+\.md)(#[^)]*)?\)", text):
        target = match.group(1)
        if not (path.parent / target).exists():
            broken.append(target)
    assert not broken, f"{doc_name} 存在失效链接：{broken}"


@pytest.mark.parametrize("file_name", ["README.md", "CONTRIBUTING.md"])
def test_root_docs_tables(file_name):
    """根目录 README / CONTRIBUTING 同样保留表格与竖线。"""
    path = PROJECT_ROOT / file_name
    assert path.exists(), f"缺少 {file_name}"
    text = _read(path)
    assert _count_pipes(text) >= 20, f"{file_name} 表格可能被破坏"
