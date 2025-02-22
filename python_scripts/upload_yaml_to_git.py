import os
import time  # Import time module to add delay
from secret_manager import SecretsManager  # Import the SecretsManager class
from git_uploader import GitHubUploader  # Import the GitHubUploader class

# Function to get YAML files from multiple directories (excluding secrets.yaml)
def get_yaml_files_from_directories(directories):
    """Retrieve all YAML files from the specified directories, excluding secrets.yaml."""
    yaml_files = []
    for directory in directories:
        if os.path.exists(directory):
            yaml_files.extend(
                [(directory, f) for f in os.listdir(directory) if f.endswith(".yaml") and f != "secrets.yaml" and f != "everything-presence-one.yaml"]
            )
        else:
            print(f"Warning: Directory {directory} does not exist. Skipping...")
    return yaml_files

# Main function
def main():
    try:
        # Load secrets
        secrets = SecretsManager()
        github_token = secrets["github_token"]
        github_repo = secrets["github_repro"]

        # Validate that required secrets exist
        if not github_token or not github_repo:
            raise ValueError("Missing GitHub token or repository information in secrets.yaml.")

        # Initialize GitHubUploader
        uploader = GitHubUploader(github_token=github_token, repo_name=github_repo)

        # Directories containing YAML files
        yaml_directories = ["/config", "/config/esphome"]  # Add /esphome as a source

        # Get all YAML files from both directories
        yaml_files = get_yaml_files_from_directories(yaml_directories)

        if not yaml_files:
            print("No YAML files found in the directories.")
            return

        print(f"Processing YAML files: {', '.join([f[1] for f in yaml_files])}")

        # Upload each YAML file with a delay
        for directory, yaml_file in yaml_files:
            yaml_file_path = os.path.join(directory, yaml_file)
            github_file_path = f"community/{yaml_file}"  # Upload under 'community/' in GitHub

            # Upload the YAML file to GitHub
            try:
                uploader.upload_file(
                    local_file_path=yaml_file_path,
                    github_file_path=github_file_path,
                    commit_message=f"Update {yaml_file}"
                )
                print(f"Uploaded: {yaml_file}")
            except Exception as e:
                print(f"Error uploading {yaml_file}: {e}")

            # Add a delay (e.g., 5 seconds) between uploads to avoid rate limiting or conflicts
            time.sleep(5)

        print("All YAML files have been updated and uploaded successfully.")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
