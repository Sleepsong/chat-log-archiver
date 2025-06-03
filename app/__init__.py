from flask import Flask
import os                
import re                
import secrets          

app = Flask(__name__)

# --- Application Configuration ---

# SECRET_KEY: Crucial for session management (like flash messages) and security.
# It should be a long, random, and secret string.
# This line tries to get it from an environment variable 'FLASK_SECRET_KEY'.
# If not found, it generates a new random 32-byte hex string for each app start.
# For development, a consistent hardcoded key might be preferred if sessions need to persist across restarts.
# For production, ALWAYS use an environment variable for the secret key.
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))

# UPLOADS_DIR_NAME: Defines the name of the main directory within the 'static' folder
# where all user-uploaded files and application data will be stored.
app.config['UPLOADS_DIR_NAME'] = 'uploads'

# ABS_UPLOADS_PATH: Constructs the absolute filesystem path to the base uploads directory.
# app.static_folder: Flask's property for the absolute path to the 'static' directory.
# This is used for Python's os module file operations (creating directories, reading/writing files).
ABS_UPLOADS_PATH = os.path.join(app.static_folder, app.config['UPLOADS_DIR_NAME'])
# Storing it in app.config for potential use elsewhere, though routes.py reconstructs it based on app.static_folder.
app.config['ABSOLUTE_UPLOADS_FOLDER'] = ABS_UPLOADS_PATH 

# ALLOWED_EXTENSIONS: A set of file extensions that are permitted for uploads.
# This helps in validating uploaded files and preventing potentially harmful file types.
app.config['ALLOWED_EXTENSIONS'] = {'json', 'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Ensure all necessary subdirectories within the main uploads folder exist.
# This list defines the structure of your data storage.
subfolders = [
    'character_data',             # For chat log JSON files
    'character_images',           # For processed character images (e.g., from base64 in chat JSONs)
    'character_image_overrides',  # For user-uploaded override images for specific chats
    'profile_cards',              # For profile card JSON files
    'scenes',                     # For scene background images (processed from base64 or direct uploads)
    'profile_images'              # For images associated with profile cards
]
# Loop through the subfolder names and create them if they don't already exist.
for folder in subfolders:
    os.makedirs(os.path.join(ABS_UPLOADS_PATH, folder), exist_ok=True)

# --- Custom Jinja2 Template Filter ---

# @app.template_filter('emphasize') defines a custom filter named 'emphasize'
# that can be used in Jinja2 templates (e.g., {{ my_text | emphasize }}).
@app.template_filter('emphasize')
def emphasize_filter(text):
    """
    Jinja2 filter to wrap text enclosed in asterisks with a <span> for emphasis.
    Example: *important* becomes <span class="emphasis">important</span>
    Args:
        text (any): The input text. Will be converted to string.
    Returns:
        str: The text with emphasis spans, marked as safe HTML.
    """
    # Ensure the input is a string before applying regex.
    if not isinstance(text, str):
        text = str(text)
    # re.sub finds all non-overlapping occurrences of the pattern r'\*(.*?)\*'
    # (asterisks enclosing any characters, non-greedy) and replaces them with
    # r'<span class="emphasis">\1</span>', where \1 is the content between asterisks.
    return re.sub(r'\*(.*?)\*', r'<span class="emphasis">\1</span>', text)

from app import routes