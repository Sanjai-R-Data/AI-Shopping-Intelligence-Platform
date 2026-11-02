"""
AI-Powered Multilingual Shopping Intelligence Platform
Synthetic Shopping Catalog Seeding Script.
Provides 18 realistic products with multiple competing retailer offers across
Electronics, Accessories, and Home Appliances.
Ensures repeatable, idempotent execution without duplicate data creation.
"""

import logging
from sqlalchemy import select, func
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.engine import Engine

from backend.app.core.database import SessionLocal, engine as default_engine, Base
from backend.app.models.shopping import Product, RetailerOffer

logger = logging.getLogger(__name__)

DEMO_PRODUCTS = [
    # -------------------------------------------------------------------------
    # Category: Electronics (1-7)
    # -------------------------------------------------------------------------
    {
        "id": "prod_apple_iphone15_pro",
        "name": "Apple iPhone 15 Pro (128GB - Natural Titanium)",
        "brand": "Apple",
        "category": "Electronics",
        "description": "Premium flagship smartphone engineered with aerospace-grade titanium, Apple A17 Pro chip, customizable Action button, and a pro-grade 48MP camera system with 3x telephoto zoom.",
        "image_url": "https://images.unsplash.com/photo-1695048133142-1a20484d2569?auto=format&fit=crop&w=600&q=80",
        "specifications": {
            "screen_size": "6.1 inches",
            "display": "Super Retina XDR OLED 120Hz ProMotion",
            "processor": "Apple A17 Pro (3nm)",
            "storage": "128GB",
            "ram": "8GB",
            "battery": "Up to 23 hours video playback",
            "weight": "187g",
            "operating_system": "iOS 17",
            "connectivity": "5G, Wi-Fi 6E, Bluetooth 5.3, USB-C 3.0",
        },
        "offers": [
            {
                "id": "off_iphone15_amazon",
                "retailer_name": "Amazon",
                "price": 989.00,
                "currency": "USD",
                "product_url": "https://www.amazon.com/dp/B0CHX1W1XY",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_iphone15_bestbuy",
                "retailer_name": "BestBuy",
                "price": 999.99,
                "currency": "USD",
                "product_url": "https://www.bestbuy.com/site/apple-iphone-15-pro-128gb/6525412.p",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_iphone15_target",
                "retailer_name": "Target",
                "price": 999.99,
                "currency": "USD",
                "product_url": "https://www.target.com/p/apple-iphone-15-pro/-/A-89471201",
                "availability": "LOW_STOCK",
            },
        ],
    },
    {
        "id": "prod_samsung_galaxy_s24_ultra",
        "name": "Samsung Galaxy S24 Ultra (256GB - Titanium Gray)",
        "brand": "Samsung",
        "category": "Electronics",
        "description": "Galaxy AI powerhouse with titanium frame, integrated S Pen stylus, Corning Gorilla Armor glass, 200MP quad-telephoto camera, and Snapdragon 8 Gen 3 for Galaxy.",
        "image_url": "https://images.unsplash.com/photo-1610945415295-d9bbf067e59c?auto=format&fit=crop&w=600&q=80",
        "specifications": {
            "screen_size": "6.8 inches",
            "display": "Dynamic AMOLED 2X QHD+ 120Hz 2600 nits",
            "processor": "Snapdragon 8 Gen 3 for Galaxy",
            "storage": "256GB UFS 4.0",
            "ram": "12GB",
            "battery": "5,000 mAh (45W fast wired charging)",
            "weight": "232g",
            "operating_system": "Android 14 (One UI 6.1)",
            "connectivity": "5G, Wi-Fi 7, Bluetooth 5.3, Ultra Wideband",
        },
        "offers": [
            {
                "id": "off_s24_walmart",
                "retailer_name": "Walmart",
                "price": 1189.50,
                "currency": "USD",
                "product_url": "https://www.walmart.com/ip/Samsung-Galaxy-S24-Ultra/532984102",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_s24_amazon",
                "retailer_name": "Amazon",
                "price": 1199.99,
                "currency": "USD",
                "product_url": "https://www.amazon.com/dp/B0CS5X681L",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_s24_bestbuy",
                "retailer_name": "BestBuy",
                "price": 1249.99,
                "currency": "USD",
                "product_url": "https://www.bestbuy.com/site/samsung-galaxy-s24-ultra/6569032.p",
                "availability": "IN_STOCK",
            },
        ],
    },
    {
        "id": "prod_apple_macbook_air_m3",
        "name": "Apple MacBook Air 13-inch (M3 - 256GB - Space Gray)",
        "brand": "Apple",
        "category": "Electronics",
        "description": "Super-portable laptop powered by Apple M3 8-core CPU and 8-core GPU, fanless silent operation, 13.6-inch Liquid Retina display, MagSafe 3, and up to 18 hours battery.",
        "image_url": "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?auto=format&fit=crop&w=600&q=80",
        "specifications": {
            "screen_size": "13.6 inches",
            "display": "Liquid Retina 2560x1664 500 nits",
            "processor": "Apple M3 (8-core CPU, 8-core GPU)",
            "storage": "256GB SSD",
            "ram": "8GB Unified Memory",
            "battery": "Up to 18 hours Apple TV streaming",
            "weight": "1.24 kg (2.7 lbs)",
            "operating_system": "macOS Sonoma",
            "connectivity": "Wi-Fi 6E, Bluetooth 5.3, 2x Thunderbolt 4",
        },
        "offers": [
            {
                "id": "off_macbook_amazon",
                "retailer_name": "Amazon",
                "price": 999.00,
                "currency": "USD",
                "product_url": "https://www.amazon.com/dp/B0CX23V2P9",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_macbook_bh",
                "retailer_name": "B&H Photo",
                "price": 1029.00,
                "currency": "USD",
                "product_url": "https://www.bhphotovideo.com/c/product/1814981-REG/apple_macbook_air_13.html",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_macbook_bestbuy",
                "retailer_name": "BestBuy",
                "price": 1049.00,
                "currency": "USD",
                "product_url": "https://www.bestbuy.com/site/apple-macbook-air-13-m3/6534604.p",
                "availability": "IN_STOCK",
            },
        ],
    },
    {
        "id": "prod_sony_wh1000xm5",
        "name": "Sony WH-1000XM5 Wireless Noise Canceling Headphones (Black)",
        "brand": "Sony",
        "category": "Electronics",
        "description": "Benchmark over-ear active noise canceling headphones featuring dual V1 and QN1 audio processors, 8 microphones, LDAC Hi-Res Audio, and 30-hour battery life.",
        "image_url": "https://images.unsplash.com/photo-1546435770-a3e426bf472b?auto=format&fit=crop&w=600&q=80",
        "specifications": {
            "type": "Over-Ear Circumaural",
            "noise_canceling": "Auto NC Optimizer with Integrated Processor V1",
            "battery_life": "30 hours with ANC on, 40 hours with ANC off",
            "driver_unit": "30mm specially engineered carbon fiber composite",
            "weight": "250g",
            "connectivity": "Bluetooth 5.2 (LDAC, AAC, SBC), 3.5mm stereo cable",
            "multipoint": "Simultaneous connection to 2 devices",
        },
        "offers": [
            {
                "id": "off_sony_amazon",
                "retailer_name": "Amazon",
                "price": 348.00,
                "currency": "USD",
                "product_url": "https://www.amazon.com/dp/B09XS7JWHH",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_sony_target",
                "retailer_name": "Target",
                "price": 349.99,
                "currency": "USD",
                "product_url": "https://www.target.com/p/sony-wh-1000xm5/-/A-86284301",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_sony_bestbuy",
                "retailer_name": "BestBuy",
                "price": 399.99,
                "currency": "USD",
                "product_url": "https://www.bestbuy.com/site/sony-wh-1000xm5/6505727.p",
                "availability": "IN_STOCK",
            },
        ],
    },
    {
        "id": "prod_dell_xps15_9530",
        "name": "Dell XPS 15 9530 Laptop (Intel Core i7 - 16GB - 512GB SSD)",
        "brand": "Dell",
        "category": "Electronics",
        "description": "High-performance creator laptop crafted from CNC machined aluminum with carbon fiber palm rest, 15.6-inch 500-nit InfinityEdge display, and Intel Core i7-13700H.",
        "image_url": "https://images.unsplash.com/photo-1593642632823-8f785ba67e45?auto=format&fit=crop&w=600&q=80",
        "specifications": {
            "screen_size": "15.6 inches",
            "display": "FHD+ 1920x1200 Anti-Glare 500 nits",
            "processor": "Intel Core i7-13700H (14-Core up to 5.0 GHz)",
            "storage": "512GB M.2 PCIe NVMe SSD",
            "ram": "16GB DDR5 4800MHz",
            "graphics": "Intel Arc A370M 4GB GDDR6",
            "weight": "1.86 kg",
            "operating_system": "Windows 11 Home",
        },
        "offers": [
            {
                "id": "off_dell_amazon",
                "retailer_name": "Amazon",
                "price": 1249.00,
                "currency": "USD",
                "product_url": "https://www.amazon.com/dp/B0C3MLP74N",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_dell_bestbuy",
                "retailer_name": "BestBuy",
                "price": 1299.99,
                "currency": "USD",
                "product_url": "https://www.bestbuy.com/site/dell-xps-15-intel-i7/6540611.p",
                "availability": "IN_STOCK",
            },
        ],
    },
    {
        "id": "prod_apple_ipad_air_m2",
        "name": "Apple iPad Air 11-inch (M2 - 128GB - Blue)",
        "brand": "Apple",
        "category": "Electronics",
        "description": "Versatile iPad Air driven by the Apple M2 chip with Liquid Retina display, landscape 12MP front camera with Center Stage, and Apple Pencil Pro support.",
        "image_url": "https://images.unsplash.com/photo-1544244015-0df4b3ffc6b0?auto=format&fit=crop&w=600&q=80",
        "specifications": {
            "screen_size": "11.0 inches",
            "display": "Liquid Retina True Tone P3 color",
            "processor": "Apple M2 (8-core CPU, 9-core GPU)",
            "storage": "128GB",
            "ram": "8GB",
            "weight": "462g",
            "connectivity": "Wi-Fi 6E, Bluetooth 5.3, USB-C",
        },
        "offers": [
            {
                "id": "off_ipad_amazon",
                "retailer_name": "Amazon",
                "price": 569.00,
                "currency": "USD",
                "product_url": "https://www.amazon.com/dp/B0D3J7V5YF",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_ipad_bestbuy",
                "retailer_name": "BestBuy",
                "price": 599.00,
                "currency": "USD",
                "product_url": "https://www.bestbuy.com/site/apple-ipad-air-11-m2/6534609.p",
                "availability": "IN_STOCK",
            },
        ],
    },
    {
        "id": "prod_nintendo_switch_oled",
        "name": "Nintendo Switch OLED Model (White Joy-Con)",
        "brand": "Nintendo",
        "category": "Electronics",
        "description": "Versatile hybrid video game console featuring a vivid 7-inch OLED screen, wide adjustable stand, enhanced audio, and wired LAN port in the dock.",
        "image_url": "https://images.unsplash.com/photo-1578303512597-81e6cc155b3e?auto=format&fit=crop&w=600&q=80",
        "specifications": {
            "screen_size": "7.0 inches OLED Multi-touch",
            "resolution": "1280x720 Handheld / 1080p Docked TV",
            "storage": "64GB Internal (microSD expandable)",
            "battery_life": "Approximately 4.5 to 9 hours",
            "weight": "420g with Joy-Con attached",
        },
        "offers": [
            {
                "id": "off_switch_amazon",
                "retailer_name": "Amazon",
                "price": 339.95,
                "currency": "USD",
                "product_url": "https://www.amazon.com/dp/B098RKWHHZ",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_switch_target",
                "retailer_name": "Target",
                "price": 349.99,
                "currency": "USD",
                "product_url": "https://www.target.com/p/nintendo-switch-oled/-/A-83887641",
                "availability": "IN_STOCK",
            },
        ],
    },

    # -------------------------------------------------------------------------
    # Category: Accessories (8-12)
    # -------------------------------------------------------------------------
    {
        "id": "prod_apple_watch_series9",
        "name": "Apple Watch Series 9 GPS 45mm (Midnight Aluminum)",
        "brand": "Apple",
        "category": "Accessories",
        "description": "Smartwatch with the S9 SiP chip, double tap hands-free gesture, 2000-nit Always-On display, ECG and blood oxygen monitoring, and crash detection.",
        "image_url": "https://images.unsplash.com/photo-1546868871-7041f2a55e12?auto=format&fit=crop&w=600&q=80",
        "specifications": {
            "case_size": "45mm",
            "display": "Always-On Retina LTPO OLED up to 2000 nits",
            "processor": "Apple S9 SiP 64-bit dual-core",
            "sensors": "Electrical heart sensor (ECG), SpO2, Temperature",
            "water_resistance": "50 meters ISO standard 22810:2010",
            "battery": "Up to 18 hours normal / 36 hours low power mode",
        },
        "offers": [
            {
                "id": "off_watch_amazon",
                "retailer_name": "Amazon",
                "price": 329.00,
                "currency": "USD",
                "product_url": "https://www.amazon.com/dp/B0CHX46D46",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_watch_bestbuy",
                "retailer_name": "BestBuy",
                "price": 359.00,
                "currency": "USD",
                "product_url": "https://www.bestbuy.com/site/apple-watch-series-9-45mm/6525419.p",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_watch_target",
                "retailer_name": "Target",
                "price": 359.99,
                "currency": "USD",
                "product_url": "https://www.target.com/p/apple-watch-series-9/-/A-89471342",
                "availability": "IN_STOCK",
            },
        ],
    },
    {
        "id": "prod_logitech_mx_master_3s",
        "name": "Logitech MX Master 3S Wireless Performance Mouse",
        "brand": "Logitech",
        "category": "Accessories",
        "description": "Ergonomic productivity mouse featuring 8000 DPI track-on-glass optical sensor, Quiet Click switches, and MagSpeed electromagnetic scroll wheel.",
        "image_url": "https://images.unsplash.com/photo-1615663245857-ac93bb7c39e7?auto=format&fit=crop&w=600&q=80",
        "specifications": {
            "sensor": "Darkfield High Precision 8000 DPI",
            "buttons": "7 customizable buttons",
            "scroll_wheel": "MagSpeed with SmartShift auto-switching",
            "battery": "500 mAh Li-Po rechargeable, up to 70 days per charge",
            "connectivity": "Bluetooth Low Energy & Logi Bolt USB receiver",
            "weight": "141g",
        },
        "offers": [
            {
                "id": "off_mxmaster_amazon",
                "retailer_name": "Amazon",
                "price": 89.99,
                "currency": "USD",
                "product_url": "https://www.amazon.com/dp/B09HM94VDS",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_mxmaster_walmart",
                "retailer_name": "Walmart",
                "price": 94.99,
                "currency": "USD",
                "product_url": "https://www.walmart.com/ip/Logitech-MX-Master-3S/152984102",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_mxmaster_bestbuy",
                "retailer_name": "BestBuy",
                "price": 99.99,
                "currency": "USD",
                "product_url": "https://www.bestbuy.com/site/logitech-mx-master-3s/6502206.p",
                "availability": "IN_STOCK",
            },
        ],
    },
    {
        "id": "prod_anker_737_powerbank",
        "name": "Anker 737 Power Bank (PowerCore 24K - 140W)",
        "brand": "Anker",
        "category": "Accessories",
        "description": "Ultra-fast portable power bank with 24,000mAh capacity, Power Delivery 3.1 140W bidirectional charging, and smart digital status display.",
        "image_url": "https://images.unsplash.com/photo-1583863788434-e58a36330cf0?auto=format&fit=crop&w=600&q=80",
        "specifications": {
            "capacity": "24,000 mAh / 86.4 Wh (Flight Approved)",
            "output_power": "140W Max Power Delivery 3.1",
            "ports": "2x USB-C (140W in/out), 1x USB-A (18W out)",
            "display": "Smart Digital Color Screen showing live power & battery health",
            "weight": "630g",
        },
        "offers": [
            {
                "id": "off_anker_amazon",
                "retailer_name": "Amazon",
                "price": 109.99,
                "currency": "USD",
                "product_url": "https://www.amazon.com/dp/B09VPHVT2Z",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_anker_bestbuy",
                "retailer_name": "BestBuy",
                "price": 129.99,
                "currency": "USD",
                "product_url": "https://www.bestbuy.com/site/anker-737-power-bank/6532451.p",
                "availability": "IN_STOCK",
            },
        ],
    },
    {
        "id": "prod_bose_qc_ultra_earbuds",
        "name": "Bose QuietComfort Ultra Earbuds (Black)",
        "brand": "Bose",
        "category": "Accessories",
        "description": "True wireless active noise canceling earbuds featuring Bose Immersive Audio spatial sound, CustomTune acoustic calibration, and IPX4 sweat resistance.",
        "image_url": "https://images.unsplash.com/photo-1590658268037-6bf12165a8df?auto=format&fit=crop&w=600&q=80",
        "specifications": {
            "type": "In-Ear True Wireless",
            "noise_canceling": "CustomTune active noise reduction",
            "battery_life": "6 hours earbuds / 24 hours total with charging case",
            "water_resistance": "IPX4 sweat and weather resistant",
            "codecs": "aptX Adaptive, AAC, SBC",
            "weight": "7.7g per earbud",
        },
        "offers": [
            {
                "id": "off_bose_amazon",
                "retailer_name": "Amazon",
                "price": 249.00,
                "currency": "USD",
                "product_url": "https://www.amazon.com/dp/B0CCZ26B5V",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_bose_target",
                "retailer_name": "Target",
                "price": 279.00,
                "currency": "USD",
                "product_url": "https://www.target.com/p/bose-qc-ultra/-/A-89410928",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_bose_bestbuy",
                "retailer_name": "BestBuy",
                "price": 299.00,
                "currency": "USD",
                "product_url": "https://www.bestbuy.com/site/bose-qc-ultra-earbuds/6554851.p",
                "availability": "IN_STOCK",
            },
        ],
    },
    {
        "id": "prod_peak_design_backpack_20l",
        "name": "Peak Design Everyday Backpack 20L (Charcoal)",
        "brand": "Peak Design",
        "category": "Accessories",
        "description": "Iconic everyday commuter and camera backpack with weatherproof 100% recycled 400D nylon shell, MagLatch closure, and customizable FlexFold dividers.",
        "image_url": "https://images.unsplash.com/photo-1553062407-98eeb64c6a62?auto=format&fit=crop&w=600&q=80",
        "specifications": {
            "capacity": "20 Liters max volume",
            "laptop_carry": "Padded sleeve for up to 16-inch laptops",
            "weatherproofing": "100% recycled 400D double poly-coated DWR nylon",
            "hardware": "Anodized aluminum MagLatch hardware",
            "weight": "2.01 kg",
            "warranty": "Lifetime Warranty",
        },
        "offers": [
            {
                "id": "off_backpack_amazon",
                "retailer_name": "Amazon",
                "price": 279.95,
                "currency": "USD",
                "product_url": "https://www.amazon.com/dp/B07ZTQ7F1D",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_backpack_bh",
                "retailer_name": "B&H Photo",
                "price": 279.95,
                "currency": "USD",
                "product_url": "https://www.bhphotovideo.com/c/product/1519782-REG/peak_design_bedb_20_ch_2.html",
                "availability": "IN_STOCK",
            },
        ],
    },

    # -------------------------------------------------------------------------
    # Category: Home Appliances (13-18)
    # -------------------------------------------------------------------------
    {
        "id": "prod_dyson_v15_detect",
        "name": "Dyson V15 Detect Cordless Vacuum Cleaner",
        "brand": "Dyson",
        "category": "Home Appliances",
        "description": "Intelligent cordless vacuum equipped with laser illumination revealing microscopic dust, a piezo sensor measuring particle counts, and 230AW suction.",
        "image_url": "https://images.unsplash.com/photo-1558317374-067fb5f30001?auto=format&fit=crop&w=600&q=80",
        "specifications": {
            "suction_power": "230 Air Watts",
            "run_time": "Up to 60 minutes with click-in battery",
            "filtration": "Whole-machine HEPA filtration capturing 99.99% particles to 0.3 microns",
            "bin_capacity": "0.77 Liters with point-and-shoot hygienic emptying",
            "weight": "3.1 kg",
            "cleaner_heads": "Digital Motorbar & Fluffy Optic laser head",
        },
        "offers": [
            {
                "id": "off_dyson_amazon",
                "retailer_name": "Amazon",
                "price": 619.00,
                "currency": "USD",
                "product_url": "https://www.amazon.com/dp/B08Z44Z71P",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_dyson_target",
                "retailer_name": "Target",
                "price": 649.99,
                "currency": "USD",
                "product_url": "https://www.target.com/p/dyson-v15-detect/-/A-82604219",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_dyson_bestbuy",
                "retailer_name": "BestBuy",
                "price": 649.99,
                "currency": "USD",
                "product_url": "https://www.bestbuy.com/site/dyson-v15-detect/6451368.p",
                "availability": "IN_STOCK",
            },
        ],
    },
    {
        "id": "prod_breville_barista_touch",
        "name": "Breville Barista Touch Espresso Machine (Stainless Steel)",
        "brand": "Breville",
        "category": "Home Appliances",
        "description": "Touchscreen automated espresso machine featuring integrated hardened steel burr grinder, ThermoJet 3-second rapid heat-up, and auto microfoam steam wand.",
        "image_url": "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?auto=format&fit=crop&w=600&q=80",
        "specifications": {
            "heating_system": "ThermoJet 3-second instant heating",
            "grinder": "Integrated Stainless Steel Conical Burr with dose control",
            "pump_pressure": "15 Bar Italian Pump",
            "milk_texturing": "Auto Purge Steam Wand with 8 texture levels & 5 temperature settings",
            "water_tank": "2 Liters / 67 oz removable tank",
            "power": "1680 Watts",
        },
        "offers": [
            {
                "id": "off_breville_amazon",
                "retailer_name": "Amazon",
                "price": 949.95,
                "currency": "USD",
                "product_url": "https://www.amazon.com/dp/B078WMLXXG",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_breville_bestbuy",
                "retailer_name": "BestBuy",
                "price": 999.95,
                "currency": "USD",
                "product_url": "https://www.bestbuy.com/site/breville-barista-touch/6173907.p",
                "availability": "IN_STOCK",
            },
        ],
    },
    {
        "id": "prod_ninja_foodi_airfryer_dz201",
        "name": "Ninja Foodi 6-in-1 8-qt 2-Basket Air Fryer (DZ201)",
        "brand": "Ninja",
        "category": "Home Appliances",
        "description": "DualZone air fryer with 2 independent 4-quart non-stick baskets allowing simultaneous cooking of two different foods with Smart Finish synchronizing completion.",
        "image_url": "https://images.unsplash.com/photo-1556911220-e15b29be8c8f?auto=format&fit=crop&w=600&q=80",
        "specifications": {
            "capacity": "8 Quarts total (Two independent 4-quart baskets)",
            "cooking_functions": "Air Fry, Air Broil, Roast, Bake, Reheat, Dehydrate",
            "temperature_range": "105°F to 450°F",
            "power": "1690 Watts",
            "dish_washer_safe": "Non-stick crisper plates and baskets are dishwasher safe",
            "weight": "8.9 kg",
        },
        "offers": [
            {
                "id": "off_ninja_amazon",
                "retailer_name": "Amazon",
                "price": 149.99,
                "currency": "USD",
                "product_url": "https://www.amazon.com/dp/B089TQWJKK",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_ninja_target",
                "retailer_name": "Target",
                "price": 159.99,
                "currency": "USD",
                "product_url": "https://www.target.com/p/ninja-foodi-8qt-air-fryer/-/A-80130541",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_ninja_bestbuy",
                "retailer_name": "BestBuy",
                "price": 179.99,
                "currency": "USD",
                "product_url": "https://www.bestbuy.com/site/ninja-foodi-dz201/6424391.p",
                "availability": "IN_STOCK",
            },
        ],
    },
    {
        "id": "prod_philips_hue_starter_kit",
        "name": "Philips Hue White & Color Ambiance Smart Starter Kit",
        "brand": "Philips",
        "category": "Home Appliances",
        "description": "Smart LED home lighting kit containing 4 A19 75W equivalent color bulbs and Hue Bridge controlling 16 million colors, automated schedules, and smart home scenes.",
        "image_url": "https://images.unsplash.com/photo-1550985543-f47f38aeee65?auto=format&fit=crop&w=600&q=80",
        "specifications": {
            "bulb_type": "4x A19 Medium Base E26 LED Bulbs",
            "brightness": "1100 Lumens per bulb (75W Equivalent)",
            "colors": "16 Million colors + Tunable white (2000K-6500K)",
            "bridge": "Includes Philips Hue Smart Bridge",
            "voice_assistant": "Amazon Alexa, Apple HomeKit, Google Assistant",
            "lifespan": "25,000 hours per bulb",
        },
        "offers": [
            {
                "id": "off_hue_amazon",
                "retailer_name": "Amazon",
                "price": 169.99,
                "currency": "USD",
                "product_url": "https://www.amazon.com/dp/B095KWCGD7",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_hue_bestbuy",
                "retailer_name": "BestBuy",
                "price": 199.99,
                "currency": "USD",
                "product_url": "https://www.bestbuy.com/site/philips-hue-starter-kit/6468752.p",
                "availability": "IN_STOCK",
            },
        ],
    },
    {
        "id": "prod_irobot_roomba_j7_plus",
        "name": "iRobot Roomba j7+ Self-Emptying Robot Vacuum",
        "brand": "iRobot",
        "category": "Home Appliances",
        "description": "Smart autonomous robot vacuum with PrecisionVision AI navigation recognizing and dodging obstacles like cords and pet waste, paired with Clean Base self-emptying dock.",
        "image_url": "https://images.unsplash.com/photo-1618221195710-dd6b41faaea6?auto=format&fit=crop&w=600&q=80",
        "specifications": {
            "navigation": "PrecisionVision AI with obstacle detection and avoidance",
            "suction": "10x Power-Lifting Suction compared to 600 series",
            "self_emptying": "Clean Base holds up to 60 days of dirt and dust",
            "filter": "High-Efficiency AllergenLock filter",
            "battery_run_time": "75 minutes with smart recharge & resume",
        },
        "offers": [
            {
                "id": "off_roomba_amazon",
                "retailer_name": "Amazon",
                "price": 499.00,
                "currency": "USD",
                "product_url": "https://www.amazon.com/dp/B094NX3ZCL",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_roomba_target",
                "retailer_name": "Target",
                "price": 499.99,
                "currency": "USD",
                "product_url": "https://www.target.com/p/irobot-roomba-j7-plus/-/A-83905814",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_roomba_bestbuy",
                "retailer_name": "BestBuy",
                "price": 599.99,
                "currency": "USD",
                "product_url": "https://www.bestbuy.com/site/irobot-roomba-j7-plus/6474136.p",
                "availability": "IN_STOCK",
            },
        ],
    },
    {
        "id": "prod_kitchenaid_artisan_5qt",
        "name": "KitchenAid Artisan Series 5-Quart Stand Mixer (Empire Red)",
        "brand": "KitchenAid",
        "category": "Home Appliances",
        "description": "Legendary kitchen culinary workhorse featuring robust tilt-head design, 59-point planetary mixing action, 10 speeds, and stainless steel bowl with comfort handle.",
        "image_url": "https://images.unsplash.com/photo-1594385208974-2e75f8d7bb48?auto=format&fit=crop&w=600&q=80",
        "specifications": {
            "bowl_capacity": "5.0 Quarts (bakes up to 9 dozen cookies)",
            "speeds": "10 distinct culinary speeds",
            "motor_power": "325 Watts high-efficiency motor",
            "mixing_action": "59-point planetary mixing touchpoints",
            "included_accessories": "Coated flat beater, dough hook, 6-wire whip, pouring shield",
            "weight": "11.8 kg",
        },
        "offers": [
            {
                "id": "off_kitchenaid_amazon",
                "retailer_name": "Amazon",
                "price": 379.99,
                "currency": "USD",
                "product_url": "https://www.amazon.com/dp/B00005UP2P",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_kitchenaid_target",
                "retailer_name": "Target",
                "price": 399.99,
                "currency": "USD",
                "product_url": "https://www.target.com/p/kitchenaid-artisan-5qt/-/A-10884812",
                "availability": "IN_STOCK",
            },
            {
                "id": "off_kitchenaid_bestbuy",
                "retailer_name": "BestBuy",
                "price": 399.99,
                "currency": "USD",
                "product_url": "https://www.bestbuy.com/site/kitchenaid-artisan-5-quart/2627589.p",
                "availability": "IN_STOCK",
            },
        ],
    },
]


