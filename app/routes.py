import os
import json
import uuid
from urllib.parse import urlparse, quote
import mimetypes 
import base64 
import re 
from flask import request, render_template, redirect, url_for, flash
from werkzeug.utils import secure_filename
from app import app

# --- Folder Configurations ---
FILESYSTEM_BASE_UPLOADS_PATH = os.path.join(app.static_folder, app.config['UPLOADS_DIR_NAME'])
CHARACTER_DATA_FOLDER = os.path.join(FILESYSTEM_BASE_UPLOADS_PATH, 'character_data')
CHARACTER_IMAGE_OVERRIDES_FOLDER = os.path.join(FILESYSTEM_BASE_UPLOADS_PATH, 'character_image_overrides')
CHARACTER_IMAGES_FOLDER = os.path.join(FILESYSTEM_BASE_UPLOADS_PATH, 'character_images')
PROFILE_CARDS_FOLDER = os.path.join(FILESYSTEM_BASE_UPLOADS_PATH, 'profile_cards')
PROFILE_IMAGES_FOLDER = os.path.join(FILESYSTEM_BASE_UPLOADS_PATH, 'profile_images')
SCENES_FOLDER = os.path.join(FILESYSTEM_BASE_UPLOADS_PATH, 'scenes')
STATIC_PATH_PREFIX_FOR_UPLOADS = app.config['UPLOADS_DIR_NAME']

# === Utility Functions ===
def allowed_file(filename):
    """Checks if a filename has an allowed extension."""
    if not filename: return False
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_sanitized_card_filename(name):
    """Creates a sanitized filename for profile card JSONs."""
    sanitized_name = name.lower().replace(" ", "_")
    return secure_filename(sanitized_name) + '.json'

def normalize_card_data(data_from_json, default_name=""):
    """Normalizes profile card metadata (excluding image processing)."""
    normalized = {}
    normalized['name'] = str(data_from_json.get('name', data_from_json.get('Name', default_name))).strip()
    normalized['gender'] = str(data_from_json.get('gender', data_from_json.get('Gender', ''))).strip()
    normalized['age'] = str(data_from_json.get('age', data_from_json.get('Age', ''))).strip()
    normalized['likes'] = str(data_from_json.get('likes', data_from_json.get('Like', ''))).strip()
    normalized['dislikes'] = str(data_from_json.get('dislikes', data_from_json.get('Dislike', ''))).strip()
    normalized['other_info'] = str(data_from_json.get('other_info', data_from_json.get('Other Info', ''))).strip()
    return normalized

def _save_base64_image(unique_identifier, base64_data_uri, target_folder, filename_prefix=""):
    """
    Internal helper to decode base64 data URI and save as an image file.
    unique_identifier is for logging context. filename_prefix is used as the actual file base name.
    Ensures filename_prefix is secure and cleans up old versions with same prefix but different extension.
    """
    if not base64_data_uri or not isinstance(base64_data_uri, str) or not base64_data_uri.startswith('data:image'):
        app.logger.debug(f"[_save_base64_image]: Invalid or no base64 data for {unique_identifier} using prefix '{filename_prefix}'.")
        return None
    try:
        match = re.fullmatch(r'data:(image\/(?P<type>png|jpeg|gif|webp));base64,(?P<data>.+)', base64_data_uri, re.IGNORECASE)
        encoded_data = None
        extension = None

        if not match:
            if ',' not in base64_data_uri: raise ValueError("Base64 URI missing comma separator.")
            header, encoded_data_split = base64_data_uri.split(',', 1)
            if not header.startswith('data:image') or ';base64' not in header: raise ValueError("Base64 URI header malformed.")
            media_type = header.split(';')[0].split(':')[1]
            extension = mimetypes.guess_extension(media_type)
            encoded_data = encoded_data_split # Assign encoded_data here
            if not extension or extension.lower() == '.bin': # Common fallback
                if 'png' in media_type.lower(): extension = '.png'
                elif 'jpeg' in media_type.lower() or 'jpg' in media_type.lower(): extension = '.jpg'
                elif 'gif' in media_type.lower(): extension = '.gif'
                elif 'webp' in media_type.lower(): extension = '.webp'
                else: extension = '.png' 
        else:
            img_type = match.group('type').lower(); encoded_data = match.group('data')
            extension = '.' + img_type
            if img_type == 'jpeg': extension = '.jpg'
        
        if not extension.startswith('.'): extension = '.' + extension
        final_extension = extension.lower()

        if final_extension.strip('.') not in app.config['ALLOWED_EXTENSIONS']:
            app.logger.warning(f"[_save_base64_image]: Base64 for {unique_identifier} (prefix: {filename_prefix}) has disallowed extension '{final_extension}'. Defaulting to .png")
            final_extension = '.png'

        image_binary = base64.b64decode(encoded_data)
        
        # Use filename_prefix if provided, otherwise unique_identifier. Ensure it's secure.
        base_filename_for_saving = secure_filename(filename_prefix if filename_prefix else unique_identifier)
        saved_filename = base_filename_for_saving + final_extension
        save_path = os.path.join(target_folder, saved_filename)
        
        # Clean up old versions with the same base name but potentially different extensions
        if os.path.exists(target_folder):
            for old_file in os.listdir(target_folder):
                if old_file.startswith(base_filename_for_saving) and old_file != saved_filename:
                    try: 
                        os.remove(os.path.join(target_folder, old_file))
                        app.logger.debug(f"[_save_base64_image]: Removed old version '{old_file}' for base '{base_filename_for_saving}'")
                    except Exception as e_del: 
                        app.logger.error(f"[_save_base64_image]: Error removing old version '{old_file}': {e_del}")
        
        with open(save_path, 'wb') as f: f.write(image_binary)
        app.logger.info(f"SUCCESS [_save_base64_image]: Saved image for '{unique_identifier}' as '{saved_filename}' in '{target_folder}'")
        return saved_filename
    except Exception as e:
        app.logger.error(f"ERROR [_save_base64_image]: Could not save base64 image for '{unique_identifier}' (prefix: '{filename_prefix}'): {e}")
        if request and unique_identifier: 
             flash(f"Warning: Error processing an embedded image for '{unique_identifier}'.", "warning")
    return None

