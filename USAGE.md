# Reddit Content Extractor - Usage Guide

This guide provides detailed examples for using the Reddit Content Extractor script from the command line.

For a general overview, setup instructions, and interactive mode details, please see the main [README.md](README.md).

## Basic Usage

The fundamental command requires the `--url` argument pointing to the Reddit post:

```bash
python reddit_extractor.py --url https://www.reddit.com/r/ADHD/comments/1kg08k0/whats_a_weird_little_adhd_trick_that_actually/
```

* This will fetch the post details and **all** comments (default behavior).
* The output will be saved to a JSON file named automatically based on the post ID and title (e.g., `1kg08k0_whats_a_weird_little_adhd_trick_that_actually.json`).

## Controlling Comment Retrieval

* **Fetch Top N Comments:** Use `--comments N`.

    ```bash
    # Fetch post and only the top 10 comments (sorted by 'best')
    python reddit_extractor.py --url <URL> --comments 10
    ```

* **Fetch All Comments (Explicitly):** Use `--all-comments` (same as default when no comment flags are used).

    ```bash
    python reddit_extractor.py --url <URL> --all-comments
    ```

* **Fetch No Comments:** Use `--no-comments`.

    ```bash
    python reddit_extractor.py --url <URL> --no-comments
    ```

* **Change Comment Sort Order:** Use `--sort <order>`. Affects the order of top-level comments fetched. Requires fetching comments (`--comments N` or `--all-comments`).
  * Valid orders: `best`, `top`, `new`, `controversial`, `old`, `q&a`.

    ```bash
    # Fetch top 20 comments sorted by 'new'
    python reddit_extractor.py --url <URL> --comments 20 --sort new
    ```

* **Limit Comment Depth:** Use `--depth D`. Fetches replies only up to `D` levels deep. Requires fetching comments.
  * Note: Depth is **zero-indexed**.
    * `--depth 0` fetches only top-level comments (direct replies to the post). Their `replies` field will be an empty list.
    * `--depth 1` fetches top-level comments AND their direct replies. These depth 1 replies will have their `replies` field as an empty list.
    * And so on for deeper levels.
  * If not specified, all reply depths are fetched.

    ```bash
    # Fetch all comments, but only replies down to depth 3 (i.e., top-level, level 1, level 2, level 3 replies)
    python reddit_extractor.py --url <URL> --all-comments --depth 3
    ```

    ```bash
    # Fetch top 5 comments and their direct replies only (depth 1)
    python reddit_extractor.py --url <URL> --comments 5 --depth 1
    ```

## Controlling Output

* **Specify Output Filename:** Use `--output <filename.json>` or `-o <filename.json>`.

    ```bash
    python reddit_extractor.py --url <URL> -o my_custom_name.json
    ```

* **Print JSON to Console:** Use `--print`. This overrides saving to a file.

    ```bash
    python reddit_extractor.py --url <URL> --no-comments --print
    ```

## Logging and Debugging

* **Verbose Console Output:** Use `--verbose` or `-v` to see DEBUG level messages printed to the console.

    ```bash
    python reddit_extractor.py --url <URL> -v
    ```

* **Log to File:** Use `--log-file <filepath>` to save logs to a specified file. Logs are appended.

    ```bash
    python reddit_extractor.py --url <URL> --log-file reddit_extractor.log
    ```

* **Combine Verbose and File Logging:**

    ```bash
    python reddit_extractor.py --url <URL> -v --log-file detailed_run.log
    ```

    (This will show DEBUG messages on console *and* save them to the file).

## Advanced Data Options

* **Include Raw Media Details:** Use `--include-raw-media`.
  * By default, the script provides structured media information designed to be concise and useful for most cases.
  * If you need the absolute complete, unprocessed media data as provided by Reddit's API (via PRAW), including all available image resolutions for every image in a gallery, extensive internal metadata objects, etc., you can use this flag.
  * **Warning:** Enabling this option can make the output JSON file significantly larger, especially for posts with image galleries or complex media.
  * This corresponds to the `_raw_media`, `_raw_media_embed`, `_raw_secure_media`, `_raw_secure_media_embed`, `_raw_gallery_data`, and `_raw_media_metadata` fields in the output JSON if you are inspecting its structure.

    ```bash
    # Fetch post and include all raw media details
    python reddit_extractor.py --url <URL_OF_POST_WITH_GALLERY> --include-raw-media -o detailed_output.json
    ```

## Media Download Feature

When running in interactive mode, the script can download media (images, GIFs, and some videos) from the main post and/or comments. Downloaded media is saved in a folder named after the output JSON file.

**Important Note for Reddit Videos:**

* Downloaded Reddit-hosted videos will **not have sound**. Reddit stores video and audio as separate files/streams, and this script only downloads the video stream (the .mp4 file).
* Images and GIFs are downloaded as expected.

## Combining Options

Most options can be combined:

```bash
# Fetch top 100 'top' comments up to depth 5, save to specific file, and log verbose output to another file
python reddit_extractor.py --url <URL> --comments 100 --sort top --depth 5 -o results.json -v --log-file execution.log
```