def seed_database(db: Session | None = None, bind: Engine | None = None) -> int:
    """
    Idempotent catalog seeding.
    Checks existing product count:
      - If products already exist: skips seeding without duplicating data.
      - If catalog is empty: inserts all 18 demo products and their retailer offers.
    Returns the number of products seeded (0 if already seeded, 18 if freshly seeded).
    """
    engine_to_use = bind or default_engine
    Base.metadata.create_all(bind=engine_to_use)

    # Use provided session or create a new session bound to engine_to_use
    close_session_on_exit = False
    if db is not None:
        session = db
    else:
        session_factory = sessionmaker(
            bind=engine_to_use,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            class_=Session,
        )
        session = session_factory()
        close_session_on_exit = True

    try:
        existing_count = session.scalar(select(func.count(Product.id))) or 0
        if existing_count > 0:
            logger.info("Catalog already seeded (%d products exist). Skipping seed.", existing_count)
            return 0

        logger.info("Seeding %d demo products with multi-retailer offers...", len(DEMO_PRODUCTS))
        for p_data in DEMO_PRODUCTS:
            offers_data = p_data.get("offers", [])
            product = Product(
                id=p_data["id"],
                name=p_data["name"],
                brand=p_data["brand"],
                category=p_data["category"],
                description=p_data["description"],
                specifications=p_data["specifications"],
                image_url=p_data.get("image_url"),
            )
            session.add(product)

            for o_data in offers_data:
                offer = RetailerOffer(
                    id=o_data["id"],
                    product_id=product.id,
                    retailer_name=o_data["retailer_name"],
                    price=o_data["price"],
                    currency=o_data.get("currency", "USD"),
                    product_url=o_data["product_url"],
                    availability=o_data.get("availability", "IN_STOCK"),
                )
                session.add(offer)

        session.commit()
        logger.info("Catalog seeding successfully completed! 18 products inserted.")
        return len(DEMO_PRODUCTS)
    finally:
        if close_session_on_exit:
            session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    count = seed_database()
    print(f"Seeding finished. Inserted: {count} products.")