def get_character_image_path(unique_id, base64_image_data=None, process_base64_if_needed=False):
    """For Chat Log main character images. unique_id is the base filename."""
    if os.path.exists(CHARACTER_IMAGE_OVERRIDES_FOLDER):
        override = next((f for f in os.listdir(CHARACTER_IMAGE_OVERRIDES_FOLDER) if f.startswith(unique_id)), None)
        if override: return url_for('static', filename=f'{STATIC_PATH_PREFIX_FOR_UPLOADS}/character_image_overrides/{override}')
    if os.path.exists(CHARACTER_IMAGES_FOLDER):
        local_img = next((f for f in os.listdir(CHARACTER_IMAGES_FOLDER) if f.startswith(unique_id)), None)
        if local_img: return url_for('static', filename=f'{STATIC_PATH_PREFIX_FOR_UPLOADS}/character_images/{local_img}')
    if process_base64_if_needed and base64_image_data:
        # For chat images, the filename_prefix is the unique_id itself.
        saved_filename = _save_base64_image(unique_id, base64_image_data, CHARACTER_IMAGES_FOLDER, filename_prefix=unique_id)
        if saved_filename: return url_for('static', filename=f'{STATIC_PATH_PREFIX_FOR_UPLOADS}/character_images/{saved_filename}')
    return None

def get_profile_card_image_path(card_name, base64_image_data=None, process_base64_if_needed=False):
    """For Profile Card images. card_name is used to derive sanitized filename prefix."""
    sanitized_name_prefix = secure_filename(card_name.lower().replace(" ", "_"))
    if os.path.exists(PROFILE_IMAGES_FOLDER):
        local_candidate = next((f for f in os.listdir(PROFILE_IMAGES_FOLDER) if f.startswith(sanitized_name_prefix)), None)
        if local_candidate:
            return url_for('static', filename=f'{STATIC_PATH_PREFIX_FOR_UPLOADS}/profile_images/{local_candidate}')
    if process_base64_if_needed and base64_image_data:
        saved_filename = _save_base64_image(card_name, base64_image_data, PROFILE_IMAGES_FOLDER, filename_prefix=sanitized_name_prefix)
        if saved_filename:
            return url_for('static', filename=f'{STATIC_PATH_PREFIX_FOR_UPLOADS}/profile_images/{saved_filename}')
    return None

def get_scene_image_path(unique_id, base64_scene_image=None, process_base64_if_needed=False):
    """For Chat Scene background images. unique_id + '_scene' is the filename prefix."""
    filename_base_prefix = secure_filename(f"{unique_id}_scene") # Ensure this prefix is secure
    if os.path.exists(SCENES_FOLDER):
        scene_candidate = next((f for f in os.listdir(SCENES_FOLDER) if f.startswith(filename_base_prefix)), None)
        if scene_candidate:
            return url_for('static', filename=f'{STATIC_PATH_PREFIX_FOR_UPLOADS}/scenes/{scene_candidate}')
    if process_base64_if_needed and base64_scene_image:
        saved_filename = _save_base64_image(unique_id, base64_scene_image, SCENES_FOLDER, filename_prefix=filename_base_prefix)
        if saved_filename:
            return url_for('static', filename=f'{STATIC_PATH_PREFIX_FOR_UPLOADS}/scenes/{saved_filename}')
    return None

def load_profile_cards():
    profile_cards_dict = {}
    if not os.path.exists(PROFILE_CARDS_FOLDER): return profile_cards_dict
    for filename in os.listdir(PROFILE_CARDS_FOLDER):
        if filename.endswith('.json'):
            path = os.path.join(PROFILE_CARDS_FOLDER, filename)
            try:
                with open(path, 'r', encoding='utf-8') as f: data_from_json = json.load(f)
                default_name = os.path.splitext(filename)[0].replace("_", " ").title()
                card_metadata = normalize_card_data(data_from_json, default_name=default_name)
                if card_metadata.get('name'):
                    raw_image_field_from_json = data_from_json.get('image') 
                    card_metadata['display_image_path'] = get_profile_card_image_path(
                        card_metadata['name'], 
                        base64_image_data=raw_image_field_from_json, 
                        process_base64_if_needed=True 
                    )
                    profile_cards_dict[card_metadata['name'].lower()] = card_metadata
            except Exception as e: 
                app.logger.error(f"Error loading profile card {filename}: {e}")
    return profile_cards_dict

def parse_search_query(query_string):
    criteria = {'tags': [], 'author': None, 'name': None, 'title': None, 'intro': None, 'model': None, 'general_keywords': []}
    prefixes = {"tag:": "tags", "author:": "author", "name:": "name", "title:": "title", "intro:": "intro", "model:": "model"}
    pattern = re.compile(r'\b(tag|author|name|title|intro|model):(?:"([^"]*)"|([^\s"]+))', re.IGNORECASE)
    remaining_query = query_string
    for match in pattern.finditer(query_string):
        prefix_key = match.group(1).lower() + ":"; value = (match.group(2) if match.group(2) is not None else match.group(3)).strip()
        if value:
            mapped_key = prefixes.get(prefix_key)
            if mapped_key == "tags": criteria['tags'].append(value.lower())
            elif mapped_key: criteria[mapped_key] = value.lower() 
        remaining_query = remaining_query.replace(match.group(0), "", 1)
    criteria['general_keywords'] = [kw.strip().lower() for kw in remaining_query.split() if kw.strip()]
    return criteria

# === Routes ===

