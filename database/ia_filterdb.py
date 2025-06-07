import logging
import re
import base64
from struct import pack
from pyrogram.file_id import FileId
from pymongo.errors import DuplicateKeyError, OperationFailure
from umongo import Instance, Document, fields
from motor.motor_asyncio import AsyncIOMotorClient
from marshmallow.exceptions import ValidationError
from info import FILES_DATABASE_URL, SECOND_FILES_DATABASE_URL, DATABASE_NAME, COLLECTION_NAME, MAX_BTN

logger = logging.getLogger(__name__)
MAX_POOL = 10
# Primary database
client = AsyncIOMotorClient(FILES_DATABASE_URL, maxPoolSize=MAX_POOL)
db = client[DATABASE_NAME]
instance = Instance.from_db(db)

@instance.register
class Media(Document):
    file_id = fields.StrField(attribute='_id')
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    caption = fields.StrField(allow_none=True)

    class Meta:
        indexes = ('$file_name', )
        collection_name = COLLECTION_NAME
        strict = False

# Second database (if configured)
second_client = None
second_db = None
second_instance = None
SecondMedia = None

if SECOND_FILES_DATABASE_URL:
    second_client = AsyncIOMotorClient(SECOND_FILES_DATABASE_URL, maxPoolSize=MAX_POOL)
    second_db = second_client[DATABASE_NAME]
    second_instance = Instance.from_db(second_db)

    @second_instance.register
    class SecondMedia(Document):
        file_id = fields.StrField(attribute='_id')
        file_name = fields.StrField(required=True)
        file_size = fields.IntField(required=True)
        caption = fields.StrField(allow_none=True)

        class Meta:
            indexes = ('$file_name', )
            collection_name = COLLECTION_NAME
            strict = False

# Clean strings from unwanted characters
def clean_string(s):
    s = str(s or "")

    # Define keywords to preserve
    protected_keywords = [
        r"\d{3,4}p", r"x264", r"x265", r"HEVC", r"HDR",
        r"WEBRip", r"BluRay", r"DVDRip", r"HDTV", r"WEB", r"CAM"
    ]

    # Define custom usernames/words to remove (without @)
    custom_words_to_remove = [
        "Adrama_lovers", "DA_Rips", "SomeUploader"
    ]

    # Remove entire patterns before cleanup
    for word in custom_words_to_remove:
        pattern = re.compile(rf"@?{re.escape(word)}", re.IGNORECASE)
        s = pattern.sub("", s)

    # Protect keywords
    for keyword in protected_keywords:
        s = re.sub(f"(?i)({keyword})", r"__\1__", s)

    # Remove any remaining "@" symbols
    s = re.sub(r"@(?=\w+)", "", s)

    # Replace specific symbols with space
    s = re.sub(r"[-:\"';!]", " ", s)

    # Replace _ and + with space
    s = re.sub(r"[_.+]", " ", s)

    # Collapse multiple spaces and strip
    s = re.sub(r"\s+", " ", s).strip()

    # Restore protected keywords
    s = re.sub(r"__(\w{2,20})__", r"\1", s)

    return s

# Decode new-style Pyrogram File ID
def unpack_new_file_id(new_file_id):
    decoded = FileId.decode(new_file_id)
    file_id = encode_file_id(
        pack(
            "<iiqq",
            int(decoded.file_type),
            decoded.dc_id,
            decoded.media_id,
            decoded.access_hash
        )
    )
    return file_id

def encode_file_id(s: bytes) -> str:
    r = b""
    n = 0
    for i in s + bytes([22]) + bytes([4]):
        if i == 0:
            n += 1
        else:
            if n:
                r += b"\x00" + bytes([n])
                n = 0
            r += bytes([i])
    return base64.urlsafe_b64encode(r).decode().rstrip("=")

