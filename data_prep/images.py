"""Object images pipeline: downloads and processes astronomical images."""

import json
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

try:
    import httpx
except ImportError as e:
    print("Error: 'httpx' library not found.")
    print("Please install it with: uv pip install 'httpx[http2]'")
    raise SystemExit(1) from e

from PIL import Image


def download_image(url: str) -> tuple[bool, bytes | None, int | None]:
    """
    Download an image using HTTP/2.

    Returns:
        (success, image_bytes, status_code)
    """
    try:
        # Use full browser headers including security headers (required for Wikimedia thumbnails)
        headers = {
            'accept': (
                'text/html,application/xhtml+xml,application/xml;q=0.9,'
                'image/avif,image/webp,image/apng,*/*;q=0.8,'
                'application/signed-exchange;v=b3;q=0.7'
            ),
            'accept-language': 'en-US,en;q=0.9',
            'sec-ch-ua': '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'none',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36'
            ),
        }

        # Create client with HTTP/2 support to avoid rate limiting
        with httpx.Client(http2=True, timeout=120.0, follow_redirects=True) as client:
            response = client.get(url, headers=headers)

            if response.status_code == 200:
                return (True, response.content, response.status_code)
            return (False, None, response.status_code)

    except httpx.HTTPStatusError as e:
        return (False, None, e.response.status_code)

    except (httpx.RequestError, Exception):  # pylint: disable=broad-exception-caught
        return (False, None, None)


def process_domain_queue(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    domain: str,
    items: list,
    cache_dir: Path,
    output_dir: Path,
    debug: bool = False
) -> dict:
    """
    Process all image downloads for a single domain using a queue with delayed retries.

    Args:
        domain: The domain name
        items: List of (catalogue_id, url, source_dict) tuples
        cache_dir: Directory for caching original images
        output_dir: Directory for processed images
        debug: Enable debug output

    Returns:
        Dictionary with download results
    """
    queue = deque(items)
    results = {}
    retry_delays = [10, 20, 40]  # Backoff delays in seconds
    retry_counts = {}  # Track retry count per catalogue_id

    if debug:
        print(f"\n[{domain}] Processing {len(items)} images...")

    while queue:
        cat_id, url, source = queue.popleft()

        # Initialize retry count
        if cat_id not in retry_counts:
            retry_counts[cat_id] = 0

        # Determine paths (strip query parameters from URL before getting extension)
        parsed_url = urlparse(url)
        url_ext = Path(parsed_url.path).suffix or ".jpg"
        cache_path = cache_dir / f"{cat_id}{url_ext}"
        output_path = output_dir / f"{cat_id}.jpg"

        # Skip if output already exists
        if output_path.exists():
            if debug:
                print(f"  [{domain}] {cat_id} ✓ Already processed")
            results[cat_id] = ('skipped', None)
            continue

        # Use cached version if available
        if cache_path.exists():
            if debug:
                print(f"  [{domain}] {cat_id} ✓ Using cached")
            try:
                _process_image(cache_path, output_path)
                results[cat_id] = ('success', None)
                if debug:
                    img = Image.open(output_path)
                    print(f"    Saved {cat_id}.jpg ({img.size[0]}×{img.size[1]})")
            except Exception as e:  # pylint: disable=broad-exception-caught
                results[cat_id] = ('failed', None)
                print(f"  [{domain}] {cat_id} ✗ Processing failed: {e}")
            continue

        # Download image
        if debug:
            print(f"  [{domain}] {cat_id}...", end=' ', flush=True)

        success, image_bytes, status = download_image(url)

        if success and image_bytes:
            try:
                # Save to cache
                cache_path.write_bytes(image_bytes)

                # Process and save
                _process_image(cache_path, output_path)

                results[cat_id] = ('success', status)
                if debug:
                    img = Image.open(output_path)
                    print(f"✓ Downloaded & saved ({img.size[0]}×{img.size[1]})")

                # Brief delay to be respectful
                time.sleep(0.5)

            except Exception as e:  # pylint: disable=broad-exception-caught
                results[cat_id] = ('failed', status)
                print(f"✗ Processing failed: {e}")
                if cache_path.exists():
                    cache_path.unlink()  # Remove corrupted cache

        elif status == 404:
            # Give up immediately on 404
            results[cat_id] = ('not_found', 404)
            if debug:
                print("✗ Not found (404)")
            print(f"     URL: {url}")

        else:
            # Rate limit or other error
            retry_count = retry_counts[cat_id]

            if retry_count < len(retry_delays):
                # Put back in queue and wait
                queue.append((cat_id, url, source))
                retry_counts[cat_id] += 1
                delay = retry_delays[retry_count]
                max_retries = len(retry_delays)
                retry_info = f"retry {retry_count + 1}/{max_retries} after {delay}s"

                if status == 429:
                    print(f"⏸ Rate limited (429), {retry_info}")
                elif status is None:
                    print(f"⏸ Network error, {retry_info}")
                else:
                    print(f"⏸ HTTP {status}, {retry_info}")
                print(f"     URL: {url}")

                time.sleep(delay)
            else:
                # Max retries exceeded
                results[cat_id] = ('failed', status)
                print(f"✗ Failed after {retry_count} retries (status: {status})")
                print(f"     URL: {url}")

    return results