@app.route('/')
def index():
    raw_query = request.args.get('q', '').strip()
    search_criteria = parse_search_query(raw_query) # Assumes parse_search_query is defined
    
    include_messages = request.args.get('include_messages') is not None
    sort_by = request.args.get('sort_by', 'date_desc')

    chat_logs = []
    message_results = []
    profile_cards_for_search = None # Lazy load profile cards if needed

    if not os.path.exists(CHARACTER_DATA_FOLDER):
        flash("Chat data folder not found.", "error")
        return render_template('index.html', chat_logs=chat_logs, message_results=message_results, query=raw_query, include_messages=include_messages, sort_by=sort_by)

    # --- BEHAVIOR 1: Search ONLY within messages ---
    if include_messages and raw_query:
        app.logger.debug("Executing search within messages.")
        for f_name in os.listdir(CHARACTER_DATA_FOLDER):
            if not f_name.endswith('.json'): continue
            path = os.path.join(CHARACTER_DATA_FOLDER, f_name)
            try:
                with open(path, 'r', encoding='utf-8') as file: chat_log_data = json.load(file)
            except Exception as e: 
                app.logger.error(f"Error loading {f_name} during message search: {e}")
                continue

            # Check if this chat log meets the prefixed criteria (tag:, author:, model:, etc.)
            metadata_match = True
            char_name_default = os.path.splitext(f_name)[0].replace("_", " ").title()
            character_name = chat_log_data.get('messages',[{}])[0].get('speaker', char_name_default) if chat_log_data.get('messages') else char_name_default
            all_chat_tags = chat_log_data.get('tags', []) + chat_log_data.get('custom_tags', [])
            author_field = chat_log_data.get('author'); author_name = (author_field.get('name') if isinstance(author_field, dict) else author_field) or ""
            model_text = chat_log_data.get('model', '')

            if search_criteria['tags'] and not all(any(req_tag in ct.lower() for ct in all_chat_tags) for req_tag in search_criteria['tags']): metadata_match = False
            if metadata_match and search_criteria['author'] and not (search_criteria['author'] in author_name.lower()): metadata_match = False
            if metadata_match and search_criteria['name'] and not (search_criteria['name'] in character_name.lower()): metadata_match = False
            # ... (Add any other prefix checks here: title, intro) ...
            if metadata_match and search_criteria['model'] and not (model_text and search_criteria['model'].lower() == model_text.lower()): metadata_match = False
            
            # If metadata matches (or if no prefixes were specified), search messages for general keywords
            if metadata_match and search_criteria['general_keywords']:
                if profile_cards_for_search is None: profile_cards_for_search = load_profile_cards()
                unique_id = os.path.splitext(f_name)[0]
                base64_char_img = chat_log_data.get('image')

                for i, msg in enumerate(chat_log_data.get('messages', [])):
                    text = msg.get('message', '')
                    # Check if ALL general keywords are in this message
                    if all(kw in text.lower() for kw in search_criteria['general_keywords']):
                        speaker_name = msg.get('speaker', character_name)
                        is_primary = speaker_name.lower() == character_name.lower()
                        
                        # Get image path for the speaker
                        msg_display_image_path = get_character_image_path(unique_id, base64_image_data=base64_char_img, process_base64_if_needed=False) if is_primary else None
                        if not is_primary:
                            card = profile_cards_for_search.get(speaker_name.lower())
                            if card: msg_display_image_path = card.get('display_image_path')
                        
                        message_results.append({
                            'unique_id': unique_id, 'character_name': speaker_name, 'message': text, 'index': i,
                            'display_image_path': msg_display_image_path, 'is_primary_speaker': is_primary
                        })
    
    # --- BEHAVIOR 2: Search metadata and show gallery (default behavior) ---
    else:
        app.logger.debug("Executing metadata search for gallery view.")
        temp_chat_list_for_sorting = []
        for f_name in os.listdir(CHARACTER_DATA_FOLDER):
            # ... (This loop is now almost identical to the start of the previous full index function) ...
            if not f_name.endswith('.json'): continue
            path = os.path.join(CHARACTER_DATA_FOLDER, f_name)
            try:
                with open(path, 'r', encoding='utf-8') as file: chat_log_data = json.load(file)
            except Exception as e: app.logger.error(f"Error loading {f_name}: {e}"); continue

            char_name_default = os.path.splitext(f_name)[0].replace("_", " ").title()
            character_name = chat_log_data.get('messages',[{}])[0].get('speaker', char_name_default) if chat_log_data.get('messages') else char_name_default
            all_chat_tags = chat_log_data.get('tags', []) + chat_log_data.get('custom_tags', [])
            author_field = chat_log_data.get('author'); author_name = (author_field.get('name') if isinstance(author_field, dict) else author_field) or ""
            title_text = chat_log_data.get('title', ''); intro_text = chat_log_data.get('intro', ''); model_text = chat_log_data.get('model', '')

            metadata_match = True
            if search_criteria['tags'] and not all(any(req_tag in ct.lower() for ct in all_chat_tags) for req_tag in search_criteria['tags']): metadata_match = False
            if metadata_match and search_criteria['author'] and not (search_criteria['author'] in author_name.lower()): metadata_match = False
            if metadata_match and search_criteria['name'] and not (search_criteria['name'] in character_name.lower()): metadata_match = False
            if metadata_match and search_criteria['title'] and not (search_criteria['title'] in title_text.lower()): metadata_match = False
            if metadata_match and search_criteria['intro'] and not (search_criteria['intro'] in intro_text.lower()): metadata_match = False
            if metadata_match and search_criteria['model'] and not (model_text and search_criteria['model'].lower() == model_text.lower()): metadata_match = False
            if metadata_match and search_criteria['general_keywords']:
                if not all(any(kw in field.lower() for field in [character_name, title_text, intro_text, author_name]) for kw in search_criteria['general_keywords']): metadata_match = False

            if metadata_match:
                unique_id = os.path.splitext(f_name)[0]
                base64_char_img = chat_log_data.get('image')
                display_img_path_gallery = get_character_image_path(unique_id, base64_image_data=base64_char_img, process_base64_if_needed=False)
                upload_ts = os.path.getmtime(path) if os.path.exists(path) else 0
                temp_chat_list_for_sorting.append({
                    'unique_id': unique_id, 'character_name': character_name, 'display_image_path': display_img_path_gallery, 
                    'author': author_name, 'title': title_text, 'intro': intro_text, 'tags': all_chat_tags, 
                    'message_count': len(chat_log_data.get('messages', [])), 'upload_timestamp': upload_ts, 'model': model_text
                })

        # Sort the collected chat logs
        if sort_by == 'name_asc': temp_chat_list_for_sorting.sort(key=lambda x: x['character_name'].lower())
        elif sort_by == 'name_desc': temp_chat_list_for_sorting.sort(key=lambda x: x['character_name'].lower(), reverse=True)
        elif sort_by == 'date_asc': temp_chat_list_for_sorting.sort(key=lambda x: x['upload_timestamp'])
        else: temp_chat_list_for_sorting.sort(key=lambda x: x['upload_timestamp'], reverse=True)
        chat_logs = temp_chat_list_for_sorting

    return render_template('index.html', 
                           chat_logs=chat_logs, 
                           message_results=message_results, 
                           query=raw_query, 
                           include_messages=include_messages,
                           sort_by=sort_by)

