"""
预下载 BAAI/bge-m3 嵌入模型
运行: ./venv/bin/python download_bge_m3.py
下载完成后再启动主程序
"""
from sentence_transformers import SentenceTransformer
import sys

print("开始下载 BAAI/bge-m3 模型（约2.27GB），请耐心等待...")
print("下载会在断点处续传，进度会显示在下方")
print("-" * 50)

try:
    model = SentenceTransformer("BAAI/bge-m3")
    # 测试一下
    test = model.encode(["测试句子"])
    print("-" * 50)
    print(f"✓ 模型下载完成！向量维度: {test.shape[1]}")
    print("现在可以启动主程序: ./venv/bin/python main.py")
except Exception as e:
    print(f"✗ 下载失败: {e}")
    sys.exit(1)
