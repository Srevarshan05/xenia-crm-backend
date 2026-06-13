import os
import zipfile

def create_zip():
    zip_filename = "../backend_deploy.zip"
    if os.path.exists(zip_filename):
        os.remove(zip_filename)
        
    include_dirs = ["app", "alembic", "ml", "scripts"]
    include_files = ["application.py", "Procfile", "requirements.txt", "runtime.txt", "alembic.ini"]
    
    exclude_patterns = [
        "__pycache__",
        ".pyc",
        ".pyo",
        ".git",
        "venv",
        ".venv",
        ".pytest_cache",
        "run.log",
        "create_deploy_zip.py"
    ]
    
    count = 0
    with zipfile.ZipFile(zip_filename, "w", zipfile.ZIP_DEFLATED) as zipf:
        # Include top-level files
        for f in include_files:
            if os.path.exists(f):
                print(f"Adding file: {f}")
                zipf.write(f)
                count += 1
                
        # Include directories
        for d in include_dirs:
            if not os.path.exists(d):
                continue
            for root, dirs, files in os.walk(d):
                # Skip excluded directories
                if any(p in root for p in exclude_patterns):
                    continue
                for file in files:
                    if any(p in file for p in exclude_patterns):
                        continue
                    file_path = os.path.join(root, file)
                    # Use relative path for zip mapping
                    arcname = os.path.relpath(file_path, os.getcwd())
                    print(f"Adding file: {arcname}")
                    zipf.write(file_path, arcname=arcname)
                    count += 1
                    
    print(f"\nSuccessfully created {zip_filename} with {count} files.")

if __name__ == "__main__":
    create_zip()