# === Upload Chat Log ===
@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if 'chat_log' not in request.files: 
            flash('No chat log file part selected.', 'error')
            return redirect(request.url)
        chat_log_file = request.files['chat_log']
        if chat_log_file.filename == '': 
            flash('No chat log file selected.', 'error')
            return redirect(request.url)
        if not allowed_file(chat_log_file.filename): 
            flash(f"Invalid chat log file type. Allowed: {app.config['ALLOWED_EXTENSIONS']}", 'error')
            return redirect(request.url)

        unique_id = str(uuid.uuid4())
        chat_log_filename = unique_id + ".json"
        chat_log_path = os.path.join(CHARACTER_DATA_FOLDER, chat_log_filename)
        chat_log_file.save(chat_log_path)
        
        base64_image_from_json = None
        base64_scene_image_from_json = None
        try:
            with open(chat_log_path, 'r+', encoding='utf-8') as f:
                chat_data_content = json.load(f)
                chat_data_content['title'] = title
                base64_image_from_json = chat_data_content.get('image') 
                base64_scene_image_from_json = chat_data_content.get('sceneImage')
                
                scene_image_upload_file = request.files.get('scene_image_upload')
                if scene_image_upload_file and allowed_file(scene_image_upload_file.filename):
                    try:
                        img_bytes = scene_image_upload_file.read()
                        mime_type = mimetypes.guess_type(scene_image_upload_file.filename)[0] or 'image/png'
                        base64_scene_image_from_json = f"data:{mime_type};base64,{base64.b64encode(img_bytes).decode('utf-8')}"
                        chat_data_content['sceneImage'] = base64_scene_image_from_json
                        app.logger.info(f"Converted uploaded scene image to base64 for chat {unique_id}")
                    except Exception as e_b64:
                        app.logger.error(f"Error converting uploaded scene image to base64: {e_b64}")
                        flash("Error processing uploaded scene image.", "warning")
                
                f.seek(0)
                json.dump(chat_data_content, f, indent=2)
                f.truncate()
        except Exception as e:
            if os.path.exists(chat_log_path): os.remove(chat_log_path)
            flash(f"Error processing uploaded chat log: {str(e)}", "error")
            return redirect(request.url)

        character_image_file_upload = request.files.get('character_image')
        if character_image_file_upload and character_image_file_upload.filename != '':
            if allowed_file(character_image_file_upload.filename):
                image_ext = os.path.splitext(character_image_file_upload.filename)[1].lower()
                if not image_ext.startswith('.'): image_ext = '.' + image_ext
                image_override_filename = unique_id + image_ext 
                character_image_file_upload.save(os.path.join(CHARACTER_IMAGE_OVERRIDES_FOLDER, image_override_filename))
            else: 
                flash('Invalid character image file type (override). Not saved.', 'warning')
        elif base64_image_from_json: 
            get_character_image_path(unique_id, base64_image_data=base64_image_from_json, process_base64_if_needed=True)
        
        if base64_scene_image_from_json:
            get_scene_image_path(unique_id, base64_scene_image=base64_scene_image_from_json, process_base64_if_needed=True)
        
        flash('Chat log uploaded successfully!', 'success')
        return redirect(url_for('index'))
    return render_template('upload.html')

# === Display Chat Log ===
@app.route('/display/<unique_id>')
def display_chat(unique_id):
    chat_log_path = os.path.join(CHARACTER_DATA_FOLDER, unique_id + '.json')
    if not os.path.exists(chat_log_path): 
        flash("Chat log not found.", "error")
        return redirect(url_for('index'))
    try:
        with open(chat_log_path, 'r', encoding='utf-8') as f: chat_data = json.load(f)
    except Exception as e: 
        flash(f"Error loading chat log: {str(e)}", "error")
        return redirect(url_for('index'))

    char_name_def = unique_id.replace("_", " ").title()
    character_name = char_name_def
    if chat_data.get('messages') and len(chat_data['messages']) > 0 : 
        character_name = chat_data['messages'][0].get('speaker', char_name_def)
    
    chat_title_from_json = chat_data.get('title', '').strip()
    window_title = f"{chat_title_from_json} - Chat" if chat_title_from_json else f"Chat with {character_name}"

    base64_char_image = chat_data.get('image') 
    main_char_display_image_path = get_character_image_path(unique_id, base64_image_data=base64_char_image, process_base64_if_needed=True)
    base64_scene_image = chat_data.get('sceneImage')
    scene_image_display_path = get_scene_image_path(unique_id, base64_scene_image=base64_scene_image, process_base64_if_needed=True)
    active_scene_style = chat_data.get('sceneStyle', 'blurred_glass') 
    all_tags = chat_data.get('tags', []) + chat_data.get('custom_tags', []) 
    model_name = chat_data.get('model', '')
    character_url = chat_data.get('character_url', '')

    profile_cards = load_profile_cards()
    for msg in chat_data.get('messages', []):
        speaker = msg.get('speaker', '').lower()
        if speaker != character_name.lower():
            card = profile_cards.get(speaker)
            if card: msg['profile_image'] = card.get('display_image_path')
            
    return render_template('chat.html', 
                           chat_log=chat_data, character_name=character_name,
                           main_char_display_image_path=main_char_display_image_path,
                           scene_image_display_path=scene_image_display_path, 
                           active_scene_style=active_scene_style, model_name=model_name,
                           character_url=character_url, unique_id=unique_id, 
                           intro=chat_data.get('intro', ''), tags=all_tags, window_title=window_title)

