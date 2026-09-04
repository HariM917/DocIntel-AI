import os
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any

import fitz  # PyMuPDF
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import pytesseract
from pytesseract import Output

from app.config import settings

logger = logging.getLogger("docintel.ocr")


class OCRService:
    def __init__(self):
        self._init_tesseract()

    def _init_tesseract(self):
        cmd = settings.TESSERACT_CMD
        if cmd and os.path.exists(cmd):
            pytesseract.pytesseract.tesseract_cmd = cmd
            logger.info(f"Tesseract OCR initialized from configured path: {cmd}")
        else:
            system_cmd = shutil.which("tesseract")
            if system_cmd:
                pytesseract.pytesseract.tesseract_cmd = system_cmd
                logger.info(f"Tesseract OCR found on system PATH: {system_cmd}")
            else:
                default_win = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
                if os.path.exists(default_win):
                    pytesseract.pytesseract.tesseract_cmd = default_win
                    logger.info(f"Tesseract OCR initialized from default Windows path: {default_win}")
                else:
                    logger.warning("Tesseract binary not found. OCR will run in fallback text mode.")

    def preprocess_image(self, image: Image.Image) -> Image.Image:
        """Preprocesses image for optimal OCR: grayscale, autocontrast, sharpness, thresholding."""
        try:
            # 1. Convert to Grayscale
            gray = image.convert("L")

            # 2. Enhance contrast
            enhancer = ImageEnhance.Contrast(gray)
            enhanced = enhancer.enhance(1.8)

            # 3. Enhance sharpness
            sharpness = ImageEnhance.Sharpness(enhanced)
            sharpened = sharpness.enhance(1.5)

            # 4. Optional adaptive binarization / thresholding
            threshold = 180
            binarized = sharpened.point(lambda p: 255 if p > threshold else 0)
            return binarized
        except Exception as e:
            logger.warning(f"Image preprocessing warning: {e}, falling back to original image")
            return image

    def extract_text_from_image(self, image: Image.Image) -> Tuple[str, float]:
        """Runs Tesseract OCR on a PIL Image, returning extracted text and mean confidence (0.0 to 1.0)."""
        try:
            preprocessed = self.preprocess_image(image)
            data = pytesseract.image_to_data(preprocessed, output_type=Output.DICT)
            
            words = []
            confidences = []
            for i in range(len(data["text"])):
                word = data["text"][i].strip()
                conf = float(data["conf"][i])
                if word:
                    words.append(word)
                    if conf >= 0:
                        confidences.append(conf)

            text = pytesseract.image_to_string(preprocessed)
            mean_conf = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.85
            return text.strip(), round(min(1.0, max(0.1, mean_conf)), 4)
        except Exception as e:
            logger.error(f"OCR image extraction error: {e}")
            # Fallback: simple image_to_string without data table
            try:
                text = pytesseract.image_to_string(image)
                return text.strip(), 0.75
            except Exception as e2:
                logger.error(f"Fallback OCR also failed: {e2}")
                return "", 0.0

    def extract_text_from_pdf(self, file_path: Path) -> Tuple[str, float, int]:
        """Extracts text from PDF. If native text is present, uses it; otherwise renders pages to images for OCR."""
        try:
            doc = fitz.open(file_path)
            num_pages = len(doc)
            page_texts: List[str] = []
            confidences: List[float] = []

            for page_num in range(num_pages):
                page = doc[page_num]
                native_text = page.get_text().strip()

                # If the PDF page has sufficient embedded text, use it
                if len(native_text) > 40:
                    page_texts.append(native_text)
                    confidences.append(0.98)
                else:
                    # Render page to high-res image (300 DPI) for OCR
                    pix = page.get_pixmap(dpi=300)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    ocr_text, conf = self.extract_text_from_image(img)
                    page_texts.append(ocr_text)
                    confidences.append(conf)

            full_text = "\n\n--- Page Break ---\n\n".join(page_texts)
            avg_conf = (sum(confidences) / len(confidences)) if confidences else 0.85
            return full_text.strip(), round(avg_conf, 4), num_pages
        except Exception as e:
            logger.error(f"PDF processing error: {e}")
            return "", 0.0, 0

    def process_document(self, file_path: Path) -> Dict[str, Any]:
        """Main OCR entry point for both PDF and image files."""
        ext = file_path.suffix.lower()
        if ext == ".pdf":
            text, confidence, pages = self.extract_text_from_pdf(file_path)
            return {
                "text": text,
                "confidence": confidence,
                "pages": pages,
                "method": "pdf_pymupdf_tesseract",
            }
        elif ext in [".jpg", ".jpeg", ".png"]:
            try:
                img = Image.open(file_path)
                text, confidence = self.extract_text_from_image(img)
                return {
                    "text": text,
                    "confidence": confidence,
                    "pages": 1,
                    "method": "image_tesseract",
                }
            except Exception as e:
                logger.error(f"Error opening image file {file_path}: {e}")
                return {
                    "text": "",
                    "confidence": 0.0,
                    "pages": 1,
                    "method": "failed",
                    "error": str(e),
                }
        else:
            raise ValueError(f"Unsupported file extension: {ext}")


ocr_service = OCRService()
