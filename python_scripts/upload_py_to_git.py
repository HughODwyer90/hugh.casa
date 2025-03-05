import os
from fnmatch import fnmatch
from secret_manager import SecretsManager
from git_uploader import GitHubUploader

EXCLUDE_FILE_PATH = "/config/text_files/excluded_files.txt"  # Updated path

def load_exclusions():
    """Load excluded files and patterns from a text file."""
    if os.path.exists(EXCLUDE_FILE_PATH):
        with open(EXCLUDE_FILE_PATH, "r") as f:
            return [line.strip() for line in f.readlines() if line.strip()]
    return []

def should_exclude(filename, exclusions):
    """Check if a file should be excluded based on patterns."""
    return any(fnmatch(filename, pattern) for pattern in exclusions)

def get_python_files(directory, exclusions):
    """Retrieve Python files from the specified directory, excluding specified files."""
    return [f for f in os.listdir(directory) if f.endswith(".py") and not should_exclude(f, exclusions)]

def main():
    try:
        secrets = SecretsManager()
        github_token = secrets["github_token"]
        github_repo = secrets["github_repro"]

        if not github_token or not github_repo:
            print("❌ Error: Missing required tokens or repository in secrets.yaml.")
            return

        uploader = GitHubUploader(github_token=github_token, repo_name=github_repo)
        py_scripts_directory = "/config/python_scripts"
        exclusions = load_exclusions()

        if not os.path.exists(py_scripts_directory):
            raise FileNotFoundError(f"❌ The directory {py_scripts_directory} does not exist.")

        py_files = get_python_files(py_scripts_directory, exclusions)

        if not py_files:
            print("⚠️ No Python files found after exclusions.")
            return

        print(f"📂 Processing Python files: {', '.join(py_files)}")

        for py_file in py_files:
            local_file_path = os.path.join(py_scripts_directory, py_file)
            github_file_path = f"python_scripts/{py_file}"

            try:
                uploader.upload_file(
                    local_file_path=local_file_path,
                    github_file_path=github_file_path,
                    commit_message=f"Update {py_file}"
                )
                print(f"✅ Successfully uploaded: {py_file}")
            except Exception as e:
                print(f"❌ Error uploading {py_file}: {e}")

        print("✅ All Python files have been uploaded successfully.")

    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()