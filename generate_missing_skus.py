#!/usr/bin/env python3

import json
import pandas as pd
import csv
from pathlib import Path

# Load the data files
with open('output/parsed/parsed_results.json', 'r') as f:
    clear_products = json.load(f)

with open('output/llm/llm_parsed_results.json', 'r') as f:
    llm_products = json.load(f)

# Load generated variants to get SKUs that were successfully converted to variants
try:
    variants_df = pd.read_csv('output/variants/product_variant_import.csv')
    if len(variants_df) > 0:
        variant_skus = set(variants_df['default_code'].dropna().tolist())
    else:
        variant_skus = set()
    print(f"Found {len(variant_skus)} SKUs in product_variant_import.csv")
except Exception as e:
    print(f"Error loading product_variant_import.csv: {e}")
    variant_skus = set()

# Load templates to get SKUs in simple products
try:
    templates_df = pd.read_csv('output/templates/new_templates.csv')
    template_skus = set(templates_df['default_code'].dropna().tolist())
    print(f"Found {len(template_skus)} SKUs in templates")
except Exception as e:
    print(f"Error loading templates: {e}")
    template_skus = set()

# Create index map for LLM products
llm_by_index = {}
for product in llm_products:
    index = product.get('index')
    if index is not None:
        llm_by_index[index] = product

# Combine all products with LLM results taking priority
combined_products = []
for i, product in enumerate(clear_products):
    index = product.get('index', i)
    
    # Use LLM result if available, otherwise regex result
    if index in llm_by_index:
        final_product = llm_by_index[index]
        source = 'llm'
    else:
        final_product = product
        source = 'regex'
    
    combined_products.append({
        'index': index,
        'sku': final_product.get('sku', ''),
        'product_name': final_product.get('product_name', '') or final_product.get('name', ''),
        'source': source,
        'original_name': final_product.get('name', '')
    })

# Find missing SKUs
missing_skus = []
all_processed_skus = variant_skus.union(template_skus)

for product in combined_products:
    sku = product.get('sku', '')
    product_name = product.get('product_name', '')
    
    if sku and sku not in all_processed_skus:
        reason = 'no_template_match'
        if not product_name:
            reason = 'no_product_name'
        
        missing_skus.append({
            'sku': sku,
            'product_name': product_name,
            'original_name': product.get('original_name', ''),
            'source': product.get('source', 'unknown'),
            'reason': reason
        })

print(f"\nMissing SKUs Analysis:")
print(f"======================")
print(f"Total products: {len(combined_products)}")
print(f"SKUs in variants: {len(variant_skus)}")
print(f"SKUs in templates: {len(template_skus)}")
print(f"Total processed SKUs: {len(all_processed_skus)}")
print(f"Missing SKUs: {len(missing_skus)}")

# Create output directory
output_path = Path("output/variants")
output_path.mkdir(parents=True, exist_ok=True)

# Save missing SKUs as JSON
missing_skus_file = output_path / "missing_skus.json"
with open(missing_skus_file, 'w') as f:
    json.dump(missing_skus, f, indent=2)

# Save missing SKUs as CSV
missing_skus_csv = output_path / "missing_skus.csv"
if missing_skus:
    fieldnames = ['sku', 'product_name', 'original_name', 'source', 'reason']
    with open(missing_skus_csv, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(missing_skus)

print(f"\nGenerated missing SKUs reports:")
print(f"- {missing_skus_file}")
print(f"- {missing_skus_csv}")

# Show a sample of missing SKUs
print(f"\nSample missing SKUs (first 10):")
for i, sku_info in enumerate(missing_skus[:10]):
    print(f"  {sku_info['sku']}: {sku_info['product_name']} (Reason: {sku_info['reason']})")