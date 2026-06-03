#!/usr/bin/env python3
"""
Validate image URLs in sources/image_sources.json.

For each entry with verified: 0 or -1 and non-empty url:
- Sends HEAD request to check if image exists
- Sets verified: 1 if successful (200 OK)
- Sets verified: -1 if not found (404) or after retries fail
- Uses per-domain queues with delayed retries (10s, 20s, 40s) to handle rate limiting
- Processes domains in parallel
"""

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


def validate_url_simple(url: str) -> tuple[bool, int | None]:
    """
    Validate a URL with a single HEAD request using HTTP/2.

    Returns:
        (success, status_code) where success is True if 200, False otherwise
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
        with httpx.Client(http2=True, timeout=10.0, follow_redirects=True) as client:
            response = client.head(url, headers=headers)
            return (response.status_code == 200, response.status_code)

    except httpx.HTTPStatusError as e:
        return (False, e.response.status_code)

    except (httpx.RequestError, Exception):  # pylint: disable=broad-exception-caught
        return (False, None)
def process_domain_queue(domain: str, items: list) -> dict:
    """
    Process all items for a single domain using a queue with delayed retries.

    Args:
        domain: The domain name
        items: List of (catalogue_id, url, item_ref) tuples

    Returns:
        Dictionary with validation results
    """
    queue = deque(items)
    results = {}
    retry_delays = [10, 20, 40]  # Backoff delays in seconds
    retry_counts = {}  # Track retry count per URL

    print(f"\n[{domain}] Processing {len(items)} URLs...")

    while queue:
        cat_id, url, item_ref = queue.popleft()

        # Initialize retry count
        if cat_id not in retry_counts:
            retry_counts[cat_id] = 0

        print(f"  [{domain}] {cat_id}...", end=' ', flush=True)

        success, status = validate_url_simple(url)

        if success:
            item_ref['verified'] = 1
            results[cat_id] = ('success', status)
            print("✓ OK")
            # No delay, continue immediately

        elif status == 404:
            # Give up immediately on 404
            item_ref['verified'] = -1
            results[cat_id] = ('not_found', 404)
            print("✗ Not found (404)")
            print(f"     URL: {url}")

        else:
            # Rate limit or other error
            retry_count = retry_counts[cat_id]

            if retry_count < len(retry_delays):
                # Put back in queue and wait
                queue.append((cat_id, url, item_ref))
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
                item_ref['verified'] = -1
                results[cat_id] = ('failed', status)
                print(f"✗ Failed after {retry_count} retries (status: {status})")
                print(f"     URL: {url}")

    return results


def main() -> None:  # pylint: disable=too-many-locals
    """
    Main function to validate all image URLs in image_sources.json.

    Reads the JSON file, groups URLs by domain, validates them in parallel,
    and updates the verified field for each entry.
    """
    # Determine paths
    script_dir = Path(__file__).parent
    data_prep_dir = script_dir.parent
    json_path = data_prep_dir / 'sources' / 'image_sources.json'

    # Read the JSON file
    print(f"Reading {json_path}...")
    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)

    # Count entries by status
    total = len(data)
    to_check = [item for item in data
                if item.get('verified', 0) in (0, -1) and item.get('url', '')]
    already_verified = sum(1 for item in data if item.get('verified', 0) == 1)
    empty_urls = sum(1 for item in data if not item.get('url', ''))
    failed_previously = sum(1 for item in data if item.get('verified', 0) == -1)

    print(f"Total entries: {total}")
    print(f"Already verified: {already_verified}")
    print(f"Previously failed: {failed_previously}")
    print(f"Empty URLs: {empty_urls}")
    print(f"To check: {len(to_check)}\n")

    if not to_check:
        print("No entries to validate!")
        return

    # Group by domain
    domain_groups = defaultdict(list)
    for item in to_check:
        url = item['url']
        parsed = urlparse(url)
        domain = parsed.netloc
        cat_id = item['catalogue_id']
        domain_groups[domain].append((cat_id, url, item))

    print(f"Grouped into {len(domain_groups)} domains:")
    for domain, items in domain_groups.items():
        print(f"  {domain}: {len(items)} URLs")

    # Process each domain in parallel
    all_results = {}
    with ThreadPoolExecutor(max_workers=len(domain_groups)) as executor:
        futures = {
            executor.submit(process_domain_queue, domain, items): domain
            for domain, items in domain_groups.items()
        }

        for future in as_completed(futures):
            domain = futures[future]
            try:
                results = future.result()
                all_results.update(results)
            except Exception as e:  # pylint: disable=broad-exception-caught
                print(f"\n[{domain}] Error: {e}")

    # Write updated data back
    print(f"\nWriting updated data to {json_path}...")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

    # Summary
    validated_count = sum(1 for status, _ in all_results.values() if status == 'success')
    not_found_count = sum(1 for status, _ in all_results.values() if status == 'not_found')
    failed_count = sum(1 for status, _ in all_results.values() if status == 'failed')

    print("\n✓ Validation complete:")
    print(f"  - Successfully validated: {validated_count}")
    print(f"  - Not found (404): {not_found_count}")
    print(f"  - Failed (other errors): {failed_count}")
    print(f"  - Total checked: {len(to_check)}")


if __name__ == '__main__':
    main()
