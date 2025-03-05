import os
from secret_manager import SecretsManager
from git_uploader import GitHubUploader
from html_generator import HTMLGenerator
from fnmatch import fnmatch

EXCLUDE_FILE_PATH = "/config/text_files/excluded_files.txt"

def load_exclusions():
    """Load excluded files and patterns from a text file."""
    if os.path.exists(EXCLUDE_FILE_PATH):
        with open(EXCLUDE_FILE_PATH, "r") as f:
            return [line.strip() for line in f.readlines() if line.strip()]
    return []

def should_exclude(filename, exclusions):
    """Check if a file should be excluded based on patterns."""
    return any(fnmatch(filename, pattern) for pattern in exclusions)

def get_files_from_directory(directory, file_type, exclusions):
    """Retrieve all files of a given type from a directory, excluding specified files."""
    return [f for f in os.listdir(directory) if f.endswith(file_type) and not should_exclude(f, exclusions)]

def get_yaml_files_from_directories(directories, exclusions, file_type=".yaml"):
    """Retrieve YAML files from multiple directories, excluding specific ones."""
    return [
        f for directory in directories if os.path.exists(directory)
        for f in os.listdir(directory)
        if f.endswith(file_type) and not should_exclude(f, exclusions)
    ]

def main():
    try:
        secrets = SecretsManager()
        github_token = secrets["github_token"]
        github_repo = secrets["github_repro"]

        if not github_token or not github_repo:
            raise ValueError("Missing GitHub token or repository information in secrets.yaml.")

        uploader = GitHubUploader(github_token=github_token, repo_name=github_repo)
        exclusions = load_exclusions()

        html_directory = "/config/www/community/"
        yaml_directories = ["/config", "/config/esphome"]
        assets_directory = "/config/www/community/assets"

        for directory in [html_directory, assets_directory] + yaml_directories:
            if not os.path.exists(directory):
                print(f"Warning: Directory {directory} does not exist. Skipping...")

        html_files = get_files_from_directory(html_directory, ".html", exclusions)
        yaml_files = get_yaml_files_from_directories(yaml_directories, exclusions, ".yaml")

        if html_files:
            print(f"Processing HTML files: {', '.join(html_files)}")
            print(f"Processing YAML files: {', '.join(yaml_files)}")

            index_html_content = HTMLGenerator.generate_index_html(html_files, yaml_files)
            index_file_path = os.path.join(html_directory, "index.html")

            with open(index_file_path, "w", encoding="utf-8") as file:
                file.write(index_html_content)

            try:
                uploader.upload_file(
                    local_file_path=index_file_path,
                    github_file_path="community/index.html",
                    commit_message="Update index.html with latest file listings"
                )
                print("✅ index.html has been updated and uploaded successfully.")
            except Exception as e:
                print(f"❌ Error uploading index.html: {e}")

        asset_files = ["table-functions.js", "index-functions.js", "table-styles.css", "index-styles.css", "favicon.ico"]
        files_to_upload = {
            os.path.join(assets_directory, asset_file): f"community/assets/{asset_file}" for asset_file in asset_files
        }

        for local_path, github_path in files_to_upload.items():
            if os.path.exists(local_path) and not should_exclude(os.path.basename(local_path), exclusions):
                try:
                    uploader.upload_file(
                        local_file_path=local_path,
                        github_file_path=github_path,
                        commit_message=f"Update {os.path.basename(local_path)}"
                    )
                    print(f"✅ {os.path.basename(local_path)} uploaded to GitHub assets folder.")
                except Exception as e:
                    print(f"❌ Error uploading {os.path.basename(local_path)}: {e}")
            else:
                print(f"⚠️ Skipping {os.path.basename(local_path)} due to exclusions or missing file.")

    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()