import asyncio
import random
import csv
import json
from playwright.async_api import async_playwright

# ---------------- CONFIG ----------------
KEYWORDS = ["mini waffle maker non stick", "electric can opener hands free", "cast iron skillet pre seasoned 12 inch", "mandoline slicer with safety glove", "compact food scale grams", "under bed storage bags with zipper", "stackable pantry organizer bins", "cable management box for desk", "lazy susan turntable 12 inch", "wall mounted key holder entryway", "cooling weighted blanket for adults", "linen look curtains blackout", "bamboo pillow queen size set of 2", "boho throw pillow covers 18x18","best magnesium glycinate supplement", "daily vitamin pack for men", "ashwagandha stress relief capsules", "probiotic 50 billion CFU", "collagen peptides powder unflavored", "odor eliminator for home", "laundry detergent sheets eco friendly", "air purifier for large room HEPA", "disinfectant wipes bulk 300 count", "water filter pitcher long lasting"]
PAGES = [3, 4, 5, 6]

MAX_CONCURRENT = 6
RETRIES = 2

BASE_URL = "https://www.amazon.com/s?k="

# ---------------- UTIL ----------------
async def human_delay(a=1.5, b=3.5):
    await asyncio.sleep(random.uniform(a, b))

async def scroll(page):
    for _ in range(4):
        await page.mouse.wheel(0, 2500)
        await asyncio.sleep(1)


# ---------------- AMAZON LOCATION ----------------
async def set_bronx_location(page):
    try:
        await page.goto("https://www.amazon.com")
        await page.wait_for_timeout(3000)
        await page.click("#glow-ingress-block")
        await page.wait_for_selector("#GLUXZipUpdateInput", timeout=15000)
        await page.fill("#GLUXZipUpdateInput", "10451")
        await page.click("#GLUXZipUpdate")
        await page.wait_for_timeout(5000)
        try:
            await page.click("input.a-button-input", timeout=3000)
        except:
            pass
        print("Location set to Bronx NY (10451)")
    except Exception as e:
        print("Location setup failed:", e)

# ---------------- EXTRACT LINKS ----------------
async def extract_links(page):
    elements = await page.query_selector_all("a.a-link-normal.s-no-outline")

    urls = set()
    for el in elements:
        href = await el.get_attribute("href")
        if href and "/dp/" in href:
            clean = href.split("?")[0]
            urls.add("https://www.amazon.com" + clean)

    return list(urls)

# ---------------- PRODUCT SCRAPE ----------------
async def scrape_product(context, url):
    page = await context.new_page()

    for attempt in range(RETRIES):
        try:
            await page.goto(url, timeout=60000)
            await human_delay()

            # Wait for images block
            await page.wait_for_selector("#altImages", timeout=10000)

            images = await page.query_selector_all("#altImages img")
            image_count = len(images)

            # Title
            title_el = await page.query_selector("#productTitle")
            title = await title_el.inner_text() if title_el else ""

            # Price
            price_el = await page.query_selector(".a-price .a-offscreen")
            price = await price_el.inner_text() if price_el else ""

            # Rating
            rating_el = await page.query_selector("span.a-icon-alt")
            rating = await rating_el.inner_text() if rating_el else ""

            # Reviews
            review_el = await page.query_selector("#acrCustomerReviewText")
            reviews = await review_el.inner_text() if review_el else ""

            # Brand
            brand_el = await page.query_selector("#bylineInfo")
            brand = await brand_el.inner_text() if brand_el else ""

            await page.close()

            return {
                "url": url,
                "title": title.strip(),
                "price": price,
                "rating": rating,
                "reviews": reviews,
                "brand": brand,
                "images": image_count
            }

        except:
            if attempt == RETRIES - 1:
                await page.close()
                return None

            await asyncio.sleep(2)

# ---------------- WORKER ----------------
async def worker(context, queue, results):
    while True:
        url = await queue.get()

        data = await scrape_product(context, url)

        if data:
            print(f"{data['images']} imgs | {data['title'][:40]}")

            results.append(data)

            # live backup
            with open("backup.json", "a", encoding="utf-8") as f:
                f.write(json.dumps(data) + "\n")

        queue.task_done()

# ---------------- MAIN ----------------
async def main():
    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            locale="en-US",
            timezone_id="America/New_York",
            geolocation={"latitude": 40.8448, "longitude": -73.8648},
            permissions=["geolocation"]
        )

        page = await context.new_page()
        await set_bronx_location(page)

        try:
            await context.storage_state(path="amazon_bronx.json")
        except:
            pass

        all_links = set()

        # STEP 1: collect links
        for keyword in KEYWORDS:
            for pageno in PAGES:
                url = f"{BASE_URL}{keyword.replace(' ', '+')}&page={pageno}"

                try:
                    await page.goto(url)
                    await human_delay()
                    await scroll(page)

                    links = await extract_links(page)
                    print(f"{keyword} p{pageno}: {len(links)}")

                    all_links.update(links)

                except Exception as e:
                    print("Search error:", e)

        print(f"\nTotal links: {len(all_links)}")

        # STEP 2: queue
        queue = asyncio.Queue()
        results = []

        for link in all_links:
            await queue.put(link)

        tasks = []
        for _ in range(MAX_CONCURRENT):
            tasks.append(asyncio.create_task(worker(context, queue, results)))

        await queue.join()

        for t in tasks:
            t.cancel()

        if not results:
            print("No results collected.")
            await browser.close()
            return

        # STEP 3: save categorized CSVs
        with open("products_all.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)

        # separate files
        for n in [2, 3, 4]:
            filtered = [r for r in results if r["images"] == n]

            with open(f"products_{n}_images.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=results[0].keys())
                writer.writeheader()
                writer.writerows(filtered)

        print("\nSaved all files")

        await browser.close()

# ---------------- RUN ----------------
if __name__ == "__main__":
    asyncio.run(main())