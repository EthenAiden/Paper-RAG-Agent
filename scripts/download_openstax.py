"""
OpenStax 免费教材下载脚本
OpenStax 提供 50+ 本经过同行评审的开源教材，采用 CC BY 4.0 许可证
官网: https://openstax.org
"""

import os
import requests
import json
from pathlib import Path

# OpenStax API 端点
API_URL = "https://openstax.org/apps/cms/api/v2/pages/?type=books.Book&fields=*,high_resolution_pdf_url,low_resolution_pdf_url,title,slug,subjects"

# 下载目录
DOWNLOAD_DIR = Path("test_textbooks")

def get_books():
    """获取所有可下载的教材列表"""
    print("正在获取教材列表...")
    response = requests.get(API_URL)
    response.raise_for_status()
    data = response.json()
    
    books = []
    for item in data.get('items', []):
        pdf_url = item.get('high_resolution_pdf_url') or item.get('low_resolution_pdf_url')
        if pdf_url:
            books.append({
                'title': item.get('title'),
                'slug': item.get('slug'),
                'pdf_url': pdf_url,
                'subjects': item.get('subjects', [])
            })
    return books

def download_book(book, output_dir):
    """下载单本教材"""
    title = book['title']
    pdf_url = book['pdf_url']
    
    # 清理文件名
    safe_title = "".join(c if c.isalnum() or c in (' ', '-', '_') else '' for c in title)
    filename = f"{safe_title}.pdf"
    filepath = output_dir / filename
    
    if filepath.exists():
        print(f"  [跳过] {title} - 已存在")
        return str(filepath)
    
    print(f"  [下载] {title}...")
    
    try:
        response = requests.get(pdf_url, stream=True)
        response.raise_for_status()
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"  [完成] {filename}")
        return str(filepath)
    except Exception as e:
        print(f"  [错误] 下载失败: {e}")
        return None

def main():
    # 创建下载目录
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    
    # 获取教材列表
    books = get_books()
    print(f"找到 {len(books)} 本可下载的教材\n")
    
    # 显示教材列表
    print("=" * 60)
    print("可下载的教材列表:")
    print("=" * 60)
    for i, book in enumerate(books, 1):
        subjects = ', '.join(book['subjects']) if book['subjects'] else '未分类'
        print(f"{i:2d}. {book['title']} ({subjects})")
    print("=" * 60)
    
    # 选择下载方式
    print("\n请选择下载方式:")
    print("1. 下载所有教材")
    print("2. 选择特定教材下载")
    print("3. 仅下载计算机/数学相关教材")
    print("4. 退出")
    
    choice = input("\n请输入选项 (1-4): ").strip()
    
    if choice == '1':
        print("\n开始下载所有教材...")
        downloaded = []
        for book in books:
            result = download_book(book, DOWNLOAD_DIR)
            if result:
                downloaded.append(result)
        print(f"\n下载完成! 共下载 {len(downloaded)} 本教材到 {DOWNLOAD_DIR}")
        
    elif choice == '2':
        print("\n请输入要下载的教材编号 (用逗号分隔，如: 1,3,5):")
        indices = input("> ").strip()
        try:
            selected = [int(i.strip()) - 1 for i in indices.split(',')]
            print("\n开始下载选中的教材...")
            for idx in selected:
                if 0 <= idx < len(books):
                    download_book(books[idx], DOWNLOAD_DIR)
            print(f"\n下载完成!")
        except ValueError:
            print("输入无效")
            
    elif choice == '3':
        # 筛选计算机/数学相关
        keywords = ['math', 'computer', 'calculus', 'statistics', 'algebra', 'programming']
        filtered = []
        for book in books:
            title_lower = book['title'].lower()
            subjects_lower = [s.lower() for s in book['subjects']]
            if any(kw in title_lower or any(kw in s for s in subjects_lower) for kw in keywords):
                filtered.append(book)
        
        print(f"\n找到 {len(filtered)} 本相关教材:")
        for book in filtered:
            print(f"  - {book['title']}")
        
        confirm = input("\n是否下载? (y/n): ").strip().lower()
        if confirm == 'y':
            for book in filtered:
                download_book(book, DOWNLOAD_DIR)
            print("\n下载完成!")
    
    elif choice == '4':
        print("已退出")
    else:
        print("无效选项")

if __name__ == "__main__":
    main()