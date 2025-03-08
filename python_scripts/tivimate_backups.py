import os
import glob

backup_folder = "/media/"
backup_files = sorted(glob.glob(os.path.join(backup_folder, "*.tmb")), key=os.path.getmtime, reverse=True)

# Keep only the most recent backup, delete the rest
if len(backup_files) > 1:
    for file in backup_files[1:]:
        os.remove(file)
