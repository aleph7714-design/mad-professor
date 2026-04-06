"""
组会模式管理器

流程：
1. 基于论文内容，LLM 生成 5 道由浅入深的问题
2. 教授逐题提问，学生逐题回答
3. LLM 评估每道题的答案质量，更新好感度
4. 5 题结束后给出组会总结
5. 彩蛋：好感度达到 100 时触发特殊傲娇台词
"""

import json
import logging
from typing import List, Dict, Optional
from PyQt6.QtCore import QObject, pyqtSignal

from config import LLMClient


EASTER_EGG_SPEECH = (
    "……这篇论文，你已经掌握得差不多了。"
    "（停顿）"
    "……别误会，我只是在陈述事实。"
    "不过嘛……希望你自己也能发出这样水准的文章。"
    "当然，那要等你好好努力之后才算数。哼。"
)

SEMINAR_QUESTION_COUNT = 5


class SeminarManager(QObject):
    """组会模式管理器"""

    # ---- 信号 ----
    seminar_started = pyqtSignal(str)           # 组会开始（论文标题）
    question_ready = pyqtSignal(str, int, int)  # 问题文本, 当前题号(1-based), 总题数
    evaluation_ready = pyqtSignal(str, int, str)  # 点评文本, 好感度delta, 质量标签
    seminar_ended = pyqtSignal(str)             # 组会总结文本
    easter_egg_triggered = pyqtSignal(str)      # 彩蛋台词
    error_occurred = pyqtSignal(str)            # 错误信息

    def __init__(self, affinity_manager=None, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)

        self.affinity_manager = affinity_manager
        self.llm_client = None
        try:
            self.llm_client = LLMClient()
        except Exception as e:
            self.logger.error(f"SeminarManager: LLM 初始化失败: {e}")

        # 组会状态
        self.is_active = False
        self.paper_title = ""
        self.paper_context = ""        # 用于 LLM 的论文摘要上下文
        self.questions: List[str] = []
        self.current_index = 0         # 当前题号（0-based）
        self.session_results: List[Dict] = []  # 每题的评估结果
        self._easter_egg_fired = False  # 彩蛋是否已触发

    # ======================== 公开接口 ========================

    def start_seminar(self, paper_data: dict):
        """开始组会：生成问题并提出第一道"""
        if not self.llm_client:
            self.error_occurred.emit("LLM 客户端未初始化，无法开始组会")
            return

        if not paper_data:
            self.error_occurred.emit("未加载论文，请先选择论文")
            return

        self.paper_title = (
            paper_data.get("translated_title", "")
            or paper_data.get("title", "未知论文")
        )
        self.paper_context = self._build_paper_context(paper_data)

        self.is_active = True
        self.current_index = 0
        self.session_results = []
        self._easter_egg_fired = False

        self.logger.info(f"开始组会: {self.paper_title}")
        self.seminar_started.emit(self.paper_title)

        # 生成问题列表
        try:
            self.questions = self._generate_questions()
            if not self.questions:
                self.error_occurred.emit("问题生成失败，请重试")
                self.is_active = False
                return
        except Exception as e:
            self.error_occurred.emit(f"生成问题失败: {e}")
            self.is_active = False
            return

        # 提出第一道题
        self._emit_current_question()

    def submit_answer(self, answer: str):
        """
        学生提交答案，LLM 评估后：
          1. 发出 evaluation_ready 信号（带点评 + delta）
          2. 更新好感度
          3. 自动提下一题，或结束组会
        """
        if not self.is_active:
            return

        question = self.questions[self.current_index]

        try:
            result = self._evaluate_answer(question, answer)
        except Exception as e:
            self.logger.error(f"评估答案失败: {e}")
            result = {
                "feedback": "（评估出错，跳过本题）",
                "delta": 0,
                "quality": "unknown",
            }

        self.session_results.append({
            "question": question,
            "answer": answer,
            **result,
        })

        delta = result["delta"]
        feedback = result["feedback"]
        quality = result["quality"]

        # 更新好感度
        if self.affinity_manager and delta != 0:
            self.affinity_manager.update_affinity(
                delta, f"组会第{self.current_index + 1}题"
            )

        self.evaluation_ready.emit(feedback, delta, quality)

        # 检查彩蛋
        if (
            self.affinity_manager
            and self.affinity_manager.affinity >= 100
            and not self._easter_egg_fired
        ):
            self._easter_egg_fired = True
            self.easter_egg_triggered.emit(EASTER_EGG_SPEECH)

        # 移动到下一题
        self.current_index += 1
        if self.current_index < len(self.questions):
            self._emit_current_question()
        else:
            self._end_seminar()

    def end_seminar_early(self):
        """提前结束组会"""
        if self.is_active:
            self._end_seminar(early=True)

    # ======================== 内部方法 ========================

    def _emit_current_question(self):
        """发出当前题目信号"""
        question = self.questions[self.current_index]
        total = len(self.questions)
        idx_1based = self.current_index + 1
        self.logger.info(f"提出第 {idx_1based}/{total} 题: {question[:60]}")
        self.question_ready.emit(question, idx_1based, total)

    def _build_paper_context(self, paper_data: dict) -> str:
        """从 paper_data 提取关键信息供 LLM 参考"""
        parts = []
        title = paper_data.get("translated_title") or paper_data.get("title", "")
        if title:
            parts.append(f"论文标题：{title}")

        abstract = paper_data.get("abstract", {})
        if isinstance(abstract, dict):
            ab_text = abstract.get("translated_content") or abstract.get("content", "")
        else:
            ab_text = str(abstract)
        if ab_text:
            parts.append(f"摘要：{ab_text[:600]}")

        sections = paper_data.get("sections", [])
        section_titles = []
        for s in sections[:8]:
            t = s.get("translated_title") or s.get("title", "")
            if t:
                section_titles.append(t)
        if section_titles:
            parts.append(f"主要章节：{' | '.join(section_titles)}")

        return "\n".join(parts) if parts else f"论文：{title}"

    def _generate_questions(self) -> List[str]:
        """调用 LLM 生成由浅入深的 N 道问题"""
        prompt = f"""你是一位学术导师，正在对学生进行关于下列论文的组会考核。

{self.paper_context}

请生成 {SEMINAR_QUESTION_COUNT} 道由浅入深的问题，考察学生对这篇论文的理解：
- 前2题：基础理解（论文解决什么问题、用了什么方法）
- 中间2题：深入理解（方法细节、实验设计、结果分析）
- 最后1题：批判思考（局限性、改进方向、与其他工作的比较）

要求：
- 每道题简洁明确，不超过60字
- 问题必须基于这篇论文的具体内容，不要泛泛而问
- 用中文提问

只输出问题列表，JSON格式：
{{"questions": ["问题1", "问题2", "问题3", "问题4", "问题5"]}}"""

        try:
            response = self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                stream=False,
            )
            # 清理 markdown 代码块
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

            data = json.loads(cleaned)
            questions = data.get("questions", [])
            if len(questions) < SEMINAR_QUESTION_COUNT:
                raise ValueError(f"问题数量不足: {len(questions)}")
            self.logger.info(f"成功生成 {len(questions)} 道问题")
            return questions[:SEMINAR_QUESTION_COUNT]
        except Exception as e:
            self.logger.error(f"生成问题失败: {e}, 原始响应: {response[:300] if 'response' in dir() else 'N/A'}")
            raise

    def _evaluate_answer(self, question: str, answer: str) -> Dict:
        """LLM 评估学生答案，返回点评文本和好感度变化"""
        reading_stage_hint = ""
        if self.affinity_manager:
            count = self.affinity_manager.conversation_count
            if count <= 3:
                reading_stage_hint = "（学生刚开始了解这篇论文，可以适当宽容）"
            elif count <= 8:
                reading_stage_hint = "（学生已有一定了解，期望有基本理解）"
            else:
                reading_stage_hint = "（学生应该已深入理解，期望高质量回答）"

        prompt = f"""你是一位严格但有人情味的学术教授，正在评估学生的组会答题情况。
{reading_stage_hint}

论文背景：
{self.paper_context}

当前问题：{question}

学生回答：{answer}

请评估这个回答，给出：
1. 点评（以教授语气，简洁有力，不超过100字，可以暴躁或傲娇）
2. 好感度变化 delta（整数）：
   - 回答优秀（切中要点+有深度）：+6 到 +8
   - 回答良好（基本正确）：+3 到 +5
   - 回答一般（大差不差）：+1 到 +2
   - 回答不足（方向对但细节错）：-1 到 0
   - 回答很差（完全错误或"不知道"）：-3 到 -5
3. quality标签：excellent / good / average / poor / terrible

只输出JSON，不要额外解释：
{{"feedback": "点评文字", "delta": 整数, "quality": "标签"}}"""

        response = self.llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            stream=False,
        )
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            data = json.loads(cleaned)
            delta = max(-5, min(8, int(data.get("delta", 0))))
            return {
                "feedback": data.get("feedback", "（无法评估）"),
                "delta": delta,
                "quality": data.get("quality", "average"),
            }
        except Exception as e:
            self.logger.warning(f"解析评估结果失败: {e}, 原始: {response[:200]}")
            return {"feedback": response[:200], "delta": 0, "quality": "average"}

    def _end_seminar(self, early: bool = False):
        """结束组会，生成总结"""
        self.is_active = False

        if not self.session_results:
            self.seminar_ended.emit("组会已结束（没有完成任何题目）。")
            return

        # 统计
        answered = len(self.session_results)
        total_delta = sum(r["delta"] for r in self.session_results)
        quality_counts = {"excellent": 0, "good": 0, "average": 0, "poor": 0, "terrible": 0}
        for r in self.session_results:
            q = r.get("quality", "average")
            if q in quality_counts:
                quality_counts[q] += 1

        # 生成总结语
        summary = self._generate_summary(answered, total_delta, quality_counts, early)
        self.logger.info(f"组会结束: 完成 {answered} 题, 好感度总变化 {total_delta:+d}")
        self.seminar_ended.emit(summary)

    def _generate_summary(
        self, answered: int, total_delta: int, quality_counts: dict, early: bool
    ) -> str:
        """生成组会总结文字（本地生成，不调用 LLM，避免额外延迟）"""
        excellent = quality_counts.get("excellent", 0)
        good = quality_counts.get("good", 0)
        poor = quality_counts.get("poor", 0) + quality_counts.get("terrible", 0)

        if early:
            opening = f"你提前结束了组会（完成了 {answered}/{SEMINAR_QUESTION_COUNT} 题）。"
        else:
            opening = f"组会结束，共完成 {answered} 道题。"

        if total_delta >= 10:
            verdict = "整体表现优秀，对论文有深入理解。继续保持。"
        elif total_delta >= 4:
            verdict = "整体表现良好，基本掌握了论文核心内容。"
        elif total_delta >= 0:
            verdict = "整体表现一般，还有提升空间，建议再仔细读读论文。"
        else:
            verdict = "整体表现欠佳，对论文的理解还不够深入，需要加强。"

        details = []
        if excellent > 0:
            details.append(f"{excellent} 题回答优秀")
        if good > 0:
            details.append(f"{good} 题回答良好")
        if poor > 0:
            details.append(f"{poor} 题需要改进")

        detail_str = "、".join(details) + "。" if details else ""
        delta_str = f"本次组会好感度变化：{total_delta:+d}。"

        return f"{opening}{detail_str}{verdict}{delta_str}"
