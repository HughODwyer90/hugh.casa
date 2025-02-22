import os
from secret_manager import SecretsManager  # Import the SecretsManager class
from git_uploader import GitHubUploader  # Import the GitHubUploader class
from html_generator import HTMLGenerator  # Import the HTMLGenerator class

# Function to get HTML and YAML files in the respective directories, excluding specific files
def get_files_from_directory(directory, file_type, exclude=("index.html", "secrets.yaml")):
    """Retrieve all files of a given type from a directory, excluding specified files."""
    return [f for f in os.listdir(directory) if f.endswith(file_type) and f not in exclude]

# Main function to generate and upload index.html, JS, and CSS files
def main():
    try:
        # Load secrets
        secrets = SecretsManager()
        github_token = secrets["github_token"]
        github_repo = secrets["github_repro"]

        if not github_token or not github_repo:
            raise ValueError("Missing GitHub token or repository information in secrets.yaml.")

        # Initialize GitHubUploader
        uploader = GitHubUploader(github_token=github_token, repo_name=github_repo)

        # Define directories
        html_directory = "/config/www/community/"
        yaml_directory = "/config/"
        assets_directory = "/config/www/community/assets"  # Correct directory for JS & CSS

        # Ensure directories exist
        for directory in [html_directory, yaml_directory, assets_directory]:
            if not os.path.exists(directory):
                raise FileNotFoundError(f"The directory {directory} does not exist.")

        # Retrieve files
        html_files = get_files_from_directory(html_directory, ".html")
        yaml_files = get_files_from_directory(yaml_directory, ".yaml")

        if not html_files:
            print("No HTML files found, skipping index.html generation.")
        else:
            print(f"Processing HTML files: {', '.join(html_files)}")
            print(f"Processing YAML files: {', '.join(yaml_files)}")

            # Generate index.html using HTMLGenerator class
            index_html_content = HTMLGenerator.generate_index_html(html_files, yaml_files)

            # Save index.html locally
            index_file_path = os.path.join(html_directory, "index.html")
            with open(index_file_path, "w", encoding="utf-8") as file:
                file.write(index_html_content)

            # Upload index.html to GitHub
            try:
                uploader.upload_file(
                    local_file_path=index_file_path,
                    github_file_path="community/index.html",  # Upload index.html to community/
                    commit_message="Update index.html with latest file listings"
                )
                print("index.html has been updated and uploaded successfully.")
            except Exception as e:
                print(f"Error uploading index.html to GitHub: {e}")

        # Upload JavaScript and CSS files to assets/ in GitHub
        js_file_path = os.path.join(assets_directory, "table-functions.js")
        css_file_path = os.path.join(assets_directory, "table-styles.css")

        files_to_upload = {
            js_file_path: "assets/table-functions.js",
            css_file_path: "assets/table-styles.css",
        }

        for local_path, github_path in files_to_upload.items():
            if os.path.exists(local_path):
                try:
                    uploader.upload_file(
                        local_file_path=local_path,
                        github_file_path=github_path,
                        commit_message=f"Update {os.path.basename(local_path)}"
                    )
                    print(f"{os.path.basename(local_path)} has been uploaded to GitHub assets folder.")
                except Exception as e:
                    print(f"Error uploading {os.path.basename(local_path)} to GitHub: {e}")
            else:
                print(f"Warning: {os.path.basename(local_path)} not found. Skipping upload.")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