def _process_image(cache_path: Path, output_path: Path) -> None:
    """Process a cached image: convert to RGB, resize, and save as JPEG."""
    # Disable decompression bomb protection since we're thumbnailing to 400x400
    # (some astronomical images like M42 are very large, e.g., 18000x18000 pixels)
    Image.MAX_IMAGE_PIXELS = None

    img = Image.open(cache_path)

    # Convert to RGB if needed (handles RGBA, grayscale, etc.)
    if img.mode != "RGB":
        img = img.convert("RGB")

    # Resize to fit within 400×400 while preserving aspect ratio
    img.thumbnail((400, 400), Image.Resampling.LANCZOS)

    # Save as JPEG with quality 70
    img.save(output_path, "JPEG", quality=70, optimize=True)


class ImagePipeline:
    """Download and process astronomical object images from curated sources."""

    def __init__(
        self,
        sources_dir: Path,
        output_dir: Path,
        cache_dir: Path | None = None,
        debug: bool = False,
    ):
        """Initialize the image pipeline.

        Args:
            sources_dir: Directory containing image_sources.json.
            output_dir: Directory where processed images will be saved.
            cache_dir: Directory for caching original downloaded images.
            debug: Enable debug output.
        """
        self._sources_dir = sources_dir
        self._output_dir = output_dir
        self._cache_dir = cache_dir if cache_dir else sources_dir.parent / "cache"
        self._debug = debug

    def run(self, limit: int | None = None) -> Path:  # pylint: disable=too-many-locals,too-many-statements
        """Execute the image download and processing pipeline.

        Groups images by domain and processes each domain in parallel with
        retry logic to handle rate limiting.

        Args:
            limit: Maximum number of NEW images to download (already processed
                   images are not counted toward this limit; None = no limit).

        Returns:
            Path to the images output directory.
        """
        images_dir = self._output_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        cache_images_dir = self._cache_dir / "images"
        cache_images_dir.mkdir(parents=True, exist_ok=True)

        # Load image sources manifest
        manifest_path = self._sources_dir / "image_sources.json"
        with manifest_path.open("r", encoding="utf-8") as f:
            image_sources = json.load(f)

        # Filter to verified sources only
        image_sources = [s for s in image_sources if s.get('verified') == 1]

        # Apply limit if specified (only count non-processed images)
        if limit is not None:
            filtered_sources = []
            non_processed_count = 0
            for source in image_sources:
                cat_id = source['catalogue_id']
                output_path = images_dir / f"{cat_id}.jpg"

                # Always include already processed (they'll be skipped quickly)
                if output_path.exists():
                    filtered_sources.append(source)
                else:
                    # Only count and limit non-processed images
                    if non_processed_count < limit:
                        filtered_sources.append(source)
                        non_processed_count += 1
            image_sources = filtered_sources

        if self._debug:
            print(f"Loaded {len(image_sources)} verified image sources from manifest")

        if not image_sources:
            print("No verified image sources to process!")
            return images_dir

        # Group by domain for parallel processing
        domain_groups = defaultdict(list)
        for source in image_sources:
            url = source['url']
            parsed = urlparse(url)
            domain = parsed.netloc
            cat_id = source['catalogue_id']
            domain_groups[domain].append((cat_id, url, source))

        if self._debug:
            print(f"Grouped into {len(domain_groups)} domains:")
            for domain, items in domain_groups.items():
                print(f"  {domain}: {len(items)} images")

        # Process each domain in parallel
        all_results = {}
        with ThreadPoolExecutor(max_workers=len(domain_groups)) as executor:
            futures = {
                executor.submit(
                    process_domain_queue,
                    domain,
                    items,
                    cache_images_dir,
                    images_dir,
                    self._debug
                ): domain
                for domain, items in domain_groups.items()
            }

            for future in as_completed(futures):
                domain = futures[future]
                try:
                    results = future.result()
                    all_results.update(results)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    print(f"\n[{domain}] Error: {e}")

        # Summary
        success_count = sum(1 for status, _ in all_results.values() if status == 'success')
        skipped_count = sum(1 for status, _ in all_results.values() if status == 'skipped')
        not_found_count = sum(1 for status, _ in all_results.values() if status == 'not_found')
        failed_count = sum(1 for status, _ in all_results.values() if status == 'failed')

        print("\n✓ Image processing complete:")
        print(f"  - Successfully processed: {success_count}")
        print(f"  - Skipped (already exists): {skipped_count}")
        print(f"  - Not found (404): {not_found_count}")
        print(f"  - Failed (other errors): {failed_count}")
        print(f"  - Total: {len(image_sources)}")

        return images_dir
