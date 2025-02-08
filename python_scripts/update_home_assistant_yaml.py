import os
import time  # Import time module to add delay
from secret_manager import SecretsManager  # Import the SecretsManager class
from git_uploader import GitHubUploader  # Import the GitHubUploader class

# Function to get all YAML files from a directory (excluding secrets.yaml)
def get_yaml_files_from_directory(directory):
    """Retrieve all YAML files from the specified directory, excluding secrets.yaml."""
    return [f for f in os.listdir(directory) if f.endswith(".yaml") and f != "secrets.yaml"]

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

        # Directory containing YAML files
        yaml_directory = "/config"  # Path to the directory containing YAML files
        yaml_files = get_yaml_files_from_directory(yaml_directory)

        if not yaml_files:
            print("No YAML files found in the directory.")
            return

        print(f"Processing YAML files: {', '.join(yaml_files)}")

        # Upload each YAML file with a delay
        for yaml_file in yaml_files:
            yaml_file_path = os.path.join(yaml_directory, yaml_file)
            github_file_path = f"community/{yaml_file}"

            # Upload the YAML file to GitHub
            try:
                uploader.upload_file(
                    local_file_path=yaml_file_path,
                    github_file_path=github_file_path,
                    commit_message=f"Update {yaml_file}"
                )
            except Exception as e:
                print(f"Error uploading {yaml_file}: {e}")

            # Add a delay (e.g., 5 seconds) between uploads to avoid rate limiting or conflicts
            time.sleep(5)

        print("All YAML files have been updated and uploaded successfully.")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
