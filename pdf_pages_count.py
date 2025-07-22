import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import threading
from tqdm import tqdm
import queue
import time
from datetime import datetime

def scan_directory(directory, file_queue, progress_bar, lock):
    """Scan a directory and add files to queue."""
    try:
        for root, dirs, files in os.walk(directory):
            for file in files:
                file_queue.put(os.path.join(root, file))
                with lock:
                    progress_bar.update(1)
    except Exception as e:
        print(f"Error scanning {directory}: {e}")

def scan_directories_parallel(root_directory):
    """Parallel directory scanning with dynamic progress bar."""
    file_queue = queue.Queue()
    lock = threading.Lock()
    
    # Get immediate subdirectories
    subdirs = []
    try:
        for item in os.listdir(root_directory):
            path = os.path.join(root_directory, item)
            if os.path.isdir(path):
                subdirs.append(path)
    except Exception as e:
        print(f"Error listing directory: {e}")
        return []
    
    if not subdirs:
        subdirs = [root_directory]  # Scan root if no subdirs
    
    print(f"Scanning {len(subdirs)} directories in parallel...")
    
    with tqdm(desc="Files found", unit="files", dynamic_ncols=True) as pbar:
        with ThreadPoolExecutor(max_workers=min(20, len(subdirs))) as executor:
            futures = [executor.submit(scan_directory, subdir, file_queue, pbar, lock) 
                      for subdir in subdirs]
            
            # Wait for all scanning to complete
            for future in as_completed(futures):
                future.result()
    
    # Convert queue to list
    files = []
    while not file_queue.empty():
        files.append(file_queue.get())
    
    return files

def main():
    # Set your directory path here
    directory = 'W:/03_processati'
    
    if not os.path.exists(directory):
        print("Directory not found!")
        return
    
    print("Scanning directory structure...")
    all_files = scan_directories_parallel(directory)
    
    if not all_files:
        print("No files found!")
        return
    
    # Count file types and folders
    file_types = {}
    folder_counts = {}
    
    for file_path in all_files:
        # File type counting
        ext = os.path.splitext(file_path)[1].lower()
        if not ext:
            ext = '<no extension>'
        file_types[ext] = file_types.get(ext, 0) + 1
        
        # Folder counting
        folder = os.path.dirname(file_path)
        folder_counts[folder] = folder_counts.get(folder, 0) + 1
    
    # Print summary
    print(f"\n--- FILE COUNT SUMMARY ---")
    print(f"Total files found: {len(all_files):,}")
    print(f"\nFile types breakdown:")
    for ext, count in sorted(file_types.items(), key=lambda x: x[1], reverse=True):
        print(f"  {ext}: {count:,}")
    
    print(f"\nTop folders by file count:")
    for folder, count in sorted(folder_counts.items(), key=lambda x: x[0]):
        print(f"  {folder}: {count:,}")
        
    # Log to file
    log_dir = "logs/count"
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"file_count_{timestamp}.txt")
    
    with open(log_file, 'w', encoding='utf-8') as f:
        f.write(f"File Count Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Directory: {directory}\n")
        f.write(f"=" * 60 + "\n\n")
        f.write(f"Total files found: {len(all_files):,}\n")
        f.write(f"Total folders: {len(folder_counts):,}\n\n")
        
        f.write("File types breakdown:\n")
        for ext, count in sorted(file_types.items(), key=lambda x: x[1], reverse=True):
            f.write(f"  {ext}: {count:,}\n")
        
        f.write("\nFolders by file count:\n")
        for folder, count in sorted(folder_counts.items(), key=lambda x: x[0]):
            f.write(f"  {folder}: {count:,}\n")
    
    print(f"\nResults logged to: {log_file}")

if __name__ == "__main__":
    main()