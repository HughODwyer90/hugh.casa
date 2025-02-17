import datetime
import os

# Get the current year
year = datetime.datetime.now().year

# Construct the filename
log_filename = f"/config/text_files/{year}_working_from_home.txt"

# Generate the message directly in the script
message = f"{datetime.datetime.now().strftime('%Y-%m-%d')} - Worked remotely"

# Write the message to the log file
with open(log_filename, 'a') as file:
    file.write(f"{message}\n")  # Ensure newline is added here

# Print the message for debugging purposes
#print(message)
