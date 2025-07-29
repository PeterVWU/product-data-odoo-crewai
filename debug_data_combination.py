#!/usr/bin/env python3

import json
import sys
sys.path.append('src')
from product_data_odoo.tools.variant_builder import _combine_product_data

# Load data
with open('output/parsed/parsed_results.json', 'r') as f:
    clear_products = json.load(f)

with open('output/llm/llm_parsed_results.json', 'r') as f:
    llm_products = json.load(f)

print(f"Loaded {len(clear_products)} clear products and {len(llm_products)} LLM products")

# Combine data
combined = _combine_product_data(clear_products, llm_products)
print(f"Combined into {len(combined)} products")

# Find a test product with attributes
test_product = None
for product in combined:
    if product.get('attributes') and len(product['attributes']) > 0:
        test_product = product
        break

if test_product:
    print(f"\nSample combined product:")
    print(f"Name: {test_product.get('product_name')}")
    print(f"Source: {test_product.get('source')}")
    print(f"Attributes: {test_product.get('attributes')}")
    print(f"Attribute types: {[(k, type(v)) for k, v in test_product.get('attributes', {}).items()]}")
else:
    print("No products with attributes found!")
    
    # Check some samples
    print("\nFirst 3 combined products:")
    for i, product in enumerate(combined[:3]):
        print(f"{i+1}. Name: {product.get('product_name')}")
        print(f"   Source: {product.get('source')}")  
        print(f"   Attributes: {product.get('attributes')}")
        print()