# === Edit Chat Log ===
@app.route('/edit/<unique_id>', methods=['GET', 'POST'])
def edit_chat(unique_id):
    chat_log_path = os.path.join(CHARACTER_DATA_FOLDER, unique_id + '.json')
    if not os.path.exists(chat_log_path): 
        flash("Chat log not found.", "error"); return redirect(url_for('index'))
    
    current_chat_data = {}
    try:
        with open(chat_log_path, 'r', encoding='utf-8') as f_read: current_chat_data = json.load(f_read)
    except Exception as e: 
        flash(f"Error reading chat log for edit: {str(e)}", "error"); return redirect(url_for('index'))

    if request.method == 'POST':
        action = request.form.get('action')
        chat_data_to_update = current_chat_data.copy() 
        try:
            if action == 'edit-details':
                chat_data_to_update['title'] = request.form.get('title', chat_data_to_update.get('title', '')).strip()
                chat_data_to_update['intro'] = request.form.get('intro', chat_data_to_update.get('intro', '')).strip()
                chat_data_to_update['custom_tags'] = [t.strip() for t in request.form.get('custom_tags', '').split(',') if t.strip()]
                auth_name, auth_url = request.form.get('author_name', '').strip(), request.form.get('author_url', '').strip()
                if auth_name or auth_url: chat_data_to_update['author'] = {'name': auth_name, 'url': auth_url}
                elif 'author' in chat_data_to_update: del chat_data_to_update['author']
                char_name_form = request.form.get('character_name', '').strip()
                if char_name_form:
                    if not chat_data_to_update.get('messages'): chat_data_to_update['messages'] = []
                    if chat_data_to_update['messages']: chat_data_to_update['messages'][0]['speaker'] = char_name_form
                    else: chat_data_to_update['messages'].append({'speaker': char_name_form, 'message': 'Default message.'})
                
                new_char_img_file = request.files.get('new_image')
                if new_char_img_file and new_char_img_file.filename != '' and allowed_file(new_char_img_file.filename):
                    if os.path.exists(CHARACTER_IMAGE_OVERRIDES_FOLDER):
                        for old_img in [img for img in os.listdir(CHARACTER_IMAGE_OVERRIDES_FOLDER) if img.startswith(unique_id)]:
                            try: os.remove(os.path.join(CHARACTER_IMAGE_OVERRIDES_FOLDER, old_img))
                            except OSError as e_del: app.logger.error(f"Error deleting old override image {old_img}: {e_del}")
                    img_ext = os.path.splitext(new_char_img_file.filename)[1].lower()
                    if not img_ext.startswith('.'): img_ext = '.' + img_ext
                    new_char_img_file.save(os.path.join(CHARACTER_IMAGE_OVERRIDES_FOLDER, unique_id + img_ext))
                    chat_data_to_update['image'] = "" 
                
                new_scene_img_file = request.files.get('new_scene_image_edit')
                if new_scene_img_file and new_scene_img_file.filename != '' and allowed_file(new_scene_img_file.filename):
                    scene_fname_base = f"{unique_id}_scene"
                    if os.path.exists(SCENES_FOLDER):
                        for old_s in os.listdir(SCENES_FOLDER): 
                            if old_s.startswith(scene_fname_base): os.remove(os.path.join(SCENES_FOLDER, old_s))
                    try:
                        img_bytes = new_scene_img_file.read(); mime = mimetypes.guess_type(new_scene_img_file.filename)[0] or 'image/png'
                        chat_data_to_update['sceneImage'] = f"data:{mime};base64,{base64.b64encode(img_bytes).decode('utf-8')}"
                    except Exception as e_b64: app.logger.error(f"Error converting scene image on edit: {e_b64}"); flash("Error processing scene image.", "warning")
                
                with open(chat_log_path, 'w', encoding='utf-8') as f: json.dump(chat_data_to_update, f, indent=2)
                flash("Chat details updated.", "success")

            elif action == 'upload-json':
                new_log_file = request.files.get('new_chat_log')
                if not new_log_file or new_log_file.filename == '': flash("No new JSON provided.", "error")
                elif not allowed_file(new_log_file.filename): flash("Invalid new JSON file type.", "error")
                else:
                    new_log_file.save(chat_log_path); flash_msg = "Chat log replaced."
                    new_data = {}; title_form = request.form.get('title', '').strip()
                    try:
                        with open(chat_log_path, 'r+', encoding='utf-8') as f_new:
                            new_data = json.load(f_new)
                            if title_form: new_data['title'] = title_form
                            char_b64 = new_data.get('image'); scene_b64 = new_data.get('sceneImage')
                            if isinstance(char_b64, str) and char_b64.startswith('data:image'): get_character_image_path(unique_id, base64_image_data=char_b64, process_base64_if_needed=True)
                            if isinstance(scene_b64, str) and scene_b64.startswith('data:image'): get_scene_image_path(unique_id, base64_scene_image=scene_b64, process_base64_if_needed=True)
                            f_new.seek(0); json.dump(new_data, f_new, indent=2); f_new.truncate()
                        if title_form: flash_msg += " Title also updated."
                    except Exception as e_proc: flash_msg = f"Replaced JSON, but error processing it: {str(e_proc)}"
                    flash(flash_msg, "success" if "error" not in flash_msg.lower() else "warning")
        except Exception as e: flash(f"Error updating chat log: {str(e)}", "error")
        return redirect(url_for('display_chat', unique_id=unique_id))

    current_scene_img_b64 = current_chat_data.get('sceneImage')
    current_scene_path = get_scene_image_path(unique_id, base64_scene_image=current_scene_img_b64, process_base64_if_needed=False)
    return render_template('edit.html', unique_id=unique_id, 
                           chat_title=current_chat_data.get('title', ''),
                           character_name=current_chat_data.get('messages', [{}])[0].get('speaker', '') if current_chat_data.get('messages') else '',
                           author_name=current_chat_data.get('author', {}).get('name', ''), 
                           author_url=current_chat_data.get('author', {}).get('url', ''),
                           character_intro=current_chat_data.get('intro', ''), 
                           custom_tags=', '.join(current_chat_data.get('custom_tags', [])),
                           current_scene_image_display_path=current_scene_path)

