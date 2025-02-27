import asyncio
from fastapi import FastAPI, HTTPException
from playwright.async_api import async_playwright
import json
import re
from fastapi.responses import FileResponse
import mysql.connector
import time



app = FastAPI()

# Configuration de la base de données MySQL
def get_db_connection():
    return mysql.connector.connect(
        host="srv1588.hstgr.io",
        user="u423420538_scrapper",
        password="5Ge&y8rFHcV",
        database="u423420538_scrapper"
    )

# Function to load cookies from a JSON file
def load_cookies():
    try:
        with open("cookies.json", "r") as file:
            cookies = json.load(file)
        return cookies
    except Exception as e:
        print(f"Error loading cookies: {e}")
        return []

# Fonction pour sauvegarder les produits dans la base de données
def save_to_db(product_data):
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        query = """
        INSERT INTO products (product_title, product_price, product_link, product_image, product_rating, product_num_reviews, description)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        for product in product_data:

            product.setdefault("description", "N/A")

            cursor.execute(query, (
                product["product_title"],
                product["product_price"],
                product["product_link"],
                product["product_image"],
                product["product_rating"],
                product["product_num_reviews"],
                product["description"]
            ))

        connection.commit()
        cursor.close()
        connection.close()
        print("Data saved to MySQL database.")
    except Exception as e:
        print(f"Error saving to database: {e}")

async def scrape_product_details(product_url, context):
    try:
        # Prepend "https://www.google.com" if the URL is relative
        if not product_url.startswith("http"):
            product_url = f"https://www.google.com{product_url}"

        print(f"Scraping product URL: {product_url}")

        # Open a new page for the product details
        page = await context.new_page()
        await page.goto(product_url, wait_until="domcontentloaded")
        # await page.goto(product_url, timeout=60000, wait_until="domcontentloaded")

        # Extract the description
        description = await page.inner_text("div.Zh8lCd") if await page.query_selector("div.Zh8lCd") else "N/A"
        # Check if the description is empty
        if not description.strip():  # If the description is empty or contains only spaces
            description = "N/A"
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
        # await page.wait_for_timeout(5000)  # Wait for the page to load

        try:
            await page.wait_for_selector("div.sh-dgr__content", timeout=60000)  # Increase timeout
            products = await page.query_selector_all("div.sh-dgr__content")
            product_data = []

            # Variables pour le comptage
            total_products = len(products)
            success_count = 0
            error_count = 0

            # Scrape product details concurrently
            tasks = []
            for product in products[:10]:  # Limit to 60 products for testing
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
                    if product_dict["product_link"] and "shopping/product/" in product_dict["product_link"]:
                        tasks.append(scrape_product_details(product_dict["product_link"], context))
                        success_count += 1
                    else:
                        print(f"URL non valide ignorée : {product_dict['product_link']}")
                        error_count += 1

                    product_data.append(product_dict)
                except Exception as e:
                    print(f"Error scraping product: {e}")
                    error_count += 1

            # Wait for all product detail scraping tasks to complete
            details_list = await asyncio.gather(*tasks)

            # Merge product details into the product data
            for i, details in enumerate(details_list):
                product_data[i].update(details)

            await browser.close()

            # Save data to MySQL
            save_to_db(product_data)

            # Print results
            print(f"Scraping terminé. Total de produits : {total_products}")
            print(f"Produits scrapés avec succès : {success_count}")
            print(f"Produits avec erreurs : {error_count}")

            return product_data
        except Exception as e:
            print(f"Error waiting for selector: {e}")
            await browser.close()
            return []
# API Endpoint
@app.get("/scrape/")
async def scrape(query: str):
    try:
        start_time = time.time()
        product_data = await scrape_google_shopping(query)
        end_time = time.time()
        print(f"Temps d'exécution : {end_time - start_time} secondes")
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