import os
from datetime import datetime
from secret_manager import SecretsManager  # Import the SecretsManager class
from git_uploader import GitHubUploader  # Import the GitHubUploader class

# Function to retrieve all .py files from the specified directory
def get_python_files(directory):
    """Retrieve all Python files from the specified directory."""
    return [f for f in os.listdir(directory) if f.endswith(".py")]

# Main script logic
try:
    # Load secrets
    secrets = SecretsManager()

    # Retrieve secrets from the SecretsManager
    github_token = secrets["github_token"]
    github_repo = secrets["github_repro"]

    if not github_token or not github_repo:
        print("Error: Missing required tokens or repository in secrets.yaml.")
        exit(1)

    # Initialize GitHubUploader
    uploader = GitHubUploader(github_token=github_token, repo_name=github_repo)

    # Directory containing Python scripts
    py_scripts_directory = "/config/python_scripts"

    # Ensure the directory exists
    if not os.path.exists(py_scripts_directory):
        raise FileNotFoundError(f"The directory {py_scripts_directory} does not exist.")

    # Get all Python files in the directory
    py_files = get_python_files(py_scripts_directory)

    if not py_files:
        print("No Python files found in the directory.")
        exit(0)

    print(f"Found Python files: {', '.join(py_files)}")

    # Upload each Python file to GitHub
    for py_file in py_files:
        local_file_path = os.path.join(py_scripts_directory, py_file)
        github_file_path = f"python_scripts/{py_file}"

        try:
            # Upload the file to GitHub
            uploader.upload_file(
                local_file_path=local_file_path,
                github_file_path=github_file_path,
                commit_message=f"Update {py_file}"
            )
            print(f"Successfully uploaded: {py_file}")
        except Exception as e:
            print(f"Error uploading {py_file}: {e}")

    print("All Python files have been uploaded successfully.")

except Exception as e:
    print(f"An unexpected error occurred: {e}")
