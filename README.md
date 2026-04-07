# 暴躁教授论文陪读 — 二次开发版

> 基于开源项目 [mad-professor](https://github.com/LYiHub/mad-professor-public) 进行二次开发，在原有"暴躁教授 + 论文阅读"的基础上，新增**好感度系统**、**组会模式**、**论文锐评**等功能，让学术论文阅读体验更具沉浸感与趣味性。

![](/Users/luojinghao/Desktop/暴躁教授/Screenshot%202026-04-03%20at%2020.20.27.png)

---

## 创意说明

### 为什么做这个项目？

阅读学术论文是一件枯燥的事。原项目将 LLM 包装成一位"暴躁教授"来陪读论文，已经很有意思了——但教授永远只有一种脾气，交互也只有问答一种模式。我在此基础上做了三件事：

1. 好感度（养成）系统
2. 组会模式
3. 教授锐评

### 新增功能详解

#### 1. 好感度系统

教授对你的态度不再一成不变。每次提问，LLM 都会评估你的问题质量并调整好感度（0~100），教授的语气随之改变：

| 好感度    | 阶段  | 教授态度                      |
| ------ | --- | ------------------------- |
| 0-20   | 敌意  | 极度不耐烦，随时可能"摔门离开"（触发60秒冷却） |
| 20-40  | 冷淡  | 爱答不理，回答简短                 |
| 40-60  | 中性  | 标准严格教授                    |
| 60-80  | 温和  | 嘴上刻薄但偶尔流露认可               |
| 80-100 | 傲娇  | 嘴硬心软，否认自己在夸你              |

- 好感度按**每篇论文独立追踪**，切换论文时实时切换
- 标题栏实时显示好感度表情、进度条和数值
- 惹怒教授（好感度降至 0 附近）会触发冷却机制：教授摔门离开，60 秒内无法互动

##### 好感度评分机制

每次对话结束后，LLM 从以下 4 个维度评估你的提问质量：

| 维度 | 含义 |
|------|------|
| 相关性 | 问题与当前论文的相关程度 |
| 深度 | 是表面理解还是深入思考 |
| 批判性 | 是否有质疑、对比或反思 |
| 追问质量 | 是否在延续上一个话题深挖 |

综合评估后给出好感度变化值（delta）：

| 问题类型 | delta |
|----------|-------|
| 优秀追问 / 批判性问题 | +5 ~ +8 |
| 有深度的好问题 | +3 ~ +5 |
| 普通但相关 | +1 ~ +2 |
| 简单基础（早期可容忍） | 0 ~ -1 |
| 与论文无关 / 敷衍 | -3 ~ -6 |
| 完全废话 / 不尊重学术 | -5 ~ -8 |

> **阅读阶段保护**：根据对话轮次分为早期（前3轮）/ 中期（4-8轮）/ 深入（9轮以后）。早期阶段 delta 最低只会到 -1，不会因为问了基础问题被重罚。

#### 2. 组会模式

点击标题栏的"组会"按钮，进入模拟组会答辩：

- 教授根据当前论文内容生成 **5 个渐进式问题**（2 基础 + 2 深入 + 1 批判性思考）
- 学生逐题回答，教授实时评分并给出点评
- 每道题的评估结果会影响好感度（见下表）
- 组会结束后给出总结评价

##### 组会答题评分

| 答题质量 | delta |
|----------|-------|
| 优秀（切中要点 + 有深度） | +6 ~ +8 |
| 良好（基本正确） | +3 ~ +5 |
| 一般（大差不差） | +1 ~ +2 |
| 不足（方向对但细节错） | -1 ~ 0 |
| 很差（完全错误或"不知道"） | -3 ~ -5 |

**彩蛋**：当好感度达到 100 时，教授会触发一段特殊的傲娇独白台词，普通对话和组会中均可触发。

![](/Users/luojinghao/Desktop/暴躁教授/Screenshot%202026-04-03%20at%2020.48.10.png)

#### 3. 教授锐评

当你选择一篇论文时，教授会自动发表一段"锐评"作为聊天的第一条消息：

- **含水量分析**：学术套话密度、贡献是否夸大、实验设置是否避重就轻，给出主观含水量百分比
- **复现难度评估**：方法描述清晰度、代码/数据可获取性、超参数完整度，给出星级评分（1~5 星）
- 全程教授暴躁/傲娇语气，锐评内容有理有据
- 锐评语气随好感度变化——好感度高时，教授的吐槽里会夹杂着不经意的认可

#### 4. 其他改进

- **删除论文**：右键侧边栏论文可删除
- **扫描版 PDF 支持**：新增 OCR 回退（Tesseract + PyMuPDF），支持图片型 PDF
- **Markdown 解析修复**：修复 `**Abstract**` 等加粗标题无法被正确识别的问题
- **RAG 空文档保护**：防止空向量库导致的 IndexError 崩溃
- **窗口按钮修复**：将无法在 macOS 上渲染的 emoji 按钮替换为通用 Unicode 字符

---

## 安装与运行指南

### 环境要求

| 项目      | 要求                          |
| ------- | --------------------------- |
| Python  | 3.10+                       |
| 操作系统    | Windows / macOS / Linux     |
| GPU（可选） | CUDA 11.8/12.4/12.6，6GB+ 显存 |
| macOS   | 支持 Apple Silicon（MPS 加速）    |

> macOS 用户无需 CUDA，项目会自动检测 MPS 设备。CPU-only 模式也可运行，但 embedding 加载较慢。

### 依赖项目与服务

**开源依赖：**

- [MinerU](https://github.com/opendatalab/MinerU) — PDF 解析引擎
- [RealtimeSTT](https://github.com/KoljaB/RealtimeSTT) — 实时语音识别（可选）

**在线 API 服务：**

- [DeepSeek API](https://api-docs.deepseek.com) — LLM 对话（必需）
- [MiniMax TTS](https://platform.minimaxi.com) — 语音合成（可选）

### 安装步骤

**1. 创建 conda 环境**

```bash
conda create -n mad-professor python=3.10.16
conda activate mad-professor
```

**2. 安装 MinerU**

```bash
pip install -U magic-pdf[full]==1.3.3 -i https://mirrors.aliyun.com/pypi/simple
```

**3. 安装项目依赖**

```bash
pip install -r requirements.txt
```

**4. 安装 PyTorch（按平台选择）**

CUDA 用户（以 12.4 为例）：

```bash
pip install --force-reinstall torch torchvision torchaudio "numpy<=2.1.1" --index-url https://download.pytorch.org/whl/cu124
```

macOS Apple Silicon 用户：

```bash
pip install --force-reinstall torch torchvision torchaudio "numpy<=2.1.1"
```

**5. 安装 FAISS**

GPU 版（需要 CUDA）：

```bash
conda install -c conda-forge faiss-gpu
```

CPU 版（macOS 或无 GPU 环境）：

```bash
pip install faiss-cpu
```

**6. 下载模型**

```bash
python download_models.py
```

脚本会自动下载 MinerU 所需模型并配置 `magic-pdf.json`。BGE-M3 embedding 模型会在首次运行时自动下载。

如使用 CUDA，需修改用户目录下的 `magic-pdf.json`：

```json
{
    "device-mode": "cuda"
}
```

**7. （macOS 额外步骤）安装 Tesseract OCR**

用于扫描版 PDF 的 OCR 回退：

```bash
brew install tesseract
brew install tesseract-lang  # 可选：安装额外语言包
```

**8. 配置 API 密钥**

编辑 `config.py`，填入你的 API 密钥：

```python
# DeepSeek LLM（必需）
API_BASE_URL = "https://api.deepseek.com"
API_KEY = "your-deepseek-api-key"

# MiniMax TTS（可选，不配置则无语音输出）
TTS_GROUP_ID = "your-minimax-group-id"
TTS_API_KEY = "your-minimax-api-key"
```

### 启动运行

```bash
python main.py
```

### 使用流程

1. **导入论文**：点击侧边栏"导入论文"按钮，选择 PDF 文件，等待自动处理完成
2. **阅读论文**：点击侧边栏中的论文名称，中间区域显示论文内容，可通过顶部按钮切换中英文
3. **查看锐评**：选中论文后，右侧聊天框会自动显示教授对该论文的锐评
4. **提问互动**：在聊天框输入问题与教授对话，注意观察好感度变化
5. **组会模式**：点击标题栏"组会"按钮，进入 5 题答辩测试
6. **删除论文**：右键点击侧边栏论文名称，选择删除

---

## 项目结构

```
mad-professor/
├── main.py                    # 程序入口
├── config.py                  # API 配置与模型设置
├── AI_professor_UI.py         # 主窗口 UI
├── AI_manager.py              # AI 功能总管（对话/语音/RAG/好感度/组会/锐评）
├── AI_professor_chat.py       # AI 对话逻辑（多策略路由）
├── affinity_manager.py        # [新增] 好感度系统（5 阶段，按论文追踪）
├── seminar_manager.py         # [新增] 组会模式（5 题渐进式答辩）
├── paper_critique.py          # [新增] 论文锐评生成器
├── data_manager.py            # 数据管理（论文索引/处理队列/删除）
├── rag_retriever.py           # RAG 向量检索
├── pipeline.py                # PDF 处理管线调度器
│
├── processor/                 # 处理器模块（8 阶段流水线）
│   ├── pdf_processor.py       # PDF → Markdown（含 OCR 回退）
│   ├── md_processor.py        # Markdown → 结构化 JSON
│   ├── json_processor.py      # JSON 精炼
│   ├── tiling_processor.py    # 语义分块
│   ├── translate_processor.py # 中英翻译
│   ├── md_restore_processor.py # JSON → Markdown 还原
│   ├── extra_info_processor.py # 摘要/问答/公式分析生成
│   └── rag_processor.py       # FAISS 向量索引构建
│
├── ui/                        # PyQt6 界面组件
│   ├── chat_widget.py         # 聊天界面（含好感度条/组会横幅/冷却提示）
│   ├── markdown_view.py       # 论文渲染（LaTeX/中英切换）
│   ├── message_bubble.py      # 消息气泡
│   ├── sidebar_widget.py      # 侧边栏（论文列表/右键删除）
│   └── upload_widget.py       # 上传对话框
│
├── prompt/                    # LLM 提示词模板
├── assets/                    # UI 资源文件
├── font/                      # 中文字体（思源黑体/宋体）
├── data/                      # 论文 PDF 存放目录
└── output/                    # 处理结果输出目录
```

---

## 技术栈

| 层面        | 技术                              |
| --------- | ------------------------------- |
| 桌面框架      | PyQt6 + PyQt6-WebEngine         |
| LLM       | DeepSeek Chat API（OpenAI 兼容接口）  |
| Embedding | BAAI/bge-m3（多语言，384维）           |
| 向量检索      | FAISS（支持 CPU/GPU）               |
| PDF 解析    | pymupdf4llm + Tesseract OCR（回退） |
| RAG 框架    | LangChain + LangChain-Community |
| 语音输入      | RealtimeSTT（Whisper）            |
| 语音合成      | MiniMax TTS API                 |
| 数学渲染      | KaTeX                           |

## 已知问题

1. 目前仅适用学术论文结构的 PDF，非论文格式可能报错
2. 音频设备未完成加载时激活麦克风可能导致切换失败
3. 外放时 AI 语音可能被重复录入，建议使用耳机
4. 锐评的水分/复现难度评估为 LLM 主观判断，仅供娱乐参考

## 致谢

- 原项目：[LYiHub/mad-professor-public](https://github.com/LYiHub/mad-professor-public)
- [MinerU](https://github.com/opendatalab/MinerU) — PDF 解析
- [RealtimeSTT](https://github.com/KoljaB/RealtimeSTT) — 语音识别
- [DeepSeek](https://www.deepseek.com) — LLM 服务
- [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3) — 多语言 Embedding 模型

## 许可证

本项目采用 Apache 2.0 许可证 — 详情见 [LICENSE](LICENSE) 文件