# Save the media file to the database
async def save_file(message, media):
    try:
        file_id = unpack_new_file_id(media.file_id)
        file_name = clean_string(media.file_name)
        file_caption = clean_string(message.caption)

        file = Media(
            file_id=file_id,
            file_name=file_name,
            file_size=media.file_size,
            caption=file_caption
        )
    except ValidationError:
        logging.exception(f"Validation error while saving file: {media.file_name}")
        return 'err'
    except Exception as e:
        logging.exception(f"Unexpected error while preparing file: {e}")
        return 'err'
    else:
        try:
            await file.commit()
            print(f'[DB] Saved to 1st db - {file_name}')
            return 'suc'
        except DuplicateKeyError:
            print(f'[DB] Duplicate - {file_name}')
            return 'dup'
        except OperationFailure:  # if 1st db is full
            if SECOND_FILES_DATABASE_URL and SecondMedia:
                try:
                    second_file = SecondMedia(
                        file_id=file_id,
                        file_name=file_name,
                        file_size=media.file_size,
                        caption=file_caption
                    )
                    await second_file.commit()
                    print(f'[DB] Saved to 2nd db - {file_name}')
                    return 'suc'
                except DuplicateKeyError:
                    print(f'[DB] Already Saved in 2nd db - {file_name}')
                    return 'dup'
                except Exception as e:
                    logging.exception(f"Commit error for second db {file_name}: {e}")
                    return 'err'
            else:
                logging.exception(f"Primary db operation failed and no second db configured: {file_name}")
                return 'err'
        except Exception as e:
            logging.exception(f"Commit error for {file_name}: {e}")
            return 'err'

# For search-based retrieval
async def get_search_results(query, max_results=MAX_BTN, offset=0, lang=None):
    query = query.strip()
    if not query:
        raw_pattern = '.'
    elif ' ' not in query:
        raw_pattern = r'(\b|[\.\+\-_])' + query + r'(\b|[\.\+\-_])'
    else:
        raw_pattern = query.replace(' ', r'.*[\s\.\+\-_]')

    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except:
        regex = query

    filter = {'file_name': regex}
    
    # Get results from primary database
    cursor = Media.find(filter).sort('$natural', -1)
    results = [doc async for doc in cursor]
    
    # Get results from second database if configured
    if SECOND_FILES_DATABASE_URL and SecondMedia:
        cursor2 = SecondMedia.find(filter).sort('$natural', -1)
        results.extend([doc async for doc in cursor2])

    if lang:
        lang_files = [file for file in results if lang in file.file_name.lower()]
        files = lang_files[offset:][:max_results]
        total_results = len(lang_files)
    else:
        total_results = len(results)
        files = results[offset:][:max_results]

    next_offset = offset + max_results
    if next_offset >= total_results:
        next_offset = ''
    return files, next_offset, total_results

# For deleting files by search
async def delete_files(query):
    query = query.strip()
    if not query:
        raw_pattern = '.'
    elif ' ' not in query:
        raw_pattern = r'(\b|[\.\+\-_])' + query + r'(\b|[\.\+\-_])'
    else:
        raw_pattern = query.replace(' ', r'.*[\s\.\+\-_]')

    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except:
        regex = query

    filter = {'file_name': regex}
    
    # Get results from primary database
    cursor = Media.find(filter)
    results = [doc async for doc in cursor]
    
    # Get results from second database if configured
    if SECOND_FILES_DATABASE_URL and SecondMedia:
        cursor2 = SecondMedia.find(filter)
        results.extend([doc async for doc in cursor2])
    
    total = len(results)
    return total, results

# For getting full file details
async def get_file_details(query):
    filter = {'file_id': query}
    
    # Search in primary database first
    cursor = Media.find(filter)
    filedetails = await cursor.to_list(length=1)
    
    # If not found and second database exists, search there
    if not filedetails and SECOND_FILES_DATABASE_URL and SecondMedia:
        cursor2 = SecondMedia.find(filter)
        filedetails = await cursor2.to_list(length=1)
    
    return filedetails