# === Delete Chat Log ===
@app.route('/delete/<unique_id>', methods=['POST'])
def delete_chat(unique_id):
    log_path = os.path.join(CHARACTER_DATA_FOLDER, unique_id + '.json')
    paths_to_delete = [log_path]
    if os.path.exists(CHARACTER_IMAGE_OVERRIDES_FOLDER):
        paths_to_delete.extend([os.path.join(CHARACTER_IMAGE_OVERRIDES_FOLDER, f) for f in os.listdir(CHARACTER_IMAGE_OVERRIDES_FOLDER) if f.startswith(unique_id)])
    if os.path.exists(CHARACTER_IMAGES_FOLDER):
        paths_to_delete.extend([os.path.join(CHARACTER_IMAGES_FOLDER, f) for f in os.listdir(CHARACTER_IMAGES_FOLDER) if f.startswith(unique_id)])
    if os.path.exists(SCENES_FOLDER):
        paths_to_delete.extend([os.path.join(SCENES_FOLDER, f) for f in os.listdir(SCENES_FOLDER) if f.startswith(f"{unique_id}_scene")])
    
    deleted_items_count = 0
    for item_path in paths_to_delete:
        if os.path.exists(item_path):
            try: os.remove(item_path); deleted_items_count +=1
            except OSError as e: flash(f"Error deleting file {item_path}: {str(e)}", "error")
    
    if deleted_items_count > 0 : flash(f'Chat log and associated files ({deleted_items_count} items) deleted.', 'success')
    else: flash('Chat log not found or no files to delete.', 'warning')
    return redirect(url_for('index'))

# === Profile Card Routes ===
@app.route('/profile_cards')
def profile_cards(): 
    return render_template('profile_cards.html', profile_cards=sorted(load_profile_cards().values(), key=lambda x: x.get('name', '').lower()))

@app.route('/upload_profile_card', methods=['GET', 'POST'])
def upload_profile_card():
    if request.method == 'POST':
        final_json_to_save, op_type, card_name_for_ops = None, "created", None
        uploaded_json_file = request.files.get('json_file')

        if uploaded_json_file and uploaded_json_file.filename != '': 
            if allowed_file(uploaded_json_file.filename):
                try:
                    data_from_json_upload = json.load(uploaded_json_file)
                    card_name_for_ops = data_from_json_upload.get('name', data_from_json_upload.get('Name'))
                    if not card_name_for_ops: flash('Uploaded JSON profile card must have a "name" or "Name" field.', 'error'); return redirect(request.url)
                    final_json_to_save = data_from_json_upload 
                except Exception as e: flash(f'Error processing profile card JSON: {str(e)}', 'error'); return redirect(request.url)
            else: flash('Invalid JSON file type for profile card.', 'error'); return redirect(request.url)
        else: 
            card_name_for_ops = request.form.get('name', '').strip()
            if not card_name_for_ops: flash('Profile card name is required.', 'error'); return redirect(request.url)
            image_field_for_json = "" 
            uploaded_image_file = request.files.get('image_file')
            if uploaded_image_file and allowed_file(uploaded_image_file.filename):
                sanitized_name_for_file_base = secure_filename(card_name_for_ops.lower().replace(" ", "_"))
                image_ext = os.path.splitext(uploaded_image_file.filename)[1].lower()
                if not image_ext.startswith('.'): image_ext = '.' + image_ext
                saved_image_filename = sanitized_name_for_file_base + image_ext
                uploaded_image_file.save(os.path.join(PROFILE_IMAGES_FOLDER, saved_image_filename))
            final_json_to_save = {"name": card_name_for_ops, "image": image_field_for_json, 
                                "gender": request.form.get('gender', ''), "age": request.form.get('age', ''),
                                "likes": request.form.get('favorites', ''), "dislikes": request.form.get('dislikes', ''),
                                "other_info": request.form.get('other_info', '')}
        
        if final_json_to_save and card_name_for_ops:
            json_filename = get_sanitized_card_filename(card_name_for_ops)
            json_path = os.path.join(PROFILE_CARDS_FOLDER, json_filename)
            if os.path.exists(json_path): op_type = "updated"
            with open(json_path, 'w', encoding='utf-8') as f: json.dump(final_json_to_save, f, indent=2)
            if uploaded_json_file and isinstance(final_json_to_save.get("image"), str) and final_json_to_save["image"].startswith("data:image"):
                 get_profile_card_image_path(card_name_for_ops, base64_image_data=final_json_to_save.get("image"), process_base64_if_needed=True)
            flash(f'Profile card for "{card_name_for_ops}" {op_type}.', 'success'); return redirect(url_for('profile_cards'))
        flash('Could not process profile card data.', 'error'); return redirect(request.url)
    return render_template('upload_profile_card.html')

@app.route('/edit_profile_card/<card_name_param>', methods=['GET', 'POST'])
def edit_profile_card(card_name_param):
    all_cards = load_profile_cards(); profile_card_to_edit = all_cards.get(card_name_param.lower())
    if not profile_card_to_edit: flash(f"Card '{card_name_param}' not found.", 'error'); return redirect(url_for('profile_cards'))
    original_json_filename = get_sanitized_card_filename(profile_card_to_edit.get('name', card_name_param))
    original_json_path = os.path.join(PROFILE_CARDS_FOLDER, original_json_filename); raw_json_image_field = ""
    if os.path.exists(original_json_path):
        try:
            with open(original_json_path, 'r', encoding='utf-8') as f_orig: raw_json_image_field = json.load(f_orig).get("image", "")
        except Exception as e: app.logger.error(f"Error reading original JSON for card {profile_card_to_edit['name']}: {e}")

    if request.method == 'POST':
        new_name = request.form.get('name', '').strip()
        if not new_name: flash("Name cannot be empty.", "error"); return render_template('edit_profile_card.html', profile_card=profile_card_to_edit, original_card_name=card_name_param, raw_json_image_field=raw_json_image_field)
        updated_json_image_field = raw_json_image_field 
        new_image_file_upload = request.files.get('image_file_edit')
        if new_image_file_upload and allowed_file(new_image_file_upload.filename):
            sanitized_new_name_for_file_base = secure_filename(new_name.lower().replace(" ", "_"))
            if os.path.exists(PROFILE_IMAGES_FOLDER):
                 for old_img_candidate in os.listdir(PROFILE_IMAGES_FOLDER):
                    if old_img_candidate.startswith(sanitized_new_name_for_file_base): # Check for new name conflicts
                        try: os.remove(os.path.join(PROFILE_IMAGES_FOLDER, old_img_candidate))
                        except Exception as e: app.logger.error(f"Error deleting old profile image {old_img_candidate}: {e}")
            image_ext = os.path.splitext(new_image_file_upload.filename)[1].lower()
            if not image_ext.startswith('.'): image_ext = '.' + image_ext
            saved_image_filename = sanitized_new_name_for_file_base + image_ext
            new_image_file_upload.save(os.path.join(PROFILE_IMAGES_FOLDER, saved_image_filename))
            updated_json_image_field = "" 
        updated_json_data_to_save = {"name": new_name, "image": updated_json_image_field,
            "gender": request.form.get('gender', ''), "age": request.form.get('age', ''),
            "likes": request.form.get('likes', ''), "dislikes": request.form.get('dislikes', ''),
            "other_info": request.form.get('other_info', '')}
        new_json_filename = get_sanitized_card_filename(new_name)
        new_json_path = os.path.join(PROFILE_CARDS_FOLDER, new_json_filename)
        if original_json_path != new_json_path: 
            if os.path.exists(new_json_path): flash(f"Profile card JSON for '{new_name}' already exists.", "error"); return render_template('edit_profile_card.html', profile_card=profile_card_to_edit, original_card_name=card_name_param, raw_json_image_field=raw_json_image_field)
            if os.path.exists(original_json_path): 
                 try: os.remove(original_json_path)
                 except Exception as e_del_json : app.logger.error(f"Error removing old json {original_json_path}: {e_del_json}")
        with open(new_json_path, 'w', encoding='utf-8') as f: json.dump(updated_json_data_to_save, f, indent=2)
        if isinstance(updated_json_data_to_save.get("image"), str) and updated_json_data_to_save["image"].startswith("data:image"):
            get_profile_card_image_path(new_name, base64_image_data=updated_json_data_to_save["image"], process_base64_if_needed=True)
        flash(f'Profile card "{new_name}" updated successfully.', 'success'); return redirect(url_for('profile_cards'))
    return render_template('edit_profile_card.html', profile_card=profile_card_to_edit, original_card_name=card_name_param, raw_json_image_field=raw_json_image_field)

