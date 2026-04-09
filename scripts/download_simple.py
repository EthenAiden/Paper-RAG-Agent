"""
简化版教材下载脚本 - 直接下载几本常用的开源教材
"""

import os
import requests
from pathlib import Path

# 预定义的免费开源教材 (来自 OpenStax, CC BY 4.0 许可)
TEXTBOOKS = [
    {
        "title": "Calculus Volume 1",
        "url": "https://assets.openstax.org/oscms-prodcms/media/documents/Calculus_Volume_1_-_WEB.pdf",
        "category": "数学"
    },
    {
        "title": "Calculus Volume 2",
        "url": "https://assets.openstax.org/oscms-prodcms/media/documents/Calculus_Volume_2_-_WEB.pdf",
        "category": "数学"
    },
    {
        "title": "Calculus Volume 3",
        "url": "https://assets.openstax.org/oscms-prodcms/media/documents/Calculus_Volume_3_-_WEB.pdf",
        "category": "数学"
    },
    {
        "title": "College Physics",
        "url": "https://assets.openstax.org/oscms-prodcms/media/documents/College_Physics_2e_-_WEB.pdf",
        "category": "物理"
    },
    {
        "title": "Chemistry 2e",
        "url": "https://assets.openstax.org/oscms-prodcms/media/documents/Chemistry_2e_-_WEB.pdf",
        "category": "化学"
    },
    {
        "title": "Biology 2e",
        "url": "https://assets.openstax.org/oscms-prodcms/media/documents/Biology_2e_-_WEB.pdf",
        "category": "生物"
    },
    {
        "title": "Introduction to Sociology 3e",
        "url": "https://assets.openstax.org/oscms-prodcms/media/documents/Introduction_to_Sociology_3e_-_WEB.pdf",
        "category": "社会学"
    },
    {
        "title": "Principles of Economics",
        "url": "https://assets.openstax.org/oscms-prodcms/media/documents/Principles_of_Economics_3e_-_WEB.pdf",
        "category": "经济学"
    },
    {
        "title": "Psychology 2e",
        "url": "https://assets.openstax.org/oscms-prodcms/media/documents/Psychology_2e_-_WEB.pdf",
        "category": "心理学"
    },
    {
        "title": "Statistics",
        "url": "https://assets.openstax.org/oscms-prodcms/media/documents/Introductory_Statistics_2e_-_WEB.pdf",
        "category": "数学"
    }
]

def download_file(url, filepath):
    """下载文件"""
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"  错误: {e}")
        return False

def main():
    # 创建下载目录
    output_dir = Path("test_textbooks")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("OpenStax 免费开源教材下载")
    print("来源: https://openstax.org (CC BY 4.0 许可)")
    print("=" * 60)
    print(f"\n将下载 {len(TEXTBOOKS)} 本教材到: {output_dir.absolute()}\n")
    
    downloaded = 0
    for book in TEXTBOOKS:
        title = book['title']
        url = book['url']
        category = book['category']
        
        # 清理文件名
        safe_title = "".join(c if c.isalnum() or c in (' ', '-') else '' for c in title)
        filename = f"{safe_title}.pdf"
        filepath = output_dir / filename
        
        print(f"[{category}] {title}")
        
        if filepath.exists():
            print(f"  已存在，跳过")
            downloaded += 1
            continue
        
        print(f"  下载中...", end=" ")
        if download_file(url, filepath):
            print("完成!")
            downloaded += 1
    
    print(f"\n{'=' * 60}")
    print(f"下载完成! 成功: {downloaded}/{len(TEXTBOOKS)}")
    print(f"文件位置: {output_dir.absolute()}")
    print("=" * 60)

if __name__ == "__main__":
    main()