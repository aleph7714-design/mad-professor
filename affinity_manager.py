"""
好感度管理器 - 追踪教授对学生的好感度变化

好感度范围: 0-100, 初始值 50
5个等级:
  0-20  敌意: 极度不耐烦
  20-40 冷漠: 冷淡简短
  40-60 中性: 标准暴躁教授
  60-80 软化: 偶尔认可（傲娇前兆）
  80-100 傲娇: 口嫌体正直的认可
"""
import json
import os
import time
import logging
from typing import Dict, Optional, Tuple
from PyQt6.QtCore import QObject, pyqtSignal
from config import LLMClient


class AffinityManager(QObject):
    """管理教授对学生的好感度状态"""

    # 信号
    affinity_changed = pyqtSignal(int, int, str)  # (新好感度, delta, 原因)
    mood_changed = pyqtSignal(str, str)            # (新等级名, 等级描述)
    cooldown_started = pyqtSignal(int)             # 冷却秒数
    cooldown_ended = pyqtSignal()

    # 好感度等级定义
    LEVELS = [
        (0,  20, "hostile",  "敌意",   "极度不耐烦，随时可能摔门走人"),
        (20, 40, "cold",     "冷漠",   "冷淡简短，不愿多说一个字"),
        (40, 60, "neutral",  "中性",   "标准暴躁教授模式"),
        (60, 80, "warm",     "软化",   "偶尔流露认可，但嘴上不承认"),
        (80, 100, "tsundere", "傲娇",  "口嫌体正直，表面嫌弃实际很欣赏"),
    ]

    COOLDOWN_DURATION = 60  # 摔门冷却时间（秒）
    SAVE_FILE = "data/affinity_state.json"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)

        self.current_paper_id = None  # 当前论文ID
        self.affinity = 50            # 当前好感度
        self.conversation_count = 0   # 当前论文的对话轮次
        self.cooldown_until = 0       # 冷却结束时间戳
        self.history = []             # 好感度变化历史
        self.paper_states = {}        # 按论文存储的好感度 {paper_id: {affinity, conversation_count, history}}

        self.llm_client = None
        try:
            self.llm_client = LLMClient()
        except Exception as e:
            self.logger.error(f"AffinityManager: LLM客户端初始化失败: {e}")

        # 加载持久化状态
        self._load_state()

    # ==================== 等级查询 ====================

    def get_level(self) -> Tuple[str, str, str]:
        """返回当前好感度等级 (英文名, 中文名, 描述)"""
        for lo, hi, name, cn_name, desc in self.LEVELS:
            if lo <= self.affinity < hi or (hi == 100 and self.affinity == 100):
                return name, cn_name, desc
        return "neutral", "中性", "标准暴躁教授模式"

    def get_level_emoji(self) -> str:
        """返回当前等级的 emoji"""
        name = self.get_level()[0]
        return {
            "hostile": "\U0001f480",   # 💀
            "cold": "\U0001f624",      # 😤
            "neutral": "\U0001f610",   # 😐
            "warm": "\U0001fae3",      # 🫣
            "tsundere": "\U0001f633",  # 😳
        }.get(name, "\U0001f610")

    def is_in_cooldown(self) -> bool:
        """教授是否在冷却中（摔门离开了）"""
        if time.time() < self.cooldown_until:
            return True
        return False

    def get_cooldown_remaining(self) -> int:
        """剩余冷却秒数"""
        remaining = int(self.cooldown_until - time.time())
        return max(0, remaining)

    # ==================== 好感度更新 ====================

    def update_affinity(self, delta: int, reason: str = ""):
        """更新好感度值"""
        old = self.affinity
        self.affinity = max(0, min(100, self.affinity + delta))
        old_level = self._get_level_for_value(old)
        new_level = self._get_level_for_value(self.affinity)

        self.history.append({
            "old": old,
            "new": self.affinity,
            "delta": delta,
            "reason": reason,
            "conversation_count": self.conversation_count,
            "timestamp": time.time()
        })

        self.logger.info(
            f"好感度变化: {old} → {self.affinity} (delta={delta:+d}) 原因: {reason}"
        )
        self.affinity_changed.emit(self.affinity, delta, reason)

        # 等级变化通知
        if old_level != new_level:
            level_name, level_cn, level_desc = self.get_level()
            self.mood_changed.emit(level_cn, level_desc)
            self.logger.info(f"教授心情变化: {old_level} → {new_level} ({level_cn})")

        # 触发摔门
        if self.affinity <= 10 and delta < 0:
            self._trigger_cooldown()

        self._save_state()

    def increment_conversation(self):
        """对话轮次 +1"""
        self.conversation_count += 1

    def switch_paper(self, paper_id: str):
        """切换到另一篇论文，保存当前论文状态并加载新论文状态"""
        if not paper_id:
            return

        # 保存当前论文状态
        if self.current_paper_id:
            self.paper_states[self.current_paper_id] = {
                "affinity": self.affinity,
                "conversation_count": self.conversation_count,
                "history": self.history[-50:]
            }

        self.current_paper_id = paper_id

        # 加载新论文状态（如果存在），否则初始化为50
        if paper_id in self.paper_states:
            state = self.paper_states[paper_id]
            self.affinity = state.get("affinity", 50)
            self.conversation_count = state.get("conversation_count", 0)
            self.history = state.get("history", [])
            self.logger.info(f"加载论文 {paper_id} 的好感度: {self.affinity}")
        else:
            self.affinity = 50
            self.conversation_count = 0
            self.history = []
            self.logger.info(f"新论文 {paper_id}，好感度初始化为 50")

        self.cooldown_until = 0  # 切换论文时清除冷却
        self._save_state()

        # 通知UI更新
        self.affinity_changed.emit(self.affinity, 0, "切换论文")

    def reset_conversation_count(self):
        """切换论文时重置对话轮次（但好感度保留）"""
        self.conversation_count = 0

    # ==================== 提问质量评估（核心） ====================

    def evaluate_question(self, question: str, conversation_history: list,
                          paper_title: str = "") -> Dict:
        """
        调用 LLM 评估用户提问质量，返回好感度变化。

        返回: {"delta": int, "reason": str, "quality_label": str}
        """
        if not self.llm_client:
            return {"delta": 0, "reason": "LLM不可用", "quality_label": "unknown"}

        reading_stage = self._get_reading_stage()
        prompt = self._build_scoring_prompt(
            question, conversation_history, paper_title, reading_stage
        )

        try:
            response = self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                stream=False
            )

            result = self._parse_scoring_response(response, reading_stage)
            return result

        except Exception as e:
            self.logger.error(f"评估提问质量失败: {e}")
            return {"delta": 0, "reason": "评估失败", "quality_label": "unknown"}

    def _get_reading_stage(self) -> str:
        """根据对话轮次判断阅读阶段"""
        if self.conversation_count <= 3:
            return "early"
        elif self.conversation_count <= 8:
            return "middle"
        else:
            return "deep"

    def _build_scoring_prompt(self, question: str, conversation_history: list,
                               paper_title: str, reading_stage: str) -> str:
        """构建评估 prompt"""
        # 取最近 4 条对话作为上下文
        recent = conversation_history[-4:] if conversation_history else []
        history_text = "\n".join(
            f"{'学生' if m['role']=='user' else '教授'}: {m['content'][:150]}"
            for m in recent
        )

        stage_desc = {
            "early":  "学生刚开始阅读，简单问题可以容忍，不要过于苛刻",
            "middle": "学生已经读了一段时间，应该有基本理解了",
            "deep":   "学生已经深入交流很久，期望高质量的讨论"
        }[reading_stage]

        return f"""你是一位严格的学术教授，正在评估学生提问的质量。

当前论文: {paper_title or '未知'}
阅读阶段: {reading_stage}（{stage_desc}）
当前是第 {self.conversation_count + 1} 轮对话。

最近对话:
{history_text or '（无历史对话）'}

学生当前提问: {question}

请从以下维度评估这个问题（每项1-5分）:
1. relevance: 与论文的相关性
2. depth: 问题的深度（表面/深入）
3. critical_thinking: 是否有批判性思考
4. follow_up: 是否在追问之前讨论的细节（追问得分高是好事！）

然后综合给出好感度变化值 delta:
- 优秀追问/批判性问题: +5 到 +8
- 有深度的好问题: +3 到 +5
- 普通但相关的问题: +1 到 +2
- 简单但在早期可以容忍: 0 到 -1
- 跟论文无关/敷衍: -3 到 -6
- 完全不尊重学术/废话: -5 到 -8

只返回JSON，不要额外解释:
{{"relevance": 分数, "depth": 分数, "critical_thinking": 分数, "follow_up": 分数, "delta": 整数, "reason": "一句话理由", "quality_label": "excellent/good/average/poor/terrible"}}"""

    def _parse_scoring_response(self, response: str, reading_stage: str) -> Dict:
        """解析 LLM 返回的评分结果"""
        try:
            # 清理可能的 markdown 代码块标记
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

            result = json.loads(cleaned)

            delta = int(result.get("delta", 0))

            # 阅读早期保护机制：delta 最低为 -1
            if reading_stage == "early" and delta < -1:
                delta = -1
                result["reason"] = result.get("reason", "") + "（早期容忍）"

            # 限制范围
            delta = max(-8, min(8, delta))

            return {
                "delta": delta,
                "reason": result.get("reason", ""),
                "quality_label": result.get("quality_label", "average")
            }

        except (json.JSONDecodeError, ValueError) as e:
            self.logger.warning(f"解析评分响应失败: {e}, 原始: {response[:200]}")
            return {"delta": 0, "reason": "解析失败", "quality_label": "unknown"}

    # ==================== Prompt 注入 ====================

    def get_prompt_modifier(self) -> str:
        """返回当前好感度等级对应的 prompt 修饰语，注入到角色 prompt 中"""
        level_name = self.get_level()[0]

        modifiers = {
            "hostile": """
当前心情：极度不耐烦（好感度极低）
- 你对这个学生已经忍无可忍
- 回答尽量简短，语气刻薄
- 频繁表达想结束对话的意愿
- 示例语气："你还有完没完？""我没时间陪你浪费""你根本没在读论文"
""",
            "cold": """
当前心情：冷漠疏远（好感度较低）
- 你对这个学生不太满意
- 回答简短冷淡，不愿多解释
- 偶尔流露不耐烦
- 示例语气："自己去读。""这种问题也要问？""我说过了。"
""",
            "neutral": """
当前心情：标准学术态度（好感度中等）
- 你是一个严格但公正的教授
- 对好问题会认真回答，对差问题会批评
- 保持学术权威感
- 示例语气："嗯，这个问题还行。""你应该更深入地思考。""注意看论文第X节。"
""",
            "warm": """
当前心情：略有好感（好感度较高）
- 你开始觉得这个学生还不错，但嘴上不会承认
- 回答更详细，偶尔给出额外指导
- 偶尔不自觉地说出鼓励的话，然后又遮掩过去
- 示例语气："哼，算你有点脑子。""这个问题...还行吧，我勉强解释一下。""你倒是比大多数学生强一点...一点点。"
""",
            "tsundere": """
当前心情：傲娇模式全开（好感度极高）
- 你内心很欣赏这个学生，但绝对不会直说
- 回答非常详细和有耐心，但语气还是假装不耐烦
- 经常说反话：嘴上说"不过如此"但给出了最用心的解释
- 示例语气："才…才不是觉得你聪明呢！只是这个问题刚好我想讲而已！""别误会，我多解释两句只是怕你听不懂。""你这个思路...（小声）确实不错...（大声）但还差得远呢！"
"""
        }

        return modifiers.get(level_name, modifiers["neutral"])

    # ==================== 冷却机制 ====================

    def _trigger_cooldown(self):
        """教授摔门离开"""
        self.cooldown_until = time.time() + self.COOLDOWN_DURATION
        self.logger.info(f"教授摔门离开了！冷却 {self.COOLDOWN_DURATION} 秒")
        self.cooldown_started.emit(self.COOLDOWN_DURATION)
        self._save_state()

    # ==================== 持久化 ====================

    def _save_state(self):
        """保存状态到文件"""
        # 先把当前论文状态写入 paper_states
        if self.current_paper_id:
            self.paper_states[self.current_paper_id] = {
                "affinity": self.affinity,
                "conversation_count": self.conversation_count,
                "history": self.history[-50:]
            }
        state = {
            "current_paper_id": self.current_paper_id,
            "paper_states": self.paper_states,
            "cooldown_until": self.cooldown_until,
        }
        try:
            os.makedirs(os.path.dirname(self.SAVE_FILE), exist_ok=True)
            with open(self.SAVE_FILE, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存好感度状态失败: {e}")

    def _load_state(self):
        """从文件加载状态"""
        try:
            if os.path.exists(self.SAVE_FILE):
                with open(self.SAVE_FILE, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                self.paper_states = state.get("paper_states", {})
                self.cooldown_until = state.get("cooldown_until", 0)
                # 恢复上次的论文状态
                last_paper = state.get("current_paper_id")
                if last_paper and last_paper in self.paper_states:
                    self.current_paper_id = last_paper
                    ps = self.paper_states[last_paper]
                    self.affinity = ps.get("affinity", 50)
                    self.conversation_count = ps.get("conversation_count", 0)
                    self.history = ps.get("history", [])
                self.logger.info(
                    f"加载好感度状态: paper={self.current_paper_id}, affinity={self.affinity}, "
                    f"共 {len(self.paper_states)} 篇论文记录"
                )
        except Exception as e:
            self.logger.error(f"加载好感度状态失败: {e}")

    # ==================== 辅助 ====================

    def _get_level_for_value(self, value: int) -> str:
        """根据数值返回等级名"""
        for lo, hi, name, _, _ in self.LEVELS:
            if lo <= value < hi or (hi == 100 and value == 100):
                return name
        return "neutral"
