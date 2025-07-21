import sys
import fitz  # PyMuPDF

def debug_pdf(pdf_path):
    print(f"--- Debugging PDF: {pdf_path} ---")
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"Failed to open PDF: {e}")
        return

    page_count = doc.page_count
    print(f"Reported page count: {page_count}")

    for idx in range(page_count + 2):  # Try to go 2 beyond reported count
        print(f"\nTrying to access page index {idx} (human page {idx+1})...")
        try:
            page = doc.load_page(idx)
            print(f"  Success: Page {idx} loaded.")
            print(f"  Page size: {page.rect}")
            # Optionally, print more info (metadata, text, etc.)
            text = page.get_text("text")
            print(f"  Page text length: {len(text)}")
        except Exception as e:
            print(f"  Error accessing page {idx}: {e}")

    doc.close()
    print("--- End of PDF debug ---")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python .\pdf_index_err_check.py <pdf_path>")
    else:
        debug_pdf(sys.argv[1])