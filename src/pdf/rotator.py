"""PDF page rotation operations."""

import logging
import fitz


class PDFRotator:
    """Handles PDF page rotation operations."""
    
    @staticmethod
    def rotate_pdf(page_doc, rotation_angle: int):
        """
        Rotate a PDF document by the specified angle.
        
        Args:
            page_doc: PyMuPDF document containing a single page
            rotation_angle: Angle to rotate (0, 90, 180, 270)
            
        Returns:
            PyMuPDF document with rotated page
        """
        if rotation_angle == 0:
            return page_doc
        
        try:
            rotated = fitz.open()
            for page in page_doc:
                mat = fitz.Matrix(1, 1).prerotate(rotation_angle)
                pix = page.get_pixmap(matrix=mat)
                new_page = rotated.new_page(width=pix.width, height=pix.height)
                new_page.insert_image(new_page.rect, pixmap=pix)
            return rotated
        except Exception as e:
            logging.error(f"Error rotating PDF: {e}")
            return page_doc
