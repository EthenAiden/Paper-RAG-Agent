"""
OCR 服务 - 提供 HTTP API
"""
import tempfile
import logging
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from unstructured.partition.pdf import partition_pdf
from unstructured.partition.image import partition_image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="OCR Service", version="1.0.0")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/ocr")
async def ocr_file(file: UploadFile = File(...), languages: str = "chi_sim+eng"):
    """
    OCR 识别文件（PDF 或图片）
    
    Args:
        file: 上传的文件
        languages: OCR 语言，默认中英文，用 + 分隔
    
    Returns:
        {"text": "识别出的文本"}
    """
    ext = Path(file.filename).suffix.lower()
    
    if ext not in {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp"}:
        raise HTTPException(400, f"不支持的文件格式: {ext}")
    
    lang_list = languages.split("+")
    
    # 保存到临时文件
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        if ext == ".pdf":
            elements = partition_pdf(
                filename=tmp_path,
                languages=lang_list,
                extract_images_in_pdf=True,
            )
        else:
            elements = partition_image(
                filename=tmp_path,
                languages=lang_list,
            )
        
        text = "\n".join(str(el) for el in elements)
        logger.info(f"OCR 完成: {file.filename}, 字符数: {len(text)}")
        
        return {"text": text}
    
    except Exception as e:
        logger.error(f"OCR 失败: {e}")
        raise HTTPException(500, f"OCR 失败: {str(e)}")
    
    finally:
        import os
        os.unlink(tmp_path)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)