@app.route('/delete_profile_card/<card_name_param>', methods=['POST'])
def delete_profile_card(card_name_param):
    all_cards = load_profile_cards(); card_to_delete = all_cards.get(card_name_param.lower()) 
    if not card_to_delete: flash(f"Card '{card_name_param}' not found.", 'error'); return redirect(url_for('profile_cards'))
    actual_card_name = card_to_delete.get('name', card_name_param); filename_to_delete = get_sanitized_card_filename(actual_card_name)
    card_json_path = os.path.join(PROFILE_CARDS_FOLDER, filename_to_delete)
    sanitized_name_for_file_lookup = secure_filename(actual_card_name.lower().replace(" ", "_"))
    if os.path.exists(PROFILE_IMAGES_FOLDER):
        image_candidate = next((f for f in os.listdir(PROFILE_IMAGES_FOLDER) if f.startswith(sanitized_name_for_file_lookup)), None)
        if image_candidate:
            try: os.remove(os.path.join(PROFILE_IMAGES_FOLDER, image_candidate)); app.logger.info(f"Deleted profile image: {image_candidate}")
            except Exception as e: app.logger.error(f"Error deleting profile image {image_candidate}: {e}")
    if os.path.exists(card_json_path):
        try: os.remove(card_json_path); flash(f'Card "{actual_card_name}" deleted.', 'success')
        except OSError as e: flash(f"Error deleting card file '{actual_card_name}': {str(e)}", "error")
    else: flash(f'Card file "{filename_to_delete}" not found for deletion.', 'warning')
    return redirect(url_for('profile_cards'))

