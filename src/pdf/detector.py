"""PDF page orientation detection using OCR."""

import io
import logging
import fitz
import pytesseract
from PIL import Image
from pytesseract import TesseractError


class OrientationDetector:
    """Handles PDF page orientation detection using OCR."""
    
    @staticmethod
    def detect_orientation(pdf_document, source_path: str, page_no: int, 
                          initial_dpi: int = 200, max_trials: int = 3) -> int:
        """
        Detect the orientation of a PDF page using Tesseract OCR.
        
        Returns:
            int: Rotation angle needed to correct orientation (0, 90, 180, 270)
        """
        dpi = initial_dpi
        last_rotate = 0
        last_conf = 0

        for trial in range(1, max_trials + 1):
            try:
                # Rasterize page to PIL image
                pix = pdf_document[0].get_pixmap(dpi=dpi)
                png_bytes = pix.tobytes("png")
                img = Image.open(io.BytesIO(png_bytes))

                # Run Tesseract OSD (Orientation and Script Detection)
                try:
                    osd = pytesseract.image_to_osd(img, output_type=pytesseract.Output.DICT)
                    rotate = int(osd.get('rotate', 0) or 0)
                    conf = float(osd.get('orientation_conf', 0) or 0.0)
                except TesseractError as te:
                    logging.warning(f"OSD failed for {source_path}, page {page_no+1}: {te}")
                    rotate, conf = 0, 0.0

                logging.debug(f"Trial {trial}: DPI={dpi}, orientation={rotate}, confidence={conf}"
                             f" (File={source_path}, Page={page_no + 1})")

                # Accept result if confidence is sufficient
                if conf >= 2:
                    if trial > 1:
                        logging.info(f"Orientation ({rotate}) stabilized at trial {trial}"
                                   f" (DPI={dpi}, confidence={conf}) {source_path}, page {page_no+1}")
                    return rotate

                # Low confidence - increase DPI and retry
                last_rotate, last_conf = rotate, conf
                logging.warning(f"Low orientation confidence ({conf:.1f}) at DPI={dpi}"
                               f" for {source_path}, page {page_no + 1}; retrying with higher DPI.")
                dpi += 100

            except Exception as e:
                err_msg = (f"Orientation detection failed on trial {trial} "
                          f"(DPI={dpi}) for {source_path}, page {page_no + 1}: {e}")
                logging.error(err_msg, exc_info=True)
                dpi += 100

        logging.warning(f"Max trials reached for {source_path}, page {page_no+1}. "
                       f"Returning last {last_rotate}° @ confidence {last_conf}")
        return last_rotate
