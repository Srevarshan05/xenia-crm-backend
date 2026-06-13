import os
import zipfile

def clean_and_zip(source_dir, zip_filename, exclude_dirs, exclude_files=None, include_files_only=None):
    """
    Creates a ZIP archive from source_dir, excluding specified directories and files.
    """
    if exclude_files is None:
        exclude_files = set()
    
    print(f"Creating {zip_filename} from {source_dir}...")
    
    # Absolute paths for comparison
    source_dir = os.path.abspath(source_dir)
    
    # Check if archive exists, delete it first
    if os.path.exists(zip_filename):
        os.remove(zip_filename)
        
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            # Exclude folders by modifying dirs list in-place
            dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith('.')]
            
            # Relative directory path from source_dir
            rel_dir = os.path.relpath(root, source_dir)
            
            for file in files:
                # Exclude specific files or extensions
                if file in exclude_files or file.endswith('.pyc') or file.endswith('.db') or file.endswith('.log') or file.startswith('.'):
                    continue
                
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, source_dir)
                
                # If we have a whitelist, enforce it
                if include_files_only is not None and rel_path not in include_files_only:
                    continue
                
                zipf.write(full_path, rel_path)
                
    print(f"Successfully created {zip_filename} ({os.path.getsize(zip_filename)} bytes).")

def main():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    backend_src = os.path.join(base_dir, "backend")
    channel_src = os.path.join(base_dir, "channel-service")
    
    dist_dir = os.path.join(base_dir, "backend", "dist")
    if not os.path.exists(dist_dir):
        os.makedirs(dist_dir)
        
    # 1. Package Xenia Main Backend
    backend_exclude_dirs = {
        "venv", ".git", "node_modules", "__pycache__", "dist", ".pytest_cache", "brain"
    }
    backend_exclude_files = {
        ".env", ".env.example", "create_db.py", "results.json", "check_search_path.py", "find_ddg.py", "find_icons.py"
    }
    zip_backend_path = os.path.join(dist_dir, "backend-v1-2.zip")
    clean_and_zip(backend_src, zip_backend_path, backend_exclude_dirs, backend_exclude_files)
    
    # 2. Package Channel Simulator
    channel_exclude_dirs = {
        "venv", ".git", "node_modules", "__pycache__"
    }
    zip_channel_path = os.path.join(dist_dir, "channel_v1.zip")
    clean_and_zip(channel_src, zip_channel_path, channel_exclude_dirs)
    
    print("\nPackaging completed. Files are saved in backend/dist/")

if __name__ == "__main__":
    main()
