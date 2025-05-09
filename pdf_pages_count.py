# Requires: pip install tabulate PyPDF2
import logging
from pathlib import Path
from typing import Union
from PyPDF2 import PdfReader
from PyPDF2.errors import PdfReadWarning
from tabulate import tabulate
import warnings

warnings.filterwarnings("ignore", category=PdfReadWarning)

# --- Logging setup ---
LOG_DIR = Path('logs')
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / 'check.txt'

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# File handler
fh = logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')
fh.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s | %(levelname)-7s | %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)

# Console handler
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(formatter)
logger.addHandler(ch)
# ---------------------

def count_pdf_pages(folder: Union[str, Path]) -> int:
    """
    Recursively count all pages in every PDF under `folder` using metadata only.
    """
    total_pages = 0
    folder = Path(folder)
    for pdf_path in folder.rglob('*.pdf'):
        try:
            reader = PdfReader(str(pdf_path))
            # Use the /Count entry from the page tree root instead of loading all pages
            page_count = reader.trailer['/Root']['/Pages']['/Count']
            total_pages += page_count
        except Exception as e:
            logger.warning(f"⚠️ Skipping {pdf_path!r}: {e}")
    return total_pages

if __name__ == "__main__":
    root1 = Path("D:/01_unzipped")
    root2 = Path("D:/02_processed")

    # Get set of customer-folder names in each root
    names1 = {p.name for p in root1.iterdir() if p.is_dir()}
    names2 = {p.name for p in root2.iterdir() if p.is_dir()}

    # Build a sorted list of all customer names present in either root
    all_customers = sorted(names1 | names2)

    # Prepare presence table rows
    rows = []
    for customer in all_customers:
        in1 = '✅' if customer in names1 else '❌'
        in2 = '✅' if customer in names2 else '❌'
        rows.append([in1, customer, in2])

    # Log the presence table
    table = tabulate(rows, headers=[str(root1), "customer_folder", str(root2)], tablefmt="github")
    logger.info("Customer-folder presence:\n" + table)

    # Compare page counts for common customers
    logger.info("Page counts for common customers:")
    for customer in sorted(names1 & names2):
        folder1 = root1 / customer
        folder2 = root2 / customer

        pages1 = count_pdf_pages(folder1)
        pages2 = count_pdf_pages(folder2)

        status = "✅" if pages1 == pages2 else "❌"
        logger.info(f"{status} {customer}")
        logger.info(f"    • {pages1} pages in {folder1}")
        logger.info(f"    • {pages2} pages in {folder2}")
        
        # # If totals don’t match, enumerate exactly which split‐page PDFs are missing
        # if pages1 != pages2:
        #     for pdf_path in folder1.rglob('*.pdf'):
        #         try:
        #             reader = PdfReader(str(pdf_path))
        #             page_count = reader.trailer['/Root']['/Pages']['/Count']
        #         except Exception as e:
        #             logger.warning(f"⚠️ Unable to read {pdf_path!r} for missing‐page check: {e}")
        #             continue

        #         missing = []
        #         base = pdf_path.stem
        #         for i in range(1, page_count + 1):
        #             # allow any prefix, but require basename_page_<n>.pdf at the end
        #             pattern = f"*{base}_page_{i}.pdf"
        #             if not list(folder2.rglob(pattern)):
        #                 missing.append(i)

        #         if missing:
        #             missing_str = ', '.join(str(n) for n in missing)
        #             logger.info(f"        • Missing pages for {pdf_path.name}: {missing_str}")