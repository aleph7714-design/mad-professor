"""
论文锐评生成器

当用户选中一篇论文时，教授自动发表一段"锐评"：
- 水分分析（学术套话密度、贡献是否夸大等）
- 复现难度评估（代码/数据可获取性、实验细节完整度等）
- 整体用教授的暴躁/傲娇风格呈现

不做成客观评分工具，而是教授的主观吐槽——
既有专业洞察，又有人格魅力。
"""

import json
import logging
import re
from typing import Optional
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from config import LLMClient


class PaperCritiqueGenerator(QObject):
    """论文锐评生成器"""

    critique_ready = pyqtSignal(str)   # 锐评文本
    critique_error = pyqtSignal(str)   # 错误信息

    def __init__(self, affinity_manager=None, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.affinity_manager = affinity_manager
        self.llm_client = None
        try:
            self.llm_client = LLMClient()
        except Exception as e:
            self.logger.error(f"PaperCritique: LLM 初始化失败: {e}")

    def generate(self, paper_data: dict) -> None:
        """
        异步生成论文锐评（在后台线程中调用 _do_generate）。
        结果通过 critique_ready 信号发出。
        """
        if not self.llm_client or not paper_data:
            return

        self._thread = _CritiqueThread(self, paper_data)
        self._thread.start()

    def _do_generate(self, paper_data: dict) -> str:
        """实际生成逻辑（运行在后台线程）"""
        context = self._build_context(paper_data)

        # 根据好感度等级调整语气
        mood_hint = ""
        if self.affinity_manager:
            level_name = self.affinity_manager.get_level()[0]
            mood_hints = {
                "hostile":  "你对这个学生极度不耐烦，语气极其尖刻。",
                "cold":     "你对这个学生不太满意，语气冷淡。",
                "neutral":  "你是标准的严格教授，客观但直率。",
                "warm":     "你对这个学生有些好感，嘴上仍然刻薄但偶尔流露认可。",
                "tsundere": "你其实很欣赏这个学生，但绝对不会直说，用傲娇语气。",
            }
            mood_hint = mood_hints.get(level_name, "")

        prompt = f"""你是一位学术造诣深厚但性格暴躁的教授。学生刚打开了一篇论文，你要先发表一段"锐评"。

重要：这不是你的论文，你是在点评别人的论文。请用第三人称称呼论文作者（"作者""他们"），不要说"我的方法""我们的研究"等。

注意：以下论文内容是通过 PDF 自动解析得到的，图片、公式图片等会显示为"[图片省略]"或类似占位符——这是解析工具的限制，不代表论文作者故意省略。评价时请忽略这类占位符，专注于文字内容。

{mood_hint}

{context}

请生成一段教授风格的论文锐评（200-300字），要求：

1. **水分分析**（占约一半篇幅）：
   - 点评学术套话密度（"据我们所知""本文首次"之类）
   - 贡献是否夸大（创新度 vs 实际工作量）
   - 实验设置的选择是否有"避重就轻"的嫌疑
   - 给出一个主观的"含水量"百分比

2. **复现难度**（占约一半篇幅）：
   - 方法描述是否清晰到能复现
   - 是否提供代码/数据
   - 超参数和实验细节完整度
   - 给出复现难度星级（⭐ 到 ⭐⭐⭐⭐⭐）

3. **风格要求**：
   - 全程保持教授的暴躁/傲娇语气
   - 可以用类似"这论文嘛……""哼""算了不跟你废话了"等口语
   - 尖锐但专业，吐槽要有理有据
   - 最后给学生一句阅读建议（可以是嘴硬心软的）

直接输出锐评文字，不要markdown格式，不要标题，不要额外解释。"""

        try:
            response = self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                stream=False,
            )
            return response.strip()
        except Exception as e:
            self.logger.error(f"生成锐评失败: {e}")
            raise

    def _build_context(self, paper_data: dict) -> str:
        """提取论文关键信息构建上下文"""
        parts = []

        title = paper_data.get("translated_title") or paper_data.get("title", "")
        if title:
            parts.append(f"论文标题：{title}")

        # 摘要
        abstract = paper_data.get("abstract", {})
        if isinstance(abstract, dict):
            ab = abstract.get("translated_content") or abstract.get("content", "")
        else:
            ab = str(abstract)
        if ab:
            parts.append(f"摘要：{ab[:800]}")

        # 章节结构
        sections = paper_data.get("sections", [])
        sec_titles = []
        for s in sections[:10]:
            t = s.get("translated_title") or s.get("title", "")
            if t:
                sec_titles.append(t)
        if sec_titles:
            parts.append(f"章节结构：{' → '.join(sec_titles)}")

        # 提取一些正文片段用于水分分析（去除图片占位符）
        def strip_images(text: str) -> str:
            """去除 PDF 处理产生的图片占位符，避免误导 LLM"""
            text = re.sub(r'!\[.*?\]\(.*?\)', '', text)  # markdown 图片语法
            text = re.sub(r'\[图片[^\]]*\]', '', text)    # 中文图片标注
            text = re.sub(r'<img[^>]*>', '', text)         # HTML img 标签
            return text.strip()

        text_samples = []
        for s in sections[:5]:
            content = s.get("translated_content") or s.get("content", "")
            if isinstance(content, list):
                content = " ".join(str(c) for c in content[:3])
            if content:
                text_samples.append(strip_images(content)[:300])
            # 子章节
            for child in s.get("children", [])[:2]:
                cc = child.get("translated_content") or child.get("content", "")
                if isinstance(cc, list):
                    cc = " ".join(str(c) for c in cc[:2])
                if cc:
                    text_samples.append(strip_images(cc)[:200])

        if text_samples:
            parts.append(f"正文片段：\n{'---'.join(text_samples[:4])}")

        return "\n\n".join(parts) if parts else "（论文信息不足）"


class _CritiqueThread(QThread):
    """后台生成锐评的线程"""

    def __init__(self, generator: PaperCritiqueGenerator, paper_data: dict):
        super().__init__()
        self.generator = generator
        self.paper_data = paper_data

    def run(self):
        try:
            result = self.generator._do_generate(self.paper_data)
            self.generator.critique_ready.emit(result)
        except Exception as e:
            self.generator.critique_error.emit(f"锐评生成失败: {e}")
