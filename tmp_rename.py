import os
import re

def add_dash_to_page_number(root_folder):
    for dirpath, _, files in os.walk(root_folder):
        for fname in files:
            if fname.lower().endswith('.pdf'):
                # Only match the last 'page' before the number and .pdf
                new_fname = re.sub(r'(page)(\d+)(\.pdf)$', r'page-\2\3', fname, flags=re.IGNORECASE)
                if new_fname != fname:
                    src = os.path.join(dirpath, fname)
                    dst = os.path.join(dirpath, new_fname)
                    # Avoid overwriting existing files
                    if not os.path.exists(dst):
                        print(f"Renaming: {src} -> {dst}")
                        os.rename(src, dst)
                    else:
                        print(f"SKIP (target exists): {dst}")

if __name__ == "__main__":
    folder = r"W:/03_processati"  # Change this to your output folder
    add_dash_to_page_number(folder)