# === Memory Combination Route ===
@app.route('/combine_memories', methods=['GET', 'POST'])
def combine_memories():
    if request.method == 'POST':
        memory_files_list = request.files.getlist('memory_files'); file_order_str = request.form.get('file_order_input') 
        combined_chat_title = request.form.get('combined_chat_title', '').strip()
        combined_chat_intro = request.form.get('combined_chat_intro', '').strip()
        combined_custom_tags_str = request.form.get('combined_custom_tags', '').strip()
        user_char_img_combined = request.files.get('combined_character_image')
        user_scene_img_combined = request.files.get('scene_image_upload')

        if not combined_chat_title: flash('Title for combined chat is required.', 'error'); return redirect(request.url)
        actual_uploads_count = sum(1 for f in memory_files_list if f and f.filename)
        if actual_uploads_count == 0: flash('Select at least one memory file.', 'error'); return redirect(request.url)
        
        ordered_fnames = []
        if not file_order_str or (file_order_str == "[]" and actual_uploads_count > 0) :
            if actual_uploads_count == 1 and memory_files_list[0].filename: ordered_fnames = [memory_files_list[0].filename]
            else: flash('File order missing/empty. Select and order files.', 'error'); return redirect(request.url)
        else:
            try:
                ordered_fnames = json.loads(file_order_str)
                if not isinstance(ordered_fnames, list) or (actual_uploads_count > 0 and not ordered_fnames) or (len(ordered_fnames) != actual_uploads_count):
                    flash(f'File order/count mismatch. Order: {len(ordered_fnames)}, Files: {actual_uploads_count}. Re-select/order.', 'error'); return redirect(request.url)
            except json.JSONDecodeError: flash('Invalid file order format.', 'error'); return redirect(request.url)

        uploaded_files_map = {f.filename: f for f in memory_files_list if f and f.filename}
        first_speaker, parsed_mems_list = None, []
        for fname in ordered_fnames:
            f_obj = uploaded_files_map.get(fname)
            if not f_obj or not allowed_file(f_obj.filename): flash(f'Invalid/missing file: {fname}', 'error'); return redirect(request.url)
            try: f_obj.seek(0); mem_content = json.load(f_obj); f_obj.seek(0)
            except: flash(f'Could not parse {fname}', 'error'); return redirect(request.url)
            if not mem_content.get('messages') or not mem_content['messages']: flash(f'"{fname}" no messages.', 'error'); return redirect(request.url)
            curr_speaker = mem_content['messages'][0].get('speaker')
            if not curr_speaker: flash(f'First msg in "{fname}" needs speaker.', 'error'); return redirect(request.url)
            if first_speaker is None: first_speaker = curr_speaker
            elif first_speaker != curr_speaker: flash(f'Speaker mismatch in "{fname}". Expected "{first_speaker}", got "{curr_speaker}".', 'error'); return redirect(request.url)
            parsed_mems_list.append(mem_content)
        if not parsed_mems_list: flash("No valid memory content.", "error"); return redirect(request.url)

        combo_msgs, first_msg_txt, first_msg_spk = [], None, None
        if parsed_mems_list:
            first_mem_data = parsed_mems_list[0]; first_mem_msgs = first_mem_data.get('messages', [])
            combo_msgs.extend(first_mem_msgs)
            if first_mem_msgs: first_msg_txt, first_msg_spk = first_mem_msgs[0].get('message'), first_mem_msgs[0].get('speaker')
            for i in range(1, len(parsed_mems_list)):
                sub_msgs = parsed_mems_list[i].get('messages', [])
                if sub_msgs:
                    is_dup = first_msg_txt and sub_msgs[0].get('message') == first_msg_txt and sub_msgs[0].get('speaker') == first_msg_spk
                    combo_msgs.extend(sub_msgs[1:] if is_dup else sub_msgs)
        
        meta_src = parsed_mems_list[0]
        auth_data = meta_src.get('author'); auth_name = ""; auth_url = meta_src.get('author_url', '')
        if isinstance(auth_data, dict): auth_name=auth_data.get('name',''); auth_url=auth_data.get('url', auth_url)
        elif isinstance(auth_data, str): auth_name = auth_data
        base_tags_raw = meta_src.get('tags', []); custom_tags = [t.strip() for t in combined_custom_tags_str.split(',') if t.strip()]
        if not isinstance(base_tags_raw, list): base_tags = [str(base_tags_raw)] if base_tags_raw else []
        else: base_tags = [str(t) for t in base_tags_raw]
        
        b64_char_img = meta_src.get('image', ''); b64_scene_img = meta_src.get('sceneImage', '')
        new_id = str(uuid.uuid4()); char_img_json = b64_char_img; scene_img_json = b64_scene_img

        if user_char_img_combined and allowed_file(user_char_img_combined.filename):
            img_ext = os.path.splitext(user_char_img_combined.filename)[1].lower();
            if not img_ext.startswith('.'): img_ext = '.' + img_ext
            user_char_img_combined.save(os.path.join(CHARACTER_IMAGE_OVERRIDES_FOLDER, new_id + img_ext))
            char_img_json = "" 
        if user_scene_img_combined and allowed_file(user_scene_img_combined.filename):
            try:
                bts = user_scene_img_combined.read(); mime = mimetypes.guess_type(user_scene_img_combined.filename)[0] or 'image/png'
                scene_img_json = f"data:{mime};base64,{base64.b64encode(bts).decode('utf-8')}"
            except Exception as e_b64s: app.logger.error(f"Error converting scene img for combined: {e_b64s}"); flash("Error processing scene img.", "warning")
        
        new_log = {"title": combined_chat_title, "author": {"name": auth_name, "url": auth_url} if auth_name or auth_url else {},
                   "model": meta_src.get('model', ''), "image": char_img_json, "sceneImage": scene_img_json, 
                   "intro": combined_chat_intro, "tags": base_tags, "custom_tags": custom_tags, "messages": combo_msgs}
        with open(os.path.join(CHARACTER_DATA_FOLDER, new_id + ".json"), 'w', encoding='utf-8') as f: json.dump(new_log, f, indent=2)
        
        if char_img_json: get_character_image_path(new_id, base64_image_data=char_img_json, process_base64_if_needed=True)
        if scene_img_json: get_scene_image_path(new_id, base64_scene_image=scene_img_json, process_base64_if_needed=True)
        flash('Memories combined successfully!', 'success'); return redirect(url_for('display_chat', unique_id=new_id))
    return render_template('combine_memories.html')

# === Chat Settings Route ===
@app.route('/chat/<unique_id>/chat_settings', methods=['POST'])
def chat_settings(unique_id):
    log_path = os.path.join(CHARACTER_DATA_FOLDER, unique_id + '.json')
    if not os.path.exists(log_path): flash('Chat log not found.', 'error'); return redirect(url_for('index'))
    try:
        with open(log_path, 'r', encoding='utf-8') as f: data = json.load(f)
    except Exception as e: flash(f'Error loading chat data: {str(e)}', 'error'); return redirect(url_for('display_chat', unique_id=unique_id))
    
    action = request.form.get('action'); new_scene_img = request.files.get('new_scene_image_file')
    style_pref = request.form.get('scene_style_preference'); updated = False

    if action == 'upload_scene' and new_scene_img and allowed_file(new_scene_img.filename):
        scene_fname_base = f"{unique_id}_scene"
        if os.path.exists(SCENES_FOLDER):
            for old_f in os.listdir(SCENES_FOLDER):
                if old_f.startswith(scene_fname_base): 
                    try: os.remove(os.path.join(SCENES_FOLDER, old_f))
                    except Exception as e_d: app.logger.error(f"Error deleting old scene {old_f}: {e_d}")
        try:
            bts = new_scene_img.read(); mime = mimetypes.guess_type(new_scene_img.filename)[0] or 'image/png'
            data['sceneImage'] = f"data:{mime};base64,{base64.b64encode(bts).decode('utf-8')}"
            updated = True; flash('New scene image uploaded.', 'success')
        except Exception as e_b: app.logger.error(f"Error converting scene image for {unique_id}: {e_b}"); flash('Error processing scene image.', 'error')
    elif action == 'remove_scene':
        data['sceneImage'] = ""; scene_fname_base = f"{unique_id}_scene"
        if os.path.exists(SCENES_FOLDER):
            for old_f in os.listdir(SCENES_FOLDER):
                if old_f.startswith(scene_fname_base): 
                    try: os.remove(os.path.join(SCENES_FOLDER, old_f))
                    except Exception as e_d: app.logger.error(f"Error deleting old scene {old_f}: {e_d}")
        updated = True; flash('Scene image removed.', 'success')
    
    if 'scene_style_preference' in request.form:
        if style_pref in ['blurred_glass', 'cover']:
            if data.get('sceneStyle') != style_pref: data['sceneStyle'] = style_pref; updated = True; flash(f'Scene style set.', 'success')
        elif not style_pref and 'sceneStyle' in data: 
            del data['sceneStyle']; updated = True; flash('Scene style reset to default.', 'success')
    if updated:
        try:
            with open(log_path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=2)
        except Exception as e: flash(f'Error saving settings: {str(e)}', 'error')
    return redirect(url_for('display_chat', unique_id=unique_id))