import os
import random
import io
from PyPDF2 import PdfReader, PdfWriter
from pathlib import Path

def get_all_pdf_paths(folder):
    return list(Path(folder).rglob("*.pdf"))

def merge_and_rotate_pdfs(pdf_paths, rotate_probability=0.8, page_cap=None):
    writer = PdfWriter()
    all_pages = []

    # Process each PDF and collect the pages
    for pdf_path in pdf_paths:
        reader = PdfReader(str(pdf_path))
        for page in reader.pages:
            if random.random() < rotate_probability:
                angle = random.choice([90, 180, 270])
                page.rotate(angle)
            all_pages.append(page)

    # Shuffle all pages
    random.shuffle(all_pages)

    # Cap the number of pages if necessary
    if page_cap:
        all_pages = all_pages[:page_cap]

    # Add pages to the writer
    for page in all_pages:
        writer.add_page(page)

    # Create an in-memory PDF output
    output_pdf_io = io.BytesIO()
    writer.write(output_pdf_io)

    # Return the in-memory PDF
    return output_pdf_io.getvalue()

if __name__ == "__main__":
    folder = "samples/libra"  # change this to your folder path
    output_pdf = "samples/sample.pdf"
    n = 10  # number of PDFs to merge
    page_cap = 15  # limit the number of pages to 10 (set to None for no limit)

    all_pdfs = get_all_pdf_paths(folder)
    selected_pdfs = random.sample(all_pdfs, min(n, len(all_pdfs)))

    merged_pdf = merge_and_rotate_pdfs(selected_pdfs, rotate_probability=0.8, page_cap=page_cap)

    # Save the final output PDF to a file
    with open(output_pdf, "wb") as f_out:
        f_out.write(merged_pdf)

    print(f"Merged {len(selected_pdfs)} PDFs and saved the result to {output_pdf}")
