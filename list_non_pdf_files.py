import os

# Change this to your target directory
TARGET_DIR = os.path.abspath('./input')

def list_non_pdf_files(target_dir):
    for dirpath, dirnames, filenames in os.walk(target_dir):
        for fname in filenames:
            if not fname.lower().endswith('.pdf'):
                print(os.path.join(dirpath, fname))

if __name__ == '__main__':
    list_non_pdf_files(TARGET_DIR)
