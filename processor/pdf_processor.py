from pathlib import Path
import logging
import re

import pymupdf4llm
import fitz

logger = logging.getLogger(__name__)

class PDFProcessor:
    """PDF处理器：将PDF转换为Markdown格式（使用pymupdf4llm，兼容macOS）"""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.logger.debug("初始化PDF处理器（pymupdf4llm后端）")

    def process(self, pdf_path: str, output_dir: str) -> Path:
        """
        处理PDF文件

        Args:
            pdf_path: PDF文件路径
            output_dir: 输出目录路径

        Returns:
            Path: 生成的Markdown文件路径

        Raises:
            FileNotFoundError: 当PDF文件不存在时
        """
        pdf_path = Path(pdf_path)
        output_dir = Path(output_dir)

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")

        try:
            paper_name = pdf_path.stem
            output_image_path = output_dir / "images"
            output_image_path.mkdir(parents=True, exist_ok=True)

            self.logger.info("开始PDF处理流程（pymupdf4llm）...")

            # 使用pymupdf4llm提取markdown
            md_text = pymupdf4llm.to_markdown(str(pdf_path))

            # 检查是否为扫描件（无可提取文本）
            if self._is_empty_extraction(md_text):
                self.logger.warning("检测到PDF可能是扫描件，尝试OCR提取...")
                md_text = self._ocr_extract(pdf_path)

            # 规范化标题级别
            md_text = self._normalize_heading_levels(md_text)

            # 保存Markdown文件
            markdown_path = output_dir / f"{paper_name}.md"
            markdown_path.write_text(md_text, encoding='utf-8')

            self.logger.info(f"Markdown文件已保存到: {markdown_path}")
            return markdown_path

        except Exception as e:
            self.logger.error(f"PDF处理失败: {str(e)}", exc_info=True)
            raise

    def _is_empty_extraction(self, md_text: str) -> bool:
        """检查提取结果是否为空（扫描件PDF的特征）"""
        # 去掉图片占位符和空白后检查是否有实际文字
        cleaned = re.sub(r'\*\*==>.*?<==\*\*', '', md_text)
        cleaned = cleaned.strip()
        # 少于100个字符认为是空的
        return len(cleaned) < 100

    def _find_tessdata(self) -> str:
        """查找 tessdata 目录"""
        import shutil
        candidates = [
            "/opt/homebrew/share/tessdata",
            "/usr/local/share/tessdata",
            "/usr/share/tesseract-ocr/5/tessdata",
            "/usr/share/tessdata",
        ]
        # 如果 tesseract 在 PATH 中，从它推断
        tess = shutil.which("tesseract")
        if tess:
            import subprocess
            try:
                result = subprocess.run([tess, "--print-parameters"],
                                        capture_output=True, text=True, timeout=5)
                for line in result.stdout.split('\n'):
                    if 'tessdata' in line.lower():
                        parts = line.split()
                        if len(parts) >= 2 and Path(parts[-1]).is_dir():
                            candidates.insert(0, parts[-1])
            except Exception:
                pass
        for c in candidates:
            if Path(c).is_dir() and (Path(c) / "eng.traineddata").exists():
                return c
        return ""

    def _ocr_extract(self, pdf_path: Path) -> str:
        """使用 PyMuPDF 内置 OCR 提取扫描件文字"""
        tessdata = self._find_tessdata()
        doc = fitz.open(str(pdf_path))
        md_parts = []

        for page_num in range(doc.page_count):
            page = doc[page_num]
            text = ""
            try:
                kwargs = {"flags": fitz.TEXT_DEHYPHENATE, "language": "eng"}
                if tessdata:
                    kwargs["tessdata"] = tessdata
                tp = page.get_textpage_ocr(**kwargs)
                text = page.get_text("text", textpage=tp).strip()
            except Exception as e:
                self.logger.warning(f"OCR第{page_num}页失败: {e}")
                text = page.get_text("text").strip()

            if text:
                # 简单格式化：每页作为一个段落
                if page_num == 0:
                    # 第一页通常包含标题，取第一行作为标题
                    lines = text.split('\n')
                    if lines:
                        md_parts.append(f"# {lines[0]}")
                        md_parts.append('\n'.join(lines[1:]))
                    else:
                        md_parts.append(text)
                else:
                    md_parts.append(text)

        doc.close()

        if not md_parts:
            self.logger.error("OCR提取也失败了，PDF可能是纯图片格式")
            return "# 无法提取文本\n\n该PDF为纯图片格式，无法自动提取文本内容。"

        return '\n\n'.join(md_parts)

    def _normalize_heading_levels(self, md_text: str) -> str:
        """将标题级别规范化：找到最小级别并整体提升到 # 开始。
        pymupdf4llm 倾向于用 ## 作为顶级，而 md_processor 期望 # 作为顶级。"""
        import re
        lines = md_text.split('\n')
        heading_levels = []
        for line in lines:
            m = re.match(r'^(#+)\s', line)
            if m:
                heading_levels.append(len(m.group(1)))

        if not heading_levels:
            return md_text

        min_level = min(heading_levels)
        if min_level <= 1:
            return md_text  # 已经有一级标题，无需调整

        # 把所有标题提升 (min_level - 1) 级
        shift = min_level - 1
        normalized = []
        for line in lines:
            m = re.match(r'^(#+)(\s.*)', line)
            if m:
                new_hashes = '#' * (len(m.group(1)) - shift)
                line = new_hashes + m.group(2)
            normalized.append(line)
        return '\n'.join(normalized)
