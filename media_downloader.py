import os
import requests
import logging
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

def get_filename_from_url(url: str) -> Optional[str]:
    """Extracts a filename from a URL, trying to get the last path component."""
    try:
        parsed_url = urlparse(url)
        path = parsed_url.path
        filename = os.path.basename(path)
        if filename: # Ensure it's not empty (e.g. for root URLs)
            # Basic sanitization: remove query params from filename if they got included by basename
            return filename.split('?')[0]
        return None
    except Exception as e:
        logger.error(f"Error parsing URL to get filename: {url} - {e}")
        return None

def download_media_item(media_url: str, output_folder: str, item_index: int = 0) -> bool:
    """Downloads a single media item from a URL into the specified folder.

    Args:
        media_url: The URL of the media to download.
        output_folder: The folder path to save the downloaded media.
        item_index: An index to help create unique filenames if needed.

    Returns:
        True if download was successful, False otherwise.
    """
    if not media_url or not isinstance(media_url, str):
        logger.warning(f"Invalid media URL provided for download: {media_url}")
        return False

    try:
        logger.info(f"Attempting to download: {media_url}")
        response = requests.get(media_url, stream=True, timeout=30) # stream=True for large files, timeout
        response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)

        # Try to get a filename from URL
        filename = get_filename_from_url(media_url)
        
        # Fallback or unique filename generation if needed
        if not filename:
            # Try to get a hint from content-type if possible, otherwise use a generic name
            content_type = response.headers.get('content-type')
            extension = '.dat' # default extension
            if content_type:
                if 'image/jpeg' in content_type:
                    extension = '.jpg'
                elif 'image/png' in content_type:
                    extension = '.png'
                elif 'image/gif' in content_type:
                    extension = '.gif'
                elif 'video/mp4' in content_type:
                    extension = '.mp4'
                # Add more content types as needed
            filename = f"media_item_{item_index}{extension}"
            logger.debug(f"Could not derive filename from URL, using generated name: {filename}")
        else:
            # Ensure filename is somewhat unique if multiple items have same name (e.g. index.html)
            # Or if multiple items from a gallery are named similarly by the API
            base, ext = os.path.splitext(filename)
            # A simple uniqueness addition by index, can be made more robust if needed.
            # This handles if get_filename_from_url returns something generic like 'image'
            if item_index > 0: # Only add index if it's not the first item or if filename might be generic
                 filename = f"{base}_{item_index}{ext}"

        # Basic sanitization (very simple, can be expanded)
        # Replace characters that are problematic in filenames on some OSes
        # For more robust sanitization, a library might be better.
        safe_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.() "
        sanitized_filename = "".join(c if c in safe_chars else '_' for c in filename).strip()
        if not sanitized_filename:
            sanitized_filename = f"downloaded_media_{item_index}.dat"
        
        file_path = os.path.join(output_folder, sanitized_filename)

        # Ensure folder exists (it should have been created by reddit_extractor.py)
        if not os.path.exists(output_folder):
            logger.error(f"Output folder {output_folder} does not exist. Cannot save media.")
            return False

        logger.info(f"Saving media to: {file_path}")
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        logger.info(f"Successfully downloaded and saved {file_path}")
        return True

    except requests.exceptions.RequestException as e:
        logger.error(f"Error downloading {media_url}: {e}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred while downloading {media_url}: {e}", exc_info=True)
        return False

if __name__ == '__main__':
    # Basic test for the downloader
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
    test_image_url = "https://i.redd.it/someimage.jpg" # Replace with a real, small, public image URL for testing
    test_video_url = "https://v.redd.it/somevideo/DASH_720.mp4" # Replace with a real, small, public video URL
    
    test_output_folder = "test_media_downloads"
    if not os.path.exists(test_output_folder):
        os.makedirs(test_output_folder)

    logger.info("--- Testing Media Downloader ---")
    
    # Example: find a small public domain image for testing
    # For example, from Wikimedia Commons, a small public domain PNG or JPG.
    # Ensure the URL points directly to the image file.
    # Example (replace with an actual working direct link to a small image):
    # test_image_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/7/74/A-Cat.png/220px-A-Cat.png" 
    # This URL might not work directly due to Wikimedia policies or hotlinking protection, find a stable direct link.

    # Create a dummy URL that might be harder to parse for filename to test fallback
    hard_to_parse_url = "https://example.com/media/download?id=123&type=image"

    # Test 1: Image with a clear filename
    # if download_media_item(test_image_url, test_output_folder, item_index=0):
    #     print(f"Test 1 (image) download successful (check {test_output_folder})")
    # else:
    #     print(f"Test 1 (image) download failed.")

    # Test 2: Video with a clear filename
    # if download_media_item(test_video_url, test_output_folder, item_index=1):
    #     print(f"Test 2 (video) download successful (check {test_output_folder})")
    # else:
    #     print(f"Test 2 (video) download failed.")

    # Test 3: URL with no clear filename extension (tests fallback naming)
    # if download_media_item(hard_to_parse_url, test_output_folder, item_index=2):
    #      print(f"Test 3 (hard_to_parse_url) download successful (check {test_output_folder})")
    # else:
    #     print(f"Test 3 (hard_to_parse_url) download failed.")

    # Test 4: Invalid URL
    if not download_media_item("htp://invalid-url-format", test_output_folder, item_index=3):
        print("Test 4 (invalid URL) correctly failed as expected.")
    else:
        print("Test 4 (invalid URL) unexpectedly succeeded.")

    # Test 5: Non-existent URL (should fail with HTTPError)
    if not download_media_item("https://example.com/non_existent_file.jpg", test_output_folder, item_index=4):
        print("Test 5 (non-existent URL) correctly failed as expected.")
    else:
        print("Test 5 (non-existent URL) unexpectedly succeeded.")

    print("\nPlease manually verify downloaded files in the 'test_media_downloads' folder if any tests were un-commented and expected to succeed.")
    print("Remember to replace placeholder URLs with actual, small, publicly downloadable media for thorough testing.")
    logger.info("--- Media Downloader Test Finished ---") 