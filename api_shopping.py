import asyncio
from fastapi import FastAPI, HTTPException
from playwright.async_api import async_playwright
import json
import re
from fastapi.responses import FileResponse


app = FastAPI()

# Function to load cookies from a JSON file
def load_cookies():
    try:
        with open("cookies.json", "r") as file:
            cookies = json.load(file)
        return cookies
    except Exception as e:
        print(f"Error loading cookies: {e}")
        return []

async def scrape_product_details(product_url, context):
    try:
        # Prepend "https://www.google.com" if the URL is relative
        if not product_url.startswith("http"):
            product_url = f"https://www.google.com{product_url}"

        print(f"Scraping product URL: {product_url}")

        # Open a new page for the product details
        page = await context.new_page()
        await page.goto(product_url, wait_until="domcontentloaded")

        # Extract the description
        description = await page.inner_text("div.Zh8lCd") if await page.query_selector("div.Zh8lCd") else "N/A"

        await page.close()
        return {
            "description": description
        }
    except Exception as e:
        print(f"Error scraping product details: {e}")
        return {
            "description": "N/A",
        }

async def scrape_google_shopping(query):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        # Load cookies into the browser context
        cookies = load_cookies()
        if cookies:
            await context.add_cookies(cookies)
            print("Cookies loaded successfully.")

        page = await context.new_page()

        # Block unnecessary resources to speed up loading
        await page.route("**/*.{png,jpg,jpeg,gif,svg,webp}", lambda route: route.abort())
        await page.route("**/*.css", lambda route: route.abort())
        await page.route("**/*.js", lambda route: route.abort())

        await page.goto(f"https://www.google.com/search?q={query}&tbm=shop")

        # Debug: Take a screenshot of the search results page
        await page.screenshot(path="search_results_screenshot.png")
        print("Screenshot saved: search_results_screenshot.png")

        # Save a screenshot on the server
        screenshot_path = "/home/screenshot.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"Scraping product URL: {screenshot_path}")
        try:
            await page.wait_for_selector("div.sh-dgr__content", timeout=60000)  # Increase timeout
            products = await page.query_selector_all("div.sh-dgr__content")
            product_data = []

            # Scrape product details concurrently
            tasks = []  # This is a list to store coroutines
            for product in products[:5]:  # Limit to 5 products for testing
                try:
                    # Extract product details
                    product_title = await product.query_selector("h3.tAxDx")
                    product_price = await product.query_selector("span.a8Pemb")
                    product_link = await product.query_selector("a.xCpuod")
                    product_image = await product.query_selector("img")
                    product_rating = await product.query_selector("span.Rsc7Yb")

                    product_dict = {
                        "product_title": await product_title.inner_text() if product_title else "N/A",
                        "product_price": await product_price.inner_text() if product_price else "N/A",
                        "product_link": await product_link.get_attribute("href") if product_link else "N/A",
                        "product_image": await product_image.get_attribute("src") if product_image else "N/A",
                        "product_rating": float(
                            (await product_rating.inner_text()).replace(",", ".")) if product_rating else "N/A",
                        "product_num_reviews": int(
                            re.findall(r"\d+", await product_rating.inner_text())[-1]) if product_rating else "N/A",
                    }

                    # Scrape additional details concurrently
                    if product_dict["product_link"] != "N/A":
                        # Append the coroutine to the tasks list
                        tasks.append(scrape_product_details(product_dict["product_link"], context))

                    product_data.append(product_dict)
                except Exception as e:
                    print(f"Error scraping product: {e}")

            # Wait for all product detail scraping tasks to complete
            details_list = await asyncio.gather(*tasks)

            # Merge product details into the product data
            for i, details in enumerate(details_list):
                product_data[i].update(details)

            await browser.close()
            return product_data
        except Exception as e:
            print(f"Error waiting for selector: {e}")
            await browser.close()
            return []

# API Endpoint
@app.get("/scrape/")
async def scrape(query: str):
    try:
        product_data = await scrape_google_shopping(query)
        if not product_data:
            raise HTTPException(status_code=404, detail="No products found")
        return product_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/test")
async def test_scraper():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        # Load cookies into the browser context
        cookies = load_cookies()
        if cookies:
            await context.add_cookies(cookies)
            print("Cookies loaded successfully.")

        page = await browser.new_page()
        await page.goto("https://www.google.com")
        title = await page.title()
        await browser.close()
        return {"title": title}

@app.get("/view/")
async def view_screenshot():
    return FileResponse("/home/shopping-scrapper/search_results_screenshot.png")
# Run the FastAPI app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)